"""SV (senza voto / no-vote) risk for a starter (ADR-2026-080).

``sv_risk = 1 - participation_rate``, clamped to [0, 1]. ``participation_rate``
is the already-computed probability the player gets a vote at all (DuckDB
player table). This is a display flag, not a model output.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .optimizer import PlayerSlot

DEFAULT_THRESHOLD = 0.35
_MED_CUTOFF = 0.20


class SVRiskLevel(str, Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


def _participation(row: Mapping | object) -> float:
    for key in ("participation_rate", "p_vote"):
        if isinstance(row, Mapping):
            if key in row:
                val = row[key]
                break
        elif hasattr(row, key):
            val = getattr(row, key)
            break
        elif hasattr(row, "get") and row.get(key) is not None:
            val = row.get(key)
            break
    else:
        raise KeyError("row has no participation_rate / p_vote")
    f = float(val)
    if f != f:  # NaN
        return 0.0
    return f


def sv_risk(row: Mapping | object) -> float:
    """``1 - participation_rate`` clamped to [0, 1]."""
    return max(0.0, min(1.0, 1.0 - _participation(row)))


def sv_risk_level(value: float) -> SVRiskLevel:
    if value < _MED_CUTOFF:
        return SVRiskLevel.LOW
    if value < DEFAULT_THRESHOLD:
        return SVRiskLevel.MED
    return SVRiskLevel.HIGH


def flag_sv_risk(
    starters: Sequence["PlayerSlot"], threshold: float = DEFAULT_THRESHOLD
) -> list[int]:
    """``player_code`` of every starter whose :func:`sv_risk` is >= ``threshold``."""
    return [p.player_code for p in starters if sv_risk(p) >= threshold]
