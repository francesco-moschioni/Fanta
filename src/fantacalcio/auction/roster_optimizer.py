"""Optimal roster completion within budget and role-slot constraints
(docs/CURRENT_TASK.md, M4 slice 6 -- "rosa ideale").

Given how many more players are needed per role and a budget, finds the
combination of undrafted candidates that maximizes total VAR -- an exact 0/1
multi-dimensional knapsack (DP over budget x per-role counts already chosen),
not a greedy heuristic. Tractable because role caps are small (roster
composition, config/auction_rules.v1.yaml) and round budgets are modest, but
the candidate pool is capped to the top `TOP_N_PER_ROLE` players by VAR per
role first -- an explicit, documented approximation for performance, not a
silent one: a candidate outside that cut could in principle be part of the
true optimum (e.g. a very cheap, moderate-VAR filler needed only to hit a
tight budget), so results are reported as "best found within this candidate
pool", not "provably globally optimal".

This is a planning tool: it never touches the ledger or recomputes VAR/cost --
both come in as already-computed numbers (CLAUDE.md: no new formulas in a
UI-adjacent layer, only combination of what the deterministic engine already
produced).

The objective is "maximize total VAR", not "always fill every requested
slot": if every affordable candidate for a role has negative VAR, that slot is
deliberately left unfilled rather than forced, since filling it would lower
total VAR. Callers that need every slot filled regardless of quality (a
mandatory-completion mode) must handle that separately -- this module doesn't
claim to solve it.
"""

from __future__ import annotations

from dataclasses import dataclass

TOP_N_PER_ROLE = 25


class RosterOptimizerError(ValueError):
    pass


def candidate_price_floor(quotazione_asta: int, admin_quotazione: int | None = None) -> int:
    """Minimum legal cost for a non-locked candidate: the admin's own
    per-player quotation when one exists, otherwise the fantacalcio listone
    quotation. `optimize_roster_completion` must never propose a candidate
    below this -- in G1/G2 the sealed-bid minimum is the published quotation
    (ADR-2026-013), so a lower `cost` here would describe an offer the rules
    don't allow. `admin_quotazione` is `None` today (no per-player admin
    quotation has been imported yet, `apply_official_admin_list.py`); this
    function exists so callers don't need to change when one arrives."""
    if admin_quotazione is not None:
        return max(admin_quotazione, quotazione_asta)
    return quotazione_asta


@dataclass(frozen=True)
class Candidate:
    player_code: int
    role: str
    var_mean: float
    cost: int  # quotazione_asta, used as the price proxy -- not a bid prediction


@dataclass(frozen=True)
class OptimizationResult:
    selected: tuple[Candidate, ...]
    total_var: float
    total_cost: int
    candidates_considered: int
    candidate_pool_capped: bool  # True if TOP_N_PER_ROLE actually excluded some candidates


def optimize_roster_completion(
    candidates: list[Candidate],
    role_slots_needed: dict[str, int],
    budget: int,
) -> OptimizationResult:
    """Exact 0/1 knapsack over the (capped) candidate pool, respecting
    per-role slot caps in `role_slots_needed` and total `budget`."""
    if budget < 0:
        raise RosterOptimizerError(f"budget must be >= 0, got {budget}")
    for role, need in role_slots_needed.items():
        if need < 0:
            raise RosterOptimizerError(f"role_slots_needed[{role!r}] must be >= 0, got {need}")

    roles = tuple(r for r, need in role_slots_needed.items() if need > 0)
    if not roles:
        return OptimizationResult(selected=(), total_var=0.0, total_cost=0, candidates_considered=0, candidate_pool_capped=False)

    trimmed: list[Candidate] = []
    capped = False
    for role in roles:
        role_candidates = sorted((c for c in candidates if c.role == role), key=lambda c: c.var_mean, reverse=True)
        if len(role_candidates) > TOP_N_PER_ROLE:
            capped = True
        trimmed.extend(role_candidates[:TOP_N_PER_ROLE])

    zero_counts = tuple(0 for _ in roles)
    # State -> (best total VAR so far, indices of trimmed[] chosen to reach it).
    best: dict[tuple[int, tuple[int, ...]], float] = {(0, zero_counts): 0.0}
    choice: dict[tuple[int, tuple[int, ...]], tuple[int, ...]] = {(0, zero_counts): ()}

    for idx, c in enumerate(trimmed):
        role_idx = roles.index(c.role)
        for state, total_var in list(best.items()):
            used_budget, counts = state
            if counts[role_idx] >= role_slots_needed[c.role]:
                continue
            new_budget = used_budget + c.cost
            if new_budget > budget:
                continue
            new_counts = tuple(v + 1 if i == role_idx else v for i, v in enumerate(counts))
            new_state = (new_budget, new_counts)
            candidate_var = total_var + c.var_mean
            if candidate_var > best.get(new_state, -1.0):
                best[new_state] = candidate_var
                choice[new_state] = choice[state] + (idx,)

    best_state = max(best, key=lambda k: best[k])
    selected = tuple(trimmed[i] for i in choice[best_state])
    return OptimizationResult(
        selected=selected,
        total_var=best[best_state],
        total_cost=best_state[0],
        candidates_considered=len(trimmed),
        candidate_pool_capped=capped,
    )
