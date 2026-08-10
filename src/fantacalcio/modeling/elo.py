"""Sequential Elo ratings with a fitted outcome-probability mapping.

Ratings update strictly in chronological match order, so a prediction for match N
only ever depends on matches 1..N-1 — leakage-safe by construction, not just by
convention. The win/draw/loss probability mapping (not just the raw Elo expected
score) is fit on the training fold via log-loss minimization.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

DEFAULT_INITIAL_RATING = 1500.0


@dataclass
class EloRatings:
    k_factor: float = 20.0
    home_advantage: float = 60.0
    initial_rating: float = DEFAULT_INITIAL_RATING
    ratings: dict[str, float] = field(default_factory=dict)

    def get(self, team: str) -> float:
        return self.ratings.get(team, self.initial_rating)

    def expected_score(self, home_team: str, away_team: str) -> float:
        diff = self.get(home_team) + self.home_advantage - self.get(away_team)
        return 1.0 / (1.0 + 10 ** (-diff / 400.0))

    def rating_diff(self, home_team: str, away_team: str) -> float:
        return self.get(home_team) + self.home_advantage - self.get(away_team)

    def update(self, home_team: str, away_team: str, actual_home_score: float) -> None:
        """actual_home_score: 1.0 win, 0.5 draw, 0.0 loss (home team's perspective)."""
        expected = self.expected_score(home_team, away_team)
        home_rating = self.get(home_team)
        away_rating = self.get(away_team)
        self.ratings[home_team] = home_rating + self.k_factor * (actual_home_score - expected)
        self.ratings[away_team] = away_rating + self.k_factor * ((1 - actual_home_score) - (1 - expected))


def _result_to_score(ftr: str) -> float:
    return {"H": 1.0, "D": 0.5, "A": 0.0}[ftr]


def fit_elo_sequential(train: pd.DataFrame, k_factor: float = 20.0, home_advantage: float = 60.0) -> tuple[EloRatings, list[float]]:
    """Replay `train` in chronological order, updating ratings after each match.
    Returns the final ratings and the rating_diff computed *before* each match (i.e.
    the leakage-safe feature used for outcome-probability fitting)."""
    elo = EloRatings(k_factor=k_factor, home_advantage=home_advantage)
    diffs = []
    for _, row in train.sort_values("Date").iterrows():
        diffs.append(elo.rating_diff(row["HomeTeam"], row["AwayTeam"]))
        elo.update(row["HomeTeam"], row["AwayTeam"], _result_to_score(row["FTR"]))
    return elo, diffs


@dataclass(frozen=True)
class OutcomeProbabilityModel:
    """Maps an Elo rating difference to (P(home win), P(draw), P(away win)) via a
    small, explicit parametric form fit by log-loss minimization: win/loss split
    from the standard logistic expected score, draw probability as a Gaussian bump
    centered on diff=0 (closer ratings -> more likely draw)."""

    scale: float
    draw_base: float
    draw_width: float

    def predict(self, diff: float) -> tuple[float, float, float]:
        win_share = 1.0 / (1.0 + 10 ** (-diff / self.scale))
        p_draw = min(0.45, max(0.05, self.draw_base * np.exp(-((diff / self.draw_width) ** 2))))
        p_home = win_share * (1 - p_draw)
        p_away = (1 - win_share) * (1 - p_draw)
        return (float(p_home), float(p_draw), float(p_away))


def fit_outcome_probability_model(diffs: list[float], results: list[str]) -> OutcomeProbabilityModel:
    """Fit (scale, draw_base, draw_width) by minimizing average log loss on the
    training fold's (rating_diff, actual result) pairs."""
    outcome_idx = np.array([{"H": 0, "D": 1, "A": 2}[r] for r in results])
    diffs_arr = np.array(diffs)

    def neg_log_lik(params: np.ndarray) -> float:
        scale, draw_base, draw_width = params
        if scale <= 1 or draw_width <= 1 or not (0 < draw_base < 1):
            return 1e6
        win_share = 1.0 / (1.0 + 10 ** (-diffs_arr / scale))
        p_draw = np.clip(draw_base * np.exp(-((diffs_arr / draw_width) ** 2)), 0.05, 0.45)
        p_home = win_share * (1 - p_draw)
        p_away = (1 - win_share) * (1 - p_draw)
        probs = np.stack([p_home, p_draw, p_away], axis=1)
        eps = 1e-12
        chosen = probs[np.arange(len(outcome_idx)), outcome_idx]
        return float(-np.mean(np.log(np.clip(chosen, eps, 1))))

    result = minimize(neg_log_lik, x0=np.array([400.0, 0.28, 200.0]), method="Nelder-Mead")
    scale, draw_base, draw_width = result.x
    return OutcomeProbabilityModel(scale=float(scale), draw_base=float(draw_base), draw_width=float(draw_width))
