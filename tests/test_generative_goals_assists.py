import numpy as np
import pytest

from fantacalcio.scoring.generative import PlayerRates, blended_goal_rate, sample_events


def test_deterministic_under_seed():
    rates = PlayerRates(goal_per90=0.4, assist_per90=0.2, n_goal_events=30, n_assist_events=15)
    minutes = np.full(200, 90.0)
    a = sample_events(rates, "A", minutes, None, np.random.default_rng(1))
    b = sample_events(rates, "A", minutes, None, np.random.default_rng(1))
    np.testing.assert_array_equal(a["goals"], b["goals"])
    np.testing.assert_array_equal(a["assists"], b["assists"])


def test_goal_marginal_matches_rate_minutes_thinned():
    rates = PlayerRates(goal_per90=0.5, assist_per90=0.0, n_goal_events=200)
    minutes = np.full(20000, 45.0)  # half a match -> half the per-90 rate
    ev = sample_events(rates, "A", minutes, None, np.random.default_rng(3))
    assert abs(ev["goals"].mean() - 0.5 * 0.5) < 0.02


def test_xg_blend_pulls_rate_toward_xg_when_history_thin():
    thin = PlayerRates(goal_per90=0.1, assist_per90=0.1, n_goal_events=2, xg_goal_per90=0.6)
    rich = PlayerRates(goal_per90=0.1, assist_per90=0.1, n_goal_events=400, xg_goal_per90=0.6)
    assert blended_goal_rate(thin, "A") > blended_goal_rate(rich, "A")


def test_assists_binomial_on_team_goals():
    rates = PlayerRates(goal_per90=0.0, assist_per90=1.0, n_assist_events=200)
    minutes = np.full(5000, 90.0)
    team_goals = np.full(5000, 0, dtype=int)
    ev = sample_events(rates, "C", minutes, team_goals, np.random.default_rng(4))
    assert ev["assists"].sum() == 0  # no team goals -> no assists


def test_penalty_taker_conversion_and_miss():
    # n_goal_events high so open-play rate shrinks to ~0 and only penalties contribute.
    rates = PlayerRates(
        goal_per90=0.0, assist_per90=0.0, n_goal_events=1000, pen_taker=True,
        pen_per_appearance=1.0, pen_conversion=0.75,
    )
    minutes = np.full(20000, 90.0)
    ev = sample_events(rates, "A", minutes, None, np.random.default_rng(6))
    converted = ev["goals"].mean()
    missed = ev["penalties_missed"].mean()
    assert abs((converted + missed) - 1.0) < 0.05  # ~1 pen per appearance
    assert abs(converted / (converted + missed) - 0.75) < 0.05


def test_negative_rate_rejected():
    with pytest.raises(ValueError):
        PlayerRates(goal_per90=-0.1, assist_per90=0.0)
