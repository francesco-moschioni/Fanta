"""Sub-module 4 — cards / own goals (tiny per-90 rates, position-keyed).

Per ``docs/research/priorart_stage4.md`` §6 and §"Recommended" Module 4:

* ``yellow ~ Poisson(lambda_yc x minutes / 90)``, ``lambda_yc`` position-keyed and
  per-player shrunk; capped at 1 for scoring (a second yellow is a red);
* ``red ~ Bernoulli(min(lambda_rc x minutes / 90, 1))``;
* ``own_goal ~ Bernoulli(~0.03 x minutes / 90)`` for keepers/defenders, ~0
  otherwise.

The **team-level fair-play / defensive modifier stays BLOCKED**
(``docs/OPEN_QUESTIONS.md``): :func:`team_defensive_modifier` raises, exactly like
``scoring.engine``'s blocked components. Per-club simulated bookings are recorded
by the season simulator so the modifier can be switched on later without a
re-run, but no aggregation is computed here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..engine import ScoringComponentBlocked

ROLE_YELLOW_PER90 = {"P": 0.05, "D": 0.18, "C": 0.20, "A": 0.12}
_ROLE_RED_PER90 = 0.012
_ROLE_OWN_GOAL_PER90 = 0.03
_SHRINK_K = 20.0
_OWN_GOAL_ROLES = frozenset({"P", "D"})


@dataclass(frozen=True)
class DisciplineRates:
    """Per-player discipline rates. ``yellow_per90 = None`` -> role prior only."""

    yellow_per90: float | None = None
    n_yellow_events: float = 0.0
    red_per90: float = _ROLE_RED_PER90
    own_goal_per90: float = _ROLE_OWN_GOAL_PER90

    def __post_init__(self) -> None:
        if self.yellow_per90 is not None and self.yellow_per90 < 0:
            raise ValueError("yellow_per90 must be >= 0")
        if self.red_per90 < 0 or self.own_goal_per90 < 0:
            raise ValueError("red_per90 / own_goal_per90 must be >= 0")


def _shrunk_yellow(rates: DisciplineRates, role: str) -> float:
    role_mean = ROLE_YELLOW_PER90.get(role, 0.15)
    if rates.yellow_per90 is None:
        return role_mean
    w = rates.n_yellow_events / (rates.n_yellow_events + _SHRINK_K)
    return w * rates.yellow_per90 + (1.0 - w) * role_mean


def sample_discipline(
    rates: DisciplineRates,
    role: str,
    minutes: np.ndarray,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Per-appearance ``yellow`` (0/1), ``red`` (0/1), ``own_goal`` (0/1)."""
    minutes = np.asarray(minutes, dtype=float)
    thin = np.clip(minutes / 90.0, 0.0, None)

    yellow = np.minimum(rng.poisson(_shrunk_yellow(rates, role) * thin), 1)
    red = rng.binomial(1, np.clip(rates.red_per90 * thin, 0.0, 1.0))
    if role in _OWN_GOAL_ROLES:
        own_goal = rng.binomial(1, np.clip(rates.own_goal_per90 * thin, 0.0, 1.0))
    else:
        own_goal = np.zeros(minutes.shape, dtype=int)

    return {
        "yellow": np.asarray(yellow, dtype=int),
        "red": np.asarray(red, dtype=int),
        "own_goal": np.asarray(own_goal, dtype=int),
    }


def team_defensive_modifier(*_args: object, **_kwargs: object) -> float:
    raise ScoringComponentBlocked(
        "Team-level fair-play / defensive modifier is still open in "
        "docs/OPEN_QUESTIONS.md. Stage 4 delivers only the individual card / "
        "own-goal draws; the team aggregation is not built until an ADR records "
        "its formula. Per-club simulated bookings are recorded for later use."
    )


__all__ = [
    "DisciplineRates",
    "ROLE_YELLOW_PER90",
    "sample_discipline",
    "team_defensive_modifier",
]
