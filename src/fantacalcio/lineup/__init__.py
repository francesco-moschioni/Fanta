"""Pure lineup-selection logic for the post-auction "Giornata / Formazione" tool
(M6, docs/UX_PRODUCT.md; ADR-2026-080).

No Streamlit / DB imports live here: this package only takes plain value objects
(``PlayerSlot``) plus the versioned ruleset and returns frozen result objects.
The Streamlit page ``app/pages/8_⚽_Formazione.py`` is the only caller that knows
about the roster ledger, locks, and the DuckDB player table -- exactly like the
auction pages call ``fantacalcio.auction.*`` without embedding domain logic.

Nothing in here recomputes anything that belongs in ``scoring/engine.py`` or
``scoring/monte_carlo.py``. The single formula implemented -- the historical
defence modifier in :mod:`fantacalcio.lineup.modifier` -- is explicitly the
UNRATIFIED historical formula (docs/OPEN_QUESTIONS.md) and is only ever reached
behind an opt-in flag with a visible disclaimer.
"""

from __future__ import annotations

from .bench import bench_notes, order_bench
from .captain import CaptainSuggestion, suggest_captain
from .formations import ROLE_SLOTS, Formation, load_formations, parse_formation
from .modifier import MODIFIER_DISCLAIMER, historical_defence_modifier
from .optimizer import (
    LineupResult,
    PlayerSlot,
    best_xi,
    compare_formations,
)
from .risk_profile import (
    AGGRESSIVO,
    BILANCIATO,
    PRESETS,
    PRUDENTE,
    RiskProfile,
    player_score,
)
from .sv_risk import SVRiskLevel, flag_sv_risk, sv_risk, sv_risk_level

__all__ = [
    "Formation",
    "parse_formation",
    "load_formations",
    "ROLE_SLOTS",
    "RiskProfile",
    "PRUDENTE",
    "BILANCIATO",
    "AGGRESSIVO",
    "PRESETS",
    "player_score",
    "PlayerSlot",
    "LineupResult",
    "best_xi",
    "compare_formations",
    "historical_defence_modifier",
    "MODIFIER_DISCLAIMER",
    "CaptainSuggestion",
    "suggest_captain",
    "order_bench",
    "bench_notes",
    "sv_risk",
    "flag_sv_risk",
    "sv_risk_level",
    "SVRiskLevel",
]
