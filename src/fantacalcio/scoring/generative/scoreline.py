"""Sub-module 3 — team-match scoreline (ONE shared draw per club-match).

Per ``docs/research/priorart_stage4.md`` §4 and §"Recommended" Module 3/6:

* one ``(goals_for, goals_against)`` draw per club per simulated matchday,
  **shared** by every one of that club's players in that matchday — this is the
  minimal teammate/opponent dependency (v1 of sub-module 6);
* a Stage-2 odds-implied joint pmf when a priced grid is passed
  (``TeamMatchPrior.joint_pmf``, e.g. from
  ``modeling.odds_priors.team_goals_distribution``);
* else a scalar Dixon-Coles-style ``(lambda_for, lambda_against)`` Poisson draw;
* else a role-pool empirical fallback (league-average Poisson).

``clean_sheet`` and ``goals_conceded`` are read off that single draw, so all of a
club's D/P in the same simulated matchday share their clean-sheet outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_FALLBACK_GOALS_FOR = 1.35
_FALLBACK_GOALS_AGAINST = 1.35


@dataclass(frozen=True)
class TeamMatchPrior:
    """Prior for one club in one fixture.

    Exactly one channel is used, in priority order:

    1. ``joint_pmf`` — a 2-D ``(gf, ga)`` probability grid (Stage-2 odds path);
    2. ``lam_for`` / ``lam_against`` — scalar Poisson means (Dixon-Coles path);
    3. neither -> the league-average empirical fallback.
    """

    joint_pmf: np.ndarray | None = None
    lam_for: float | None = None
    lam_against: float | None = None

    def __post_init__(self) -> None:
        if self.joint_pmf is not None:
            arr = np.asarray(self.joint_pmf, dtype=float)
            if arr.ndim != 2:
                raise ValueError("joint_pmf must be a 2-D (gf, ga) grid")
            if arr.min() < 0 or not np.isclose(arr.sum(), 1.0, atol=1e-6):
                raise ValueError("joint_pmf must be non-negative and sum to 1")
        for name in ("lam_for", "lam_against"):
            v = getattr(self, name)
            if v is not None and v < 0:
                raise ValueError(f"{name} must be >= 0")


def _resolve_lams(prior: TeamMatchPrior | None) -> tuple[float, float]:
    if prior is not None and prior.lam_for is not None and prior.lam_against is not None:
        return float(prior.lam_for), float(prior.lam_against)
    return _FALLBACK_GOALS_FOR, _FALLBACK_GOALS_AGAINST


def sample_team_match(prior: TeamMatchPrior | None, rng: np.random.Generator) -> tuple[int, int]:
    """One ``(goals_for, goals_against)`` draw for a club-match."""
    if prior is not None and prior.joint_pmf is not None:
        grid = np.asarray(prior.joint_pmf, dtype=float)
        k = grid.shape[1]
        flat = grid.ravel()
        idx = int(rng.choice(flat.size, p=flat / flat.sum()))
        return idx // k, idx % k
    lam_for, lam_against = _resolve_lams(prior)
    return int(rng.poisson(lam_for)), int(rng.poisson(lam_against))


def sample_many(
    prior: TeamMatchPrior | None, n: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised ``n`` independent ``(gf, ga)`` draws for the same prior."""
    if prior is not None and prior.joint_pmf is not None:
        grid = np.asarray(prior.joint_pmf, dtype=float)
        k = grid.shape[1]
        flat = grid.ravel()
        idx = rng.choice(flat.size, size=n, p=flat / flat.sum())
        return (idx // k).astype(int), (idx % k).astype(int)
    lam_for, lam_against = _resolve_lams(prior)
    return rng.poisson(lam_for, n).astype(int), rng.poisson(lam_against, n).astype(int)


def clean_sheet(goals_against: np.ndarray | int) -> np.ndarray:
    """``1`` where the club conceded zero, else ``0``."""
    return (np.asarray(goals_against) == 0).astype(int)


def goals_conceded(goals_against: np.ndarray | int) -> np.ndarray:
    return np.asarray(goals_against, dtype=int)


__all__ = [
    "TeamMatchPrior",
    "sample_team_match",
    "sample_many",
    "clean_sheet",
    "goals_conceded",
]
