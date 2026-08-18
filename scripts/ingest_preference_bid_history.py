"""Curates a per-preference bid-history dataset from the admin's raw Google
Forms exports ("Lista N - ... (Risposte).xlsx"), including the FAILED
preferences that never make it into the ledger (the ledger only ever records
the winning outcome, ADR-2026-055/063). Confirmed with the user 2026-08-18:
this history is used only to model opponent behaviour/aggressiveness
(`src/fantacalcio/auction/market_model.py`), never written to the ledger and
never used to infer future demand for a specific player.

Each list's "Risposte del modulo 1" sheet has one row per team, 6
(player, bid) preference pairs. Cell fill color marks the outcome:
  green (00FF00)  -> preference won
  red   (FF0000)  -> preference tried, lost
  orange (FF9900) -> preference never evaluated (an earlier one already won)
Any other color is written through as "unknown" rather than guessed.

Output: one row per (team, list, preference_rank) at
data/curated/preference_bid_history/preference_bids.csv, columns:
  source_file, team_id, list_pool_name, role, preference_rank, player_code,
  bid_amount, outcome

Usage:
    python scripts/ingest_preference_bid_history.py <xlsx1> [<xlsx2> ...] [--yes]

Dry-run (default) resolves everything and prints a summary without writing.
Pass --yes to write the CSV (always a full rebuild from the given files, not
an incremental append -- deterministic/reproducible per CLAUDE.md).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fantacalcio.persistence import player_table, team_labels_store
from import_g1_results import resolve_team_id  # noqa: E402

OUT_PATH = Path("data/curated/preference_bid_history/preference_bids.csv")

_COLOR_OUTCOME = {
    "FF00FF00": "won",
    "FFFF0000": "lost",
    "FFFF9900": "not_reached",
}


def _ascii_key(s: str) -> str:
    return "".join(ch for ch in s if ord(ch) < 128).strip()


def resolve_player(conn, name: str):
    clean = _ascii_key(name) or name.strip()
    matches = player_table.search_players(conn, name_query=clean)
    matches = matches[matches["role"] != "P"]
    if len(matches) == 1:
        return matches.iloc[0], None
    if len(matches) == 0:
        fuzzy = player_table.search_players_fuzzy(conn, name_query=clean)
        fuzzy = fuzzy[fuzzy["role"] != "P"]
        if len(fuzzy) == 1:
            return fuzzy.iloc[0], None
        return None, f"nessun match per {name!r}"
    exact = matches[matches["display_name"].str.lower().str.strip() == clean.lower()]
    if len(exact) == 1:
        return exact.iloc[0], None
    return None, f"{len(matches)} match ambigui per {name!r}"


def parse_one_file(xlsx_path: Path, player_conn, labels: dict[str, str]) -> tuple[list[dict], list[str]]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Risposte del modulo 1"]
    rows_out: list[dict] = []
    errors: list[str] = []

    for row in ws.iter_rows(min_row=2):
        team_name_cell = row[1]
        if team_name_cell.value is None:
            continue
        team_id = resolve_team_id(str(team_name_cell.value), labels)
        if team_id is None:
            errors.append(f"[{xlsx_path.name}] squadra non risolta: {team_name_cell.value!r}")
            continue

        for pref_rank, (name_idx, bid_idx) in enumerate([(2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13)], start=1):
            name_cell, bid_cell = row[name_idx], row[bid_idx]
            if name_cell.value is None or name_cell.value == "-":
                continue
            fill = name_cell.fill.fgColor.rgb if name_cell.fill and name_cell.fill.fgColor else None
            outcome = _COLOR_OUTCOME.get(fill, "unknown")
            player, err = resolve_player(player_conn, str(name_cell.value))
            if err:
                errors.append(f"[{xlsx_path.name}] {team_name_cell.value!r} pref#{pref_rank}: {err}")
                continue
            try:
                bid_amount = int(bid_cell.value)
            except (TypeError, ValueError):
                errors.append(f"[{xlsx_path.name}] {team_name_cell.value!r} pref#{pref_rank}: offerta non numerica {bid_cell.value!r}")
                continue
            rows_out.append({
                "source_file": xlsx_path.name,
                "team_id": team_id,
                "list_pool_name": player["list_pool_name"],
                "role": player["role"],
                "preference_rank": pref_rank,
                "player_code": player["player_code"],
                "bid_amount": bid_amount,
                "outcome": outcome,
            })
    return rows_out, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx_paths", type=Path, nargs="+")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    player_conn = player_table.connect()
    labels_conn = team_labels_store.connect()
    labels = team_labels_store.get_all_labels(labels_conn)

    all_rows: list[dict] = []
    all_errors: list[str] = []
    for p in args.xlsx_paths:
        rows, errors = parse_one_file(p, player_conn, labels)
        all_rows.extend(rows)
        all_errors.extend(errors)

    if all_errors:
        print(f"{len(all_errors)} ERRORI DI RISOLUZIONE:")
        for e in all_errors:
            print(f"  - {e}")

    df = pd.DataFrame(all_rows)
    print(f"\n{len(df)} righe di preferenza risolte da {len(args.xlsx_paths)} file.")
    if len(df):
        print(df["outcome"].value_counts().to_string())

    if not args.yes:
        print("\nDRY-RUN: nessuna scrittura. Rilancia con --yes per scrivere il CSV.")
        return 1 if all_errors else 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"Scritto {OUT_PATH} ({len(df)} righe).")
    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
