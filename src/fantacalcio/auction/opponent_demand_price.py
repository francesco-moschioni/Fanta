"""Opponent demand -> expected clearing price (Engine v2 Stage 6, ADR-2026-076;
design: docs/research/priorart_stage6.md sec 5).

A bounded, monotone, saturating form for the price a player is likely to CLEAR at
(the 2nd-highest willingness, not the winner's max -- winner's-curse discipline):

    E[clear] = q * role_inflation
               * (1 + (g_max - 1) * (1 - exp(-kappa * max(demand_pressure - d0, 0))))

then hard-clipped to `richest_rival_bid` when known (the price cannot exceed the richest
rival's max legal bid). Properties enforced: monotone non-decreasing in
`demand_pressure`; `>= q*role_inflation` (absent a lower `richest_rival_bid` clip);
finite; `demand_pressure = 0` (with `d0 = 0`) => exactly `q*role_inflation`.

`demand_pressure_from_state` reads opponent demand from replay state only (ledger-derived,
leakage-safe): opponents still needing the role, weighted by budget-per-open-slot and,
when supplied, `market_model` aggressiveness. `calibrate_clearing_form` is an optional
convenience fit (numpy/scipy only), NOT required by the main path.

ADR-2026-057 reported the competition signal alongside the bid but never multiplied it
into the price. Folding opponent demand INTO the price (via this module, wired through
`recommend_max_bid(opponent_demand=...)`) reverses that -- it is OPT-IN and off by
default; see ADR-2026-076.
"""

from __future__ import annotations

import math

from ..config import Ruleset
from ..domain import LeagueState
from .bid_recommendation import budget_remaining_for_round, remaining_roster_slots

DEFAULT_CLEARING_FORM = {"g_max": 2.5, "kappa": 0.6, "d0": 0.0, "role_inflation": 1.0}


def expected_clearing_price(
    quotazione: float,
    *,
    demand_pressure: float,
    role_inflation: float = 1.0,
    g_max: float = 2.5,
    kappa: float = 0.6,
    d0: float = 0.0,
    richest_rival_bid: float | None = None,
) -> float:
    """Bounded saturating clearing-price estimate. See module docstring for the form
    and the guarantees."""
    if g_max < 1.0:
        raise ValueError(f"g_max must be >= 1.0, got {g_max}")
    if kappa < 0.0:
        raise ValueError(f"kappa must be >= 0.0, got {kappa}")
    anchor = float(quotazione) * float(role_inflation)
    d = max(float(demand_pressure) - float(d0), 0.0)
    premium = (g_max - 1.0) * (1.0 - math.exp(-kappa * d))
    price = anchor * (1.0 + premium)
    if richest_rival_bid is not None:
        price = min(price, float(richest_rival_bid))
    return float(price)


def _current_round_id(league_state: LeagueState, ruleset: Ruleset, round_id: str | None) -> str:
    if round_id is not None:
        return round_id
    seen: set[str] = set()
    for team in league_state.teams.values():
        seen.update(team.budgets)
    if seen:
        return max(seen, key=lambda rid: ruleset.round_by_id(rid).order)
    return ruleset.rounds[0].id


def demand_pressure_from_state(
    league_state: LeagueState,
    ruleset: Ruleset,
    role: str,
    *,
    exclude_team_id: str,
    round_id: str | None = None,
    aggressiveness: dict | None = None,
) -> float:
    """Opponent demand pressure for `role` (voti code P/D/C/A): sum over opponents that
    still have an open slot in `role` of their relative budget-per-open-slot, optionally
    scaled by `market_model.team_aggressiveness_index` when passed in `aggressiveness`.

    Uniform affordability => pressure equals the count of opponents still needing the
    role; a richer-than-average opponent contributes more, a poorer one less. Reads
    replay-derived state only (leakage-safe)."""
    rid = _current_round_id(league_state, ruleset, round_id)
    bpos_list: list[float] = []
    aggr_list: list[float] = []
    for team_id, team_state in league_state.teams.items():
        if team_id == exclude_team_id:
            continue
        slots = remaining_roster_slots(team_state, ruleset)
        if slots.get(role, 0) <= 0:
            continue
        total_open = sum(slots.values())
        rem = budget_remaining_for_round(team_state, rid, ruleset)
        bpos = rem / total_open if total_open > 0 else float(rem)
        bpos_list.append(max(0.0, bpos))
        aggr = 1.0
        if aggressiveness and team_id in aggressiveness:
            entry = aggressiveness[team_id]
            ratio = getattr(entry, "team_mean_ratio", None)
            if ratio and ratio > 0:
                aggr = float(ratio)
        aggr_list.append(aggr)
    if not bpos_list:
        return 0.0
    avg = sum(bpos_list) / len(bpos_list)
    if avg <= 0:
        return float(len(bpos_list))
    return float(sum((b / avg) * a for b, a in zip(bpos_list, aggr_list)))


def calibrate_clearing_form(realised_prices_df=None) -> dict:
    """Optional lightweight fit of the saturating premium on realised prices.

    Expects a frame with columns `price`, `quotazione`, `demand_pressure`. Fits
    `kappa` and `g_max` by least squares of `log(price/quotazione)` on the saturating
    form (pinball at the median reduces to LS here); returns `DEFAULT_CLEARING_FORM` on
    an empty/absent frame or any fit failure. Convenience, not on the main path."""
    if realised_prices_df is None or len(realised_prices_df) == 0:
        return dict(DEFAULT_CLEARING_FORM)
    try:
        import numpy as np
        from scipy.optimize import curve_fit

        df = realised_prices_df
        q = np.asarray(df["quotazione"], dtype=float)
        price = np.asarray(df["price"], dtype=float)
        dpr = np.asarray(df["demand_pressure"], dtype=float)
        ratio = np.log(np.clip(price / np.clip(q, 1e-9, None), 1e-9, None))

        def model(d, kappa, g_max):
            return np.log1p((g_max - 1.0) * (1.0 - np.exp(-kappa * np.maximum(d, 0.0))))

        popt, _ = curve_fit(
            model, dpr, ratio, p0=[0.6, 2.5], bounds=([1e-3, 1.0], [10.0, 10.0]), maxfev=5000
        )
        return {"g_max": float(popt[1]), "kappa": float(popt[0]), "d0": 0.0, "role_inflation": 1.0}
    except Exception:
        return dict(DEFAULT_CLEARING_FORM)
