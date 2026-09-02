"""Captain suggestion (ADR-2026-080).

The historical captain bonus is tiered on the *base vote* (docs/SCORING_RULES.md:
>=6 -> +1, >=7 -> +2, >=8 -> +3, <5.5 -> -1) but the exact operational form is
UNRESOLVED (docs/OPEN_QUESTIONS.md §"Motore partita"). So this does NOT optimise
against the bonus rule: it simply names the starter with the highest profile
score -- "most likely to score high", not "optimal under the bonus".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .risk_profile import RiskProfile

if TYPE_CHECKING:  # pragma: no cover
    from .optimizer import PlayerSlot

_CAVEAT = (
    "I tier esatti del bonus capitano non sono ratificati (docs/OPEN_QUESTIONS.md), "
    "quindi questo è il giocatore con il punteggio atteso più alto, non la scelta "
    "ottima rispetto alla regola del bonus."
)


@dataclass(frozen=True)
class CaptainSuggestion:
    player_code: int
    display_name: str
    reason: str


def suggest_captain(
    starters: Sequence["PlayerSlot"], profile: RiskProfile
) -> CaptainSuggestion | None:
    """Highest-``score`` starter. Returns None for an empty starting XI."""
    if not starters:
        return None
    best = max(starters, key=lambda p: (p.score, p.player_code))
    reason = (
        f"Punteggio atteso più alto dei titolari (profilo {profile.name}): "
        f"{best.score:.2f}, media simulata {best.sim_mean:.2f}. {_CAVEAT}"
    )
    return CaptainSuggestion(
        player_code=best.player_code, display_name=best.display_name, reason=reason
    )
