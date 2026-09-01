import logging

import numpy as np
import pytest

from fantacalcio.modeling.odds_priors import (
    clean_sheet_prob,
    devig,
    expected_goals_conceded,
    goals_conceded_pmf,
    match_outcome_probs,
    season_team_priors,
    shin_z,
    team_goals_distribution,
)


# --------------------------------------------------------------------------- #
# devig                                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method", ["shin", "multiplicative", "power"])
def test_devig_sums_to_one(method):
    p = devig([2.1, 3.4, 3.9], method=method)
    assert p.shape == (3,)
    assert np.isclose(p.sum(), 1.0, atol=1e-9)
    assert np.all(p > 0.0)


def test_shin_recovers_input_on_zero_margin_book():
    true_p = np.array([0.5, 0.3, 0.2])
    fair_odds = 1.0 / true_p  # booksum == 1 exactly
    out = devig(fair_odds, method="shin")
    assert np.allclose(out, true_p, atol=1e-6)


def test_shin_z_small_margin_limit():
    # z ~= margin / (n - 1) for a small overround (n = 3 -> margin / 2).
    true_p = np.array([0.45, 0.30, 0.25])
    margin = 0.02
    odds = 1.0 / (true_p * (1.0 + margin))
    z = shin_z(odds)
    assert z == pytest.approx(margin / 2.0, abs=0.01)


def test_devig_monotone_in_odds():
    base = devig([2.0, 3.5, 4.0], method="shin")
    lengthened = devig([2.6, 3.5, 4.0], method="shin")  # home odds drift out
    assert lengthened[0] < base[0]  # lower implied home prob


def test_devig_two_outcome_over_under():
    p = devig([1.9, 2.0], method="shin")
    assert np.isclose(p.sum(), 1.0)
    assert p[0] > p[1]  # shorter price -> higher prob


# --------------------------------------------------------------------------- #
# team_goals_distribution                                                    #
# --------------------------------------------------------------------------- #
def test_grid_sums_to_one_and_round_trips_outcomes():
    p_in = devig([2.2, 3.3, 3.4], method="shin")
    grid = team_goals_distribution(*p_in, total_goals=2.7)
    assert np.isclose(grid.sum(), 1.0, atol=1e-6)
    mh, md, ma = match_outcome_probs(grid)
    # supremacy is matched exactly; draw is whatever the model implies -> loose tol
    assert (mh - ma) == pytest.approx(p_in[0] - p_in[2], abs=1e-3)
    assert md == pytest.approx(p_in[1], abs=0.05)


def test_higher_over_2_5_raises_expected_total_goals():
    p_in = (0.40, 0.28, 0.32)
    low = team_goals_distribution(*p_in, p_over_2_5=0.40)
    high = team_goals_distribution(*p_in, p_over_2_5=0.62)
    ks = np.arange(low.shape[0])
    e_low = (low.sum(axis=1) @ ks) + (low.sum(axis=0) @ ks)
    e_high = (high.sum(axis=1) @ ks) + (high.sum(axis=0) @ ks)
    assert e_high > e_low + 0.3


def test_strong_home_favourite_has_higher_lambda_home():
    grid = team_goals_distribution(0.75, 0.17, 0.08, total_goals=2.8)
    ks = np.arange(grid.shape[0])
    e_home = grid.sum(axis=1) @ ks
    e_away = grid.sum(axis=0) @ ks
    assert e_home > e_away


def test_independent_fallback_triggers_and_logs(caplog):
    with caplog.at_level(logging.WARNING, logger="fantacalcio.modeling.odds_priors"):
        grid = team_goals_distribution(0.985, 0.010, 0.005, total_goals=0.8)
    assert np.isclose(grid.sum(), 1.0, atol=1e-6)
    assert any("independent" in r.message.lower() or "s=0" in r.message.lower() for r in caplog.records)


