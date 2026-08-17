"""Import G1 (portieri+difensori) auction results from the admin's recap Excel
into the ledger as AssignmentEvent instances.

Source: "Riepilogo primo giro asta.xlsx", Foglio1 -- one row per team, 4
(name, price) pairs: [0] the real club whose 3-goalkeeper block was bought,
[1..3] three defenders bought individually.

Usage:
    python scripts/import_g1_results.py <path-to-xlsx> [--dry-run] [--yes]

Dry-run (default) resolves every name and validates every event via replay()
without writing anything. Pass --yes to actually append to the ledger.
"""
from __future__ import annotations

import argparse
import difflib
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fantacalcio.config import ConfigError, load_ruleset
from fantacalcio.domain import AssignmentEvent, AssignmentItem, DomainError, Role, replay
from fantacalcio.identity.teams import normalize_name
from fantacalcio.persistence import ledger_store, player_table, team_labels_store

ROUND_ID = "G1"
SOURCE = "admin_g1_recap_xlsx_import"
AUTHOR = "utente"


def normalize(s: str) -> str:
    return " ".join(s.replace("’", "'").replace("�", "'").strip().split()).lower()


def load_rows(xlsx_path: Path) -> list[list]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Foglio1"]
    rows = []
    for row in ws.iter_rows(values_only=True):
        if row[0] is None:
            continue
        rows.append(row)
    return rows


def resolve_team_id(excel_name: str, labels: dict[str, str]) -> str | None:
    target = normalize(excel_name)
    for team_id, label in labels.items():
        if normalize(label) == target:
            return team_id
    # loose fallback: strip non-alnum
    def squash(s: str) -> str:
        return "".join(ch for ch in normalize(s) if ch.isalnum())
    target_sq = squash(excel_name)
    for team_id, label in labels.items():
        if squash(label) == target_sq:
            return team_id
    # a shortened free-text name (e.g. "Ajajax" for "AJAJAX BRAZORF")
    for team_id, label in labels.items():
        if normalize(label).startswith(target) or target.startswith(normalize(label)):
            return team_id
    # fuzzy fallback: free-text team names have inconsistent spelling/casing
    best_team_id, best_ratio = None, 0.0
    for team_id, label in labels.items():
        ratio = difflib.SequenceMatcher(None, normalize(excel_name), normalize(label)).ratio()
        if ratio > best_ratio:
            best_team_id, best_ratio = team_id, ratio
    if best_ratio >= 0.75:
        return best_team_id
    return None


KNOWN_UNDERSIZED_GK_CLUBS = {"Cagliari", "Lecce"}  # only 2 real goalkeepers on file (data gap)


def resolve_gk_block(conn, club_name: str):
    matches = player_table.search_players(conn, role="P", team_name=club_name.strip())
    if len(matches) > 3:
        matches = matches.sort_values("var_mean", ascending=False).head(3)
    return matches


def resolve_player(conn, name: str):
    clean = name.strip()
    matches = player_table.search_players(conn, name_query=clean)
    matches = matches[matches["role"] != "P"]
    if len(matches) == 0:
        fuzzy = player_table.search_players_fuzzy(conn, name_query=clean)
        fuzzy = fuzzy[fuzzy["role"] != "P"]
        if len(fuzzy) == 1:
            return fuzzy.iloc[0], None
        def squash(s: str) -> str:
            return "".join(ch for ch in normalize_name(s) if ch.isalnum())

        if len(fuzzy) > 1 and squash(fuzzy.iloc[0]["display_name"]) == squash(clean):
            return fuzzy.iloc[0], None
        return None, f"nessun match per {name!r} (fuzzy: {len(fuzzy)} candidati: {', '.join(fuzzy['display_name'].tolist())})"
    if len(matches) > 1:
        exact = matches[matches["display_name"].str.lower().str.strip() == clean.lower()]
        if len(exact) == 1:
            return exact.iloc[0], None
        return None, f"{len(matches)} match ambigui per {name!r}: {', '.join(matches['display_name'].tolist())}"
    return matches.iloc[0], None


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

    rows = load_rows(args.xlsx_path)
    print(f"{len(rows)} righe lette da Foglio1.")

    candidates: list[AssignmentEvent] = []
    undersized_events: list[AssignmentEvent] = []
    errors: list[str] = []

    for row in rows:
        excel_team_name = row[0]
        team_id = resolve_team_id(excel_team_name, labels)
        if team_id is None:
            errors.append(f"Squadra non risolta: {excel_team_name!r}")
            continue

        club_name, gk_price = row[1], row[2]
        gk_matches = resolve_gk_block(player_conn, club_name)
        undersized_known = club_name.strip() in KNOWN_UNDERSIZED_GK_CLUBS and len(gk_matches) == 2
        if len(gk_matches) != 3 and not undersized_known:
            errors.append(
                f"[{excel_team_name}] blocco portieri {club_name!r}: trovati {len(gk_matches)} "
                f"portieri invece di 3."
            )
        else:
            source = SOURCE + ("_undersized_gk_block_known_gap" if undersized_known else "")
            gk_event = AssignmentEvent(
                event_id=uuid.uuid4().hex,
                ts=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                round_id=ROUND_ID,
                team_id=team_id,
                pool_id="goalkeeper_blocks",
                role=Role.GK,
                item=AssignmentItem(player_ids=tuple(str(p["player_code"]) for _, p in gk_matches.iterrows())),
                amount=int(gk_price),
                source=source,
                author=AUTHOR,
            )
            candidates.append(gk_event)
            if undersized_known:
                undersized_events.append(gk_event)

        for name, price in [(row[3], row[4]), (row[5], row[6]), (row[7], row[8])]:
            if name is None:
                continue
            player, err = resolve_player(player_conn, name)
            if err:
                errors.append(f"[{excel_team_name}] {err}")
                continue
            pool_id = player["list_pool_name"]
            domain_role = Role.DEF if player["role"] == "D" else (
                Role.MID if player["role"] == "C" else Role.FWD
            )
            candidates.append(AssignmentEvent(
                event_id=uuid.uuid4().hex,
                ts=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                round_id=ROUND_ID,
                team_id=team_id,
                pool_id=pool_id,
                role=domain_role,
                item=AssignmentItem(player_ids=(str(player["player_code"]),)),
                amount=int(price),
                source=SOURCE,
                author=AUTHOR,
            ))

    if errors:
        print(f"\n{len(errors)} ERRORI DI RISOLUZIONE (nessuna scrittura effettuata):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"\n{len(candidates)} eventi risolti. Validazione via replay()...")
    try:
        replay(ruleset, existing_events + candidates)
    except (DomainError, ConfigError) as exc:
        print(f"REPLAY FALLITO, nessuna scrittura effettuata: {exc}")
        return 1
    if undersized_events:
        print(f"{len(undersized_events)} blocchi da 2 portieri (data gap noto, sotto la dimensione configurata).")
    print("Replay OK: tutti gli invarianti rispettati.")

    if not args.yes:
        print("\nDRY-RUN: nessuna scrittura effettuata. Rilancia con --yes per scrivere sul ledger.")
        for c in candidates[:5]:
            print(f"  {c.team_id} {c.pool_id} {c.item.player_ids} {c.amount}cr")
        print("  ...")
        return 0

    for c in candidates:
        ledger_store.append_event(ledger_conn, c)
    print(f"Scritti {len(candidates)} eventi sul ledger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
