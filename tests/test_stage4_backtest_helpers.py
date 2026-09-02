"""Unit tests for the pure helpers of scripts/run_stage4_generative_backtest.py
(Engine v2 Stage 4 promotion gate, ADR-2026-077 addendum).

Only the leakage-free / deterministic building blocks are covered here: the
real-fixture-list builder from a football-data-shaped frame and the realised
seasonal-total computation from a voti-panel-shaped frame. The Monte-Carlo gate
itself is an integration script, not unit-tested.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_stage4_generative_backtest as s4  # noqa: E402
from fantacalcio.scoring.engine import PlayerMatchdayEvents, score_fantavoto  # noqa: E402


def test_build_team_fixtures_orders_by_date_and_flags_home():
    fd = pd.DataFrame(
        [
            {"Date": "2022-08-13", "HomeTeam": "Alpha", "AwayTeam": "Beta"},
            {"Date": "2022-08-13", "HomeTeam": "Gamma", "AwayTeam": "Delta"},
            {"Date": "2022-08-20", "HomeTeam": "Beta", "AwayTeam": "Alpha"},
            {"Date": "2022-08-20", "HomeTeam": "Delta", "AwayTeam": "Gamma"},
            {"Date": "2022-08-27", "HomeTeam": "Alpha", "AwayTeam": "Gamma"},
            {"Date": "2022-08-27", "HomeTeam": "Beta", "AwayTeam": "Delta"},
        ]
    )
    fx = s4.build_team_fixtures(fd)

    assert set(fx) == {"Alpha", "Beta", "Gamma", "Delta"}
    alpha = fx["Alpha"]
    assert [f.matchday for f in alpha] == [1, 2, 3]
    assert [f.is_home for f in alpha] == [True, False, True]
    # every team gets exactly its real number of fixtures, contiguous from 1
    for team, games in fx.items():
        assert [f.matchday for f in games] == list(range(1, len(games) + 1))


def test_build_team_fixtures_matchday_is_chronological_rank():
    # deliberately unsorted input
    fd = pd.DataFrame(
        [
            {"Date": "2022-09-01", "HomeTeam": "Alpha", "AwayTeam": "Beta"},
            {"Date": "2022-08-01", "HomeTeam": "Beta", "AwayTeam": "Alpha"},
        ]
    )
    fx = s4.build_team_fixtures(fd)
    # Alpha's earlier match (Aug, away) must be matchday 1
    assert fx["Alpha"][0].matchday == 1
    assert fx["Alpha"][0].is_home is False
    assert fx["Alpha"][1].is_home is True


def _panel_row(**kw):
    base = dict(
        player_code=1,
        role="C",
        voto=6.0,
        voto_no_vote=False,
        goals_scored=0,
        goals_conceded=0,
        own_goals=0,
        yellow_cards=0,
        red_cards=0,
        penalties_missed=0,
        assists=0,
        matchday=1,
        team_goals_conceded=float("nan"),
    )
    base.update(kw)
    return base


def test_score_panel_and_season_real_totals():
    panel = pd.DataFrame(
        [
            _panel_row(player_code=1, matchday=1, voto=6.0),
            _panel_row(player_code=1, matchday=2, voto=7.0),
            _panel_row(player_code=1, matchday=3, voto=4.0, voto_no_vote=True),  # excluded
            _panel_row(player_code=2, matchday=1, voto=6.0, goals_scored=1),
        ]
    )
    scored = s4.score_panel_fantavoto(panel)
    # the no-vote row is dropped
    assert len(scored) == 3
    assert set(scored["player_code"]) == {1, 2}

    totals = s4.season_real_totals(scored)
    assert totals.loc[1] == pytest.approx(13.0)  # 6.0 + 7.0, no events
    expected_p2 = score_fantavoto(
        6.0,
        PlayerMatchdayEvents(role="C", played=True, goals_scored=1, assists=0,
                             goals_conceded=0, own_goals=0, yellow_cards=0,
                             red_cards=0, penalties_missed=0, team_goals_conceded=None),
    )
    assert totals.loc[2] == pytest.approx(expected_p2)
    assert expected_p2 > 6.0  # a goal is a bonus


def test_score_panel_uses_team_goals_conceded_when_present():
    panel = pd.DataFrame(
        [
            _panel_row(player_code=9, role="P", matchday=1, voto=6.0, team_goals_conceded=0.0),
            _panel_row(player_code=9, role="P", matchday=2, voto=6.0, team_goals_conceded=3.0),
        ]
    )
    scored = s4.score_panel_fantavoto(panel).sort_values("matchday")
    vals = scored["our_fantavoto"].tolist()
    # keeper clean sheet (md1) must score higher than conceding three (md2)
    assert vals[0] > vals[1]


def test_match_team_fuzzy():
    fd_names = ["Milan", "Inter", "Hellas Verona", "Roma"]
    assert s4.match_team("Milan", fd_names) == "Milan"
    assert s4.match_team("Verona", fd_names) == "Hellas Verona"
    assert s4.match_team("Nonexistent", fd_names) is None
