"""Import G2 (centrocampisti/attaccanti) real auction results from the admin's
cumulative recap Excel into the ledger as AssignmentEvent instances.

Source: "Riepilogo secondo giro asta.xlsx", Foglio1 -- one row per team, 9
(name, price) column pairs total, but only the last 5 are G2:
  [0]      real club whose G1 goalkeeper block was bought (already on the
           ledger from ADR-2026-055's G1 import -- SKIPPED here)
  [1..3]   the 3 G1 defenders (already on the ledger -- SKIPPED here)
  [4..6]   the 3 G2 midfielder bands (NEW)
  [7..8]   the 2 G2 forward bands (NEW)
Which specific band (top_1_20 / top_21_40 / top_41_60) each pair belongs to is
not encoded in this sheet -- resolved from the player's own `list_pool_name` in
the player table instead, same approach as import_g1_results.py.

Cell fill color in the source sheet distinguishes normal sealed-bid wins
(green/cyan/red) from admin-manual automatic assignments (yellow/purple,
confirmed by the user 2026-08-18) -- both are real outcomes and both get
written as AssignmentEvents; the manual ones just carry a distinguishing
`source` suffix so a future reviewer can tell the two apart without re-reading
the spreadsheet colors.

Usage:
    python scripts/import_g2_results.py <path-to-xlsx> [--yes]

Dry-run (default) resolves every name and validates every event via replay()
without writing anything. Pass --yes to actually append to the ledger.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fantacalcio.config import ConfigError, load_ruleset
from fantacalcio.domain import AssignmentEvent, AssignmentItem, DomainError, Role, replay
from fantacalcio.persistence import ledger_store, player_table, team_labels_store

# Reuse the same team-name resolver as the G1 importer instead of duplicating it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_g1_results import resolve_team_id  # noqa: E402

ROUND_ID = "G2"
SOURCE = "admin_g2_recap_xlsx_import"
SOURCE_AUTO_ASSIGNED = "admin_g2_recap_xlsx_import_manual_auto_assignment"
AUTHOR = "utente"

# (name_col_idx, price_col_idx) 0-based within the row tuple, for the 5 NEW G2
# pairs only (J/K, L/M, N/O, P/Q, R/S -- 0-based: 9,10 / 11,12 / 13,14 / 15,16 / 17,18).
G2_PAIR_COLUMNS = [(9, 10), (11, 12), (13, 14), (15, 16), (17, 18)]

# Fill colors (ARGB) that mark an admin manual automatic assignment rather than
# a normal sealed-bid win, confirmed by the user.
AUTO_ASSIGNED_COLORS = {"FFFFFF00", "FFB4A7D6"}


def load_rows_with_colors(xlsx_path: Path) -> list[tuple[str, list]]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Foglio1"]
    out = []
    for row in ws.iter_rows(min_row=2):
        team_cell = row[0]
        if team_cell.value is None:
            continue
        cells = list(row)
        out.append((team_cell.value, cells))
    return out


def _ascii_key(s: str) -> str:
    """Strips non-ASCII chars (mojibake replacement chars included) so override
    keys don't depend on exactly which garbled byte the source file happens to
    contain for an accented letter."""
    return "".join(ch for ch in s if ord(ch) < 128).strip()


def resolve_player(conn, name: str):
    code = PLAYER_CODE_OVERRIDES.get(_ascii_key(name))
    if code is not None:
        matches = player_table.search_players(conn)
        row = matches[matches["player_code"] == code]
        if len(row) == 1:
            return row.iloc[0], None
        return None, f"player_code override {code} per {name!r} non trovato nel player table"
    clean = MANUAL_NAME_OVERRIDES.get(_ascii_key(name), name.strip())
    matches = player_table.search_players(conn, name_query=clean)
    matches = matches[matches["role"] != "P"]
    if len(matches) == 0:
        fuzzy = player_table.search_players_fuzzy(conn, name_query=clean)
        fuzzy = fuzzy[fuzzy["role"] != "P"]
        if len(fuzzy) == 1:
            return fuzzy.iloc[0], None
        return None, f"nessun match per {name!r} (fuzzy: {len(fuzzy)} candidati: {', '.join(fuzzy['display_name'].tolist())})"
    if len(matches) > 1:
        exact = matches[matches["display_name"].str.lower().str.strip() == clean.lower()]
        if len(exact) == 1:
            return exact.iloc[0], None
        return None, f"{len(matches)} match ambigui per {name!r}: {', '.join(matches['display_name'].tolist())}"
    return matches.iloc[0], None


# Manual overrides for the handful of names the automatic resolver could not
# disambiguate on its own (mojibake from the source file, reversed name order,
# or first-name-only entries genuinely ambiguous without team/club context).
# Every entry here was confirmed against the source data by inspection, not
# guessed -- see docs/CURRENT_TASK.md for the reasoning per player.
MANUAL_NAME_OVERRIDES: dict[str, str] = {
    "Soul": "soul",  # mojibake in source file matches identical mojibake in player table
    "Carlos K": "kevin carlos",  # "Carlos K." = Kevin Carlos, surname/first-name order swapped in recap
    "Gonalo Ramos": "ramos",  # "Ramos G." in player table
    "K. Davis": "davis",  # "Davis K." in player table, order swapped
    "Jesus rodriguez": "rodriguez je",  # "Rodriguez Je." -- disambiguates from "Rodriguez Ju." (defender)
    "lautaro": "martinez",  # "Martinez L." in player table, first-name-only entry
    "Bernabe": "bernab",  # mojibake "Bernab�" in player table
    "Adams": "Adams A.",  # confirmed by user 2026-08-18: Venezia's Adams A., not Torino's Adams C.
}

# Direct player_code overrides for names too ambiguous for a text query to
# disambiguate even with MANUAL_NAME_OVERRIDES (e.g. two same-surname players
# in different G2 bands). Confirmed by user 2026-08-18.
PLAYER_CODE_OVERRIDES: dict[str, int] = {
    "Kone": 5589,  # "Kone M." (midfielders_top_1_20), not "Kone I." (21_40) or "Kone B." (remaining_players)
}

# Names the user asked to be skipped and resolved manually later rather than
# guessed -- never write an event for these.
SKIP_NAMES: set[str] = set()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx_path", type=Path)
    parser.add_argument("--yes", action="store_true", help="Actually append to the ledger (default: dry-run only)")
    args = parser.parse_args()

    ruleset = load_ruleset(Path("config/auction_rules.v1.yaml"))
    player_conn = player_table.connect()
    labels_conn = team_labels_store.connect()
    labels = team_labels_store.get_all_labels(labels_conn)

    ledger_conn = ledger_store.connect()
    existing_events = ledger_store.load_events(ledger_conn)

    rows = load_rows_with_colors(args.xlsx_path)
    print(f"{len(rows)} righe lette da Foglio1.")

    candidates: list[AssignmentEvent] = []
    auto_assigned_events: list[AssignmentEvent] = []
    errors: list[str] = []

    for excel_team_name, cells in rows:
        team_id = resolve_team_id(excel_team_name, labels)
        if team_id is None:
            errors.append(f"Squadra non risolta: {excel_team_name!r}")
            continue

        for name_idx, price_idx in G2_PAIR_COLUMNS:
            name_cell, price_cell = cells[name_idx], cells[price_idx]
            if name_cell.value is None:
                continue
            if _ascii_key(str(name_cell.value)) in SKIP_NAMES:
                print(f"SKIP (richiesto dall'utente): [{excel_team_name}] {name_cell.value!r}")
                continue
            player, err = resolve_player(player_conn, str(name_cell.value))
            if err:
                errors.append(f"[{excel_team_name}] {err}")
                continue
            fill = name_cell.fill.fgColor.rgb if name_cell.fill and name_cell.fill.fgColor else None
            is_auto = fill in AUTO_ASSIGNED_COLORS
            domain_role = Role.MID if player["role"] == "C" else Role.FWD
            candidates.append(AssignmentEvent(
                event_id=uuid.uuid4().hex,
                ts=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                round_id=ROUND_ID,
                team_id=team_id,
                pool_id=player["list_pool_name"],
                role=domain_role,
                item=AssignmentItem(player_ids=(str(player["player_code"]),)),
                amount=int(price_cell.value),
                source=SOURCE_AUTO_ASSIGNED if is_auto else SOURCE,
                author=AUTHOR,
            ))
            if is_auto:
                auto_assigned_events.append(candidates[-1])

    if errors:
        print(f"\n{len(errors)} ERRORI DI RISOLUZIONE (nessuna scrittura effettuata):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"\n{len(candidates)} eventi risolti ({len(auto_assigned_events)} assegnazioni manuali admin). Validazione via replay()...")
    try:
        replay(ruleset, existing_events + candidates)
    except (DomainError, ConfigError) as exc:
        print(f"REPLAY FALLITO, nessuna scrittura effettuata: {exc}")
        return 1
    print("Replay OK: tutti gli invarianti rispettati.")

    if not args.yes:
        print("\nDRY-RUN: nessuna scrittura effettuata. Rilancia con --yes per scrivere sul ledger.")
        for c in candidates[:5]:
            print(f"  {c.team_id} {c.pool_id} {c.item.player_ids} {c.amount}cr ({c.source})")
        print("  ...")
        return 0

    for c in candidates:
        ledger_store.append_event(ledger_conn, c)
    print(f"Scritti {len(candidates)} eventi sul ledger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
