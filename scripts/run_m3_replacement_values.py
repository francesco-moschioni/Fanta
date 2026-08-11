#!/usr/bin/env python3
"""M3: value above replacement for the real 2026/27 roster.

Reads the Monte Carlo output (scripts/run_monte_carlo_fantavoto.py) and the real
roster composition rules (config/auction_rules.v1.yaml), computes replacement level
per role, and ranks players by VAR instead of raw expected fantavoto -- the first
step that actually reflects auction value, not just "how good is this player".

Report stays local under data/staged/ (gitignored, personal-use-licensed sources).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.auction.replacement import add_value_above_replacement, compute_replacement_levels
from fantacalcio.config import load_ruleset

MONTE_CARLO_CSV = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_2026_27.csv")
REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_m3_replacement_values.md")
CSV_PATH = Path("data/staged/fantacalcio_voti_manual/_m3_replacement_values.csv")
RULESET_PATH = Path("config/auction_rules.v1.yaml")


def main() -> None:
    ruleset = load_ruleset(RULESET_PATH)
    pool = pd.read_csv(MONTE_CARLO_CSV)

    levels = compute_replacement_levels(pool, ruleset)
    result = add_value_above_replacement(pool, levels)
    result = result.sort_values("var_mean", ascending=False)
    result.to_csv(CSV_PATH, index=False)

    lines = [
        "# M3 — value above replacement, 2026/27 roster",
        "",
        "Replacement level per role = value of the player ranked exactly at that "
        "role's total league slot count (from config/auction_rules.v1.yaml, not "
        "hardcoded). VAR = player's simulated mean fantavoto minus their role's "
        "replacement level.",
        "",
        "## Replacement levels",
        "",
        "| Role | League slots | Players available | Shortfall | Replacement level (mean) |",
        "|---|---:|---:|---:|---:|",
    ]
    for role in ["P", "D", "C", "A"]:
        n_slots = getattr(ruleset.roster, {"P": "goalkeeper_block_size", "D": "defenders", "C": "midfielders", "A": "forwards"}[role]) * ruleset.teams
        shortfall = levels.shortfall_by_role[role]
        flag = " [!]" if shortfall > 0 else ""
        lines.append(f"| {role} | {n_slots} | {levels.n_players_by_role[role]} | {shortfall}{flag} | {levels.by_role[role]:.3f} |")

    if any(levels.shortfall_by_role.values()):
        lines += [
            "",
            "[!] **Supply shortfall detected**: fewer players are available in the "
            "2026/27 quotazioni pool than there are league-wide roster slots for at "
            "least one role. Replacement level for that role falls back to the "
            "lowest-ranked available player rather than the true slot-count rank — "
            "an approximation, not an error, but worth knowing about. For forwards, "
            "this is exactly the scenario `forwards_fallback_if_supply_insufficient: "
            "4` in config/auction_rules.v1.yaml anticipates (roster quota can drop to "
            "4 forwards if supply runs out).",
        ]

    lines += ["", "## Top 15 by value above replacement", "", "| Player | Role | Team | Sim mean | Replacement | VAR mean | VAR range (P10-P90) |", "|---|---|---|---:|---:|---:|---|"]
    for row in result.head(15).itertuples(index=False):
        lines.append(
            f"| {row.display_name} | {row.role} | {row.team_name} | {row.sim_mean:.2f} | "
            f"{row.replacement_level:.2f} | {row.var_mean:.2f} | [{row.var_p10:.2f}, {row.var_p90:.2f}] |"
        )

    lines += ["", "## Bottom 5 (below replacement) among players with real history", "", "| Player | Role | Team | VAR mean |", "|---|---|---|---:|"]
    with_history = result[result["player_games_in_pool"] > 0]
    for row in with_history.tail(5).itertuples(index=False):
        lines.append(f"| {row.display_name} | {row.role} | {row.team_name} | {row.var_mean:.2f} |")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nCSV: {CSV_PATH}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
