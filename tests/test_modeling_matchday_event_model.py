"""Tests for Matchday Event-Level Predictive Model."""

from fantacalcio.modeling.dixon_coles import DixonColesModel
from fantacalcio.modeling.matchday_event_model import (
    estimate_player_event_rates,
    project_match,
    project_player_matchday,
)


def test_project_match_defaults():
    proj = project_match("Genoa", "Empoli")
    assert proj.home_team == "Genoa"
    assert proj.away_team == "Empoli"
    assert proj.expected_home_goals > 0
    assert proj.expected_away_goals > 0
    assert abs((proj.prob_home_win + proj.prob_draw + proj.prob_away_win) - 1.0) < 1e-4


def test_project_match_dixon_coles():
    dc = DixonColesModel(
        attack={"Inter": 0.5, "Lecce": -0.5},
        defense={"Inter": -0.3, "Lecce": 0.3},
        home_advantage=0.2,
        teams=["Inter", "Lecce"],
    )
    proj = project_match("Inter", "Lecce", dixon_coles_model=dc)
    assert proj.expected_home_goals > proj.expected_away_goals
    assert proj.prob_home_win > proj.prob_away_win
    assert proj.prob_home_clean_sheet > proj.prob_away_clean_sheet


def test_estimate_player_event_rates():
    rates = estimate_player_event_rates(
        player_code=101,
        role="A",
        is_home=True,
        team_exp_goals=2.0,
        opp_exp_goals=0.8,
        participation_rate=0.8,
        base_voto=6.5,
    )
    assert rates.player_code == 101
    assert rates.role == "A"
    assert rates.starter_prob > rates.sub_prob
    assert rates.no_vote_prob < 0.3
    assert rates.lambda_goals > 0.1
    assert rates.lambda_assists > 0.05
    assert rates.prob_clean_sheet == 0.0  # Attacker has 0 clean sheet prob


def test_project_player_matchday_goalkeeper():
    proj = project_player_matchday(
        player_code=1,
        player_name="Sommer Y.",
        role="P",
        team="Inter",
        opponent="Lecce",
        is_home=True,
        participation_rate=0.95,
        base_voto=6.2,
    )
    assert proj.player_name == "Sommer Y."
    assert proj.role == "P"
    assert proj.event_rates.prob_clean_sheet > 0.3
    assert proj.expected_fantavoto > 0.0
