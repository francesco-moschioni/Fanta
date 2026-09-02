"""Condition a bootstrap fantavoto ensemble on odds-implied team-goal marginals.

Engine v2 Stage 2 (ADR-2026-074), design ``docs/research/priorart_stage2.md`` §4.

This REPLACES the additive ``team_strength_adjustment.apply_adjustment`` on the
odds-priors path. ``team_strength_adjustment`` stays importable and is the
documented fallback for when odds are absent.

The method is importance reweighting / SIR: per-draw weights
``w_s ∝ target_pmf[g_s] / empirical_pmf[g_s]`` on the realised
``team_goals_conceded`` (or goal/assist) marginal of the ensemble, clipped and
optionally tempered, then a seeded SIR resample. No parametric assumption is put
on base voto -- the bootstrap's ``p(base voto | conceded)`` is inherited.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace

import numpy as np

from .monte_carlo import DEFAULT_SEED, HistoricalRow, SimulationResult

logger = logging.getLogger(__name__)

# Only defenders are conditioned on the odds-implied goals-conceded marginal.
# Goalkeepers are deliberately excluded: ADR-2026-023 already found team-strength
# adjustment makes GK agreement with real Fm *worse* (k=0 for GK), and the Stage 2
# rolling-origin backtest (ADR-2026-074) confirmed the same for odds conditioning
# -- the P arm regressed on CRPS_fair. A keeper's fantavoto variance is dominated
# by saves / penalties, not by team goals conceded, so `condition_samples` is a
# no-op for role "P" (matches `team_strength_adjustment.apply_adjustment`, which
# also skips GK).
CONDITION_ROLES = frozenset({"D"})
SCORING_ROLES = frozenset({"A", "C"})
_ESS_FLOOR_FRACTION = 0.10
# Fantavoto goal bonus (docs/SCORING_RULES.md): +3 for every role. Used only by
# the scale_scoring_propensity heuristic when per-draw event rows aren't passed.
_GOAL_BONUS = 3.0


def _conceded_of(row: HistoricalRow, role: str) -> float:
    if role in CONDITION_ROLES and row.team_goals_conceded is not None:
        return float(row.team_goals_conceded)
    return float(row.goals_conceded)


def _ess(weights: np.ndarray) -> float:
    return float(1.0 / np.sum(weights**2))


def condition_samples(
    result: SimulationResult,
    *,
    target_conceded_pmf: np.ndarray,
    historical_rows: Sequence[HistoricalRow],
    role: str,
    rng: np.random.Generator | None = None,
    temper: float = 1.0,
    weight_clip: float = 10.0,
) -> SimulationResult:
    """Reweight/SIR-resample ``result`` so its conceded marginal matches ``target_conceded_pmf``.

    ``historical_rows`` must be the per-draw sampled rows aligned 1:1 with
    ``result.samples`` (length ``result.n_sims``); the realised conceded count of
    draw ``s`` is ``team_goals_conceded`` for P/D, else ``goals_conceded``.

    Weights ``w_s = target_pmf[g_s] / empirical_pmf[g_s]`` are normalised to mean
    1, clipped at ``weight_clip`` * mean, raised to ``temper``, renormalised, then
    an SIR resample of size ``n`` is drawn with ``rng``. Effective sample size is
    logged. If ESS < 10% of ``n`` (or the weights degenerate to zero) the input
    ``result`` is returned unchanged with a warning -- no silent degradation.

    Role ``"P"`` (goalkeeper) is a deliberate no-op -- see :data:`CONDITION_ROLES`.
    """
    if role not in CONDITION_ROLES:
        logger.info("condition_samples: role %s not conditioned (see CONDITION_ROLES); returning unchanged", role)
        return result

    samples = np.asarray(result.samples, dtype=float)
    n = samples.size
    if len(historical_rows) != n:
        raise ValueError(
            f"condition_samples: historical_rows length {len(historical_rows)} != n_sims {n}"
        )
    target = np.asarray(target_conceded_pmf, dtype=float)
    if target.ndim != 1 or target.size < 1:
        raise ValueError("condition_samples: target_conceded_pmf must be a 1-D pmf")
    if not np.all(target >= 0.0) or not np.isfinite(target).all():
        raise ValueError("condition_samples: target_conceded_pmf has negative / non-finite entries")
    tsum = target.sum()
    if tsum <= 0.0:
        raise ValueError("condition_samples: target_conceded_pmf sums to zero")
    target = target / tsum

    g_raw = np.array([_conceded_of(r, role) for r in historical_rows], dtype=float)
    valid = np.isfinite(g_raw)
    g = np.clip(np.nan_to_num(g_raw, nan=0.0).round().astype(int), 0, target.size - 1)

    emp_counts = np.bincount(g[valid], minlength=target.size).astype(float)
    n_valid = int(valid.sum())
    if n_valid == 0:
        logger.warning("condition_samples: no valid conceded values; returning result unchanged")
        return result
    emp = emp_counts / n_valid
    emp_safe = np.where(emp <= 0.0, 1.0 / (10.0 * n_valid), emp)

    w = np.where(valid, target[g] / emp_safe[g], 1.0)
    wsum = w.sum()
    if not np.isfinite(wsum) or wsum <= 0.0:
        logger.warning("condition_samples: weights degenerated (sum=%s); returning result unchanged", wsum)
        return result
    w = w / w.mean()
    w = np.clip(w, None, weight_clip)
    if temper != 1.0:
        w = w**temper
    w = w / w.sum()

    ess = _ess(w)
    logger.info("condition_samples: ESS=%.1f (%.1f%% of %d), role=%s", ess, 100.0 * ess / n, n, role)
    if ess < _ESS_FLOOR_FRACTION * n:
        logger.warning(
            "condition_samples: ESS %.1f < %.0f%% of %d -- conditioning fights the ensemble; "
            "returning result unchanged", ess, 100 * _ESS_FLOOR_FRACTION, n
        )
        return result

    if rng is None:
        rng = np.random.default_rng(DEFAULT_SEED)
    idx = rng.choice(n, size=n, replace=True, p=w)
    return replace(result, samples=samples[idx])


def scale_scoring_propensity(
    result: SimulationResult,
    *,
    team_goals_ratio: float,
    role: str,
    historical_rows: Sequence[HistoricalRow] | None = None,
    rng: np.random.Generator | None = None,
    weight_clip: float = 10.0,
) -> SimulationResult:
    """Nudge attacking-return frequency (A/C) by the odds-implied team-goals ratio.

    ``team_goals_ratio`` is odds-implied expected team goals / the player's
    historical team-goals context (> 1 => the market expects more goals than the
    bootstrap assumes). Draws that contained a goal/assist are upweighted by the
    ratio (downweighted if < 1), then an SIR resample is drawn -- a resample, not
    an additive scalar.

    When ``historical_rows`` (aligned 1:1 with ``result.samples``) is supplied the
    goal/assist indicator is exact; otherwise a fantavoto-threshold heuristic
    (draw sits >= one goal bonus above the ensemble median) is used.
    """
    if role not in SCORING_ROLES:
        logger.warning("scale_scoring_propensity called for role %s (expected A/C); no-op", role)
        return result
    ratio = float(np.clip(team_goals_ratio, 0.2, 5.0))
    samples = np.asarray(result.samples, dtype=float)
    n = samples.size

    if historical_rows is not None:
        if len(historical_rows) != n:
            raise ValueError("scale_scoring_propensity: historical_rows length != n_sims")
        scored = np.array(
            [(r.goals_scored + r.assists) > 0 for r in historical_rows], dtype=bool
        )
    else:
        scored = (samples - np.median(samples)) >= (_GOAL_BONUS - 0.5)

    if not scored.any() or scored.all():
        logger.info("scale_scoring_propensity: degenerate scored mask (%d/%d); returning unchanged", scored.sum(), n)
        return result

    w = np.where(scored, ratio, 1.0)
    w = w / w.mean()
    w = np.clip(w, None, weight_clip)
    w = w / w.sum()

    ess = _ess(w)
    logger.info("scale_scoring_propensity: ratio=%.3f ESS=%.1f (%.1f%% of %d)", ratio, ess, 100.0 * ess / n, n)
    if ess < _ESS_FLOOR_FRACTION * n:
        logger.warning("scale_scoring_propensity: ESS below floor; returning unchanged")
        return result

    if rng is None:
        rng = np.random.default_rng(DEFAULT_SEED)
    idx = rng.choice(n, size=n, replace=True, p=w)
    return replace(result, samples=samples[idx])


__all__ = ["condition_samples", "scale_scoring_propensity", "CONDITION_ROLES", "SCORING_ROLES"]