def test_total_goals_required():
    with pytest.raises(ValueError):
        team_goals_distribution(0.4, 0.3, 0.3)


def test_total_out_of_range_raises():
    with pytest.raises(ValueError):
        team_goals_distribution(0.4, 0.3, 0.3, total_goals=6.0)


# --------------------------------------------------------------------------- #
# clean sheet / conceded from the joint grid                                 #
# --------------------------------------------------------------------------- #
def test_clean_sheet_symmetric_grid_equal_both_sides():
    grid = team_goals_distribution(0.30, 0.40, 0.30, total_goals=2.5)
    assert clean_sheet_prob(grid, "home") == pytest.approx(clean_sheet_prob(grid, "away"), abs=1e-9)


def test_defence_heavy_grid_raises_clean_sheet():
    loose = team_goals_distribution(0.33, 0.34, 0.33, total_goals=3.6)
    tight = team_goals_distribution(0.33, 0.34, 0.33, total_goals=1.6)
    assert clean_sheet_prob(tight, "home") > clean_sheet_prob(loose, "home")


def test_clean_sheet_is_computed_from_the_joint_grid():
    grid = team_goals_distribution(0.55, 0.25, 0.20, total_goals=2.7, rho=-0.10)
    # computed as the joint column sum (structural guarantee), not a separate
    # marginal-Poisson call
    assert clean_sheet_prob(grid, "home") == pytest.approx(float(grid[:, 0].sum()), abs=1e-12)


def test_rho_inflates_draw_probability_on_the_grid():
    # the DC tau correction leaves both goal marginals invariant; where it bites
    # is the joint -> it moves mass onto the diagonal (draws)
    args = dict(total_goals=2.6)
    indep = team_goals_distribution(0.40, 0.30, 0.30, method="independent", **args)
    dc = team_goals_distribution(0.40, 0.30, 0.30, rho=-0.12, **args)
    assert match_outcome_probs(dc)[1] > match_outcome_probs(indep)[1]


def test_goals_conceded_pmf_normalised():
    grid = team_goals_distribution(0.45, 0.30, 0.25, total_goals=2.6)
    pmf = goals_conceded_pmf(grid, "away")
    assert np.isclose(pmf.sum(), 1.0, atol=1e-6)
    assert expected_goals_conceded(grid, "away") == pytest.approx(pmf @ np.arange(pmf.size))


# --------------------------------------------------------------------------- #
# season_team_priors                                                         #
# --------------------------------------------------------------------------- #
def _toy_matches():
    import pandas as pd

    rows = []
    teams = ["Inter", "Milan", "Roma", "Lecce"]
    base = pd.Timestamp("2022-08-13")
    for i, h in enumerate(teams):
        for j, a in enumerate(teams):
            if i == j:
                continue
            rows.append(
                {
                    "season": "2223",
                    "Date": base + pd.Timedelta(days=7 * (i * 3 + j)),
                    "Time": "18:00",
                    "HomeTeam": h,
                    "AwayTeam": a,
                    "FTHG": 2,
                    "FTAG": 1,
                    "AvgH": 2.1 + 0.2 * i,
                    "AvgD": 3.3,
                    "AvgA": 3.6 - 0.1 * j,
                }
            )
    return pd.DataFrame(rows)


def test_season_team_priors_aggregate_columns():
    out = season_team_priors(_toy_matches())
    assert {"season", "team", "clean_sheet_rate", "expected_goals_conceded",
            "expected_points", "n_matches", "available_time", "source_name",
            "quality_tier"}.issubset(out.columns)
    assert (out["n_matches"] > 0).all()
    assert out["source_name"].eq("football_data_co_uk").all()


def test_season_team_priors_match_granularity_available_time_is_kickoff():
    detail = season_team_priors(_toy_matches(), granularity="match")
    assert (detail["available_time"].dt.hour == 18).all()
    assert len(detail) == 2 * 12  # two team rows per fixture
