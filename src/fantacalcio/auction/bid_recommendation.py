"""Max-bid recommendation: connects the live ledger (src/fantacalcio/domain.py) to
value-above-replacement (ADR-2026-019) for a real "how much should I bid right now"
answer, given what's already been assigned.

Methodology (first pass, explicitly a known simplification, not the full
forecast-to-bid layer docs/DATA_AND_MODELING.md describes): the standard "auction
value" formula used across fantasy-sports auction tools --

  1. Reserve 1 credit for every roster slot still needed AFTER this pick (the
     "$1 rule": never let a bid leave you unable to afford minimum bids for the
     rest of your roster).
  2. Whatever's left ("discretionary budget") is distributed across the still-
     undrafted pool proportional to each player's *positive* VAR share.

Deliberately NOT included yet (see docs/DATA_AND_MODELING.md's full list):
opponent demand modelling, observed market inflation, roster-fit/formation
adjustments, risk profile. Budget/roster state is always read from the live ledger
via replay, never a static snapshot -- a recommendation made mid-auction reflects
exactly what's actually been assigned so far.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import Ruleset, evaluate_budget_expr
from ..domain import LeagueState, Role as DomainRole, TeamState

VOTI_TO_DOMAIN_ROLE = {"P": DomainRole.GK, "D": DomainRole.DEF, "C": DomainRole.MID, "A": DomainRole.FWD}
_ROLE_TARGET_FIELD = {"P": "goalkeeper_block_size", "D": "defenders", "C": "midfielders", "A": "forwards"}


class BidRecommendationError(ValueError):
    pass


def budget_available_for_round(team_state: TeamState, round_id: str, ruleset: Ruleset) -> int:
    """What the team's budget_available expression evaluates to for `round_id`,
    whether or not that round has actually started for this team yet -- mirrors
    the same evaluation domain.replay() does, without duplicating the replay loop."""
    if round_id in team_state.budgets:
        return team_state.budgets[round_id].available
    remaining_by_round = {rid: b.remaining for rid, b in team_state.budgets.items()}
    round_ = ruleset.round_by_id(round_id)
    return evaluate_budget_expr(round_.budget_available_expr, remaining_by_round)


def budget_remaining_for_round(team_state: TeamState, round_id: str, ruleset: Ruleset) -> int:
    if round_id in team_state.budgets:
        return team_state.budgets[round_id].remaining
    return budget_available_for_round(team_state, round_id, ruleset)  # round not started: nothing spent yet


def remaining_roster_slots(team_state: TeamState, ruleset: Ruleset) -> dict[str, int]:
    """Slots still needed per voti-convention role code (P/D/C/A), reading targets
    from config, never hardcoded."""
    slots = {}
    for role, field_name in _ROLE_TARGET_FIELD.items():
        target = getattr(ruleset.roster, field_name)
        have = team_state.role_count(VOTI_TO_DOMAIN_ROLE[role])
        slots[role] = max(0, target - have)
    return slots


@dataclass(frozen=True)
class MaxBidRecommendation:
    team_id: str
    player_code: int
    round_id: str
    remaining_budget: int
    remaining_slots_total: int
    reserve_for_other_slots: int
    discretionary_budget: int
    player_var: float
    pool_var_sum: float
    var_share: float
    max_bid: int


def recommend_max_bid(
    league_state: LeagueState,
    ruleset: Ruleset,
    team_id: str,
    round_id: str,
    target_player_code: int,
    target_player_var: float,
    undrafted_pool: pd.DataFrame,
) -> MaxBidRecommendation:
    """`undrafted_pool` must have columns player_code, var_mean, and cover the same
    role/round pool as the target player -- callers are responsible for pre-
    filtering to the right pool (see src/fantacalcio/auction/round_pools.py); this
    function only excludes players the ledger already shows as assigned."""
    team_state = league_state.team(team_id)
    remaining_budget = budget_remaining_for_round(team_state, round_id, ruleset)

    slots = remaining_roster_slots(team_state, ruleset)
    remaining_slots_total = sum(slots.values())
    if remaining_slots_total <= 0:
        raise BidRecommendationError(f"Team {team_id!r} roster is already full; no slots to fill.")

    reserve = max(0, remaining_slots_total - 1)  # 1 credit per OTHER slot still needed
    discretionary = max(0, remaining_budget - reserve)

    # The ledger stores player ids as strings (AssignmentItem.player_ids: tuple[str,
    # ...]); the VAR pool's player_code is typically int (from pandas). Compare as
    # strings so an assigned player is actually excluded rather than silently kept
    # in the pool because of a type mismatch (found via test, 2026-08-11).
    assigned_as_str = {str(p) for p in league_state.assigned_players}
    undrafted = undrafted_pool[~undrafted_pool["player_code"].astype(str).isin(assigned_as_str)]
    if str(target_player_code) not in set(undrafted["player_code"].astype(str)):
        raise BidRecommendationError(
            f"Player {target_player_code!r} is not in the undrafted pool passed in "
            "(already assigned, or not part of this round's pool)."
        )

    pool_var_sum = float(undrafted["var_mean"].clip(lower=0).sum())
    player_var_positive = max(0.0, target_player_var)

    if pool_var_sum > 0:
        var_share = player_var_positive / pool_var_sum
    else:
        # Nobody left has positive VAR (late in a round): split discretionary budget
        # evenly rather than dividing by zero.
        var_share = 1.0 / len(undrafted) if len(undrafted) > 0 else 0.0

    max_bid = 1 + int(var_share * discretionary)
    max_bid = min(max_bid, remaining_budget)  # never recommend spending more than you have

    return MaxBidRecommendation(
        team_id=team_id,
        player_code=target_player_code,
        round_id=round_id,
        remaining_budget=remaining_budget,
        remaining_slots_total=remaining_slots_total,
        reserve_for_other_slots=reserve,
        discretionary_budget=discretionary,
        player_var=target_player_var,
        pool_var_sum=pool_var_sum,
        var_share=var_share,
        max_bid=max_bid,
    )
