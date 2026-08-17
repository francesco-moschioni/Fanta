"""Feasibility checks for G2 sealed-bid envelope drafts (ADR-2026-060): 5 banded
lists (3 midfielder bands + 2 forward bands), each an independent 6-preference
sealed bid resolved preference-rank-first-then-bid.

Pure functions, no I/O -- callers pass in state already loaded from the ledger
(`domain.LeagueState`) and the envelope store
(`persistence.g2_envelopes_store.EnvelopePick`), same split as
`lock_feasibility.py`. Per CLAUDE.md: never silently allow a draft pick that
couldn't possibly become real; explain why, in terms a user can act on.

Worst-case G2 spend modeling: within one band you win at most one player (the
highest-ranked preference that resolves in your favour), so the band's
worst-case cost is the MAX bid you set among that band's picks, not the sum --
you never pay for more than one player per band. Total worst-case G2 spend is
the sum of those per-band maxima across all 5 bands.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..config import Ruleset
from ..domain import LeagueState
from ..persistence.g2_envelopes_store import EnvelopePick
from .bid_recommendation import VOTI_TO_DOMAIN_ROLE, budget_available_for_round, remaining_roster_slots

MAX_PREFERENCES_PER_BAND = 6

G2_BAND_ROLE = {
    "midfielders_top_1_20": "C",
    "midfielders_top_21_40": "C",
    "midfielders_top_41_60": "C",
    "forwards_top_1_20": "A",
    "forwards_top_21_40": "A",
}


@dataclass(frozen=True)
class PickFeasibilityResult:
    ok: bool
    reason: str | None = None


def check_pick_feasibility(
    team_id: str,
    list_pool_name: str,
    player_code: int,
    admin_rank: float | None,
    ruleset: Ruleset,
    league_state: LeagueState,
    existing_picks: list[EnvelopePick],
) -> PickFeasibilityResult:
    """`existing_picks` should be this team's current envelope picks across ALL
    bands (`g2_envelopes_store.list_picks(conn, team_id)`), not just this band --
    a player can't sit in two bands' envelopes at once."""
    if list_pool_name not in G2_BAND_ROLE:
        return PickFeasibilityResult(ok=False, reason=f"{list_pool_name!r} non è una fascia G2 valida.")

    role = G2_BAND_ROLE[list_pool_name]
    domain_role = VOTI_TO_DOMAIN_ROLE[role]
    player_code_str = str(player_code)

    for other_team_id, other_team in league_state.teams.items():
        if player_code_str in other_team.roster.get(domain_role, []):
            if other_team_id == team_id:
                return PickFeasibilityResult(
                    ok=False, reason="Il giocatore è già nella rosa reale di questa squadra: non serve inserirlo in busta."
                )
            return PickFeasibilityResult(
                ok=False,
                reason=f"Il giocatore è già stato assegnato alla squadra {other_team_id!r} nel ledger reale: "
                "obiettivo non più disponibile.",
            )

    same_band_picks = [p for p in existing_picks if p.list_pool_name == list_pool_name]
    if any(p.player_code == player_code for p in existing_picks):
        return PickFeasibilityResult(ok=False, reason="Il giocatore è già presente in una busta di questa squadra.")

    if len(same_band_picks) >= MAX_PREFERENCES_PER_BAND:
        return PickFeasibilityResult(
            ok=False,
            reason=f"La busta {list_pool_name!r} ha già {MAX_PREFERENCES_PER_BAND} preferenze: "
            "rimuovine una per farne spazio.",
        )

    if admin_rank is None:
        return PickFeasibilityResult(
            ok=False,
            reason="Il giocatore non ha ancora un admin_rank noto: non è confermato in quale fascia "
            "ricada, non lo si può mettere in busta finché la lista admin non lo posiziona.",
        )

    return PickFeasibilityResult(ok=True)


@dataclass(frozen=True)
class BandSpend:
    list_pool_name: str
    n_preferences: int
    max_bid: int  # worst-case cost of this band: you win at most one preference
    top_preference_player_code: int | None  # which pick carries that max bid
    first_choice_bid: int  # cost IF you win specifically preference #1 (rank 1)
    first_choice_player_code: int | None


@dataclass(frozen=True)
class G2FeasibilityReport:
    team_id: str
    g2_budget_available: int
    worst_case_total_spend: int
    margin: int  # budget_available - worst_case_total_spend; negative = overspend
    ok: bool
    first_choice_total_spend: int = 0  # spend IF every band resolves on preference #1
    first_choice_margin: int = 0
    first_choice_ok: bool = True
    bands: tuple[BandSpend, ...] = field(default_factory=tuple)
    slots_not_covered_by_g2: dict[str, int] = field(default_factory=dict)
    explanation: tuple[str, ...] = ()


def summarize_g2_feasibility(
    team_id: str,
    ruleset: Ruleset,
    league_state: LeagueState,
    all_picks: list[EnvelopePick],
) -> G2FeasibilityReport:
    """`all_picks` = this team's full envelope draft across all 5 bands
    (`g2_envelopes_store.list_picks(conn, team_id)`)."""
    team_state = league_state.team(team_id)
    g2_available = budget_available_for_round(team_state, "G2", ruleset)

    bands = []
    worst_case_total = 0
    first_choice_total = 0
    for list_pool_name in G2_BAND_ROLE:
        band_picks = [p for p in all_picks if p.list_pool_name == list_pool_name]
        if not band_picks:
            bands.append(BandSpend(list_pool_name, 0, 0, None, 0, None))
            continue
        top = max(band_picks, key=lambda p: p.bid_amount)
        worst_case_total += top.bid_amount
        first = min(band_picks, key=lambda p: p.preference_rank)
        first_choice_total += first.bid_amount
        bands.append(
            BandSpend(list_pool_name, len(band_picks), top.bid_amount, top.player_code, first.bid_amount, first.player_code)
        )

    margin = g2_available - worst_case_total
    first_choice_margin = g2_available - first_choice_total

    # Slots G2 can't fill at all (a band gives at most 1 player, 3 midfielder
    # bands + 2 forward bands = 3 MID + 2 FWD max), regardless of what's drafted --
    # informational context, not a hard constraint checked here (G3/G4/completamento
    # cover the rest, see docs/AUCTION_RULES.md).
    slots = remaining_roster_slots(team_state, ruleset)
    g2_role_cap = {"C": 3, "A": 2}
    slots_not_covered = {
        role: max(0, need - g2_role_cap.get(role, 0)) for role, need in slots.items() if role in g2_role_cap
    }

    explanation = [
        f"Budget G2 disponibile: {g2_available}",
        "Spesa peggiore per fascia = offerta massima tra le preferenze inserite (si vince al più 1 "
        "giocatore per fascia): " + ", ".join(f"{b.list_pool_name}={b.max_bid}" for b in bands),
        f"Spesa peggiore totale G2 = {worst_case_total}",
        f"Margine (caso peggiore) = {g2_available} - {worst_case_total} = {margin}"
        + (" (OK)" if margin >= 0 else " (SFORAMENTO)"),
        f"Spesa se vinci sempre la preferenza #1 di ogni fascia = {first_choice_total}",
        f"Margine (tutte prime scelte) = {g2_available} - {first_choice_total} = {first_choice_margin}"
        + (" (OK)" if first_choice_margin >= 0 else " (SFORAMENTO)"),
    ]
    for role, missing in slots_not_covered.items():
        if missing > 0:
            explanation.append(
                f"Anche vincendo tutte le fasce disponibili, restano {missing} slot di ruolo {role!r} "
                "scoperti da G2: arriveranno da G3/G4/completamento finale."
            )

    return G2FeasibilityReport(
        team_id=team_id,
        g2_budget_available=g2_available,
        worst_case_total_spend=worst_case_total,
        margin=margin,
        ok=margin >= 0,
        first_choice_total_spend=first_choice_total,
        first_choice_margin=first_choice_margin,
        first_choice_ok=first_choice_margin >= 0,
        bands=tuple(bands),
        slots_not_covered_by_g2=slots_not_covered,
        explanation=tuple(explanation),
    )


@dataclass(frozen=True)
class DownstreamProjection:
    scenario_label: str
    g2_spend: int
    g2_remaining: int
    g3_g4_budget: int  # remaining_G2 + G3's own budget_increment (read from config)
    slots_won_in_g2: int
    slots_still_needed: int
    min_required_credits: int  # cheapest N still-undrafted players' quotazione, N = slots_still_needed
    shortfall: int  # g3_g4_budget - min_required_credits; negative = can't even afford minimums
    ok: bool
    explanation: tuple[str, ...] = ()


def project_downstream_budget(
    team_id: str,
    ruleset: Ruleset,
    league_state: LeagueState,
    scenario_label: str,
    g2_scenario_spend: int,
    g2_scenario_won_player_codes: list[int],
    undrafted_pool: pd.DataFrame,
) -> DownstreamProjection:
    """Projects whether, after a hypothetical G2 outcome, there's enough budget
    left to complete the roster in G3/G4. G3/G4 have `minimum_bid_source:
    player_quotazione` (config/auction_rules.v1.yaml) -- unlike G1/G2's
    self-declared list minimum, you literally cannot bid below a player's own
    `quotazione_asta` there, so the floor check uses real quotazioni, not a
    flat 1-credit-per-slot rule (that rule is G1/G2-specific, see
    `bid_recommendation.py`).

    `undrafted_pool` must have `player_code`/`quotazione_asta` columns and
    already exclude every player the real ledger shows as assigned (same
    contract as `bid_recommendation.recommend_max_bid`'s `undrafted_pool`).
    `g2_scenario_won_player_codes` are excluded too, since the scenario assumes
    they're gone from the pool by the time G3 opens.
    """
    team_state = league_state.team(team_id)
    g2_available = budget_available_for_round(team_state, "G2", ruleset)
    g2_remaining = g2_available - g2_scenario_spend

    g3_increment = ruleset.round_by_id("G3").budget_increment
    g3_g4_budget = g2_remaining + g3_increment

    slots = remaining_roster_slots(team_state, ruleset)
    total_needed = sum(slots.values())
    slots_won = len(g2_scenario_won_player_codes)
    slots_still_needed = max(0, total_needed - slots_won)

    won_as_str = {str(p) for p in g2_scenario_won_player_codes}
    pool = undrafted_pool[~undrafted_pool["player_code"].astype(str).isin(won_as_str)]
    cheapest = pool.sort_values("quotazione_asta").head(slots_still_needed)
    min_required = int(cheapest["quotazione_asta"].sum()) if slots_still_needed > 0 else 0

    shortfall = g3_g4_budget - min_required

    explanation = [
        f"Scenario {scenario_label!r}: spesa G2 = {g2_scenario_spend}, residuo dopo G2 = {g2_available} - "
        f"{g2_scenario_spend} = {g2_remaining}",
        f"Budget G3+G4 (stesso monte, G4 = residuo G3) = residuo G2 + {g3_increment} = {g3_g4_budget}",
        f"Slot ancora da riempire dopo lo scenario G2 (vinti {slots_won}): {slots_still_needed}",
        f"Minimo richiesto per riempirli = somma delle {slots_still_needed} quotazioni più basse ancora "
        f"libere = {min_required} (G3/G4: il minimo d'offerta è la quotazione, non 1 credito)",
        f"Margine G3/G4 = {g3_g4_budget} - {min_required} = {shortfall}"
        + (" (OK)" if shortfall >= 0 else " (NON BASTA: rivedi le offerte G2 o punta giocatori più economici)"),
    ]

    return DownstreamProjection(
        scenario_label=scenario_label,
        g2_spend=g2_scenario_spend,
        g2_remaining=g2_remaining,
        g3_g4_budget=g3_g4_budget,
        slots_won_in_g2=slots_won,
        slots_still_needed=slots_still_needed,
        min_required_credits=min_required,
        shortfall=shortfall,
        ok=shortfall >= 0,
        explanation=tuple(explanation),
    )
