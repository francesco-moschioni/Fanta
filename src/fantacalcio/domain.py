"""Canonical domain types and the deterministic auction-ledger replay engine.

Scope note (M0, see docs/CURRENT_TASK.md): this module records and validates
assignment *outcomes* (who won what, for how much, in which round) and their
invariants. It does not implement sealed-bid preference resolution or live-auction
turn mechanics — those branches are explicitly blocked, see `resolve_sealed_bid_round`
below and docs/OPEN_QUESTIONS.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Union

from .config import ConfigError, Ruleset, evaluate_budget_expr


class DomainError(ValueError):
    """Raised when an event or event sequence would violate a domain invariant."""


class Role(str, Enum):
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    FWD = "FWD"


# Pools whose eligible role is unambiguous from the ruleset itself (rounds G1/G2).
# Open-auction pools (e.g. "remaining_players") intentionally have no entry here:
# any role is eligible there, per config/auction_rules.v1.yaml.
_KNOWN_POOL_ROLES: dict[str, frozenset[Role]] = {
    "goalkeeper_blocks": frozenset({Role.GK}),
    "defenders_top_1_60": frozenset({Role.DEF}),
    "midfielders_top_1_60": frozenset({Role.MID}),
    "forwards_top_1_40": frozenset({Role.FWD}),
}


@dataclass(frozen=True)
class AssignmentItem:
    """One purchase: a single player, or a goalkeeper block (multiple players)."""

    player_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.player_ids:
            raise DomainError("AssignmentItem must reference at least one player")
        if len(set(self.player_ids)) != len(self.player_ids):
            raise DomainError(f"AssignmentItem references a player more than once: {self.player_ids}")


@dataclass(frozen=True)
class AssignmentEvent:
    """A recorded auction outcome: team X won item Y in round Z for amount W."""

    event_id: str
    ts: str
    round_id: str
    team_id: str
    pool_id: str
    role: Role
    item: AssignmentItem
    amount: int
    source: str
    author: str
    corrects: str | None = None  # event_id this one supersedes, if any


@dataclass(frozen=True)
class VoidEvent:
    """An explicit undo: voids a previously applied event without erasing it."""

    event_id: str
    ts: str
    voids: str
    author: str
    reason: str


@dataclass(frozen=True)
class BudgetAdjustmentEvent:
    """A per-team, per-round budget adjustment not tied to a player purchase --
    e.g. the +3-credit custom-logo bonus (config `league.custom_logo_bonus_credits`,
    admin postilla 2026-08-11). Generic on purpose: any future admin-granted
    bonus/penalty with a free-text `reason` uses this same mechanism, not a new
    event type per rule. `amount` may be negative (a penalty), though none is
    known/requested as of this event's introduction.

    Applied once, normally to the first round (G1): later rounds whose budget
    expression references an earlier round's `remaining_*` (e.g. G2 =
    "remaining_G1 + 100") pick up the adjustment automatically through that
    chain -- no special-casing needed in `replay()` beyond G1 itself."""

    event_id: str
    ts: str
    round_id: str
    team_id: str
    amount: int
    reason: str
    author: str


Event = Union[AssignmentEvent, VoidEvent, BudgetAdjustmentEvent]


@dataclass
class TeamRoundBudget:
    available: int = 0
    spent: int = 0

    @property
    def remaining(self) -> int:
        return self.available - self.spent


@dataclass
class TeamState:
    team_id: str
    budgets: dict[str, TeamRoundBudget] = field(default_factory=dict)
    roster: dict[Role, list[str]] = field(default_factory=lambda: {r: [] for r in Role})
    gk_block_identity: str | None = None  # placeholder until real club identity lands (M1)

    def role_count(self, role: Role) -> int:
        return len(self.roster[role])


@dataclass
class LeagueState:
    ruleset: Ruleset
    teams: dict[str, TeamState] = field(default_factory=dict)
    assigned_players: set[str] = field(default_factory=set)
    events_applied: list[str] = field(default_factory=list)
    voided_events: set[str] = field(default_factory=set)

    def team(self, team_id: str) -> TeamState:
        if team_id not in self.teams:
            self.teams[team_id] = TeamState(team_id=team_id)
        return self.teams[team_id]


def resolve_sealed_bid_round(*_args: object, **_kwargs: object) -> None:
    """Blocked: sealed-bid preference resolution is not an approved rule yet.

    docs/OPEN_QUESTIONS.md ("Buste e amministrazione") and
    config/auction_rules.v1.yaml `uncertain_historical_fields` leave preference count,
    tie-breaker, minimum bid, and automatic-fallback assignment unresolved. Per
    CLAUDE.md, an unresolved historical field may not be guessed. Record an approved
    ADR in docs/DECISIONS.md, then implement this function against it.
    """
    raise NotImplementedError(
        "Sealed-bid auto-resolution is blocked by unresolved fields in "
        "config/auction_rules.v1.yaml (uncertain_historical_fields) and "
        "docs/OPEN_QUESTIONS.md ('Buste e amministrazione'). Do not implement this "
        "branch without an approved ADR in docs/DECISIONS.md."
    )


def _check_pool_role(pool_id: str, role: Role, event_id: str) -> None:
    allowed = _KNOWN_POOL_ROLES.get(pool_id)
    if allowed is not None and role not in allowed:
        raise DomainError(
            f"Event {event_id}: role {role.value} is not eligible in pool {pool_id!r} "
            f"(eligible: {sorted(r.value for r in allowed)})"
        )


def replay(ruleset: Ruleset, events: list[Event]) -> LeagueState:
    """Deterministically rebuild league state from an ordered, append-only event log.

    Replaying the same event sequence must always produce the same final state
    (gate requirement, docs/ROADMAP.md M0). Any invariant violation raises
    immediately rather than silently skipping or auto-correcting the event.
    """
    state = LeagueState(ruleset=ruleset)
    # Keyed by team_id -> {round_id: remaining budget}. Per-team, not a single
    # shared dict: a budget_available expression like "remaining_G1 + 100" must
    # resolve to *that team's own* leftover from the earlier round, never
    # whichever other team's event happened to be processed most recently for
    # that round (found via M4 slice 2 UI testing, 2026-08-11 -- see ADR).
    remaining_by_round_per_team: dict[str, dict[str, int]] = {}
    pools_by_round = {r.id: set(r.pools) for r in ruleset.rounds}
    round_by_id = {r.id: r for r in ruleset.rounds}
    max_role_counts = {
        Role.DEF: ruleset.roster.defenders,
        Role.MID: ruleset.roster.midfielders,
        Role.FWD: ruleset.roster.forwards,
    }

    last_round_order_seen = 0
    for event in events:
        if event.event_id in state.events_applied:
            raise DomainError(f"Duplicate event_id in ledger: {event.event_id}")

        if isinstance(event, VoidEvent):
            if event.voids not in state.events_applied:
                raise DomainError(
                    f"Void event {event.event_id} references unknown/unapplied event {event.voids!r}"
                )
            if event.voids in state.voided_events:
                raise DomainError(
                    f"Void event {event.event_id} references already-voided event {event.voids!r}"
                )
            state.voided_events.add(event.voids)
            state.events_applied.append(event.event_id)
            continue

        if isinstance(event, BudgetAdjustmentEvent):
            round_ = round_by_id.get(event.round_id)
            if round_ is None:
                raise ConfigError(
                    f"Event {event.event_id} references unknown round {event.round_id!r}"
                )
            if round_.order < last_round_order_seen:
                raise DomainError(
                    f"Event {event.event_id} is for round {event.round_id} (order {round_.order}) "
                    "but a later round has already been processed; the ledger must be round-ordered"
                )
            last_round_order_seen = max(last_round_order_seen, round_.order)

            team = state.team(event.team_id)
            if round_.id not in team.budgets:
                available = evaluate_budget_expr(
                    round_.budget_available_expr, remaining_by_round_per_team.get(event.team_id, {})
                )
                team.budgets[round_.id] = TeamRoundBudget(available=available)
            team.budgets[round_.id].available += event.amount

            state.events_applied.append(event.event_id)
            remaining_by_round_per_team.setdefault(event.team_id, {})[round_.id] = team.budgets[round_.id].remaining
            continue

        if not isinstance(event, AssignmentEvent):
            raise DomainError(f"Unknown event type: {type(event)!r}")

        round_ = round_by_id.get(event.round_id)
        if round_ is None:
            raise ConfigError(
                f"Event {event.event_id} references unknown round {event.round_id!r}"
            )
        if round_.order < last_round_order_seen:
            raise DomainError(
                f"Event {event.event_id} is for round {event.round_id} (order {round_.order}) "
                "but a later round has already been processed; the ledger must be round-ordered"
            )
        last_round_order_seen = max(last_round_order_seen, round_.order)

        if event.corrects is not None:
            if event.corrects not in state.events_applied:
                raise DomainError(
                    f"Correction event {event.event_id} references unknown event {event.corrects!r}"
                )
            if event.corrects in state.voided_events:
                raise DomainError(
                    f"Correction event {event.event_id} references already-voided/corrected "
                    f"event {event.corrects!r}"
                )
            state.voided_events.add(event.corrects)

        if event.pool_id not in pools_by_round[round_.id]:
            raise DomainError(
                f"Event {event.event_id}: pool {event.pool_id!r} is not eligible in round "
                f"{round_.id} (eligible pools: {sorted(pools_by_round[round_.id])})"
            )
        _check_pool_role(event.pool_id, event.role, event.event_id)

        if event.amount < 0:
            raise DomainError(f"Event {event.event_id}: negative amount {event.amount}")

        for pid in event.item.player_ids:
            if pid in state.assigned_players:
                raise DomainError(
                    f"Event {event.event_id}: player {pid!r} is already assigned to a team"
                )

        team = state.team(event.team_id)
        if round_.id not in team.budgets:
            available = evaluate_budget_expr(
                round_.budget_available_expr, remaining_by_round_per_team.get(event.team_id, {})
            )
            team.budgets[round_.id] = TeamRoundBudget(available=available)
        budget = team.budgets[round_.id]

        if budget.spent + event.amount > budget.available:
            raise DomainError(
                f"Event {event.event_id}: team {event.team_id} would overspend round "
                f"{round_.id} budget ({budget.spent}+{event.amount} > {budget.available})"
            )

        if event.role is Role.GK:
            if len(event.item.player_ids) > ruleset.roster.goalkeeper_block_size:
                raise DomainError(
                    f"Event {event.event_id}: goalkeeper block must have at most "
                    f"{ruleset.roster.goalkeeper_block_size} players, got "
                    f"{len(event.item.player_ids)}"
                )
            # A block below the configured size is allowed: some real clubs have
            # fewer than goalkeeper_block_size goalkeepers on file (data gap, not
            # a modeling error) -- e.g. Cagliari/Lecce with only 2 (ADR-2026-055).
            # An oversized block is still rejected: that would always be a bug.
            if team.gk_block_identity is not None:
                raise DomainError(
                    f"Event {event.event_id}: team {event.team_id} already has a goalkeeper block"
                )
            team.gk_block_identity = event.event_id
            team.roster[Role.GK].extend(event.item.player_ids)
        else:
            if len(event.item.player_ids) != 1:
                raise DomainError(
                    f"Event {event.event_id}: non-goalkeeper assignment must reference "
                    "exactly one player"
                )
            (pid,) = event.item.player_ids
            role = event.role
            cap = max_role_counts.get(role)
            if cap is not None and team.role_count(role) >= cap:
                raise DomainError(
                    f"Event {event.event_id}: team {event.team_id} already has {cap} "
                    f"players in role {role.value}"
                )
            team.roster[role].append(pid)

        budget.spent += event.amount
        state.assigned_players.update(event.item.player_ids)
        state.events_applied.append(event.event_id)
        remaining_by_round_per_team.setdefault(event.team_id, {})[round_.id] = budget.remaining

    return state


def effective_events(events: list[Event]) -> list[AssignmentEvent | BudgetAdjustmentEvent]:
    """Returns only the AssignmentEvents/BudgetAdjustmentEvents still in force:
    voided events and events superseded by a later correction are dropped, and
    VoidEvents themselves are dropped (they're not assignments). Order is
    preserved.

    `replay()` intentionally does NOT retroactively unwind a voided/corrected
    event's roster/budget effects (see test_domain_replay.py's
    test_void_event_marks_original_as_voided) -- that's documented there as "a
    query-time concern (M3+), not a replay-time mutation". This is that query:
    feed its output back into `replay()` to get the *current* state a UI should
    display, as opposed to the full audit trail `replay()` on the raw event list
    gives you.

    A retained AssignmentEvent whose `corrects` field pointed at a now-excluded
    event has that field cleared: after filtering, its target no longer exists
    in this view, and `replay()` requires `corrects` to reference an event
    actually present in the sequence it's given. BudgetAdjustmentEvent has no
    `corrects` field (it's never itself a correction), so it passes through
    unchanged apart from void-exclusion. The returned list is round-ordered
    (order preserved from `events`) and independently replayable."""
    voided_ids: set[str] = set()
    for event in events:
        if isinstance(event, VoidEvent):
            voided_ids.add(event.voids)
        elif isinstance(event, AssignmentEvent) and event.corrects is not None:
            voided_ids.add(event.corrects)

    result: list[AssignmentEvent | BudgetAdjustmentEvent] = []
    for e in events:
        if isinstance(e, VoidEvent) or e.event_id in voided_ids:
            continue
        if isinstance(e, AssignmentEvent) and e.corrects is not None:
            e = replace(e, corrects=None)
        result.append(e)
    return result
