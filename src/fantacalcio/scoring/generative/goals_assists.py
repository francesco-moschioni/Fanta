"""Sub-module 2 — goals / assists / penalties (shrunk per-90 Poisson, minutes-thinned).

Per ``docs/research/priorart_stage4.md`` §3 and §"Recommended" Module 2:

* ``goals_openplay ~ Poisson(lambda_goal x minutes / 90)`` with ``lambda_goal``
  Efron-Morris shrunk toward the role per-90 mean, ``w = n / (n + k)``;
* when a Stage-3 xG/xA rate is supplied, blend it in via the same shrinkage form
  (``xg_propensity`` idiom); absent xG -> history only (weight 0 on the xG term);
* penalties as a **separate** ``Bernoulli(taken) x Bernoulli(~0.77 conversion)``,
  never inside the open-play ``lambda``; a miss feeds the ruleset malus;
* assists on the **shared-draw path** as ``Binomial(team_goals, pi)`` so the
  assist / team-goal correlation and creator competition are automatic; absent a
  team-goals draw, ``Poisson(lambda_assist x minutes / 90)``.

Negative-Binomial dispersion is deferred (ADR-2026-077): Poisson is the v1
marginal; switch only if a per-90 dispersion test fails on real data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Role per-90 priors (goals, assists). Coarse league-typical values; the shrink
# target only matters for thin histories.
ROLE_GOAL_PER90 = {"P": 0.0, "D": 0.05, "C": 0.12, "A": 0.35}
ROLE_ASSIST_PER90 = {"P": 0.0, "D": 0.05, "C": 0.13, "A": 0.12}

_SHRINK_K = 20.0
_XG_PRIOR_EVENTS = 20.0
_DEFAULT_PEN_CONVERSION = 0.77


@dataclass(frozen=True)
class PlayerRates:
    """Per-player per-90 event rates and their evidence counts.

    ``n_goal_events`` / ``n_assist_events`` are the realised counts behind the
    raw rates — they drive both the role-mean shrinkage and the xG blend weight.
    """

    goal_per90: float
    assist_per90: float
    n_goal_events: float = 0.0
    n_assist_events: float = 0.0
    pen_taker: bool = False
    pen_per_appearance: float = 0.0
    pen_conversion: float = _DEFAULT_PEN_CONVERSION
    xg_goal_per90: float | None = None
    xa_per90: float | None = None

    def __post_init__(self) -> None:
        for name in ("goal_per90", "assist_per90", "pen_per_appearance"):
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be >= 0")
        if not 0.0 <= self.pen_conversion <= 1.0:
            raise ValueError("pen_conversion must be in [0, 1]")


def _shrink(raw: float, role_mean: float, n: float, k: float = _SHRINK_K) -> float:
    w = n / (n + k) if (n + k) > 0 else 0.0
    return w * raw + (1.0 - w) * role_mean


def blended_goal_rate(rates: PlayerRates, role: str) -> float:
    """Role-shrunk realised goal rate, blended with the xG rate when present."""
    base = _shrink(rates.goal_per90, ROLE_GOAL_PER90.get(role, 0.0), rates.n_goal_events)
    if rates.xg_goal_per90 is not None:
        w = rates.n_goal_events / (rates.n_goal_events + _XG_PRIOR_EVENTS)
        base = w * base + (1.0 - w) * float(rates.xg_goal_per90)
    return max(0.0, base)


def blended_assist_rate(rates: PlayerRates, role: str) -> float:
    base = _shrink(rates.assist_per90, ROLE_ASSIST_PER90.get(role, 0.0), rates.n_assist_events)
    if rates.xa_per90 is not None:
        w = rates.n_assist_events / (rates.n_assist_events + _XG_PRIOR_EVENTS)
        base = w * base + (1.0 - w) * float(rates.xa_per90)
    return max(0.0, base)


def sample_events(
    rates: PlayerRates,
    role: str,
    minutes: np.ndarray,
    team_goals: np.ndarray | None,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Per-appearance ``goals_scored``, ``assists`` and ``penalties_missed``.

    ``minutes`` and (optionally) ``team_goals`` are aligned 1:1 with the
    appearances being scored. Returns ``int`` arrays of the same length.
    """
    minutes = np.asarray(minutes, dtype=float)
    thin = np.clip(minutes / 90.0, 0.0, None)

    lam_goal = blended_goal_rate(rates, role) * thin
    goals_open = rng.poisson(lam_goal)

    if rates.pen_taker and rates.pen_per_appearance > 0.0:
        pens_taken = rng.poisson(rates.pen_per_appearance * np.clip(thin, 0.0, 1.0))
        pens_scored = rng.binomial(pens_taken, rates.pen_conversion)
        pens_missed = pens_taken - pens_scored
    else:
        pens_scored = np.zeros_like(goals_open)
        pens_missed = np.zeros_like(goals_open)

    goals = goals_open + pens_scored

    if team_goals is not None:
        tg = np.maximum(np.asarray(team_goals, dtype=int), 0)
        share = np.clip(blended_assist_rate(rates, role) / 2.0, 0.0, 0.75) * np.clip(thin, 0.0, 1.0)
        assists = rng.binomial(tg, share)
    else:
        assists = rng.poisson(blended_assist_rate(rates, role) * thin)

    return {
        "goals": goals.astype(int),
        "assists": np.asarray(assists, dtype=int),
        "penalties_missed": np.asarray(pens_missed, dtype=int),
    }


__all__ = [
    "PlayerRates",
    "ROLE_GOAL_PER90",
    "ROLE_ASSIST_PER90",
    "blended_goal_rate",
    "blended_assist_rate",
    "sample_events",
]
