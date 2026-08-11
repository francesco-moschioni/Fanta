#!/usr/bin/env python3
"""Re-fetches and re-parses football-data.co.uk Serie A seasons to pick up the odds
columns added to `_OPTIONAL_COLUMNS` (docs/CURRENT_TASK.md block 3). Registered in
docs/SOURCE_REGISTER.md as automation-permitted, public CSV, no auth.

Uses fresh snapshots rather than the pre-existing raw/ files from the earlier M1
audit run, some of whose manifests were corrupted by a since-fixed collision bug
(src/fantacalcio/ingest/snapshot.py) -- clean provenance beats reconstructing from
a known-bad manifest.
"""

from __future__ import annotations

from fantacalcio.ingest.football_data_co_uk import fetch_season, parse_snapshot, write_staged_csv

SEASON_CODES = ["2122", "2223", "2324", "2425", "2526"]


def main() -> None:
    for season_code in SEASON_CODES:
        snapshot = fetch_season(season_code)
        staged = parse_snapshot(snapshot, season_code=season_code)
        out_path = write_staged_csv(staged)
        has_odds = all(c in staged.frame.columns for c in ["AvgH", "AvgD", "AvgA"])
        print(f"{season_code}: {len(staged.frame)} rows, odds columns present: {has_odds} -> {out_path}")


if __name__ == "__main__":
    main()
