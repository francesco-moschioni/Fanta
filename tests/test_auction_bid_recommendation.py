import pandas as pd
import pytest

from fantacalcio.auction.bid_recommendation import (
    BidRecommendationError,
    budget_available_for_round,
    budget_remaining_for_round,
    recommend_max_bid,
    remaining_roster_slots,
)
from fantacalcio.domain import AssignmentEvent, AssignmentItem, Role, replay


def _pool(rows):
    return pd.DataFrame(rows, columns=["player_code", "var_mean"])


class TestBudgetHelpers:
    def test_budget_available_for_started_round(self, ruleset):
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-01",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("def-01",)), amount=10,
                source="test", author="test",
            )
        ]
        state = replay(ruleset, events)
        team = state.team("team-01")
        assert budget_available_for_round(team, "G1", ruleset) == 200
        assert budget_remaining_for_round(team, "G1", ruleset) == 190

    def test_budget_for_not_yet_started_round_evaluates_expression(self, ruleset):
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-01",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("def-01",)), amount=50,
                source="test", author="test",
            )
        ]
        state = replay(ruleset, events)
        team = state.team("team-01")
        # G2 hasn't started for this team: available = remaining_G1 (150) + 100 = 250
        assert budget_available_for_round(team, "G2", ruleset) == 250
        assert budget_remaining_for_round(team, "G2", ruleset) == 250  # nothing spent yet

    def test_remaining_roster_slots_reads_from_config(self, ruleset):
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-01",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("def-01",)), amount=10,
                source="test", author="test",
            )
        ]
        state = replay(ruleset, events)
        team = state.team("team-01")
        slots = remaining_roster_slots(team, ruleset)
        assert slots["D"] == ruleset.roster.defenders - 1
        assert slots["P"] == ruleset.roster.goalkeeper_block_size
        assert slots["C"] == ruleset.roster.midfielders
        assert slots["A"] == ruleset.roster.forwards


class TestRecommendMaxBid:
    def test_higher_var_gets_higher_max_bid(self, ruleset):
        events: list = []
        state = replay(ruleset, events)
        pool = _pool([(1, 5.0), (2, 1.0), (3, 0.5)])
        rec_high = recommend_max_bid(state, ruleset, "team-01", "G1", 1, 5.0, pool)
        rec_low = recommend_max_bid(state, ruleset, "team-01", "G1", 2, 1.0, pool)
        assert rec_high.max_bid > rec_low.max_bid

    def test_max_bid_never_exceeds_remaining_budget(self, ruleset):
        state = replay(ruleset, [])
        pool = _pool([(1, 100.0)])  # absurdly high VAR
        rec = recommend_max_bid(state, ruleset, "team-01", "G1", 1, 100.0, pool)
        assert rec.max_bid <= rec.remaining_budget

    def test_reserve_scales_with_remaining_slots(self, ruleset):
        state = replay(ruleset, [])
        pool = _pool([(1, 5.0), (2, 5.0)])
        rec = recommend_max_bid(state, ruleset, "team-01", "G1", 1, 5.0, pool)
        slots = remaining_roster_slots(state.team("team-01"), ruleset)
        assert rec.reserve_for_other_slots == sum(slots.values()) - 1

    def test_player_not_in_pool_raises(self, ruleset):
        state = replay(ruleset, [])
        pool = _pool([(2, 5.0)])
        with pytest.raises(BidRecommendationError, match="not in the undrafted pool"):
            recommend_max_bid(state, ruleset, "team-01", "G1", 999, 5.0, pool)

    def test_assigned_players_excluded_from_pool(self, ruleset):
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-02",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("1",)), amount=10,
                source="test", author="test",
            )
        ]
        state = replay(ruleset, events)
        pool = _pool([(1, 5.0), (2, 3.0)])
        with pytest.raises(BidRecommendationError, match="not in the undrafted pool"):
            recommend_max_bid(state, ruleset, "team-01", "G1", 1, 5.0, pool)

    def test_zero_pool_var_splits_evenly(self, ruleset):
        state = replay(ruleset, [])
        pool = _pool([(1, -1.0), (2, -2.0)])  # both below replacement
        rec = recommend_max_bid(state, ruleset, "team-01", "G1", 1, -1.0, pool)
        assert rec.var_share == 0.5

    def test_full_roster_raises(self, ruleset, monkeypatch):
        import fantacalcio.auction.bid_recommendation as mod

        monkeypatch.setattr(mod, "remaining_roster_slots", lambda team, rs: {"P": 0, "D": 0, "C": 0, "A": 0})
        state = replay(ruleset, [])
        pool = _pool([(1, 5.0)])
        with pytest.raises(BidRecommendationError, match="already full"):
            recommend_max_bid(state, ruleset, "team-01", "G1", 1, 5.0, pool)
