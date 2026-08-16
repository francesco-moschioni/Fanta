#!/usr/bin/env python3
"""Overlay the curated 2026/27 admin list onto `_m3_replacement_values.csv` and
rebuild the DuckDB player table the app reads (ADR-2026-044/045).

Idempotent: re-running always produces the same output from the same two
inputs (the M3 CSV and the curated admin-list CSVs), per CLAUDE.md's
determinism/reproducibility rule.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.auction.apply_official_admin_list import apply_official_admin_list
from fantacalcio.config import load_ruleset
from fantacalcio.persistence.player_table import SOURCE_CSV, build_player_table

CURATED_DIR = Path("data/curated/admin_list_2026_27")
RULESET_PATH = Path("config/auction_rules.v1.yaml")


def main() -> None:
    pool = pd.read_csv(SOURCE_CSV)
    resolved_players = pd.read_csv(CURATED_DIR / "resolved_players.csv")
    goalkeeper_blocks = pd.read_csv(CURATED_DIR / "goalkeeper_blocks.csv")
    ruleset = load_ruleset(RULESET_PATH)

    before_official = int((pool["list_state"] == "official").sum())
    merged = apply_official_admin_list(pool, resolved_players, goalkeeper_blocks, ruleset)
    after_official = int((merged["list_state"] == "official").sum())

    merged.to_csv(SOURCE_CSV, index=False)
    result = build_player_table()

    print(f"list_state=official: {before_official} -> {after_official} / {len(merged)} giocatori")
    print(f"Tabella DuckDB ricostruita: {result.db_path} ({result.n_players} giocatori)")


if __name__ == "__main__":
    main()
