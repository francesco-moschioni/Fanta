"""Risk profiles for scoring a player's matchday expectation (ADR-2026-080).

A profile is a set of weights over four per-player numbers already computed
upstream by the Monte Carlo (DuckDB player table):

* ``sim_mean``            -- expected fantavoto for one matchday if they play;
* ``sim_p10``             -- floor (10th percentile);
* ``sim_p90``             -- ceiling (90th percentile);
* ``participation_rate``  -- probability of getting a vote at all.

``BILANCIATO`` is defined so ``player_score`` == ``sim_mean`` exactly (weights
1/0/0/0). ``PRUDENTE`` shifts weight onto the floor and participation;
``AGGRESSIVO`` onto the ceiling. Nothing here is a scoring formula in the
engine sense -- it is a ranking preference the user picks.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# participation_rate is in [0, 1]; multiply by a points-like scale so `w_pvote`
# is comparable in magnitude to the other weights (a nailed-on starter is worth
# roughly a baseline voto of upside in this heuristic).
PVOTE_SCALE = 6.0


@dataclass(frozen=True)
class RiskProfile:
    name: str
    w_mean: float
    w_floor: float
    w_ceiling: float
    w_pvote: float


PRUDENTE = RiskProfile(name="prudente", w_mean=0.55, w_floor=0.35, w_ceiling=0.0, w_pvote=0.10)
BILANCIATO = RiskProfile(name="bilanciato", w_mean=1.0, w_floor=0.0, w_ceiling=0.0, w_pvote=0.0)
AGGRESSIVO = RiskProfile(name="aggressivo", w_mean=0.55, w_floor=0.0, w_ceiling=0.45, w_pvote=0.0)

PRESETS: dict[str, RiskProfile] = {
    PRUDENTE.name: PRUDENTE,
    BILANCIATO.name: BILANCIATO,
    AGGRESSIVO.name: AGGRESSIVO,
}


def _get(row: Mapping | object, key: str, default: float = 0.0) -> float:
    if isinstance(row, Mapping):
        val = row.get(key, default)
    elif hasattr(row, key):
        val = getattr(row, key)
    elif hasattr(row, "get"):  # pandas Series
        val = row.get(key, default)
    else:
        val = default
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    # pandas NaN -> fall back
    return default if f != f else f


def player_score(row: Mapping | object, profile: RiskProfile) -> float:
    """Weighted blend of mean / floor / ceiling / participation for ``row``.

    ``row`` may be a mapping, a pandas ``Series``, or any object exposing the
    attributes ``sim_mean``/``sim_p10``/``sim_p90``/``participation_rate``.
    With ``BILANCIATO`` this returns ``sim_mean`` unchanged.
    """
    mean = _get(row, "sim_mean")
    floor = _get(row, "sim_p10")
    ceiling = _get(row, "sim_p90")
    pvote = _get(row, "participation_rate")
    return (
        profile.w_mean * mean
        + profile.w_floor * floor
        + profile.w_ceiling * ceiling
        + profile.w_pvote * pvote * PVOTE_SCALE
    )
