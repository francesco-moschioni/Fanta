import numpy as np
import pytest

from fantacalcio.scoring.generative import (
    TeamMatchPrior,
    clean_sheet,
    goals_conceded,
    sample_many,
    sample_team_match,
)


def test_deterministic_under_seed():
    prior = TeamMatchPrior(lam_for=1.6, lam_against=1.1)
    a = sample_many(prior, 500, np.random.default_rng(1))
    b = sample_many(prior, 500, np.random.default_rng(1))
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])


def test_poisson_marginal_matches_lambda():
    prior = TeamMatchPrior(lam_for=1.7, lam_against=0.9)
    gf, ga = sample_many(prior, 40000, np.random.default_rng(2))
    assert abs(gf.mean() - 1.7) < 0.05
    assert abs(ga.mean() - 0.9) < 0.05


def test_clean_sheet_and_goals_conceded_from_single_draw():
    ga = np.array([0, 1, 0, 2])
    np.testing.assert_array_equal(clean_sheet(ga), [1, 0, 1, 0])
    np.testing.assert_array_equal(goals_conceded(ga), ga)


def test_joint_pmf_path_respects_grid():
    grid = np.zeros((3, 3))
    grid[2, 0] = 1.0  # always 2-0
    prior = TeamMatchPrior(joint_pmf=grid)
    gf, ga = sample_team_match(prior, np.random.default_rng(3))
    assert (gf, ga) == (2, 0)


def test_fallback_when_no_prior():
    gf, ga = sample_many(None, 20000, np.random.default_rng(4))
    assert 1.0 < gf.mean() < 1.7
    assert 1.0 < ga.mean() < 1.7


def test_bad_grid_rejected():
    with pytest.raises(ValueError):
        TeamMatchPrior(joint_pmf=np.array([0.5, 0.5]))
