import pytest

from fantacalcio.config import ConfigError
from fantacalcio.domain import (
    AssignmentEvent,
    AssignmentItem,
    BudgetAdjustmentEvent,
    DomainError,
    Role,
    VoidEvent,
    effective_events,
    replay,
    resolve_sealed_bid_round,
)
from fantacalcio.fixtures import generate_demo_events


def _assign(**kwargs) -> AssignmentEvent:
    defaults = dict(ts="2026-01-01T00:00:00Z", source="test", author="test", corrects=None)
    defaults.update(kwargs)
    return AssignmentEvent(**defaults)


def test_replay_is_deterministic(ruleset):
    events = generate_demo_events(ruleset, seed=42)
    state_a = replay(ruleset, events)
    state_b = replay(ruleset, events)

    assert state_a.assigned_players == state_b.assigned_players
    for team_id in state_a.teams:
        a, b = state_a.teams[team_id], state_b.teams[team_id]
        assert a.roster == b.roster
        assert {rid: (bud.available, bud.spent) for rid, bud in a.budgets.items()} == {
            rid: (bud.available, bud.spent) for rid, bud in b.budgets.items()
        }


def test_demo_fixture_replays_without_error(ruleset):
    events = generate_demo_events(ruleset)
    state = replay(ruleset, events)
    assert len(state.teams) == ruleset.teams
    assert len(state.assigned_players) > 0


def test_budget_never_overspent(ruleset):
    events = generate_demo_events(ruleset)
    state = replay(ruleset, events)
    for team in state.teams.values():
        for budget in team.budgets.values():
            assert budget.spent <= budget.available
            assert budget.remaining >= 0


def test_overspend_raises(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-01",)),
            amount=201,  # G1 budget is 200
        )
    ]
    with pytest.raises(DomainError, match="overspend"):
        replay(ruleset, events)


def test_duplicate_player_assignment_raises(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-01",)),
            amount=10,
        ),
        _assign(
            event_id="e2",
            round_id="G1",
            team_id="team-02",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-01",)),
            amount=10,
        ),
    ]
    with pytest.raises(DomainError, match="already assigned"):
        replay(ruleset, events)


def test_out_of_pool_assignment_raises(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="midfielders_top_1_20",  # not eligible in G1
            role=Role.MID,
            item=AssignmentItem(player_ids=("mid-01",)),
            amount=10,
        ),
    ]
    with pytest.raises(DomainError, match="not eligible in round"):
        replay(ruleset, events)


def test_role_pool_mismatch_raises(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="defenders_top_1_60",
            role=Role.MID,  # wrong role for this pool
            item=AssignmentItem(player_ids=("mid-01",)),
            amount=10,
        ),
    ]
    with pytest.raises(DomainError, match="not eligible in pool"):
        replay(ruleset, events)


def test_roster_quota_exceeded_raises(ruleset):
    events = [
        _assign(
            event_id=f"e{i}",
            round_id="G1",
            team_id="team-01",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=(f"def-{i:02d}",)),
            amount=1,
        )
        for i in range(1, ruleset.roster.defenders + 2)  # one over the cap
    ]
    with pytest.raises(DomainError, match="already has"):
        replay(ruleset, events)


def test_goalkeeper_block_oversized_raises(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="goalkeeper_blocks",
            role=Role.GK,
            item=AssignmentItem(player_ids=("gk-01", "gk-02", "gk-03", "gk-04")),  # max 3
            amount=10,
        ),
    ]
    with pytest.raises(DomainError, match="goalkeeper block must have at most"):
        replay(ruleset, events)


def test_goalkeeper_block_undersized_is_allowed(ruleset):
    """A club with fewer than goalkeeper_block_size real goalkeepers on file
    (data gap, e.g. Cagliari/Lecce with only 2) can still form a valid block --
    only an oversized block is a real bug (ADR-2026-055)."""
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="goalkeeper_blocks",
            role=Role.GK,
            item=AssignmentItem(player_ids=("gk-01", "gk-02")),
            amount=10,
        ),
    ]
    state = replay(ruleset, events)
    assert state.teams["team-01"].roster[Role.GK] == ["gk-01", "gk-02"]


def test_goalkeeper_block_empty_raises_at_construction():
    with pytest.raises(DomainError, match="at least one player"):
        AssignmentItem(player_ids=())


def test_second_goalkeeper_block_for_same_team_raises(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="goalkeeper_blocks",
            role=Role.GK,
            item=AssignmentItem(player_ids=("gk-01", "gk-02", "gk-03")),
            amount=10,
        ),
        _assign(
            event_id="e2",
            round_id="G1",
            team_id="team-01",
            pool_id="goalkeeper_blocks",
            role=Role.GK,
            item=AssignmentItem(player_ids=("gk-04", "gk-05", "gk-06")),
            amount=10,
        ),
    ]
    with pytest.raises(DomainError, match="already has a goalkeeper block"):
        replay(ruleset, events)


