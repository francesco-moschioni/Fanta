"""Shared forecast-evaluation metrics (numpy / pandas / scipy only).

Centralises the small scoring helpers that were previously scattered across the
modeling modules so that every backtest, calibration check and ranking report
uses one implementation. No global state, no I/O, deterministic.

`log_loss` keeps the exact list-of-tuples signature it had in
`fantacalcio.modeling.validation` and is re-exported from there for backwards
compatibility; `multiclass_log_loss` is the vectorised array form.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import spearmanr

__all__ = [
    "crps_ensemble",
    "pit_values",
    "coverage",
    "brier",
    "log_loss",
    "multiclass_log_loss",
    "mae",
    "rmse",
    "spearman_rank_corr",
    "ndcg_at_k",
]


def crps_ensemble(samples: np.ndarray, observed: float) -> float:
    """Empirical Continuous Ranked Probability Score for a sample ensemble.

    Uses the energy-form estimator
    ``CRPS = E|X - y| - 0.5 * E|X - X'|`` where ``X, X'`` are independent draws
    from the ensemble. Returns exactly ``0.0`` for a point-mass ensemble sitting
    on ``observed``.

    Parameters
    ----------
    samples:
        1-D array of Monte-Carlo draws from the predictive distribution.
    observed:
        The realised value.
    """
    s = np.asarray(samples, dtype=float).ravel()
    if s.size == 0:
        raise ValueError("crps_ensemble: empty sample ensemble")
    term_accuracy = float(np.mean(np.abs(s - observed)))
    term_spread = float(np.mean(np.abs(s[:, None] - s[None, :])))
    return term_accuracy - 0.5 * term_spread


def pit_values(samples_2d: np.ndarray, observed_1d: np.ndarray) -> np.ndarray:
    """Probability Integral Transform value per row.

    For each predictive ensemble (row of ``samples_2d``) returns the fraction of
    draws less than or equal to the matching ``observed_1d`` entry. A calibrated
    forecast yields PIT values that are uniform on ``[0, 1]``.
    """
    s = np.asarray(samples_2d, dtype=float)
    o = np.asarray(observed_1d, dtype=float)
    if s.ndim != 2:
        raise ValueError("pit_values: samples_2d must be 2-D (n_rows, n_samples)")
    if o.shape[0] != s.shape[0]:
        raise ValueError("pit_values: observed_1d length must match samples_2d rows")
    return np.mean(s <= o[:, None], axis=1)


def coverage(
    samples_2d: np.ndarray, observed_1d: np.ndarray, lo: float = 0.1, hi: float = 0.9
) -> float:
    """Empirical coverage of the central ``[lo, hi]`` predictive interval.

    Returns the fraction of rows whose observed value falls inside the per-row
    ``[quantile(lo), quantile(hi)]`` band. A calibrated forecast returns a value
    close to ``hi - lo``.
    """
    s = np.asarray(samples_2d, dtype=float)
    o = np.asarray(observed_1d, dtype=float)
    if s.ndim != 2:
        raise ValueError("coverage: samples_2d must be 2-D (n_rows, n_samples)")
    lo_q = np.quantile(s, lo, axis=1)
    hi_q = np.quantile(s, hi, axis=1)
    return float(np.mean((o >= lo_q) & (o <= hi_q)))


def brier(prob: np.ndarray, outcome: np.ndarray) -> float:
    """Mean Brier score for binary probabilistic forecasts.

    ``prob`` is the forecast probability of the event, ``outcome`` the realised
    0/1 indicator. Scalars are accepted.
    """
    p = np.asarray(prob, dtype=float)
    y = np.asarray(outcome, dtype=float)
    return float(np.mean((p - y) ** 2))


def log_loss(
    y_true_index: list[int],
    probs: list[tuple[float, float, float]],
    eps: float = 1e-12,
) -> float:
    """Multinomial log loss over a list of ``(p0, p1, p2, ...)`` tuples.

    ``y_true_index`` holds the realised class index per row (0=home win,
    1=draw, 2=away win for the team-strength models). Kept with this exact
    signature for the callers that imported it from
    ``fantacalcio.modeling.validation``.
    """
    total = 0.0
    for idx, p in zip(y_true_index, probs):
        total += -math.log(max(p[idx], eps))
    return total / len(y_true_index)


def multiclass_log_loss(
    probs_2d: np.ndarray, outcome_idx_1d: np.ndarray, eps: float = 1e-12
) -> float:
    """Vectorised multinomial log loss.

    ``probs_2d`` has shape ``(n_rows, n_classes)``; ``outcome_idx_1d`` holds the
    realised class index per row.
    """
    probs = np.asarray(probs_2d, dtype=float)
    idx = np.asarray(outcome_idx_1d, dtype=int)
    if probs.ndim != 2:
        raise ValueError("multiclass_log_loss: probs_2d must be 2-D")
    if idx.shape[0] != probs.shape[0]:
        raise ValueError("multiclass_log_loss: row count mismatch")
    chosen = probs[np.arange(idx.shape[0]), idx]
    return float(-np.mean(np.log(np.clip(chosen, eps, 1.0))))


def mae(pred: np.ndarray, true: np.ndarray) -> float:
    """Mean absolute error."""
    p = np.asarray(pred, dtype=float)
    t = np.asarray(true, dtype=float)
    return float(np.mean(np.abs(p - t)))


def rmse(pred: np.ndarray, true: np.ndarray) -> float:
    """Root mean squared error."""
    p = np.asarray(pred, dtype=float)
    t = np.asarray(true, dtype=float)
    return float(np.sqrt(np.mean((p - t) ** 2)))


def spearman_rank_corr(pred: np.ndarray, true: np.ndarray) -> float:
    """Spearman rank correlation between predicted and realised values.

    Returns ``0.0`` when the coefficient is undefined (e.g. a constant input).
    """
    p = np.asarray(pred, dtype=float)
    t = np.asarray(true, dtype=float)
    if p.size < 2:
        return 0.0
    rho = spearmanr(p, t).correlation
    return 0.0 if rho is None or np.isnan(rho) else float(rho)


def ndcg_at_k(pred: np.ndarray, true: np.ndarray, k: int) -> float:
    """Normalised Discounted Cumulative Gain at rank ``k``.

    Items are ranked by descending ``pred``; ``true`` supplies the (non-negative)
    relevance/gain of each item. Returns a value in ``[0, 1]``; ``0.0`` when the
    ideal DCG is zero.
    """
    p = np.asarray(pred, dtype=float)
    t = np.asarray(true, dtype=float)
    if p.shape != t.shape:
        raise ValueError("ndcg_at_k: pred and true must have the same shape")
    if k <= 0 or p.size == 0:
        return 0.0
    k = min(k, p.size)
    order = np.argsort(-p, kind="stable")[:k]
    discounts = 1.0 / np.log2(np.arange(2, k + 2))
    dcg = float(np.sum(t[order] * discounts))
    ideal = np.sort(t)[::-1][:k]
    idcg = float(np.sum(ideal * discounts[: ideal.size]))
    return dcg / idcg if idcg > 0 else 0.0
