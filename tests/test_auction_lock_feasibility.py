from fantacalcio.auction.lock_feasibility import check_lock_feasibility
from fantacalcio.domain import AssignmentEvent, AssignmentItem, Role, replay
from fantacalcio.persistence.locks_store import LockedPlayer


def _assign(**kwargs) -> AssignmentEvent:
    defaults = dict(ts="2026-01-01T00:00:00Z", source="test", author="test", corrects=None)
    defaults.update(kwargs)
    return AssignmentEvent(**defaults)


def _lock(team_id="team_01", player_code=1, role="D", note="") -> LockedPlayer:
    return LockedPlayer(team_id=team_id, player_code=player_code, role=role, note=note, locked_at="t")


class TestCheckLockFeasibility:
    def test_ok_when_no_conflicts(self, ruleset):
        state = replay(ruleset, [])
        result = check_lock_feasibility("team_01", 999, "D", ruleset, state, [])
        assert result.ok
        assert result.reason is None

    def test_infeasible_if_already_in_own_roster(self, ruleset):
        events = [
            _assign(
                event_id="e1", round_id="G1", team_id="team_01", pool_id="defenders_top_1_60",
                role=Role.DEF, item=AssignmentItem(player_ids=("999",)), amount=10,
            )
        ]
        state = replay(ruleset, events)
        result = check_lock_feasibility("team_01", 999, "D", ruleset, state, [])
        assert not result.ok
        assert "già nella rosa reale" in result.reason

    def test_infeasible_if_assigned_to_another_team(self, ruleset):
        events = [
            _assign(
                event_id="e1", round_id="G1", team_id="team_02", pool_id="defenders_top_1_60",
                role=Role.DEF, item=AssignmentItem(player_ids=("999",)), amount=10,
            )
        ]
        state = replay(ruleset, events)
        result = check_lock_feasibility("team_01", 999, "D", ruleset, state, [])
        assert not result.ok
        assert "team_02" in result.reason

    def test_infeasible_if_already_locked(self, ruleset):
        state = replay(ruleset, [])
        existing = [_lock(player_code=999, role="D")]
        result = check_lock_feasibility("team_01", 999, "D", ruleset, state, existing)
        assert not result.ok
        assert "già bloccato" in result.reason

    def test_infeasible_when_role_capacity_exceeded_by_locks_alone(self, ruleset):
        state = replay(ruleset, [])
        existing = [_lock(player_code=i, role="D") for i in range(1, ruleset.roster.defenders + 1)]
        result = check_lock_feasibility("team_01", 999, "D", ruleset, state, existing)
        assert not result.ok
        assert "Capacità di ruolo" in result.reason
        assert "rimuovi uno dei" in result.reason

    def test_infeasible_when_role_capacity_exceeded_by_real_roster_alone(self, ruleset):
        events = [
            _assign(
                event_id=f"e{i}", round_id="G1", team_id="team_01", pool_id="defenders_top_1_60",
                role=Role.DEF, item=AssignmentItem(player_ids=(f"real-{i}",)), amount=1,
            )
            for i in range(1, ruleset.roster.defenders + 1)
        ]
        state = replay(ruleset, events)
        result = check_lock_feasibility("team_01", 999, "D", ruleset, state, [])
        assert not result.ok
        assert "nessun lock possibile" in result.reason

    def test_ok_when_real_plus_locks_under_capacity(self, ruleset):
        events = [
            _assign(
                event_id="e1", round_id="G1", team_id="team_01", pool_id="defenders_top_1_60",
                role=Role.DEF, item=AssignmentItem(player_ids=("real-1",)), amount=1,
            )
        ]
        state = replay(ruleset, events)
        existing = [_lock(player_code=1, role="D")]
        result = check_lock_feasibility("team_01", 999, "D", ruleset, state, existing)
        assert result.ok

    def test_capacity_check_is_role_specific(self, ruleset):
        # Defenders at cap shouldn't block a forward lock.
        events = [
            _assign(
                event_id=f"e{i}", round_id="G1", team_id="team_01", pool_id="defenders_top_1_60",
                role=Role.DEF, item=AssignmentItem(player_ids=(f"real-{i}",)), amount=1,
            )
            for i in range(1, ruleset.roster.defenders + 1)
        ]
        state = replay(ruleset, events)
        result = check_lock_feasibility("team_01", 999, "A", ruleset, state, [])
        assert result.ok
