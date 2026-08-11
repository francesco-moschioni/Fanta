import numpy as np
import pandas as pd

from fantacalcio.scoring.monte_carlo import SimulationResult
from fantacalcio.scoring.team_strength_adjustment import (
    ATTACK_ROLES,
    DEFENSE_ROLES,
    TeamRatings,
    apply_adjustment,
    compute_adjustments,
    historical_avg_team_rating,
)


class TestHistoricalAvgTeamRating:
    def test_averages_across_players_history(self):
        df = pd.DataFrame(
            {
                "player_code": [1, 1, 2],
                "team_name": ["Weak", "Strong", "Weak"],
            }
        )
        ratings = TeamRatings(attack={"Weak": -1.0, "Strong": 1.0}, defense={})
        result = historical_avg_team_rating(df, ratings, "attack")
        assert result.loc[1] == 0.0  # average of -1.0 and 1.0
        assert result.loc[2] == -1.0

    def test_unknown_team_defaults_to_zero(self):
        df = pd.DataFrame({"player_code": [1], "team_name": ["Unknown"]})
        ratings = TeamRatings(attack={"Known": 1.0}, defense={})
        result = historical_avg_team_rating(df, ratings, "attack")
        assert result.loc[1] == 0.0


class TestComputeAdjustments:
    def test_attacker_moving_to_stronger_attack_gets_positive_adjustment(self):
        ratings = TeamRatings(attack={"Strong": 1.0}, defense={})
        current_team = pd.Series({1: "Strong"})
        role = pd.Series({1: "A"})
        hist_attack = pd.Series({1: 0.0})  # was at a league-average team
        hist_defense = pd.Series({1: 0.0})
        adj = compute_adjustments(current_team, role, hist_attack, hist_defense, ratings, k=0.5)
        assert adj.loc[1] == 0.5  # 0.5 * (1.0 - 0.0)

    def test_defender_moving_to_stronger_defense_gets_positive_adjustment(self):
        # Lower defense param = stronger defense (see module docstring sign convention).
        ratings = TeamRatings(attack={}, defense={"Strong": -1.0})
        current_team = pd.Series({1: "Strong"})
        role = pd.Series({1: "D"})
        hist_attack = pd.Series({1: 0.0})
        hist_defense = pd.Series({1: 0.0})
        adj = compute_adjustments(current_team, role, hist_attack, hist_defense, ratings, k=0.5)
        assert adj.loc[1] == 0.5  # 0.5 * (0.0 - (-1.0))

    def test_goalkeeper_gets_no_adjustment(self):
        ratings = TeamRatings(attack={"X": 5.0}, defense={"X": -5.0})
        current_team = pd.Series({1: "X"})
        role = pd.Series({1: "P"})
        hist_attack = pd.Series({1: 0.0})
        hist_defense = pd.Series({1: 0.0})
        adj = compute_adjustments(current_team, role, hist_attack, hist_defense, ratings, k=0.5)
        assert adj.loc[1] == 0.0

    def test_player_with_no_history_gets_no_adjustment(self):
        ratings = TeamRatings(attack={"X": 5.0}, defense={})
        current_team = pd.Series({1: "X"})
        role = pd.Series({1: "A"})
        adj = compute_adjustments(current_team, role, pd.Series(dtype=float), pd.Series(dtype=float), ratings, k=0.5)
        assert adj.loc[1] == 0.0

    def test_role_sets_are_disjoint_and_cover_expected_roles(self):
        assert ATTACK_ROLES == {"A", "C"}
        assert DEFENSE_ROLES == {"D"}
        assert ATTACK_ROLES.isdisjoint(DEFENSE_ROLES)


class TestApplyAdjustment:
    def test_adds_adjustment_to_all_samples(self):
        result = SimulationResult(
            player_code=1, role="A", n_sims=3, player_games_in_pool=10,
            used_role_pool_only=False, samples=np.array([6.0, 7.0, 5.0]),
        )
        adjusted = apply_adjustment(result, 0.5)
        np.testing.assert_array_equal(adjusted.samples, np.array([6.5, 7.5, 5.5]))
        assert adjusted.player_code == result.player_code
        assert adjusted.role == result.role
