import pandas as pd

from fantacalcio.auction.g2_envelope_feasibility import (
    check_pick_feasibility,
    project_downstream_budget,
    summarize_g2_feasibility,
)
from fantacalcio.domain import AssignmentEvent, AssignmentItem, Role, replay
from fantacalcio.persistence.g2_envelopes_store import EnvelopePick


def _assign(**kwargs) -> AssignmentEvent:
    defaults = dict(ts="2026-01-01T00:00:00Z", source="test", author="test", corrects=None)
    defaults.update(kwargs)
    return AssignmentEvent(**defaults)


def _pick(team_id="team_01", band="midfielders_top_1_20", player_code=1, role="C", rank=1, bid=10) -> EnvelopePick:
    return EnvelopePick(
        team_id=team_id, list_pool_name=band, player_code=player_code, role=role,
        preference_rank=rank, bid_amount=bid, saved_at="t",
    )


def _g1_started(team_id="team_01", spent=0) -> list[AssignmentEvent]:
    """A minimal G1 event so `remaining_G1` is defined for the G2 budget
    expression -- mirrors the real ledger, where G1 always finishes before G2."""
    if spent == 0:
        return []
    return [
        _assign(
            event_id="g1seed", round_id="G1", team_id=team_id, pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("g1seed-player",)), amount=spent,
        )
    ]


class TestCheckPickFeasibility:
    def test_ok_when_no_conflicts(self, ruleset):
        state = replay(ruleset, [])
        result = check_pick_feasibility("team_01", "midfielders_top_1_20", 999, 5.0, ruleset, state, [])
        assert result.ok
        assert result.reason is None

    def test_invalid_band_name(self, ruleset):
        state = replay(ruleset, [])
        result = check_pick_feasibility("team_01", "not_a_band", 999, 5.0, ruleset, state, [])
        assert not result.ok
        assert "non è una fascia" in result.reason

    def test_infeasible_if_assigned_to_own_team(self, ruleset):
        events = _g1_started(spent=1) + [
            _assign(
                event_id="e1", round_id="G2", team_id="team_01", pool_id="midfielders_top_1_20",
                role=Role.MID, item=AssignmentItem(player_ids=("999",)), amount=10,
            )
        ]
        state = replay(ruleset, events)
        result = check_pick_feasibility("team_01", "midfielders_top_1_20", 999, 5.0, ruleset, state, [])
        assert not result.ok
        assert "non serve inserirlo" in result.reason

    def test_infeasible_if_assigned_to_another_team(self, ruleset):
        events = _g1_started(team_id="team_02", spent=1) + [
            _assign(
                event_id="e1", round_id="G2", team_id="team_02", pool_id="midfielders_top_1_20",
                role=Role.MID, item=AssignmentItem(player_ids=("999",)), amount=10,
            )
        ]
        state = replay(ruleset, events)
        result = check_pick_feasibility("team_01", "midfielders_top_1_20", 999, 5.0, ruleset, state, [])
        assert not result.ok
        assert "team_02" in result.reason

    def test_infeasible_if_already_in_any_band_envelope(self, ruleset):
        state = replay(ruleset, [])
        existing = [_pick(band="forwards_top_1_20", player_code=999, role="A")]
        result = check_pick_feasibility("team_01", "midfielders_top_1_20", 999, 5.0, ruleset, state, existing)
        assert not result.ok
        assert "già presente" in result.reason

    def test_infeasible_when_band_already_has_6_preferences(self, ruleset):
        state = replay(ruleset, [])
        existing = [_pick(player_code=i, rank=i) for i in range(1, 7)]
        result = check_pick_feasibility("team_01", "midfielders_top_1_20", 999, 5.0, ruleset, state, existing)
        assert not result.ok
        assert "già 6 preferenze" in result.reason

    def test_infeasible_when_admin_rank_unknown(self, ruleset):
        state = replay(ruleset, [])
        result = check_pick_feasibility("team_01", "midfielders_top_1_20", 999, None, ruleset, state, [])
        assert not result.ok
        assert "admin_rank noto" in result.reason


