"""Blend xG/xA-implied goal/assist rates into a bootstrap fantavoto ensemble.

Engine v2 Stage 3 (ADR-2026-075). Reuses the Stage-2 SIR pattern
(``scoring.odds_conditioning``): a per-draw importance reweight of the bootstrap
ensemble, then a seeded resample — never an additive shift.

The player's realised historical goal/assist rate is blended with the
xG/xA-implied rate using the same shrinkage form as everywhere else in the
project::

    w = n / (n + prior_events)
    blended_rate = w * historical_rate + (1 - w) * xg_rate

where ``n`` is the count of realised events of that kind in the sampled rows.
Draws whose sampled row contained a goal (resp. assist) are upweighted by
``blended_goal_rate / historical_goal_rate`` (resp. the assist ratio), weights
are normalised to mean 1, clipped, and SIR-resampled. ESS is checked: below the
floor, or degenerate, the input ``result`` is returned unchanged.

**Controlled degradation**: ``xg_goal_rate is None`` puts weight 0 on the xG
term (ratio 1). If *both* rates are ``None`` the function returns the input
``result`` object unchanged and byte-identical — no rng is touched.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace

import numpy as np

from .monte_carlo import DEFAULT_SEED, HistoricalRow, SimulationResult

logger = logging.getLogger(__name__)

_ESS_FLOOR_FRACTION = 0.10
_DEFAULT_PRIOR_EVENTS = 20.0


def _blend(hist_rate: float, xg_rate: float | None, n_events: float, prior_events: float) -> float:
    """Shrinkage blend; xg_rate None -> weight 0 on xG -> returns hist_rate."""
    if xg_rate is None:
        return hist_rate
    w = n_events / (n_events + prior_events) if (n_events + prior_events) > 0 else 0.0
    return w * hist_rate + (1.0 - w) * xg_rate


def adjust_event_propensity(
    result: SimulationResult,
    *,
    historical_rows: Sequence[HistoricalRow | None],
    xg_goal_rate: float | None,
    xg_assist_rate: float | None,
    role: str,
    hist_goal_rate: float,
    hist_assist_rate: float,
    prior_events: float = _DEFAULT_PRIOR_EVENTS,
    rng: np.random.Generator | None = None,
    weight_clip: float = 10.0,
) -> SimulationResult:
    """Reweight/SIR-resample ``result`` toward xG/xA-implied goal & assist rates.

    ``historical_rows`` must be aligned 1:1 with ``result.samples`` (the list
    returned by ``simulate_fantavoto(..., collect_rows=True)``).
    """
    if xg_goal_rate is None and xg_assist_rate is None:
        # Controlled degradation: nothing to condition on -> byte-identical.
        return result

    samples = np.asarray(result.samples, dtype=float)
    n = samples.size
    if len(historical_rows) != n:
        raise ValueError(
            f"adjust_event_propensity: historical_rows length {len(historical_rows)} != n_sims {n}"
        )

    goal_flag = np.array(
        [bool(r is not None and r.goals_scored > 0) for r in historical_rows], dtype=bool
    )
    assist_flag = np.array(
        [bool(r is not None and r.assists > 0) for r in historical_rows], dtype=bool
    )

    n_goal_events = float(goal_flag.sum())
    n_assist_events = float(assist_flag.sum())

    blended_goal = _blend(hist_goal_rate, xg_goal_rate, n_goal_events, prior_events)
    blended_assist = _blend(hist_assist_rate, xg_assist_rate, n_assist_events, prior_events)

    goal_ratio = (blended_goal / hist_goal_rate) if hist_goal_rate > 0 else 1.0
    assist_ratio = (blended_assist / hist_assist_rate) if hist_assist_rate > 0 else 1.0
    goal_ratio = float(np.clip(goal_ratio, 0.2, 5.0))
    assist_ratio = float(np.clip(assist_ratio, 0.2, 5.0))

    w = np.ones(n, dtype=float)
    w[goal_flag] *= goal_ratio
    w[assist_flag] *= assist_ratio

    if np.allclose(w, w[0]):
        logger.info("adjust_event_propensity: no differential weight (role=%s); returning unchanged", role)
        return result

    w = w / w.mean()
    w = np.clip(w, None, weight_clip)
    wsum = w.sum()
    if not np.isfinite(wsum) or wsum <= 0.0:
        logger.warning("adjust_event_propensity: weights degenerated; returning unchanged")
        return result
    w = w / wsum

    ess = float(1.0 / np.sum(w**2))
    logger.info(
        "adjust_event_propensity: role=%s goal_ratio=%.3f assist_ratio=%.3f ESS=%.1f (%.1f%% of %d)",
        role, goal_ratio, assist_ratio, ess, 100.0 * ess / n, n,
    )
    if ess < _ESS_FLOOR_FRACTION * n:
        logger.warning(
            "adjust_event_propensity: ESS %.1f < %.0f%% of %d -- fights the ensemble; returning unchanged",
            ess, 100 * _ESS_FLOOR_FRACTION, n,
        )
        return result

    if rng is None:
        rng = np.random.default_rng(DEFAULT_SEED)
    idx = rng.choice(n, size=n, replace=True, p=w)
    return replace(result, samples=samples[idx])


__all__ = ["adjust_event_propensity"]
