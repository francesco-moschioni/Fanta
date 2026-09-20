"""Matchday Event-Level Predictive Model.

Combines team-level strength models (Dixon-Coles / Market Odds) with player-level
shrinkage estimators for participation rates, base voto, and event Poisson rates
(goals, assists, cards, clean sheets) to project single-matchday probabilities and expectations.

Conforms to docs/DATA_AND_MODELING.md:
- Participation / starter / sub / no-vote probability;
- Expected goals, assists, yellow/red cards, clean sheets, and base voto;
- Coherent match scoreline probabilities (Dixon-Coles / Poisson).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy.stats import poisson

from fantacalcio.modeling.dixon_coles import DixonColesModel


@dataclass(frozen=True)
class MatchProjection:
    home_team: str
    away_team: str
    expected_home_goals: float
    expected_away_goals: float
    prob_home_win: float
    prob_draw: float
    prob_away_win: float
    prob_home_clean_sheet: float
    prob_away_clean_sheet: float


@dataclass(frozen=True)
class PlayerEventRates:
    player_code: int
    role: str
    starter_prob: float
    sub_prob: float
    no_vote_prob: float
    expected_minutes: float
    expected_base_voto: float
    lambda_goals: float
    lambda_assists: float
    lambda_yellow_cards: float
    lambda_red_cards: float
    prob_clean_sheet: float  # Relevant for GK / D


@dataclass(frozen=True)
class MatchdayPlayerProjection:
    player_code: int
    player_name: str
    role: str
    team: str
    opponent: str
    is_home: bool
    match_projection: MatchProjection
    event_rates: PlayerEventRates
    expected_fantavoto: float


def project_match(
    home_team: str,
    away_team: str,
    dixon_coles_model: DixonColesModel | None = None,
    default_home_goals: float = 1.35,
    default_away_goals: float = 1.05,
) -> MatchProjection:
    """Project team expected goals and outcome probabilities for a single matchday fixture."""
    if dixon_coles_model is not None and dixon_coles_model.is_known_team(home_team) and dixon_coles_model.is_known_team(away_team):
        exp_home, exp_away = dixon_coles_model.expected_goals(home_team, away_team)
        p_home, p_draw, p_away = dixon_coles_model.outcome_probabilities(home_team, away_team)
    else:
        exp_home, exp_away = default_home_goals, default_away_goals
        p_home, p_draw, p_away = 0.45, 0.28, 0.27

    p_home_cs = float(poisson.pmf(0, exp_away))
    p_away_cs = float(poisson.pmf(0, exp_home))

    return MatchProjection(
        home_team=home_team,
        away_team=away_team,
        expected_home_goals=exp_home,
        expected_away_goals=exp_away,
        prob_home_win=p_home,
        prob_draw=p_draw,
        prob_away_win=p_away,
        prob_home_clean_sheet=p_home_cs,
        prob_away_clean_sheet=p_away_cs,
    )


def estimate_player_event_rates(
    player_code: int,
    role: str,
    is_home: bool,
    team_exp_goals: float,
    opp_exp_goals: float,
    participation_rate: float = 0.75,
    base_voto: float = 6.0,
    hist_goals_per_90: float | None = None,
    hist_assists_per_90: float | None = None,
    hist_yellow_per_90: float | None = None,
    hist_red_per_90: float | None = None,
) -> PlayerEventRates:
    """Estimate Poisson event parameters and participation probabilities for a player in a match."""
    # Participation split based on participation rate
    played_prob = min(max(participation_rate, 0.05), 0.98)
    no_vote_prob = 1.0 - played_prob
    starter_prob = played_prob * 0.85
    sub_prob = played_prob * 0.15

    # Expected minutes conditional on playing
    expected_minutes = (starter_prob * 78.0 + sub_prob * 25.0) / max(played_prob, 1e-5)

    # Role-based default per-90 rates when historical data is missing
    role_defaults = {
        "P": {"goals": 0.0, "assists": 0.01, "yellow": 0.05, "red": 0.005},
        "D": {"goals": 0.05, "assists": 0.06, "yellow": 0.20, "red": 0.01},
        "C": {"goals": 0.12, "assists": 0.12, "yellow": 0.18, "red": 0.01},
        "A": {"goals": 0.35, "assists": 0.15, "yellow": 0.12, "red": 0.01},
    }
    defaults = role_defaults.get(role, role_defaults["C"])

    g90 = hist_goals_per_90 if hist_goals_per_90 is not None else defaults["goals"]
    a90 = hist_assists_per_90 if hist_assists_per_90 is not None else defaults["assists"]
    y90 = hist_yellow_per_90 if hist_yellow_per_90 is not None else defaults["yellow"]
    r90 = hist_red_per_90 if hist_red_per_90 is not None else defaults["red"]

    # Scaling per-90 rate by expected team goals vs average team goals (~1.25)
    goal_scaling = team_exp_goals / 1.25
    mins_factor = expected_minutes / 90.0

    lambda_goals = float(g90 * goal_scaling * mins_factor)
    lambda_assists = float(a90 * goal_scaling * mins_factor)
    lambda_yellow = float(y90 * mins_factor)
    lambda_red = float(r90 * mins_factor)

    # Clean sheet probability for GK/D
    if role in ("P", "D"):
        p_clean_sheet = float(poisson.pmf(0, opp_exp_goals))
    else:
        p_clean_sheet = 0.0

    # Base voto adjustment: small boost for home, small penalty if team exp goals low
    home_voto_adj = 0.05 if is_home else -0.05
    adj_base_voto = float(base_voto + home_voto_adj)

    return PlayerEventRates(
        player_code=player_code,
        role=role,
        starter_prob=starter_prob,
        sub_prob=sub_prob,
        no_vote_prob=no_vote_prob,
        expected_minutes=expected_minutes,
        expected_base_voto=adj_base_voto,
        lambda_goals=lambda_goals,
        lambda_assists=lambda_assists,
        lambda_yellow_cards=lambda_yellow,
        lambda_red_cards=lambda_red,
        prob_clean_sheet=p_clean_sheet,
    )


def project_player_matchday(
    player_code: int,
    player_name: str,
    role: str,
    team: str,
    opponent: str,
    is_home: bool,
    dixon_coles_model: DixonColesModel | None = None,
    participation_rate: float = 0.75,
    base_voto: float = 6.0,
    hist_goals_per_90: float | None = None,
    hist_assists_per_90: float | None = None,
    hist_yellow_per_90: float | None = None,
    hist_red_per_90: float | None = None,
) -> MatchdayPlayerProjection:
    """Produce complete matchday projections and expected fantavoto for a player."""
    home_team = team if is_home else opponent
    away_team = opponent if is_home else team

    match_proj = project_match(home_team, away_team, dixon_coles_model)

    team_exp_goals = match_proj.expected_home_goals if is_home else match_proj.expected_away_goals
    opp_exp_goals = match_proj.expected_away_goals if is_home else match_proj.expected_home_goals

    rates = estimate_player_event_rates(
        player_code=player_code,
        role=role,
        is_home=is_home,
        team_exp_goals=team_exp_goals,
        opp_exp_goals=opp_exp_goals,
        participation_rate=participation_rate,
        base_voto=base_voto,
        hist_goals_per_90=hist_goals_per_90,
        hist_assists_per_90=hist_assists_per_90,
        hist_yellow_per_90=hist_yellow_per_90,
        hist_red_per_90=hist_red_per_90,
    )

    # Calculate expected bonus/malus points
    exp_bonus = (
        rates.lambda_goals * 3.0
        + rates.lambda_assists * 1.0
        - rates.lambda_yellow_cards * 0.5
        - rates.lambda_red_cards * 1.0
    )
    if role == "P":
        exp_bonus += (rates.prob_clean_sheet * 1.0) - (opp_exp_goals * 1.0)

    # Played probability
    p_played = 1.0 - rates.no_vote_prob
    exp_fv = p_played * (rates.expected_base_voto + exp_bonus)

    return MatchdayPlayerProjection(
        player_code=player_code,
        player_name=player_name,
        role=role,
        team=team,
        opponent=opponent,
        is_home=is_home,
        match_projection=match_proj,
        event_rates=rates,
        expected_fantavoto=round(exp_fv, 2),
    )