class TestSummarizeG2Feasibility:
    def test_budget_available_is_remaining_g1_plus_100(self, ruleset):
        events = [
            _assign(
                event_id="e1", round_id="G1", team_id="team_01", pool_id="defenders_top_1_60",
                role=Role.DEF, item=AssignmentItem(player_ids=("1",)), amount=50,
            )
        ]
        state = replay(ruleset, events)
        report = summarize_g2_feasibility("team_01", ruleset, state, [])
        assert report.g2_budget_available == (200 - 50) + 100

    def test_worst_case_spend_is_max_bid_per_band_not_sum(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        picks = [
            _pick(band="midfielders_top_1_20", player_code=1, rank=1, bid=30),
            _pick(band="midfielders_top_1_20", player_code=2, rank=2, bid=50),
            _pick(band="forwards_top_1_20", player_code=3, role="A", rank=1, bid=20),
        ]
        report = summarize_g2_feasibility("team_01", ruleset, state, picks)
        assert report.worst_case_total_spend == 50 + 20

    def test_ok_true_when_within_budget(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        picks = [_pick(band="midfielders_top_1_20", player_code=1, rank=1, bid=10)]
        report = summarize_g2_feasibility("team_01", ruleset, state, picks)
        assert report.ok
        assert report.margin >= 0

    def test_ok_false_when_overspending(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        picks = [
            _pick(band="midfielders_top_1_20", player_code=1, rank=1, bid=999),
            _pick(band="midfielders_top_21_40", player_code=2, rank=1, bid=999),
            _pick(band="midfielders_top_41_60", player_code=3, rank=1, bid=999),
            _pick(band="forwards_top_1_20", player_code=4, role="A", rank=1, bid=999),
            _pick(band="forwards_top_21_40", player_code=5, role="A", rank=1, bid=999),
        ]
        report = summarize_g2_feasibility("team_01", ruleset, state, picks)
        assert not report.ok
        assert report.margin < 0

    def test_slots_not_covered_by_g2_reported(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        report = summarize_g2_feasibility("team_01", ruleset, state, [])
        assert report.slots_not_covered_by_g2["C"] == ruleset.roster.midfielders - 3
        assert report.slots_not_covered_by_g2["A"] == ruleset.roster.forwards - 2

    def test_first_choice_spend_uses_rank_1_pick_not_max_bid(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        picks = [
            _pick(band="midfielders_top_1_20", player_code=1, rank=1, bid=15),
            _pick(band="midfielders_top_1_20", player_code=2, rank=2, bid=50),  # higher bid, lower preference
        ]
        report = summarize_g2_feasibility("team_01", ruleset, state, picks)
        assert report.first_choice_total_spend == 15
        assert report.worst_case_total_spend == 50


class TestProjectDownstreamBudget:
    def _pool(self, n, cheapest_price=1):
        return pd.DataFrame({
            "player_code": range(1000, 1000 + n),
            "quotazione_asta": [cheapest_price + i for i in range(n)],
        })

    def test_g3_g4_budget_is_g2_remaining_plus_g3_increment(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        pool = self._pool(50)
        projection = project_downstream_budget("team_01", ruleset, state, "test", 20, [], pool)
        g2_available = 200 - 1 + 100  # G1 available(200) - spent(1) + 100
        expected_remaining = g2_available - 20
        assert projection.g2_remaining == expected_remaining
        assert projection.g3_g4_budget == expected_remaining + ruleset.round_by_id("G3").budget_increment

    def test_min_required_uses_cheapest_undrafted_quotazioni(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        pool = self._pool(50, cheapest_price=2)  # prices 2,3,4,5,...
        projection = project_downstream_budget("team_01", ruleset, state, "test", 0, [], pool)
        cheapest_n = sorted(pool["quotazione_asta"])[: projection.slots_still_needed]
        assert projection.min_required_credits == sum(cheapest_n)

    def test_won_players_excluded_from_pool_and_from_slots_still_needed(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        pool = self._pool(50, cheapest_price=1)
        without_scenario = project_downstream_budget("team_01", ruleset, state, "test", 0, [], pool)
        with_scenario = project_downstream_budget("team_01", ruleset, state, "test", 30, [1000, 1001], pool)
        assert with_scenario.slots_still_needed == without_scenario.slots_still_needed - 2

    def test_ok_false_when_budget_cannot_cover_minimums(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        pool = self._pool(50, cheapest_price=1000)  # absurdly expensive, forces shortfall
        projection = project_downstream_budget("team_01", ruleset, state, "test", 0, [], pool)
        assert not projection.ok
        assert projection.shortfall < 0

    def test_ok_true_with_plenty_of_cheap_players(self, ruleset):
        state = replay(ruleset, _g1_started(spent=1))
        pool = self._pool(50, cheapest_price=1)
        projection = project_downstream_budget("team_01", ruleset, state, "test", 0, [], pool)
        assert projection.ok
        assert projection.shortfall >= 0
