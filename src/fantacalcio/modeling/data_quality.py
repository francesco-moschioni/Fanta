"""Explicit data-quality tier per player, for the 2026/27 roster.

Per docs/DATA_AND_MODELING.md: "quality_tier"/"quality_status" are first-class,
not optional commentary. A player with zero Serie A history is not one
undifferentiated kind of "unknown": a squad player on a newly-promoted team is a
genuinely uncertain quantity (our role-average fallback is a reasonable prior), but
an established transfer into an existing Serie A club (e.g. a Premier League/
Bundesliga regular) is a case where the role-average fallback is most likely to be
WRONG, not just uncertain -- the model has no way to know they're better (or worse)
than a typical squad player, because it has never seen them play at all.

This module classifies that distinction so it's visible in reports/CSVs, not
silently blended into a single "no history" bucket. It does not fabricate a wider
distribution for the transfer case (that would be inventing uncertainty without a
basis) -- it flags it for human judgement instead, per CLAUDE.md's "never guess"
principle.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

QUOTAZIONI_DIR = Path("data/staged/fantacalcio_quotazioni_manual")
HISTORICAL_SEASONS = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]
# Only the immediately preceding season, NOT the 5-season union: Serie A rotates
# via promotion/relegation, so a club can appear in e.g. 2023/24 but not 2025/26
# (relegated, then absent) -- checking the 5-season union wrongly classified every
# newly-promoted club's player as a "transfer" instead of "new team", because their
# club had been in Serie A at some point in the window. What actually matters for
# this classification is "was this club in Serie A last season" (bug found and
# fixed 2026-08-11, before this module was ever used for real output).
MOST_RECENT_SEASON = "2025_26"
FULL_HISTORY_THRESHOLD_GAMES = 60  # roughly 1.5+ seasons of matchdays

TIER_FULL_HISTORY = "full_history"
TIER_PARTIAL_HISTORY = "partial_history"
TIER_NO_HISTORY_NEW_TEAM = "no_history_new_team"  # likely: newly-promoted club's squad player
TIER_NO_HISTORY_TRANSFER = "no_history_transfer"  # likely: real transfer into an established club


def established_teams(staged_root: Path = QUOTAZIONI_DIR, season: str = MOST_RECENT_SEASON) -> set[str]:
    """Team names present in Serie A in the given season (default: the most recent
    completed one). Deliberately a single season, not a multi-season union -- see
    the MOST_RECENT_SEASON comment above for why the union was wrong."""
    path = staged_root / f"{season}.csv"
    if not path.is_file():
        return set()
    return set(pd.read_csv(path)["team_name"].unique())


def classify_data_quality(
    player_games_in_pool: int,
    team_name: str,
    known_teams: set[str],
    full_history_threshold: int = FULL_HISTORY_THRESHOLD_GAMES,
) -> str:
    if player_games_in_pool >= full_history_threshold:
        return TIER_FULL_HISTORY
    if player_games_in_pool > 0:
        return TIER_PARTIAL_HISTORY
    # player_games_in_pool == 0
    if team_name in known_teams:
        return TIER_NO_HISTORY_TRANSFER
    return TIER_NO_HISTORY_NEW_TEAM


def add_data_quality_tier(player_pool: pd.DataFrame, known_teams: set[str] | None = None) -> pd.DataFrame:
    """Adds a `data_quality_tier` column. `player_pool` must have `player_games_in_pool`
    and `team_name` columns (the Monte Carlo / VAR output)."""
    if known_teams is None:
        known_teams = established_teams()
    out = player_pool.copy()
    out["data_quality_tier"] = [
        classify_data_quality(games, team, known_teams)
        for games, team in zip(out["player_games_in_pool"], out["team_name"])
    ]
    return out
