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

Market context (ADR-2026-057, optional -- pass `player_conn`/`all_events`/
`opponent_ids` to enable, omitted entirely otherwise): the dollar-rule base bid
above is corrected by observed cross-round price inflation for the target's role
(`market_model.role_price_inflation` -- e.g. defenders averaged 1.23x their
quotazione in G1, so a future defender bid is scaled up accordingly), and paired
with a competition signal (`market_model.opponents_needing_role` -- how many
opponents still need this role and how much budget-per-slot they have). The
competition signal is reported alongside the bid, never multiplied into it:
turning "N opponents still need this" into a numeric price bump is a real
strategy decision that needs an explicit user-approved rule, not an invented
multiplier (CLAUDE.md: no invented formulas without approval).

Deliberately NOT included yet (see docs/DATA_AND_MODELING.md's full list):
roster-fit/formation adjustments, risk profile, folding the competition signal
into the price itself. Budget/roster state is always read from the live ledger
via replay, never a static snapshot -- a recommendation made mid-auction reflects
exactly what's actually been assigned so far.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

CLEARING_BUFFER = 1  # small overpay buffer added to the expected clearing price ceiling

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
    base_bid: int  # dollar-rule bid before any market correction
    max_bid: int  # final: base_bid corrected by role inflation (if available), capped at remaining_budget
    inflation_ratio: float | None = None  # mean observed amount/quotazione for this role, other rounds
    inflation_n: int = 0
    inflation_reliable: bool = False
    competition_teams_needing: int | None = None
    competition_teams_total: int | None = None
    competition_avg_budget_per_slot: float | None = None
    explanation: tuple[str, ...] = ()
    # Stage 6 (ADR-2026-076), all optional -- None / "" unless a Stage 6 arg was passed.
    shadow_price_ceiling: int | None = None  # value/lambda* ceiling from the budget shadow price
    clearing_price_ceiling: int | None = None  # expected clearing price + buffer (opponent demand)
    binding_constraint: str = ""  # which cap set the final max_bid, when Stage 6 was active


def recommend_max_bid(
    league_state: LeagueState,
    ruleset: Ruleset,
    team_id: str,
    round_id: str,
    target_player_code: int,
    target_player_var: float,
    undrafted_pool: pd.DataFrame,
    *,
    voti_role: str | None = None,
    player_conn=None,
    all_events: list | None = None,
    opponent_ids: list[str] | None = None,
    shadow_price=None,
    risk_aversion: float = 0.0,
    opponent_demand: float | None = None,
    clearing_form_params: dict | None = None,
    target_player_var_samples=None,
    risk_cvar_alpha: float = 0.10,
) -> MaxBidRecommendation:
    """`undrafted_pool` must have columns player_code, var_mean, and cover the same
    role/round pool as the target player -- callers are responsible for pre-
    filtering to the right pool (see src/fantacalcio/auction/round_pools.py); this
    function only excludes players the ledger already shows as assigned.

    Market context is entirely optional: pass `voti_role` + `player_conn` +
    `all_events` to apply the cross-round inflation correction, and additionally
    `opponent_ids` to attach the competition signal. Any subset omitted simply
    skips that part of the breakdown -- callers without a live DB/ledger handle
    still get the base dollar-rule bid unchanged."""
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

    base_bid = 1 + int(var_share * discretionary)
    base_bid = min(base_bid, remaining_budget)  # never recommend spending more than you have

    explanation = [
        f"Budget residuo per {round_id}: {remaining_budget}",
        f"Slot ancora da riempire (incluso questo): {remaining_slots_total} -> riserva "
        f"1 credito per ciascuno degli altri {reserve} slot",
        f"Budget discrezionale = {remaining_budget} - {reserve} = {discretionary}",
        f"Quota VAR di questo giocatore sul pool residuo = {player_var_positive:.2f} / "
        f"{pool_var_sum:.2f} = {var_share:.1%}",
        f"Prezzo base (dollar rule) = 1 + {var_share:.1%} x {discretionary} = {base_bid}",
    ]

    max_bid = base_bid
    inflation_ratio: float | None = None
    inflation_n = 0
    inflation_reliable = False
    if voti_role is not None and player_conn is not None and all_events is not None:
        # local imports: avoid a circular import with market_model, which itself
        # imports remaining_roster_slots/budget_remaining_for_round from this module
        from .market_model import estimate_price_correction, get_player_row

        target_row = get_player_row(player_conn, str(target_player_code))
        target_quotazione = int(target_row["quotazione_asta"]) if target_row is not None else None

        correction = (
            estimate_price_correction(all_events, player_conn, voti_role, target_quotazione, exclude_round_id=round_id)
            if target_quotazione is not None else None
        )
        if correction is not None:
            inflation_ratio = correction.ratio
            inflation_n = correction.n
            inflation_reliable = correction.reliable
            max_bid = min(int(round(base_bid * correction.ratio)), remaining_budget)
            reliability_note = (
                "affidabile" if correction.reliable
                else f"POCA AFFIDABILITA': solo {correction.n} osservazioni"
            )
            explanation.append(
                f"Correzione di mercato -- livello usato: {correction.source} (n={correction.n}, "
                f"{reliability_note}): prezzo corretto = {base_bid} x {correction.ratio:.2f} = {max_bid}"
            )
        else:
            explanation.append(
                "Nessun dato storico di mercato disponibile ancora (nessun turno chiuso con "
                "compravendite individuali): nessuna correzione applicata."
            )
    else:
        explanation.append("Correzione di mercato non disponibile per questa chiamata (dati di contesto assenti).")

    competition_needing = competition_total = None
    competition_avg_budget = None
    if voti_role is not None and opponent_ids is not None:
        from .market_model import opponents_needing_role  # local import: avoids a circular import with market_model

        competition = opponents_needing_role(league_state, ruleset, round_id, voti_role, opponent_ids)
        competition_needing = competition.teams_needing
        competition_total = competition.teams_total
        competition_avg_budget = competition.avg_budget_per_open_slot
        budget_note = (
            f", budget medio/slot tra chi ne ha bisogno: {competition_avg_budget:.1f}"
            if competition_avg_budget is not None else ""
        )
        explanation.append(
            f"Concorrenza stimata: {competition_needing}/{competition_total} squadre avversarie "
            f"hanno ancora uno slot {voti_role} scoperto{budget_note} (informativo, NON incluso "
            "nel prezzo qui sopra)."
        )

    # --- Stage 6 (ADR-2026-076): shadow-price / risk / opponent-demand caps ---
    # Entirely skipped (byte-identical output) unless a Stage 6 arg was passed.
    shadow_price_ceiling: int | None = None
    clearing_price_ceiling: int | None = None
    binding_constraint = ""
    if shadow_price is not None or opponent_demand is not None or risk_aversion:
        value_term = float(target_player_var)
        if risk_aversion:
            if target_player_var_samples is not None:
                import numpy as _np

                from .risk_profile import cvar as _cvar
                from .risk_profile import risk_adjusted_objective as _rao

                _s = _np.asarray(target_player_var_samples, dtype=float)
                value_term = _rao(float(_s.mean()), _cvar(_s, risk_cvar_alpha), risk_aversion)
                explanation.append(
                    f"Profilo di rischio (rho={risk_aversion:.2f}, CVaR al {risk_cvar_alpha:.0%}, "
                    f"fonte: risk_profile.risk_adjusted_objective su campioni Monte Carlo del "
                    f"giocatore): VAR aggiustata per il rischio = {value_term:.2f}"
                )
            else:
                explanation.append(
                    f"Profilo di rischio richiesto (rho={risk_aversion:.2f}) ma nessun campione "
                    "del giocatore fornito: valore non aggiustato."
                )

        _anchor = locals().get("target_quotazione", None)
        if opponent_demand is not None:
            from .opponent_demand_price import DEFAULT_CLEARING_FORM, expected_clearing_price

            _params = {**DEFAULT_CLEARING_FORM, **(clearing_form_params or {})}
            anchor = _anchor if _anchor else base_bid
            _ecp = expected_clearing_price(
                anchor,
                demand_pressure=float(opponent_demand),
                role_inflation=_params.get("role_inflation", 1.0),
                g_max=_params.get("g_max", 2.5),
                kappa=_params.get("kappa", 0.6),
                d0=_params.get("d0", 0.0),
            )
            clearing_price_ceiling = max(1, int(math.ceil(_ecp)) + CLEARING_BUFFER)
            explanation.append(
                f"Prezzo di aggiudicazione atteso (fonte: opponent_demand_price."
                f"expected_clearing_price; domanda avversari D={opponent_demand:.2f}, ancora="
                f"{anchor}) = {_ecp:.1f} -> tetto con margine +{CLEARING_BUFFER} = "
                f"{clearing_price_ceiling}"
            )

        caps: dict[str, int] = {"budget residuo": remaining_budget}
        _value_replaces_dollar_rule = (
            shadow_price is not None and shadow_price.binding and shadow_price.lambda_star > 0
        )
        if shadow_price is not None:
            if _value_replaces_dollar_rule:
                from .budget_shadow_price import max_bid_from_shadow_price

                shadow_price_ceiling = max_bid_from_shadow_price(value_term, shadow_price.lambda_star)
                caps["prezzo ombra del budget"] = shadow_price_ceiling
                explanation.append(
                    f"Prezzo ombra del budget lambda*={shadow_price.lambda_star:.4f} VAR/credito "
                    f"(fonte: budget_shadow_price.budget_shadow_price): tetto di valore = "
                    f"{value_term:.2f} / {shadow_price.lambda_star:.4f} = {shadow_price_ceiling}"
                )
            else:
                explanation.append(
                    "Prezzo ombra del budget: budget NON vincolante (lambda*=0) -> nessun "
                    "costo-opportunita', resta valida la regola dollar/$1 gia' calcolata."
                )
        if clearing_price_ceiling is not None:
            caps["prezzo di aggiudicazione"] = clearing_price_ceiling
        if not _value_replaces_dollar_rule:
            caps["valore (regola dollar)"] = max_bid

        final = min(caps.values())
        binding_constraint = min(caps, key=lambda k: caps[k])
        max_bid = max(1, min(final, remaining_budget))
        explanation.append(f"Vincolo attivo (Stage 6): {binding_constraint}")

    explanation.append(f"Massimo consigliato finale: {max_bid}")

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
        base_bid=base_bid,
        max_bid=max_bid,
        inflation_ratio=inflation_ratio,
        inflation_n=inflation_n,
        inflation_reliable=inflation_reliable,
        competition_teams_needing=competition_needing,
        competition_teams_total=competition_total,
        competition_avg_budget_per_slot=competition_avg_budget,
        explanation=tuple(explanation),
        shadow_price_ceiling=shadow_price_ceiling,
        clearing_price_ceiling=clearing_price_ceiling,
        binding_constraint=binding_constraint,
    )
