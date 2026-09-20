"""Matchday Monte Carlo Simulation.

Simulates matchday player point outcomes over N iterations (seeded, reproducible)
using event Poisson rates, participation probabilities, and base voto distributions.

Produces full uncertainty metrics:
- Mean, Median (P50), P10, P90, Min, Max;
- Probability of no-vote / SV;
- Probabilities of scoring >=1 goal, >=1 assist, clean sheet;
- Downside (P10) and Upside (P90) indicators.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from fantacalcio.modeling.matchday_event_model import MatchdayPlayerProjection, PlayerEventRates
from fantacalcio.scoring.engine import PlayerMatchdayEvents, score_fantavoto


@dataclass(frozen=True)
class MatchdaySimulationSummary:
    player_code: int
    player_name: str
    role: str
    team: str
    opponent: str
    is_home: bool
    simulations_count: int
    mean_fantavoto: float
    median_fantavoto: float
    p10_fantavoto: float
    p90_fantavoto: float
    min_fantavoto: float
    max_fantavoto: float
    prob_no_vote: float
    prob_at_least_1_goal: float
    prob_at_least_1_assist: float
    prob_clean_sheet: float
    upside_bonus: float  # P90 - Mean
    downside_risk: float  # Mean - P10


def simulate_player_matchday(
    projection: MatchdayPlayerProjection,
    n_sims: int = 10000,
    seed: int = 42,
    base_voto_std: float = 0.55,
) -> MatchdaySimulationSummary:
    """Run seeded Monte Carlo simulation for a player's single matchday performance."""
    rng = np.random.default_rng(seed)
    rates: PlayerEventRates = projection.event_rates

    # 1. Sample participation: 0 = No Vote, 1 = Played (Starter or Sub)
    no_vote_prob = rates.no_vote_prob
    played_mask = rng.random(n_sims) >= no_vote_prob
    n_played = int(np.sum(played_mask))

    if n_played == 0:
        return MatchdaySimulationSummary(
            player_code=projection.player_code,
            player_name=projection.player_name,
            role=projection.role,
            team=projection.team,
            opponent=projection.opponent,
            is_home=projection.is_home,
            simulations_count=n_sims,
            mean_fantavoto=0.0,
            median_fantavoto=0.0,
            p10_fantavoto=0.0,
            p90_fantavoto=0.0,
            min_fantavoto=0.0,
            max_fantavoto=0.0,
            prob_no_vote=1.0,
            prob_at_least_1_goal=0.0,
            prob_at_least_1_assist=0.0,
            prob_clean_sheet=0.0,
            upside_bonus=0.0,
            downside_risk=0.0,
        )

    # 2. Sample events for played iterations
    base_votos = rng.normal(loc=rates.expected_base_voto, scale=base_voto_std, size=n_played)
    # Clip base voto to realistic range [3.0, 9.5]
    base_votos = np.clip(base_votos, 3.0, 9.5)

    goals = rng.poisson(lam=rates.lambda_goals, size=n_played)
    assists = rng.poisson(lam=rates.lambda_assists, size=n_played)
    yellows = (rng.random(n_played) < rates.lambda_yellow_cards).astype(int)
    reds = (rng.random(n_played) < rates.lambda_red_cards).astype(int)

    if rates.role in ("P", "D"):
        clean_sheets = (rng.random(n_played) < rates.prob_clean_sheet).astype(int)
    else:
        clean_sheets = np.zeros(n_played, dtype=int)

    if rates.role == "P":
        # Goals conceded for goalkeeper
        opp_goals = projection.match_projection.expected_away_goals if projection.is_home else projection.match_projection.expected_home_goals
        goals_conceded = rng.poisson(lam=opp_goals, size=n_played)
    else:
        goals_conceded = np.zeros(n_played, dtype=int)

    # Calculate fantavoto for played iterations
    fantavoti_played = np.zeros(n_played)
    for i in range(n_played):
        events = PlayerMatchdayEvents(
            role=rates.role,
            played=True,
            goals_scored=int(goals[i]),
            assists=int(assists[i]),
            yellow_cards=int(yellows[i]),
            red_cards=int(reds[i]),
            team_goals_conceded=int(goals_conceded[i]) if rates.role == "P" else None,
        )
        fantavoti_played[i] = score_fantavoto(base_votos[i], events)

    # Combine played and unplayed (fantavoto = 0)
    all_fantavoti = np.zeros(n_sims)
    all_fantavoti[played_mask] = fantavoti_played

    mean_fv = float(np.mean(all_fantavoti))
    median_fv = float(np.median(all_fantavoti))
    p10_fv = float(np.percentile(all_fantavoti, 10))
    p90_fv = float(np.percentile(all_fantavoti, 90))
    min_fv = float(np.min(all_fantavoti))
    max_fv = float(np.max(all_fantavoti))

    prob_no_vote = float(1.0 - (n_played / n_sims))
    prob_goal = float(np.sum(goals > 0) / n_sims)
    prob_assist = float(np.sum(assists > 0) / n_sims)
    prob_cs = float(np.sum(clean_sheets > 0) / n_sims)

    return MatchdaySimulationSummary(
        player_code=projection.player_code,
        player_name=projection.player_name,
        role=projection.role,
        team=projection.team,
        opponent=projection.opponent,
        is_home=projection.is_home,
        simulations_count=n_sims,
        mean_fantavoto=round(mean_fv, 2),
        median_fantavoto=round(median_fv, 2),
        p10_fantavoto=round(p10_fv, 2),
        p90_fantavoto=round(p90_fv, 2),
        min_fantavoto=round(min_fv, 2),
        max_fantavoto=round(max_fv, 2),
        prob_no_vote=round(prob_no_vote, 3),
        prob_at_least_1_goal=round(prob_goal, 3),
        prob_at_least_1_assist=round(prob_assist, 3),
        prob_clean_sheet=round(prob_cs, 3),
        upside_bonus=round(max(0.0, p90_fv - mean_fv), 2),
        downside_risk=round(max(0.0, mean_fv - p10_fv), 2),
    )