def test_void_event_marks_original_as_voided(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-01",)),
            amount=10,
        ),
        VoidEvent(event_id="e2", ts="2026-01-01T00:00:00Z", voids="e1", author="admin", reason="mistake"),
    ]
    state = replay(ruleset, events)
    assert "e1" in state.voided_events
    # The roster/budget bookkeeping is intentionally not retroactively reverted by a
    # void in M0: a void records that e1 is no longer valid going forward. Rebuilding
    # a "current" view that excludes voided events is a query-time concern (M3+), not
    # a replay-time mutation, so the roster/budget effects of e1 remain in this state.
    assert "def-01" in state.assigned_players


def test_void_of_unknown_event_raises(ruleset):
    events = [
        VoidEvent(event_id="e1", ts="2026-01-01T00:00:00Z", voids="does-not-exist", author="admin", reason="x"),
    ]
    with pytest.raises(DomainError, match="unknown/unapplied event"):
        replay(ruleset, events)


def test_correction_voids_the_corrected_event(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-01",)),
            amount=10,
        ),
        _assign(
            event_id="e2",
            round_id="G1",
            team_id="team-01",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-02",)),
            amount=15,
            corrects="e1",
        ),
    ]
    state = replay(ruleset, events)
    assert "e1" in state.voided_events
    assert "e2" not in state.voided_events


def test_duplicate_event_id_raises(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-01",)),
            amount=10,
        ),
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-02",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-02",)),
            amount=10,
        ),
    ]
    with pytest.raises(DomainError, match="Duplicate event_id"):
        replay(ruleset, events)


def test_out_of_order_round_raises(ruleset):
    # Advance to G2, then attempt an event back in G1: caught by the explicit
    # round-order check. (Starting directly at G2 without ever playing G1 is instead
    # caught earlier, by the budget-expression dependency check in evaluate_budget_expr
    # — G2's budget references G1's remaining budget, which would not exist yet.)
    events = [
        _assign(
            event_id="e1",
            round_id="G1",
            team_id="team-01",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-01",)),
            amount=10,
        ),
        _assign(
            event_id="e2",
            round_id="G2",
            team_id="team-01",
            pool_id="midfielders_top_1_20",
            role=Role.MID,
            item=AssignmentItem(player_ids=("mid-01",)),
            amount=10,
        ),
        _assign(
            event_id="e3",
            round_id="G1",
            team_id="team-02",
            pool_id="defenders_top_1_60",
            role=Role.DEF,
            item=AssignmentItem(player_ids=("def-02",)),
            amount=10,
        ),
    ]
    with pytest.raises(DomainError, match="round-ordered"):
        replay(ruleset, events)


def test_starting_at_a_dependent_round_raises_config_error(ruleset):
    events = [
        _assign(
            event_id="e1",
            round_id="G2",
            team_id="team-01",
            pool_id="midfielders_top_1_20",
            role=Role.MID,
            item=AssignmentItem(player_ids=("mid-01",)),
            amount=10,
        ),
    ]
    with pytest.raises(ConfigError, match="no recorded remaining budget"):
        replay(ruleset, events)


def test_sealed_bid_resolution_is_explicitly_blocked():
    with pytest.raises(NotImplementedError, match="docs/OPEN_QUESTIONS.md"):
        resolve_sealed_bid_round()


def test_effective_events_excludes_voided_assignment(ruleset):
    events = [
        _assign(
            event_id="e1", round_id="G1", team_id="team-01", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-01",)), amount=10,
        ),
        VoidEvent(event_id="e2", ts="2026-01-01T00:00:00Z", voids="e1", author="admin", reason="mistake"),
    ]
    effective = effective_events(events)
    assert effective == []

    state = replay(ruleset, effective)
    assert "def-01" not in state.assigned_players


def test_effective_events_excludes_corrected_assignment(ruleset):
    events = [
        _assign(
            event_id="e1", round_id="G1", team_id="team-01", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-01",)), amount=10,
        ),
        _assign(
            event_id="e2", round_id="G1", team_id="team-01", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-02",)), amount=15, corrects="e1",
        ),
    ]
    effective = effective_events(events)
    assert [e.event_id for e in effective] == ["e2"]
    assert effective[0].corrects is None  # dangling reference to the excluded e1 cleared

    state = replay(ruleset, effective)
    assert "def-01" not in state.assigned_players
    assert "def-02" in state.assigned_players


def test_effective_events_keeps_untouched_assignments(ruleset):
    events = [
        _assign(
            event_id="e1", round_id="G1", team_id="team-01", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-01",)), amount=10,
        ),
    ]
    assert [e.event_id for e in effective_events(events)] == ["e1"]


