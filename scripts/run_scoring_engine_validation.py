#!/usr/bin/env python3
"""Validate the deterministic scoring engine against real data.

Applies score_fantavoto (individual-confirmed components only, see
src/fantacalcio/scoring/engine.py's module docstring for exactly what's included
and what's excluded) to every rated player-matchday row in the voti panel, averages
per player per season, and compares against the independently-sourced `Fm`
(fantamedia) field in the statistiche export.

A gap here is expected and informative, not a failure to fix silently: our engine
excludes team-level modifiers (defense modifier, performance bonus, fair play,
under-11 relief) and captain bonus, all of which contribute to Fantacalcio.it's own
Fm. This tells us how much of the total score those excluded components are
responsible for, on average.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from fantacalcio.modeling.player_voto import load_player_matchday_panel
from fantacalcio.scoring.engine import PlayerMatchdayEvents, score_fantavoto

REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_scoring_engine_validation.md")
STATISTICHE_DIR = Path("data/staged/fantacalcio_statistiche_manual")
SEASONS = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]


def main() -> None:
    print("Loading voti panel...")
    voti = load_player_matchday_panel()
    rated = voti[~voti["voto_no_vote"]].copy()

    print(f"Scoring {len(rated)} rated player-matchday rows...")
    scores = []
    for row in rated.itertuples(index=False):
        events = PlayerMatchdayEvents(
            role=row.role,
            played=True,
            goals_scored=int(row.goals_scored),
            assists=int(row.assists),
            goals_conceded=int(row.goals_conceded),
            own_goals=int(row.own_goals),
            yellow_cards=int(row.yellow_cards),
            red_cards=int(row.red_cards),
            penalties_missed=int(row.penalties_missed),
        )
        scores.append(score_fantavoto(row.voto, events))
    rated["our_fantavoto"] = scores

    per_player_season = (
        rated.groupby(["player_code", "season_label"])["our_fantavoto"].mean().reset_index()
    )

    lines = [
        "# Scoring engine validation — our fantavoto vs. Fantacalcio.it's Fm",
        "",
        "Our engine only includes the individual-confirmed components (goal, assist "
        "[approximated, see engine docstring], goal conceded, clean sheet, own goal, "
        "cards, penalty missed). It excludes defense modifier, performance bonus, "
        "fair play, under-11 relief, and captain bonus — all team-level or data-"
        "unavailable per docs/CURRENT_TASK.md scope. The gap below is a measurement "
        "of how much those excluded components matter, not an error to hide.",
        "",
        "| Season | Players matched | Mean our_fantavoto | Mean their Fm | Mean gap (theirs - ours) | Correlation |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for season in SEASONS:
        statistiche_path = STATISTICHE_DIR / f"{season}.csv"
        if not statistiche_path.is_file():
            lines.append(f"| {season} | (statistiche file not found) | | | | |")
            continue
        statistiche = pd.read_csv(statistiche_path)
        statistiche = statistiche.astype({"player_code": "int64"})
        ours_season = per_player_season[per_player_season["season_label"] == season].astype({"player_code": "int64"})
        merged = ours_season.merge(statistiche[["player_code", "fantamedia"]], on="player_code", how="inner")
        merged = merged.dropna(subset=["fantamedia"])
        if merged.empty:
            lines.append(f"| {season} | 0 | | | | |")
            continue
        gap = merged["fantamedia"] - merged["our_fantavoto"]
        corr = merged["our_fantavoto"].corr(merged["fantamedia"])
        print(f"{season}: matched={len(merged)}, mean_ours={merged['our_fantavoto'].mean():.3f}, "
              f"mean_theirs={merged['fantamedia'].mean():.3f}, gap={gap.mean():.3f}, corr={corr:.3f}")
        lines.append(
            f"| {season} | {len(merged)} | {merged['our_fantavoto'].mean():.3f} | "
            f"{merged['fantamedia'].mean():.3f} | {gap.mean():.3f} | {corr:.4f} |"
        )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport: {REPORT_PATH}")


if __name__ == "__main__":
    main()
