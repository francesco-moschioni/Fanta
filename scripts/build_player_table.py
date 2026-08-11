#!/usr/bin/env python3
"""Builds the local DuckDB player table the Streamlit UI reads from
(docs/CURRENT_TASK.md, M4 slice 1). Run this after regenerating
`_m3_replacement_values.csv` (scripts/run_monte_carlo_fantavoto.py then
scripts/run_m3_replacement_values.py) to refresh the UI's data.
"""

from __future__ import annotations

from fantacalcio.persistence.player_table import build_player_table


def main() -> None:
    result = build_player_table()
    print(f"Built {result.db_path} with {result.n_players} players.")
    print(f"Source: {result.source_path} (sha256 {result.source_sha256[:12]}...)")
    print(f"Built at: {result.built_at}")


if __name__ == "__main__":
    main()
