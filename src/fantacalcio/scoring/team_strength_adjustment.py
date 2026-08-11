"""Connects the validated Dixon-Coles team-strength model (ADR-2026-011) to the
player-level Monte Carlo fantavoto (ADR-2026-018) -- previously built independently
and never linked, per the 2026-08-11 audit.

Idea: a player's bootstrapped historical rows implicitly carry whatever team context
they were playing in at the time. If they change teams (or we're forecasting them at
a *current* team different from their historical average context), that context
should shift too. This computes, per player, the gap between their new team's
Dixon-Coles rating and the average rating of the team(s) they actually played for
historically, and applies a small additive adjustment to the Monte Carlo samples --
not a full re-derivation of event probabilities (that would need decomposing voto
into attack/defense-attributable components, which the data doesn't cleanly support).

Sign convention (from src/fantacalcio/modeling/dixon_coles.py):
  lambda_home = exp(attack[home] + defense[away] + gamma)
  lambda_away = exp(attack[away] + defense[home])
A team's own `defense[team]` value raises the OPPONENT's expected goals, so LOWER
defense[team] = stronger defense. Attack has the opposite (intuitive) sign: higher
attack[team] = more goals scored by that team.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .monte_carlo import SimulationResult
from ..modeling.dixon_coles import DixonColesModel

ATTACK_ROLES = frozenset({"A", "C"})  # goal/assist-scoring roles: use attack rating
DEFENSE_ROLES = frozenset({"D"})  # P is excluded: already covered by team_goals_conceded join


@dataclass(frozen=True)
class TeamRatings:
    attack: dict[str, float]
    defense: dict[str, float]


def team_ratings_from_model(model: DixonColesModel) -> TeamRatings:
    return TeamRatings(attack=dict(model.attack), defense=dict(model.defense))


def historical_avg_team_rating(rated_with_team: pd.DataFrame, ratings: TeamRatings, rating: str) -> pd.Series:
    """Mean team rating (attack or defense) across a player's historical rows,
    weighted implicitly by games (one row per matchday). Unknown teams default to
    0.0 -- the league-average rating, since Dixon-Coles attack params are
    sum-to-zero and 0.0 is a neutral prior for defense too."""
    lookup = ratings.attack if rating == "attack" else ratings.defense
    team_rating = rated_with_team["team_name"].map(lambda t: lookup.get(t, 0.0))
    return team_rating.groupby(rated_with_team["player_code"]).mean()


def compute_adjustments(
    current_team_by_player: pd.Series,  # player_code -> team_name (2026/27 roster)
    role_by_player: pd.Series,  # player_code -> role
    historical_avg_attack: pd.Series,  # player_code -> historical mean attack rating
    historical_avg_defense: pd.Series,  # player_code -> historical mean defense rating
    ratings: TeamRatings,
    k: float,
) -> pd.Series:
    """Returns player_code -> additive fantavoto adjustment. 0.0 for players/roles
    not covered (P, or missing history -- no historical context to compare against)."""
    adjustments = {}
    for player_code, team_name in current_team_by_player.items():
        role = role_by_player.get(player_code)
        if role in ATTACK_ROLES and player_code in historical_avg_attack.index:
            current_attack = ratings.attack.get(team_name, 0.0)
            adjustments[player_code] = k * (current_attack - historical_avg_attack.loc[player_code])
        elif role in DEFENSE_ROLES and player_code in historical_avg_defense.index:
            current_defense = ratings.defense.get(team_name, 0.0)
            # Sign flipped vs. attack: lower defense param = stronger defense = better for the player.
            adjustments[player_code] = k * (historical_avg_defense.loc[player_code] - current_defense)
        else:
            adjustments[player_code] = 0.0
    return pd.Series(adjustments)


def apply_adjustment(result: SimulationResult, adjustment: float) -> SimulationResult:
    """Returns a new SimulationResult with `adjustment` added to every sample."""
    adjusted_samples = result.samples + adjustment
    return SimulationResult(
        player_code=result.player_code,
        role=result.role,
        n_sims=result.n_sims,
        player_games_in_pool=result.player_games_in_pool,
        used_role_pool_only=result.used_role_pool_only,
        samples=adjusted_samples,
    )
