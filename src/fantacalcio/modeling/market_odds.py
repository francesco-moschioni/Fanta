"""Market-implied team strength from football-data.co.uk pre-match average odds
(`AvgH`/`AvgD`/`AvgA`, recovered in docs/CURRENT_TASK.md block 3).

Betting markets price in information Dixon-Coles (ADR-2026-011, fit from goals
alone) never sees -- injuries, suspensions, form, rumours -- so agreement between
the two is a useful independent cross-check of the goals-only model, not a
replacement for it. It is NOT wired into the 2026/27 forecast as a live input:
odds for a season that hasn't started don't exist yet, so there is nothing to
recover for the actual target season. This module's role is validation, applied
to past seasons where both odds and outcomes are already known.
"""

from __future__ import annotations

import pandas as pd


def implied_probabilities(avg_h: float, avg_d: float, avg_a: float) -> tuple[float, float, float]:
    """De-vigs (removes the bookmaker overround from) average decimal odds by
    normalizing the raw 1/odds implied probabilities to sum to 1."""
    raw_h, raw_d, raw_a = 1.0 / avg_h, 1.0 / avg_d, 1.0 / avg_a
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total


def match_expected_points(avg_h: float, avg_d: float, avg_a: float) -> tuple[float, float]:
    """Returns (home_expected_points, away_expected_points) implied by the market:
    3 points weighted by win probability, 1 point weighted by draw probability."""
    p_h, p_d, p_a = implied_probabilities(avg_h, avg_d, avg_a)
    return 3.0 * p_h + 1.0 * p_d, 3.0 * p_a + 1.0 * p_d


def team_market_rating(matches: pd.DataFrame) -> pd.Series:
    """`matches` needs [HomeTeam, AwayTeam, AvgH, AvgD, AvgA]. Returns team ->
    average market-expected points per match, across home and away matches.
    Higher = stronger, per the market's aggregate assessment."""
    rows = []
    for row in matches.itertuples(index=False):
        home_pts, away_pts = match_expected_points(row.AvgH, row.AvgD, row.AvgA)
        rows.append({"team": row.HomeTeam, "expected_points": home_pts})
        rows.append({"team": row.AwayTeam, "expected_points": away_pts})
    long = pd.DataFrame(rows)
    return long.groupby("team")["expected_points"].mean()
