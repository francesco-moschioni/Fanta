"""Budget shadow price via Lagrangian relaxation of the existing roster knapsack
(Engine v2 Stage 6, ADR-2026-076; design: docs/research/priorart_stage6.md sec 1-2).

The roster optimiser (`roster_optimizer.optimize_roster_completion`) solves an exact
0/1 multi-dimensional knapsack: maximise total VAR subject to a budget row and one
per-role slot-count equality per role. This module extracts the *marginal value of a
credit* (`lambda_star`, the budget row's dual) WITHOUT adding an LP solver to the live
path: it dualises only the budget row, which makes the inner problem decompose by role
to "take the top-k_r candidates by reduced value `VAR_i - lambda*price_i`", and finds
the smallest `lambda_star` whose optimal pick fits the budget by bisection on the
monotone budget-slack `g(lambda) = budget - cost(lambda)` (priorart sec 1.2-1.3).

When the budget-free pick (`lambda = 0`) already fits, the budget constraint is slack:
complementary slackness gives `lambda_star = 0` and `binding = False` (priorart sec 2) --
callers must then fall back to the `$1 rule` / clearing-price cap rather than dividing
by ~0.

`_pulp_dual_crosscheck` builds the same programme as an LP in PuLP and reads the budget
constraint's dual; it is used only by a skipif'd test (`pulp` is the optional `solver`
extra, never a runtime dependency).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .roster_optimizer import Candidate, optimize_roster_completion

LARGE_SENTINEL_BID = 10**9  # returned by max_bid_from_shadow_price when lambda_star == 0


@dataclass(frozen=True)
class ShadowPriceResult:
    lambda_star: float  # marginal VAR per residual credit (dV*/dB); 0.0 when non-binding
    binding: bool  # False (+ lambda_star == 0.0) when the lambda=0 pick already fits the budget
    implied_roster: tuple[int, ...]  # per-role pick counts at lambda_star, in sorted-role order
    duality_gap_estimate: float  # max(0, L(lambda_star) - V_IP(DP)); the knapsack integrality gap


def _normalize_candidates(candidates) -> list[tuple[int, str, int, float]]:
    """Accept the same row structure `optimize_roster_completion` consumes: a list of
    `Candidate`, a list of dicts (`player_code`, `role`, `cost`/`price`, `var_mean`),
    or a DataFrame of those columns. Returns (player_code, role, cost, var) tuples."""
    rows: list[tuple[int, str, int, float]] = []
    if hasattr(candidates, "to_dict"):  # pandas DataFrame
        records = candidates.to_dict("records")
    else:
        records = list(candidates)
    for r in records:
        if isinstance(r, Candidate):
            rows.append((r.player_code, r.role, int(r.cost), float(r.var_mean)))
            continue
        if isinstance(r, dict):
            cost = r.get("cost", r.get("price"))
            rows.append((r["player_code"], r["role"], int(cost), float(r["var_mean"])))
            continue
        # generic object with attributes
        cost = getattr(r, "cost", None)
        if cost is None:
            cost = getattr(r, "price")
        rows.append((r.player_code, r.role, int(cost), float(r.var_mean)))
    return rows


def _role_decomposed_pick(
    rows: list[tuple[int, str, int, float]],
    roles: tuple[str, ...],
    role_slots_needed: dict[str, int],
    lam: float,
) -> tuple[int, float, tuple[int, ...]]:
    """Inner Lagrangian problem at `lam`: per role take the `n_r` candidates with the
    largest reduced value `var - lam*cost` (role counts are equalities, so fewer than
    `n_r` positive reduced values still forces `n_r` picks -- take the least-negative).
    Returns (total_cost, sum_of_raw_var_of_pick, per-role counts)."""
    total_cost = 0
    total_var = 0.0
    counts: list[int] = []
    for role in roles:
        need = role_slots_needed[role]
        role_rows = [row for row in rows if row[1] == role]
        role_rows.sort(key=lambda row: row[3] - lam * row[2], reverse=True)
        chosen = role_rows[:need]
        counts.append(len(chosen))
        total_cost += sum(row[2] for row in chosen)
        total_var += sum(row[3] for row in chosen)
    return total_cost, total_var, tuple(counts)


def budget_shadow_price(
    candidates,
    role_slots_needed: dict[str, int],
    budget: int,
    *,
    lambda_hi: float | None = None,
    tol: float = 1e-4,
) -> ShadowPriceResult:
    """Smallest `lambda_star >= 0` whose role-decomposed optimal pick fits `budget`.

    `lambda_star` is the marginal VAR gained per extra credit of budget (the budget
    row's Lagrange multiplier); a player is worth more than its price at the margin iff
    `var_i - lambda_star*price_i > 0`, and the value-based bid ceiling is
    `var_i / lambda_star` (see `max_bid_from_shadow_price`)."""
    if budget < 0:
        raise ValueError(f"budget must be >= 0, got {budget}")
    rows = _normalize_candidates(candidates)
    roles = tuple(sorted(r for r, need in role_slots_needed.items() if need > 0))
    if not roles:
        return ShadowPriceResult(lambda_star=0.0, binding=False, implied_roster=(), duality_gap_estimate=0.0)

    # 1. Non-binding detection first: does the raw top-k_r pick already fit?
    cost0, _var0, counts0 = _role_decomposed_pick(rows, roles, role_slots_needed, 0.0)
    if cost0 <= budget:
        return ShadowPriceResult(
            lambda_star=0.0, binding=False, implied_roster=counts0, duality_gap_estimate=0.0
        )

    # 2. Bisection on the monotone budget slack g(lambda) = budget - cost(lambda).
    costs = [row[2] for row in rows if row[2] > 0]
    vars_ = [row[3] for row in rows]
    min_c = min(costs) if costs else 1
    max_v = max(vars_) if vars_ else 1.0
    hi = float(lambda_hi) if lambda_hi is not None else (max(max_v, 1.0) / min_c + 1.0)
    lo = 0.0
    # Ensure the upper bracket actually fits (defensive: widen if not).
    for _ in range(60):
        if _role_decomposed_pick(rows, roles, role_slots_needed, hi)[0] <= budget:
            break
        hi *= 2.0
    for _ in range(200):
        if hi - lo <= tol:
            break
        mid = 0.5 * (lo + hi)
        spend = _role_decomposed_pick(rows, roles, role_slots_needed, mid)[0]
        if spend > budget:
            lo = mid
        else:
            hi = mid
    lambda_star = hi

    pick_cost, pick_raw_var, pick_counts = _role_decomposed_pick(rows, roles, role_slots_needed, lambda_star)
    # L(lambda_star) = sum_i (v_i - lambda* c_i) x_i + lambda* B  (an upper bound on the IP optimum)
    l_value = (pick_raw_var - lambda_star * pick_cost) + lambda_star * budget

    dp = optimize_roster_completion(
        [Candidate(player_code=c, role=r, var_mean=v, cost=int(cost)) for (c, r, cost, v) in rows],
        role_slots_needed,
        budget,
    )
    duality_gap = max(0.0, l_value - dp.total_var)

    return ShadowPriceResult(
        lambda_star=float(lambda_star),
        binding=True,
        implied_roster=pick_counts,
        duality_gap_estimate=float(duality_gap),
    )


def max_bid_from_shadow_price(player_var: float, lambda_star: float, *, floor: int = 1) -> int:
    """Convert VAR into a credit ceiling at the exchange rate `lambda_star` (VAR per
    credit): never pay more than `player_var / lambda_star`, because beyond that price
    the marginal credits are better spent elsewhere in the roster.

    When `lambda_star == 0` (budget non-binding) there is no opportunity cost and the
    ratio is undefined -- returns `LARGE_SENTINEL_BID` (a finite, budget-agnostic large
    int, NOT math.inf) so the caller's own budget / clearing-price caps bind instead."""
    if lambda_star <= 0:
        return LARGE_SENTINEL_BID
    return max(int(floor), math.ceil(player_var / lambda_star))


def _pulp_dual_crosscheck(candidates, role_slots_needed: dict[str, int], budget: int) -> float:
    """LP-relaxation cross-check (TEST ONLY): build the same programme as an LP and
    read the budget constraint's dual price. Guarded so `pulp` stays an optional extra."""
    try:
        import pulp  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised only when the extra is absent
        raise RuntimeError("pulp not installed; this cross-check is for the skipif'd test only") from exc

    rows = _normalize_candidates(candidates)
    roles = tuple(sorted(r for r, need in role_slots_needed.items() if need > 0))
    prob = pulp.LpProblem("roster_lp", pulp.LpMaximize)
    x = {code: pulp.LpVariable(f"x_{code}", lowBound=0, upBound=1) for (code, _r, _c, _v) in rows}
    prob += pulp.lpSum(v * x[code] for (code, _r, _c, v) in rows)
    budget_con = pulp.lpSum(c * x[code] for (code, _r, c, _v) in rows) <= budget
    prob += (budget_con, "budget")
    for role in roles:
        prob += (
            pulp.lpSum(x[code] for (code, r, _c, _v) in rows if r == role) == role_slots_needed[role],
            f"role_{role}",
        )
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    return abs(prob.constraints["budget"].pi or 0.0)
