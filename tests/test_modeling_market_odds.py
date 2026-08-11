import pandas as pd
import pytest

from fantacalcio.modeling.market_odds import (
    implied_probabilities,
    match_expected_points,
    team_market_rating,
)


class TestImpliedProbabilities:
    def test_sums_to_one_after_devig(self):
        p_h, p_d, p_a = implied_probabilities(2.0, 3.5, 4.0)
        assert p_h + p_d + p_a == pytest.approx(1.0)

    def test_favourite_gets_higher_probability(self):
        p_h, p_d, p_a = implied_probabilities(1.5, 4.0, 6.0)
        assert p_h > p_d > p_a

    def test_symmetric_odds_give_near_equal_home_away_probability(self):
        p_h, p_d, p_a = implied_probabilities(3.0, 3.0, 3.0)
        assert p_h == pytest.approx(p_a)


class TestMatchExpectedPoints:
    def test_expected_points_sum_close_to_three(self):
        # Not exactly 3.0 unless draw prob is symmetric in its point split, but
        # close for reasonable odds -- this checks the formula is sane, not exact.
        home_pts, away_pts = match_expected_points(2.0, 3.5, 4.0)
        p_h, p_d, p_a = implied_probabilities(2.0, 3.5, 4.0)
        assert home_pts == pytest.approx(3.0 * p_h + p_d)
        assert away_pts == pytest.approx(3.0 * p_a + p_d)

    def test_heavy_favourite_gets_more_expected_points(self):
        home_pts, away_pts = match_expected_points(1.2, 6.0, 12.0)
        assert home_pts > away_pts


class TestTeamMarketRating:
    def test_averages_across_home_and_away_matches(self):
        # Inter is the market favourite in both fixtures: once at home (short
        # AvgH), once away (short AvgA) -- Milan is the underdog both times.
        matches = pd.DataFrame(
            {
                "HomeTeam": ["Inter", "Milan"],
                "AwayTeam": ["Milan", "Inter"],
                "AvgH": [2.0, 4.0],
                "AvgD": [3.5, 3.5],
                "AvgA": [4.0, 2.0],
            }
        )
        rating = team_market_rating(matches)
        assert set(rating.index) == {"Inter", "Milan"}
        assert rating.loc["Inter"] > rating.loc["Milan"]
