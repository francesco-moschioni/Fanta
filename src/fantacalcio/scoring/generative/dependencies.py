"""Sub-module 6 — teammate / opponent dependencies (v1: minimal).

Per ``docs/research/priorart_stage4.md`` §4 and §"Recommended" Module 3/6, the
**only** coupling in v1 is:

* the shared ``scoreline.sample_team_match`` draw, reused across every one of a
  club's players in a simulated matchday (so a back line's clean-sheet outcomes
  are correlated exactly by the shared ``goals_against``);
* a shared opponent-strength scalar carried alongside.

Everything richer — form autocorrelation, copula / ensemble-copula-coupling of
within-team residuals, joint whole-matchday simulation giving opposing defences
their natural negative correlation — is **deferred** (ADR-2026-077, Risk 1:
dependency coupling is the main variance-blow-up channel; add one channel at a
time behind a gate).

Mechanically the season simulator implements the shared draw by seeding the
scoreline RNG from the *club* id rather than the player id, so two players with
the same ``club_id`` see the identical ``(gf, ga)`` sequence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .scoreline import TeamMatchPrior, sample_team_match


@dataclass(frozen=True)
class SharedMatchContext:
    """One club-match outcome shared by all that club's players in a matchday."""

    team_goals_for: int
    team_goals_against: int
    opponent_strength: float = 0.0


def build_shared_context(
    prior: TeamMatchPrior | None,
    rng: np.random.Generator,
    opponent_strength: float = 0.0,
) -> SharedMatchContext:
    """Draw the shared club-match scoreline once and wrap it with opponent strength."""
    gf, ga = sample_team_match(prior, rng)
    return SharedMatchContext(team_goals_for=gf, team_goals_against=ga, opponent_strength=opponent_strength)


__all__ = ["SharedMatchContext", "build_shared_context"]
