"""Engine v2 Stage 4 (ADR-2026-077): decomposed generative Monte-Carlo.

The monolithic row-bootstrap of :mod:`fantacalcio.scoring.monte_carlo` is kept
intact as the "single-match level 0" entry point. This package adds coherent
generative *sub-modules* and a **season simulator** in which
``season != matchday-1 x 38`` — participation/minutes are folded into an
appearance path over the real fixture list, so the seasonal distribution carries
the law-of-total-variance term ``Var[S] = E[N] sigma^2 + Var[N] mu^2`` that naive
38x scaling drops.

Design reference: ``docs/research/priorart_stage4.md`` §"Recommended for our
Stage 4". Everything here favours the simplest form that fixes a *measured*
deficiency of the current engine; richer forms (availability Markov chain,
ordinal base voto, congestion logits, copula coupling) are deliberately deferred
and recorded in ADR-2026-077.

Determinism
-----------
Every stochastic entry point takes an explicit ``numpy`` ``Generator``. The
season simulator seeds each sub-module from an independent, **counter-based**
stream via :func:`module_rng` — ``(base_seed, entity_code, sim_index,
module_id)`` — so adding or removing a module does not shift another module's
draws.
"""

from __future__ import annotations

from ._seed import (
    MODULE_BASE_VOTO,
    MODULE_DISCIPLINE,
    MODULE_EVENTS,
    MODULE_MINUTES,
    MODULE_PARTICIPATION,
    MODULE_SCORELINE,
    module_rng,
)
from .participation import (  # noqa: E402
    KEEPER_BACKUP,
    KEEPER_NAILED,
    KEEPER_NONE,
    PlayerSeasonParticipation,
    sample_appearance,
    sample_minutes,
    simulate_appearance_counts,
)
from .goals_assists import PlayerRates, blended_assist_rate, blended_goal_rate, sample_events  # noqa: E402
from .scoreline import TeamMatchPrior, clean_sheet, goals_conceded, sample_many, sample_team_match  # noqa: E402
from .discipline import DisciplineRates, sample_discipline, team_defensive_modifier  # noqa: E402
from .base_voto import sample_appearance_scores, sample_base_voto  # noqa: E402
from .dependencies import SharedMatchContext, build_shared_context  # noqa: E402
from .season import (  # noqa: E402
    Fixture,
    GenerativeConfig,
    SeasonSimResult,
    default_season_fixtures,
    simulate_season,
)

__all__ = [
    "module_rng",
    "KEEPER_BACKUP",
    "KEEPER_NAILED",
    "KEEPER_NONE",
    "MODULE_PARTICIPATION",
    "MODULE_MINUTES",
    "MODULE_SCORELINE",
    "MODULE_EVENTS",
    "MODULE_DISCIPLINE",
    "MODULE_BASE_VOTO",
    "PlayerSeasonParticipation",
    "sample_appearance",
    "sample_minutes",
    "simulate_appearance_counts",
    "PlayerRates",
    "sample_events",
    "blended_goal_rate",
    "blended_assist_rate",
    "TeamMatchPrior",
    "sample_team_match",
    "sample_many",
    "clean_sheet",
    "goals_conceded",
    "DisciplineRates",
    "sample_discipline",
    "team_defensive_modifier",
    "sample_base_voto",
    "sample_appearance_scores",
    "SharedMatchContext",
    "build_shared_context",
    "Fixture",
    "GenerativeConfig",
    "SeasonSimResult",
    "default_season_fixtures",
    "simulate_season",
]