def test_round_budget_carryover_is_per_team_not_shared(ruleset):
    # Regression test (found via M4 slice 2 UI testing, 2026-08-11): team-01 spends
    # 190/200 in G1 (remaining 10), team-02 spends 50/200 (remaining 150). team-01's
    # G2 budget_available ("remaining_G1 + 100") must use team-01's OWN remaining
    # (10), never team-02's, regardless of event processing order.
    events = [
        _assign(
            event_id="e1", round_id="G1", team_id="team-01", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-01",)), amount=190,
        ),
        _assign(
            event_id="e2", round_id="G1", team_id="team-02", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-02",)), amount=50,
        ),
        _assign(
            event_id="e3", round_id="G2", team_id="team-01", pool_id="midfielders_top_1_20",
            role=Role.MID, item=AssignmentItem(player_ids=("mid-01",)), amount=1,
        ),
    ]
    state = replay(ruleset, events)
    assert state.team("team-01").budgets["G1"].remaining == 10
    assert state.team("team-02").budgets["G1"].remaining == 150
    assert state.team("team-01").budgets["G2"].available == 110  # 10 + 100, own leftover


def _bonus(**kwargs) -> BudgetAdjustmentEvent:
    defaults = dict(ts="2026-01-01T00:00:00Z", author="admin")
    defaults.update(kwargs)
    return BudgetAdjustmentEvent(**defaults)


def test_budget_adjustment_applied_before_any_assignment(ruleset):
    events = [
        _bonus(event_id="b1", round_id="G1", team_id="team-01", amount=3, reason="custom_logo_bonus"),
        _assign(
            event_id="e1", round_id="G1", team_id="team-01", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-01",)), amount=200,
        ),
    ]
    # G1 base budget is 200; +3 bonus means 203 can be spent without overspending.
    state = replay(ruleset, events)
    assert state.team("team-01").budgets["G1"].available == 203
    assert state.team("team-01").budgets["G1"].spent == 200
    assert state.team("team-01").budgets["G1"].remaining == 3


def test_budget_adjustment_applied_after_an_assignment(ruleset):
    events = [
        _assign(
            event_id="e1", round_id="G1", team_id="team-01", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-01",)), amount=190,
        ),
        _bonus(event_id="b1", round_id="G1", team_id="team-01", amount=3, reason="custom_logo_bonus"),
    ]
    state = replay(ruleset, events)
    assert state.team("team-01").budgets["G1"].available == 203
    assert state.team("team-01").budgets["G1"].remaining == 13


def test_budget_adjustment_propagates_to_next_round_via_remaining_chain(ruleset):
    events = [
        _bonus(event_id="b1", round_id="G1", team_id="team-01", amount=3, reason="custom_logo_bonus"),
        _assign(
            event_id="e1", round_id="G1", team_id="team-01", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-01",)), amount=190,
        ),
        _assign(
            event_id="e2", round_id="G2", team_id="team-01", pool_id="midfielders_top_1_20",
            role=Role.MID, item=AssignmentItem(player_ids=("mid-01",)), amount=1,
        ),
    ]
    state = replay(ruleset, events)
    # G1 remaining = 203 - 190 = 13; G2 available = remaining_G1 + 100 = 113.
    assert state.team("team-01").budgets["G1"].remaining == 13
    assert state.team("team-01").budgets["G2"].available == 113


def test_budget_adjustment_only_affects_its_own_team(ruleset):
    events = [
        _bonus(event_id="b1", round_id="G1", team_id="team-01", amount=3, reason="custom_logo_bonus"),
        _assign(
            event_id="e1", round_id="G1", team_id="team-02", pool_id="defenders_top_1_60",
            role=Role.DEF, item=AssignmentItem(player_ids=("def-01",)), amount=1,
        ),
    ]
    state = replay(ruleset, events)
    assert state.team("team-01").budgets["G1"].available == 203
    assert state.team("team-02").budgets["G1"].available == 200


def test_budget_adjustment_unknown_round_raises(ruleset):
    events = [_bonus(event_id="b1", round_id="G99", team_id="team-01", amount=3, reason="x")]
    with pytest.raises(ConfigError, match="unknown round"):
        replay(ruleset, events)


def test_budget_adjustment_voidable_via_effective_events(ruleset):
    events = [
        _bonus(event_id="b1", round_id="G1", team_id="team-01", amount=3, reason="custom_logo_bonus"),
        VoidEvent(event_id="v1", ts="2026-01-01T00:00:00Z", voids="b1", author="admin", reason="mistake"),
    ]
    effective = effective_events(events)
    assert effective == []
    state = replay(ruleset, effective)
    assert state.team("team-01").budgets == {}


def test_budget_adjustment_survives_effective_events_when_not_voided(ruleset):
    events = [
        _bonus(event_id="b1", round_id="G1", team_id="team-01", amount=3, reason="custom_logo_bonus"),
    ]
    effective = effective_events(events)
    assert [e.event_id for e in effective] == ["b1"]
    state = replay(ruleset, effective)
    assert state.team("team-01").budgets["G1"].available == 203
