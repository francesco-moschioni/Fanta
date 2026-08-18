"""Feasibility checks for G3 sealed-bid free-choice envelope drafts: up to
`max_players_this_phase` (config, e.g. 6) independent player picks, no lists,
no preference ranking, highest bid per player wins
(`config/auction_rules.v1.yaml`: mode `sealed_bid_free`, `resolution_priority:
highest_bid`). Pure functions, no I/O -- same split as
`g2_envelope_feasibility.py`/`lock_feasibility.py`.

Worst-case G3 spend modeling is the opposite of G2's: G2 bands cap you at
winning 1 player per band (worst case = MAX bid in the band); G3 has no such
cap -- each pick is an independent bid against a different set of
competitors, so you could plausibly win every single one. Worst-case spend is
therefore the SUM of all drafted bids, not the max.

G3/G4's minimum bid is the player's own `effective_quotazione`
(`minimum_bid_source: player_quotazione` in config), unlike G1/G2's
self-declared list minimum -- same fact already relied on in
`g2_envelope_feasibility.project_downstream_budget`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Ruleset
from ..domain import LeagueState
from ..persistence.g3_envelopes_store import G3EnvelopePick
from ..persistence.player_table import effective_quotazione
from .bid_recommendation import VOTI_TO_DOMAIN_ROLE, budget_available_for_round


@dataclass(frozen=True)
class PickFeasibilityResult:
    ok: bool
    reason: str | None = None


def check_pick_feasibility(
    team_id: str,
    player_code: int,
    role: str,
    bid_amount: int,
    player_row,
    ruleset: Ruleset,
    league_state: LeagueState,
    existing_picks: list[G3EnvelopePick],
) -> PickFeasibilityResult:
    """`player_row` is the resolved player's row from the player table
    (needed for its `effective_quotazione` minimum-bid floor). `existing_picks`
    should be this team's current G3 draft (`g3_envelopes_store.list_picks`)."""
    if role not in VOTI_TO_DOMAIN_ROLE:
        return PickFeasibilityResult(ok=False, reason=f"Ruolo {role!r} sconosciuto.")

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

    if any(p.player_code == player_code for p in existing_picks):
        return PickFeasibilityResult(ok=False, reason="Il giocatore è già presente nella busta G3 di questa squadra.")

    max_players = ruleset.round_by_id("G3").max_players_this_phase
    if max_players is not None and len(existing_picks) >= max_players:
        return PickFeasibilityResult(
            ok=False,
            reason=f"La busta G3 ha già {max_players} giocatori (il massimo consentito): rimuovine uno per farne spazio.",
        )

    min_bid = effective_quotazione(player_row)
    if bid_amount < min_bid:
        return PickFeasibilityResult(
            ok=False,
            reason=f"L'offerta minima per questo giocatore in G3/G4 è la sua quotazione ({min_bid}), non 1 credito: "
            f"{bid_amount} non è sufficiente.",
        )

    return PickFeasibilityResult(ok=True)


@dataclass(frozen=True)
class G3FeasibilityReport:
    team_id: str
    g3_budget_available: int
    n_picks: int
    max_players_this_phase: int | None
    worst_case_total_spend: int  # sum of ALL drafted bids -- you could win every one
    margin: int
    ok: bool
    picks: tuple[G3EnvelopePick, ...] = field(default_factory=tuple)
    explanation: tuple[str, ...] = ()


def summarize_g3_feasibility(
    team_id: str,
    ruleset: Ruleset,
    league_state: LeagueState,
    picks: list[G3EnvelopePick],
) -> G3FeasibilityReport:
    team_state = league_state.team(team_id)
    g3_available = budget_available_for_round(team_state, "G3", ruleset)
    max_players = ruleset.round_by_id("G3").max_players_this_phase

    worst_case_total = sum(p.bid_amount for p in picks)
    margin = g3_available - worst_case_total

    explanation = [
        f"Budget G3 disponibile: {g3_available}",
        f"In G3 non ci sono liste/fasce: ogni offerta è indipendente, potenzialmente si vincono tutti i "
        f"{len(picks)} giocatori in busta -- la spesa peggiore è la SOMMA di tutte le offerte, non il massimo.",
        "Offerte in busta: " + (", ".join(f"{p.player_code}={p.bid_amount}" for p in picks) if picks else "nessuna"),
        f"Spesa peggiore totale = {worst_case_total}",
        f"Margine (caso peggiore, vinci tutto) = {g3_available} - {worst_case_total} = {margin}"
        + (" (OK)" if margin >= 0 else " (SFORAMENTO)"),
    ]
    if max_players is not None:
        explanation.append(f"Massimo giocatori acquistabili in G3: {max_players} (da config).")

    return G3FeasibilityReport(
        team_id=team_id,
        g3_budget_available=g3_available,
        n_picks=len(picks),
        max_players_this_phase=max_players,
        worst_case_total_spend=worst_case_total,
        margin=margin,
        ok=margin >= 0,
        picks=tuple(picks),
        explanation=tuple(explanation),
    )
