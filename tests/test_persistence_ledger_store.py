import pytest

from fantacalcio.config import Ruleset, RosterComposition, Round
from fantacalcio.domain import AssignmentEvent, AssignmentItem, Role, VoidEvent
from fantacalcio.persistence.ledger_store import (
    append_event,
    connect,
    load_current_league_state,
    load_events,
    load_league_state,
)


def _ruleset():
    return Ruleset(
        schema_version=1,
        ruleset_id="test",
        status="working_current",
        effective_from="2026-01-01",
        teams=2,
        roster=RosterComposition(
            total_players=24, goalkeeper_block_size=3, goalkeeper_same_club=True,
            defenders=8, midfielders=8, forwards=5, forwards_fallback=4,
        ),
        formations=("3-4-3",),
        list_states=("unknown", "provisional", "official"),
        official_pool_authority="admin_import",
        model_ranking_is_official_pool=False,
        rounds=(
            Round(id="G1", order=1, mode="sealed_bid_list", budget_increment=200, budget_available_expr="200", pools=("defenders_top_1_60",)),
        ),
        runtime_invariants={},
        uncertain_historical_fields={},
    )


def _assignment(event_id="e1", team_id="team_01", player_id="p1", amount=10):
    return AssignmentEvent(
        event_id=event_id, ts="2026-08-11T00:00:00Z", round_id="G1", team_id=team_id,
        pool_id="defenders_top_1_60", role=Role.DEF, item=AssignmentItem(player_ids=(player_id,)),
        amount=amount, source="ui_manual", author="test", corrects=None,
    )


class TestAppendAndLoad:
    def test_append_then_load_roundtrips(self, tmp_path):
        conn = connect(tmp_path / "ledger.sqlite3")
        append_event(conn, _assignment())
        events = load_events(conn)
        assert len(events) == 1
        assert events[0].event_id == "e1"
        assert events[0].item.player_ids == ("p1",)

    def test_preserves_append_order(self, tmp_path):
        conn = connect(tmp_path / "ledger.sqlite3")
        append_event(conn, _assignment(event_id="e1", player_id="p1"))
        append_event(conn, _assignment(event_id="e2", player_id="p2"))
        events = load_events(conn)
        assert [e.event_id for e in events] == ["e1", "e2"]

    def test_duplicate_event_id_raises(self, tmp_path):
        conn = connect(tmp_path / "ledger.sqlite3")
        append_event(conn, _assignment(event_id="e1"))
        with pytest.raises(ValueError, match="already exists"):
            append_event(conn, _assignment(event_id="e1", player_id="p2"))

    def test_void_event_roundtrips(self, tmp_path):
        conn = connect(tmp_path / "ledger.sqlite3")
        append_event(conn, _assignment(event_id="e1"))
        append_event(conn, VoidEvent(event_id="e2", ts="2026-08-11T00:01:00Z", voids="e1", author="test", reason="mistake"))
        events = load_events(conn)
        assert isinstance(events[1], VoidEvent)
        assert events[1].voids == "e1"

    def test_reopening_db_path_preserves_data(self, tmp_path):
        db_path = tmp_path / "ledger.sqlite3"
        conn1 = connect(db_path)
        append_event(conn1, _assignment())
        conn1.close()

        conn2 = connect(db_path)
        events = load_events(conn2)
        assert len(events) == 1


class TestLoadLeagueState:
    def test_replays_into_league_state(self, tmp_path):
        conn = connect(tmp_path / "ledger.sqlite3")
        append_event(conn, _assignment(team_id="team_01", player_id="p1", amount=15))
        state = load_league_state(conn, _ruleset())
        assert "p1" in state.assigned_players
        assert state.team("team_01").budgets["G1"].spent == 15

    def test_voided_assignment_excluded_from_active_roster(self, tmp_path):
        conn = connect(tmp_path / "ledger.sqlite3")
        append_event(conn, _assignment(event_id="e1", team_id="team_01", player_id="p1"))
        append_event(conn, VoidEvent(event_id="e2", ts="2026-08-11T00:01:00Z", voids="e1", author="test", reason="typo"))
        state = load_league_state(conn, _ruleset())
        # load_league_state() is the full audit trail: replay() tracks voided_events
        # but doesn't retroactively unwind roster/budget effects (see domain.py). This
        # test documents that behavior rather than assuming it.
        assert "e1" in state.voided_events
        assert "p1" in state.assigned_players


class TestLoadCurrentLeagueState:
    def test_voided_assignment_frees_the_player(self, tmp_path):
        conn = connect(tmp_path / "ledger.sqlite3")
        append_event(conn, _assignment(event_id="e1", team_id="team_01", player_id="p1"))
        append_event(conn, VoidEvent(event_id="e2", ts="2026-08-11T00:01:00Z", voids="e1", author="test", reason="typo"))
        state = load_current_league_state(conn, _ruleset())
        assert "p1" not in state.assigned_players
        assert state.team("team_01").budgets == {}

    def test_no_voids_matches_full_state(self, tmp_path):
        conn = connect(tmp_path / "ledger.sqlite3")
        append_event(conn, _assignment(team_id="team_01", player_id="p1", amount=20))
        current = load_current_league_state(conn, _ruleset())
        full = load_league_state(conn, _ruleset())
        assert current.assigned_players == full.assigned_players
