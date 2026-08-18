import pandas as pd

from fantacalcio.auction.g3_envelope_feasibility import check_pick_feasibility, summarize_g3_feasibility
from fantacalcio.domain import AssignmentEvent, AssignmentItem, Role, replay
from fantacalcio.persistence.g3_envelopes_store import G3EnvelopePick


def _assign(**kwargs) -> AssignmentEvent:
    defaults = dict(ts="2026-01-01T00:00:00Z", source="test", author="test", corrects=None)
    defaults.update(kwargs)
    return AssignmentEvent(**defaults)


def _pick(team_id="team_01", player_code=1, role="C", bid=10) -> G3EnvelopePick:
    return G3EnvelopePick(team_id=team_id, player_code=player_code, role=role, bid_amount=bid, saved_at="t")


def _player_row(quotazione_asta=10, admin_score=None) -> pd.Series:
    return pd.Series({"quotazione_asta": quotazione_asta, "admin_score": admin_score})


def _through_g2(team_id="team_01") -> list[AssignmentEvent]:
    """Minimal G1+G2 history so remaining_G2 (and thus G3's budget expr) is defined."""
    return [
        _assign(
            event_id="g1seed", round_id="G1", team_id=team_id, pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("g1seed-player",)), amount=1,
        ),
        _assign(
            event_id="g2seed", round_id="G2", team_id=team_id, pool_id="midfielders_top_1_20",
            role=Role.MID, item=AssignmentItem(player_ids=("g2seed-player",)), amount=1,
        ),
    ]


class TestCheckPickFeasibility:
    def test_ok_when_no_conflicts(self, ruleset):
        state = replay(ruleset, _through_g2())
        result = check_pick_feasibility("team_01", 999, "C", 10, _player_row(quotazione_asta=10), ruleset, state, [])
        assert result.ok
        assert result.reason is None

    def test_unknown_role_rejected(self, ruleset):
        state = replay(ruleset, _through_g2())
        result = check_pick_feasibility("team_01", 999, "X", 10, _player_row(), ruleset, state, [])
        assert not result.ok
        assert "sconosciuto" in result.reason

    def test_infeasible_if_assigned_to_own_team(self, ruleset):
        events = _through_g2() + [
            _assign(
                event_id="e1", round_id="G3", team_id="team_01", pool_id="remaining_players",
                role=Role.MID, item=AssignmentItem(player_ids=("999",)), amount=10,
            )
        ]
        state = replay(ruleset, events)
        result = check_pick_feasibility("team_01", 999, "C", 10, _player_row(), ruleset, state, [])
        assert not result.ok
        assert "non serve inserirlo" in result.reason

    def test_infeasible_if_assigned_to_another_team(self, ruleset):
        events = _through_g2(team_id="team_02") + [
            _assign(
                event_id="e1", round_id="G3", team_id="team_02", pool_id="remaining_players",
                role=Role.MID, item=AssignmentItem(player_ids=("999",)), amount=10,
            )
        ]
        state = replay(ruleset, events)
        result = check_pick_feasibility("team_01", 999, "C", 10, _player_row(), ruleset, state, [])
        assert not result.ok
        assert "team_02" in result.reason

    def test_infeasible_if_already_in_envelope(self, ruleset):
        state = replay(ruleset, _through_g2())
        existing = [_pick(player_code=999)]
        result = check_pick_feasibility("team_01", 999, "C", 10, _player_row(), ruleset, state, existing)
        assert not result.ok
        assert "già presente" in result.reason

    def test_infeasible_when_max_players_reached(self, ruleset):
        state = replay(ruleset, _through_g2())
        max_players = ruleset.round_by_id("G3").max_players_this_phase
        existing = [_pick(player_code=i) for i in range(1, max_players + 1)]
        result = check_pick_feasibility("team_01", 999, "C", 10, _player_row(), ruleset, state, existing)
        assert not result.ok
        assert "massimo consentito" in result.reason

    def test_infeasible_below_quotazione_minimum(self, ruleset):
        state = replay(ruleset, _through_g2())
        result = check_pick_feasibility("team_01", 999, "C", 5, _player_row(quotazione_asta=10), ruleset, state, [])
        assert not result.ok
        assert "quotazione" in result.reason

    def test_admin_score_overrides_quotazione_for_minimum(self, ruleset):
        state = replay(ruleset, _through_g2())
        result = check_pick_feasibility(
            "team_01", 999, "C", 12, _player_row(quotazione_asta=10, admin_score=15), ruleset, state, []
        )
        assert not result.ok  # 12 < effective_quotazione (admin_score=15)


class TestSummarizeG3Feasibility:
    def test_worst_case_is_sum_not_max(self, ruleset):
        state = replay(ruleset, _through_g2())
        picks = [_pick(player_code=1, bid=10), _pick(player_code=2, bid=20), _pick(player_code=3, bid=15)]
        report = summarize_g3_feasibility("team_01", ruleset, state, picks)
        assert report.worst_case_total_spend == 45

    def test_margin_ok_when_within_budget(self, ruleset):
        state = replay(ruleset, _through_g2())
        report = summarize_g3_feasibility("team_01", ruleset, state, [_pick(bid=5)])
        assert report.ok
        assert report.margin == report.g3_budget_available - 5

    def test_overspend_detected(self, ruleset):
        state = replay(ruleset, _through_g2())
        huge_bid = ruleset.round_by_id("G3").budget_increment + 500
        report = summarize_g3_feasibility("team_01", ruleset, state, [_pick(bid=huge_bid)])
        assert not report.ok
        assert report.margin < 0

    def test_empty_envelope_zero_spend(self, ruleset):
        state = replay(ruleset, _through_g2())
        report = summarize_g3_feasibility("team_01", ruleset, state, [])
        assert report.worst_case_total_spend == 0
        assert report.ok
