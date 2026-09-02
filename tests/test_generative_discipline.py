import numpy as np
import pytest

from fantacalcio.scoring.engine import ScoringComponentBlocked
from fantacalcio.scoring.generative import (
    DisciplineRates,
    sample_discipline,
    team_defensive_modifier,
)


def test_deterministic_under_seed():
    rates = DisciplineRates(yellow_per90=0.3, n_yellow_events=20)
    minutes = np.full(300, 90.0)
    a = sample_discipline(rates, "D", minutes, np.random.default_rng(1))
    b = sample_discipline(rates, "D", minutes, np.random.default_rng(1))
    np.testing.assert_array_equal(a["yellow"], b["yellow"])


def test_yellow_marginal_matches_rate():
    # Low rate so the "cap at 1" (2nd yellow == red) loses negligible mass.
    rates = DisciplineRates(yellow_per90=0.15, n_yellow_events=500)
    minutes = np.full(40000, 90.0)
    dis = sample_discipline(rates, "D", minutes, np.random.default_rng(2))
    assert abs(dis["yellow"].mean() - 0.15) < 0.02
    assert dis["yellow"].max() <= 1


def test_own_goal_only_for_keepers_and_defenders():
    rates = DisciplineRates(own_goal_per90=0.5)
    minutes = np.full(2000, 90.0)
    fwd = sample_discipline(rates, "A", minutes, np.random.default_rng(3))
    cb = sample_discipline(rates, "D", minutes, np.random.default_rng(3))
    assert fwd["own_goal"].sum() == 0
    assert cb["own_goal"].sum() > 0


def test_minutes_thin_the_rate():
    rates = DisciplineRates(yellow_per90=0.4, n_yellow_events=500)
    cameo = sample_discipline(rates, "C", np.full(20000, 18.0), np.random.default_rng(4))
    assert abs(cameo["yellow"].mean() - 0.4 * 0.2) < 0.02


def test_team_modifier_blocked():
    with pytest.raises(ScoringComponentBlocked):
        team_defensive_modifier()
