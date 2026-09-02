"""Pick covariance / complementarity -- treat the roster as a portfolio of players
(Engine v2 Stage 6, ADR-2026-076; design: docs/research/priorart_stage6.md sec 3).

Given per-player seasonal Monte-Carlo point-sample vectors (aligned by scenario index),
this module measures how a candidate co-moves with the roster already owned:

- `Var[T(R u j)] - Var[T(R)] = Var[P_j] + 2*sum_{i in R} Cov(P_i, P_j)` -- the
  complementarity signal (positive => stacks/amplifies both tails, negative => hedges);
- the scenario-level downside version `q10(t_R + p_j) - q10(t_R)` -- the change in the
  roster's "bad-season floor" -- preferred for the UI (no covariance matrix, robust to
  the skewed, capped-downside / long-upside shape of fantacalcio points).

CAVEAT (priorart sec 3.2 / sec 7.4 risk 1): today's Monte-Carlo draws players
independently, so the sample covariance here is effectively DIAGONAL and understates the
true cross-player correlation (same-club clean-sheet co-movement, same-fixture
anti-correlation, common calendar/rule shocks). These functions are therefore a FLOOR
on roster risk, to be refined when Stage 4 joint sims land.
"""

from __future__ import annotations

import numpy as np


def _align(player_samples: dict[int, np.ndarray]) -> tuple[list[int], np.ndarray]:
    if not player_samples:
        raise ValueError("player_samples is empty")
    codes = sorted(player_samples)
    mat = np.vstack([np.asarray(player_samples[c], dtype=float) for c in codes])
    lengths = {row.shape[0] for row in mat}
    if len(lengths) != 1:
        raise ValueError(f"player sample vectors have mismatched lengths: {lengths}")
    return codes, mat


def roster_point_samples(player_samples: dict[int, np.ndarray]) -> np.ndarray:
    """Sum the aligned per-player sample vectors into the roster point-total vector."""
    _codes, mat = _align(player_samples)
    return mat.sum(axis=0)


def covariance_matrix(player_samples: dict[int, np.ndarray]) -> tuple[list[int], np.ndarray]:
    """Sample covariance (ddof=1) of the aligned per-player sample vectors.

    NOTE: with today's independent per-player Monte Carlo this is effectively diagonal
    and understates true cross-player correlation -- a floor, refined at Stage 4."""
    codes, mat = _align(player_samples)
    if mat.shape[1] < 2:
        return codes, np.zeros((len(codes), len(codes)))
    return codes, np.cov(mat, ddof=1)


def marginal_variance_contribution(roster_samples: np.ndarray, candidate_samples: np.ndarray) -> float:
    """`Var[T(R) + P_j] - Var[T(R)]` from the scenario samples (ddof=1)."""
    roster = np.asarray(roster_samples, dtype=float)
    cand = np.asarray(candidate_samples, dtype=float)
    return float(np.var(roster + cand, ddof=1) - np.var(roster, ddof=1))


def marginal_downside_contribution(
    roster_samples: np.ndarray, candidate_samples: np.ndarray, q: float = 0.10
) -> float:
    """Change in the roster's lower-tail quantile floor from adding the candidate:
    `q_q(t_R + p_j) - q_q(t_R)`. Positive => the candidate lifts the bad-season floor."""
    roster = np.asarray(roster_samples, dtype=float)
    cand = np.asarray(candidate_samples, dtype=float)
    before = float(np.quantile(roster, q))
    after = float(np.quantile(roster + cand, q))
    return after - before


def complementarity_adjustment(
    candidate_var: float,
    marginal_var_contribution: float,
    marginal_downside_contribution: float,
    *,
    risk_aversion: float = 0.0,
) -> float:
    """Risk-adjust a candidate's raw VAR by how it co-moves with the current roster.

    `risk_aversion == 0` returns `candidate_var` unchanged (backward compatible). For
    `risk_aversion > 0` the penalty grows with the marginal variance the candidate adds
    (a same-club, highly-correlated pick adds `Var[P_j] + 2*sum Cov` -- more than an
    uncorrelated pick of equal raw VAR) and shrinks when the candidate lifts the
    roster's downside floor (`marginal_downside_contribution > 0`)."""
    if risk_aversion == 0.0:
        return float(candidate_var)
    var_term = math_sqrt_nonneg(marginal_var_contribution)
    penalty = risk_aversion * (var_term - marginal_downside_contribution)
    return float(candidate_var - penalty)


def math_sqrt_nonneg(x: float) -> float:
    return float(np.sqrt(x)) if x > 0 else 0.0
