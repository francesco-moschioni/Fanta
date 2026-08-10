"""Mandatory naive baselines, per docs/DATA_AND_MODELING.md.

Every real model must be compared against these; a model that doesn't beat them on
its primary metric is not worth the added complexity.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ConstantOutcomeBaseline:
    """Predicts the same (P(H), P(D), P(A)) for every match: the training set's
    empirical outcome rates."""

    p_home: float
    p_draw: float
    p_away: float

    def predict(self, n: int) -> list[tuple[float, float, float]]:
        return [(self.p_home, self.p_draw, self.p_away)] * n


def fit_constant_outcome_baseline(train: pd.DataFrame) -> ConstantOutcomeBaseline:
    counts = train["FTR"].value_counts(normalize=True)
    return ConstantOutcomeBaseline(
        p_home=float(counts.get("H", 0.0)),
        p_draw=float(counts.get("D", 0.0)),
        p_away=float(counts.get("A", 0.0)),
    )


@dataclass(frozen=True)
class PreviousSeasonAverageGoals:
    """Predicts constant expected home/away goals: the training set's league-wide
    average, ignoring team identity."""

    avg_home_goals: float
    avg_away_goals: float


def fit_previous_season_average_goals(train: pd.DataFrame) -> PreviousSeasonAverageGoals:
    return PreviousSeasonAverageGoals(
        avg_home_goals=float(train["FTHG"].mean()),
        avg_away_goals=float(train["FTAG"].mean()),
    )
