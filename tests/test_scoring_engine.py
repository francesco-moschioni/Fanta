import pytest

from fantacalcio.scoring.engine import (
    PlayerMatchdayEvents,
    ScoringComponentBlocked,
    captain_bonus,
    defense_modifier,
    equalizing_or_winning_goal_bonus,
    fair_play_bonus,
    penalty_saved_points,
    penalty_won_points,
    performance_bonus,
    score_fantavoto,
    score_player_matchday,
    under_11_relief,
)


def _events(**overrides) -> PlayerMatchdayEvents:
    defaults = dict(role="C", played=True)
    defaults.update(overrides)
    return PlayerMatchdayEvents(**defaults)


class TestScorePlayerMatchday:
    def test_not_played_scores_zero(self):
        breakdown = score_player_matchday(_events(played=False, goals_scored=2))
        assert breakdown.total == 0.0

    def test_goal_worth_three_points(self):
        breakdown = score_player_matchday(_events(goals_scored=2))
        assert breakdown.goal_points == 6.0

    def test_assist_worth_one_point(self):
        breakdown = score_player_matchday(_events(assists=3))
        assert breakdown.assist_points == 3.0

    def test_goal_conceded_worth_minus_one_for_goalkeeper_individual_data(self):
        breakdown = score_player_matchday(_events(role="P", goals_conceded=2))
        assert breakdown.goal_conceded_points == -2.0

    def test_defender_gets_no_goal_conceded_malus_ever(self):
        # Empirically tested (2026-08-11, see engine.py docstring "Tested-and-
        # reverted"): giving defenders an individual goal-conceded malus/clean-
        # sheet bonus, even from a real team-result join, made agreement with
        # Fantacalcio.it's real Fm much worse. This component is goalkeeper-only.
        breakdown = score_player_matchday(_events(role="D", goals_conceded=2, team_goals_conceded=2))
        assert breakdown.goal_conceded_points == 0.0
        assert breakdown.clean_sheet_points == 0.0

    def test_defender_gets_no_clean_sheet_even_with_team_data(self):
        breakdown = score_player_matchday(_events(role="D", team_goals_conceded=0))
        assert breakdown.clean_sheet_points == 0.0
        assert breakdown.goal_conceded_points == 0.0

    def test_clean_sheet_for_goalkeeper(self):
        breakdown = score_player_matchday(_events(role="P", goals_conceded=0))
        assert breakdown.clean_sheet_points == 1.0

    def test_no_clean_sheet_bonus_for_midfielder_or_forward(self):
        for role in ("C", "A"):
            breakdown = score_player_matchday(_events(role=role, goals_conceded=0, team_goals_conceded=0))
            assert breakdown.clean_sheet_points == 0.0

    def test_no_clean_sheet_for_goalkeeper_if_conceded(self):
        breakdown = score_player_matchday(_events(role="P", goals_conceded=1))
        assert breakdown.clean_sheet_points == 0.0

    def test_team_data_overrides_unreliable_individual_field_for_goalkeeper(self):
        # Team data disagrees with the (normally reliable) individual field for P;
        # team data should win since it's a real match-result join.
        breakdown = score_player_matchday(_events(role="P", goals_conceded=0, team_goals_conceded=1))
        assert breakdown.clean_sheet_points == 0.0
        assert breakdown.goal_conceded_points == -1.0

    def test_goalkeeper_team_data_takes_priority_over_individual_field(self):
        breakdown = score_player_matchday(_events(role="P", goals_conceded=3, team_goals_conceded=0))
        assert breakdown.clean_sheet_points == 1.0
        assert breakdown.goal_conceded_points == 0.0

    def test_own_goal_worth_minus_two(self):
        breakdown = score_player_matchday(_events(own_goals=1))
        assert breakdown.own_goal_points == -2.0

    def test_yellow_card_worth_minus_half(self):
        breakdown = score_player_matchday(_events(yellow_cards=1))
        assert breakdown.card_points == -0.5

    def test_red_card_worth_minus_one(self):
        breakdown = score_player_matchday(_events(red_cards=1))
        assert breakdown.card_points == -1.0

    def test_yellow_and_red_combine(self):
        breakdown = score_player_matchday(_events(yellow_cards=1, red_cards=1))
        assert breakdown.card_points == -1.5

    def test_penalty_missed_worth_minus_three(self):
        breakdown = score_player_matchday(_events(penalties_missed=1))
        assert breakdown.penalty_missed_points == -3.0

    def test_full_matchday_totals_correctly(self):
        events = _events(
            role="D", goals_scored=1, assists=1, goals_conceded=0, own_goals=0,
            yellow_cards=1, red_cards=0, penalties_missed=0,
        )
        breakdown = score_player_matchday(events)
        # +3 goal +1 assist -0.5 yellow = 3.5 (no clean sheet: defenders excluded, see engine.py)
        assert breakdown.total == 3.5

    def test_full_matchday_totals_correctly_for_goalkeeper_clean_sheet(self):
        events = _events(role="P", goals_conceded=0, yellow_cards=1)
        breakdown = score_player_matchday(events)
        # +1 clean sheet -0.5 yellow = 0.5
        assert breakdown.total == 0.5


class TestScoreFantavoto:
    def test_adds_base_voto_to_bonus_malus(self):
        events = _events(goals_scored=1)  # +3
        assert score_fantavoto(6.0, events) == 9.0

    def test_not_played_returns_base_voto_unchanged(self):
        events = _events(played=False, goals_scored=5)
        assert score_fantavoto(6.0, events) == 6.0


class TestBlockedComponents:
    @pytest.mark.parametrize(
        "fn",
        [
            penalty_saved_points,
            penalty_won_points,
            equalizing_or_winning_goal_bonus,
            captain_bonus,
            fair_play_bonus,
            defense_modifier,
            performance_bonus,
            under_11_relief,
        ],
    )
    def test_raises_scoring_component_blocked(self, fn):
        with pytest.raises(ScoringComponentBlocked):
            fn()
