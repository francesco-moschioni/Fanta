"""Monte Carlo simulation of opponent competition on a single player in G3
(sealed-bid free choice, no lists -- ADR docs/CURRENT_TASK.md 2026-08-18).

G3 has no lists, so who's actually targeting a given player is genuinely
unknown -- there is nothing to look up. This simulates it from real signals
already in the codebase, confirmed with the user 2026-08-18:

1. WHO might bid: any opponent with an open roster slot in the player's role
   is a candidate. The probability a specific candidate bids on THIS specific
   player is approximated as (their remaining open slots in the role) /
   (size of the remaining undrafted pool in that role) -- the expected
   fraction of what's left they'll end up buying, not a guessed "how much
   they like this player" (no data exists for that).
2. HOW MUCH a bidding opponent offers: the player's `effective_quotazione`
   times a price ratio drawn from the same historical inflation cascade
   `bid_recommendation.py` already uses (`market_model.estimate_price_correction`),
   corrected by that specific opponent's own observed aggressiveness
   (`market_model.team_aggressiveness_index`) when there's enough data for
   them individually, otherwise left at the league-wide estimate.
3. UNCERTAINTY: ratios are drawn uniformly from the historical [low, high]
   range already computed by the inflation cascade, not a fabricated
   distribution shape -- consistent with CLAUDE.md's "no invented formulas
   without approval" and the existing "always a range, never a bare point
   estimate" convention in market_model.py.

Deterministic/seeded (CLAUDE.md: simulation must be reproducible) -- same
inputs and seed always produce the same result.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import Ruleset
from ..domain import LeagueState
from ..persistence.player_table import effective_quotazione
from .bid_recommendation import budget_remaining_for_round, remaining_roster_slots
from .market_model import estimate_price_correction, market_regime_ratio, team_aggressiveness_index

DEFAULT_N_SIMULATIONS = 5000
DEFAULT_SEED = 42


@dataclass(frozen=True)
class CompetitionSimulation:
    player_code: int
    voti_role: str
    effective_quotazione: int
    n_simulations: int
    n_eligible_opponents: int  # opponents with an open slot in this role AND enough G3 budget to afford the minimum
    price_correction_source: str
    price_correction_reliable: bool
    prob_no_competition: float  # fraction of simulations where nobody else bids at all
    max_opponent_bid_p10: int
    max_opponent_bid_p50: int
    max_opponent_bid_p90: int
    max_opponent_bid_samples: tuple[int, ...]  # raw per-simulation max opposing bid, for win_probability_for_bid
    explanation: tuple[str, ...]


def win_probability_for_bid(simulation: CompetitionSimulation, candidate_bid: int) -> float:
    """Fraction of simulated scenarios where `candidate_bid` would have beaten
    every opposing bid that materialized. Ties are excluded from a "win"
    (config `sealed_bid_tie_breaker` is explicitly undefined, docs/OPEN_QUESTIONS.md
    -- never assumed to resolve in your favour)."""
    if not simulation.max_opponent_bid_samples:
        return 1.0
    wins = sum(1 for m in simulation.max_opponent_bid_samples if candidate_bid > m)
    return wins / len(simulation.max_opponent_bid_samples)


def simulate_opponent_competition(
    player_row: pd.Series,
    ruleset: Ruleset,
    league_state: LeagueState,
    player_conn,
    all_events: list,
    opponent_ids: list[str],
    undrafted_pool: pd.DataFrame,
    round_id: str = "G3",
    n_simulations: int = DEFAULT_N_SIMULATIONS,
    seed: int = DEFAULT_SEED,
) -> CompetitionSimulation:
    """`undrafted_pool` must have `player_code`/`role` columns and already
    exclude every player the real ledger shows as assigned (same contract as
    `bid_recommendation.recommend_max_bid`'s `undrafted_pool`)."""
    voti_role = player_row["role"]
    quot = effective_quotazione(player_row)

    correction = estimate_price_correction(all_events, player_conn, voti_role, quot, exclude_round_id=round_id)
    if correction is None:
        base_low, base_high, source, reliable = 1.0, 1.0, "nessun dato storico disponibile (nessuna inflazione assunta)", False
    else:
        base_low, base_high = correction.low_ratio, correction.high_ratio
        source, reliable = correction.source, correction.reliable

    regime = market_regime_ratio(all_events, player_conn, exclude_round_id=round_id)
    aggressiveness = team_aggressiveness_index(all_events, player_conn, opponent_ids, exclude_round_id=round_id)

    remaining_pool_size = int((undrafted_pool["role"] == voti_role).sum())

    candidates: list[tuple[str, float, float]] = []  # (team_id, p_bid, team_ratio_multiplier)
    for opponent_id in opponent_ids:
        team_state = league_state.team(opponent_id)
        slots = remaining_roster_slots(team_state, ruleset)
        open_in_role = slots.get(voti_role, 0)
        if open_in_role <= 0:
            continue
        if budget_remaining_for_round(team_state, round_id, ruleset) < quot:
            continue  # can't even afford the minimum bid
        p_bid = min(1.0, open_in_role / remaining_pool_size) if remaining_pool_size > 0 else 0.0
        if p_bid <= 0:
            continue

        team_multiplier = 1.0
        team_agg = aggressiveness.get(opponent_id)
        if team_agg is not None and team_agg.reliable and regime is not None and regime.mean_ratio > 0:
            team_multiplier = team_agg.team_mean_ratio / regime.mean_ratio
        candidates.append((opponent_id, p_bid, team_multiplier))

    rng = np.random.default_rng(seed)
    max_bids: list[int] = []
    no_competition_count = 0
    for _ in range(n_simulations):
        sim_bids = []
        for _team_id, p_bid, team_multiplier in candidates:
            if rng.random() < p_bid:
                ratio = rng.uniform(base_low, base_high) * team_multiplier
                ratio = max(ratio, 1.0)  # can never bid below the player's own quotazione (G3/G4 rule)
                sim_bids.append(round(quot * ratio))
        if sim_bids:
            max_bids.append(max(sim_bids))
        else:
            max_bids.append(0)
            no_competition_count += 1

    max_bids_arr = np.array(max_bids)
    explanation = [
        f"Quotazione effettiva del giocatore: {quot}",
        f"Correzione di inflazione usata: {source}" + ("" if reliable else " (poco affidabile, pochi dati)"),
        f"{len(candidates)} avversari eleggibili (slot di ruolo {voti_role!r} scoperto + budget G3 sufficiente per il minimo) "
        f"su un pool residuo di {remaining_pool_size} giocatori di quel ruolo.",
        f"Probabilità stimata che NESSUN avversario faccia un'offerta su questo giocatore: {no_competition_count / n_simulations:.0%}",
        f"Offerta massima avversaria simulata: mediana {int(np.percentile(max_bids_arr, 50))}, "
        f"90° percentile {int(np.percentile(max_bids_arr, 90))} (su {n_simulations} simulazioni, seed={seed}).",
    ]

    return CompetitionSimulation(
        player_code=int(player_row["player_code"]),
        voti_role=voti_role,
        effective_quotazione=quot,
        n_simulations=n_simulations,
        n_eligible_opponents=len(candidates),
        price_correction_source=source,
        price_correction_reliable=reliable,
        prob_no_competition=no_competition_count / n_simulations,
        max_opponent_bid_p10=int(np.percentile(max_bids_arr, 10)),
        max_opponent_bid_p50=int(np.percentile(max_bids_arr, 50)),
        max_opponent_bid_p90=int(np.percentile(max_bids_arr, 90)),
        max_opponent_bid_samples=tuple(int(m) for m in max_bids),
        explanation=tuple(explanation),
    )
