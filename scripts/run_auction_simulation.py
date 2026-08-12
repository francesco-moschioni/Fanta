#!/usr/bin/env python3
"""Full 4-round, 20-team auction simulation on the real 2026/27 roster,
exercising the real domain/ledger/bid-recommendation/lock/optimizer code end
to end (docs/CURRENT_TASK.md).

Purpose: stress-test the whole live-auction path before the real auction,
the way ADR-2026-028's cross-team budget bug and ADR-2026-032's goalkeeper
gap were found -- by actually running it, not just unit-testing pieces in
isolation. Uses a throwaway, isolated SQLite database
(data/local/_simulation_ledger.sqlite3), never the user's real
data/local/ledger.sqlite3 -- deleted and rebuilt fresh on every run.

Assignment/pricing here is a deterministic simulation policy for testing
purposes, NOT a claim about how the real sealed-bid auction resolves (that's
admin-decided, preference-then-bid, still blocked -- see
resolve_sealed_bid_round in src/fantacalcio/domain.py). Each team takes its
highest-VAR still-available player in turn, at the price
recommend_max_bid() itself computes -- this doubles as a stress test of that
formula across far more scenarios than the earlier hand-written demo
(scripts/run_m3_bid_recommendation_demo.py) covered.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from fantacalcio.auction.bid_recommendation import (
    BidRecommendationError,
    VOTI_TO_DOMAIN_ROLE,
    recommend_max_bid,
)
from fantacalcio.auction.lock_feasibility import check_lock_feasibility
from fantacalcio.auction.roster_optimizer import Candidate, optimize_roster_completion
from fantacalcio.config import ConfigError, load_ruleset
from fantacalcio.domain import (
    AssignmentEvent,
    AssignmentItem,
    BudgetAdjustmentEvent,
    DomainError,
    Role,
    effective_events,
    replay,
)
from fantacalcio.ledger_io import event_to_dict
from fantacalcio.persistence.ledger_store import append_event, connect as connect_ledger, load_events
from fantacalcio.persistence.locks_store import add_lock, connect as connect_locks, list_locks

RULESET_PATH = Path("config/auction_rules.v1.yaml")
PLAYER_CSV = Path("data/staged/fantacalcio_voti_manual/_m3_replacement_values.csv")
SIM_DB_PATH = Path("data/local/_simulation_ledger.sqlite3")
SIM_LOCKS_DB_PATH = Path("data/local/_simulation_locks.sqlite3")
REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_auction_simulation_report.md")

ROLE_TARGET_FIELD = {"P": "goalkeeper_block_size", "D": "defenders", "C": "midfielders", "A": "forwards"}


class SimulationError(RuntimeError):
    pass


def _fresh_db(path: Path) -> None:
    if path.is_file():
        path.unlink()


def _team_ids(n: int) -> list[str]:
    return [f"team_{i:02d}" for i in range(1, n + 1)]


def _assign_goalkeeper_blocks(pool: pd.DataFrame, team_ids: list[str], ruleset) -> tuple[list[dict], list[str]]:
    """Greedy same-club-first assignment. Returns (assignments, notes) where
    each assignment is {"team_id", "player_codes", "team_name"} and notes
    records any team that couldn't get a same-club triplet (real 2026/27 data
    finding: only 59 goalkeepers exist for 60 needed slots, and at least two
    clubs have only 2 real goalkeepers listed -- see the run's report)."""
    block_size = ruleset.roster.goalkeeper_block_size
    gk = pool[pool["role"] == "P"].sort_values("var_mean", ascending=False).copy()
    by_club: dict[str, list[dict]] = {}
    for row in gk.itertuples(index=False):
        by_club.setdefault(row.team_name, []).append({"player_code": row.player_code, "var_mean": row.var_mean})

    same_club_clubs = sorted(
        (club for club, players in by_club.items() if len(players) >= block_size),
        key=lambda c: -max(p["var_mean"] for p in by_club[c]),
    )

    assignments = []
    notes = []
    used_codes: set[int] = set()
    team_iter = iter(team_ids)

    for club in same_club_clubs:
        team_id = next(team_iter, None)
        if team_id is None:
            break
        chosen = sorted(by_club[club], key=lambda p: -p["var_mean"])[:block_size]
        assignments.append({"team_id": team_id, "player_codes": [c["player_code"] for c in chosen], "team_name": club})
        used_codes.update(c["player_code"] for c in chosen)

    remaining_teams = list(team_iter)
    if remaining_teams:
        leftover = gk[~gk["player_code"].isin(used_codes)].sort_values("var_mean", ascending=False)
        leftover_list = [{"player_code": r.player_code, "team_name": r.team_name} for r in leftover.itertuples(index=False)]
        for team_id in remaining_teams:
            if len(leftover_list) < block_size:
                notes.append(
                    f"{team_id}: impossibile formare un blocco portieri completo -- solo "
                    f"{len(leftover_list)} portieri rimasti nel pool (dato reale 2026/27: "
                    f"59 portieri totali per 60 slot richiesti)."
                )
                break
            chosen = leftover_list[:block_size]
            leftover_list = leftover_list[block_size:]
            clubs_involved = sorted({c["team_name"] for c in chosen})
            notes.append(
                f"{team_id}: blocco cross-club (nessun club con {block_size} portieri liberi rimasti) "
                f"-- {', '.join(clubs_involved)}."
            )
            assignments.append({"team_id": team_id, "player_codes": [c["player_code"] for c in chosen], "team_name": "misto"})

    return assignments, notes


def main() -> None:
    print("=== Simulazione asta completa (4 turni, 20 squadre, dati reali 2026/27) ===\n")
    ruleset = load_ruleset(RULESET_PATH)
    pool = pd.read_csv(PLAYER_CSV)
    team_ids = _team_ids(ruleset.teams)

    _fresh_db(SIM_DB_PATH)
    _fresh_db(SIM_LOCKS_DB_PATH)
    ledger_conn = connect_ledger(SIM_DB_PATH)
    locks_conn = connect_locks(SIM_LOCKS_DB_PATH)

    report: list[str] = ["# Simulazione asta completa — report", ""]
    errors: list[str] = []

    def _current_events():
        return load_events(ledger_conn)

    def _current_state():
        return replay(ruleset, effective_events(_current_events()))

    def _try_append(event) -> bool:
        try:
            replay(ruleset, _current_events() + [event])
        except (DomainError, ConfigError) as exc:
            errors.append(f"[{type(exc).__name__}] {event_to_dict(event)} -> {exc}")
            return False
        append_event(ledger_conn, event)
        return True

    # --- Bonus logo per alcune squadre (prime 5), come nel mondo reale ---
    print("Fase 0: bonus logo personalizzato per le prime 5 squadre...")
    for team_id in team_ids[:5]:
        bonus = BudgetAdjustmentEvent(
            event_id=f"bonus-{team_id}", ts="2026-08-11T00:00:00Z", round_id="G1",
            team_id=team_id, amount=ruleset.custom_logo_bonus_credits, reason="custom_logo_bonus", author="sim",
        )
        if not _try_append(bonus):
            print(f"  [!] Bonus fallito per {team_id}")
    report.append(f"- Bonus logo assegnato a {min(5, len(team_ids))} squadre.")

    # --- G1: blocco portieri ---
    print("\nFase 1: blocchi portieri (G1)...")
    gk_assignments, gk_notes = _assign_goalkeeper_blocks(pool, team_ids, ruleset)
    event_counter = 0
    for a in gk_assignments:
        event_counter += 1
        # Prezzo: quotazione totale del blocco, limitato al budget disponibile.
        rows = pool[pool["player_code"].isin(a["player_codes"])]
        price = int(min(rows["quotazione_asta"].sum(), 200))
        event = AssignmentEvent(
            event_id=f"gk-{event_counter}", ts="2026-08-11T00:00:00Z", round_id="G1",
            team_id=a["team_id"], pool_id="goalkeeper_blocks", role=Role.GK,
            item=AssignmentItem(player_ids=tuple(str(c) for c in a["player_codes"])),
            amount=price, source="simulation", author="sim",
        )
        if not _try_append(event):
            print(f"  [!] Blocco portieri fallito per {a['team_id']}")
    print(f"  {len(gk_assignments)}/{len(team_ids)} squadre con blocco portieri assegnato.")
    for note in gk_notes:
        print(f"  [nota] {note}")
    report.append(f"- Blocchi portieri: {len(gk_assignments)}/{len(team_ids)} squadre coperte.")
    report.extend(f"  - {n}" for n in gk_notes)

    # --- Round di acquisto per ruolo, con prezzo da recommend_max_bid ---
    def _run_role_round(round_id: str, role_code: str, round_pool_label: str, event_prefix: str) -> dict:
        domain_role = VOTI_TO_DOMAIN_ROLE[role_code]
        target = getattr(ruleset.roster, ROLE_TARGET_FIELD[role_code])
        assigned_count = 0
        shortfall_teams = []
        counter = 0
        for pass_num in range(target):  # up to `target` passes, one pickup per team per pass
            # Snake order (alternating direction each pass): a fixed order would let the
            # same early teams win first pick every single pass, systematically
            # disadvantaging the same late teams round after round -- not a claim about
            # the real sealed-bid mechanism (which has no "picks" at all), just a fairer
            # simplification for this simulation.
            pass_order = team_ids if pass_num % 2 == 0 else list(reversed(team_ids))
            for team_id in pass_order:
                state = _current_state()
                if state.team(team_id).role_count(domain_role) >= target:
                    continue
                full_pool = pool[(pool["role"] == role_code) & (pool["round_pool"] == round_pool_label)]
                undrafted = full_pool[~full_pool["player_code"].astype(str).isin(state.assigned_players)]
                if undrafted.empty:
                    shortfall_teams.append(team_id)
                    continue
                target_row = undrafted.sort_values("var_mean", ascending=False).iloc[0]
                pool_df = undrafted[["player_code", "var_mean"]]
                try:
                    rec = recommend_max_bid(
                        state, ruleset, team_id, round_id, int(target_row["player_code"]),
                        float(target_row["var_mean"]), pool_df,
                    )
                except BidRecommendationError:
                    continue  # rosa già piena per quel ruolo o pool esaurito per questa squadra
                except ConfigError as exc:
                    errors.append(f"ConfigError per {team_id}/{round_id}: {exc}")
                    continue
                counter += 1
                event = AssignmentEvent(
                    event_id=f"{event_prefix}-{counter}", ts="2026-08-11T00:00:00Z", round_id=round_id,
                    team_id=team_id, pool_id=target_row["list_pool_name"], role=domain_role,
                    item=AssignmentItem(player_ids=(str(int(target_row["player_code"])),)),
                    amount=max(1, rec.max_bid), source="simulation", author="sim",
                )
                if _try_append(event):
                    assigned_count += 1
        return {"assigned": assigned_count, "shortfall_team_hits": len(set(shortfall_teams))}

    print("\nFase 2: difensori (G1)...")
    d_g1 = _run_role_round("G1", "D", "G1", "d1")
    print(f"  {d_g1['assigned']} difensori assegnati nel pool G1.")

    print("\nFase 3: centrocampisti e attaccanti (G2)...")
    c_g2 = _run_role_round("G2", "C", "G2", "c2")
    print(f"  {c_g2['assigned']} centrocampisti assegnati nel pool G2.")
    a_g2 = _run_role_round("G2", "A", "G2", "a2")
    print(f"  {a_g2['assigned']} attaccanti assegnati nel pool G2 (squadre senza disponibilità: {a_g2['shortfall_team_hits']}).")

    print("\nFase 4: tutti i ruoli rimanenti (G3/G4)...")
    d_g3 = _run_role_round("G3", "D", "G3_G4", "d3")
    c_g3 = _run_role_round("G3", "C", "G3_G4", "c3")
    a_g3 = _run_role_round("G3", "A", "G3_G4", "a3")
    d_g4 = _run_role_round("G4", "D", "G3_G4", "d4")
    c_g4 = _run_role_round("G4", "C", "G3_G4", "c4")
    a_g4 = _run_role_round("G4", "A", "G3_G4", "a4")
    print(f"  G3: {d_g3['assigned']} D, {c_g3['assigned']} C, {a_g3['assigned']} A.")
    print(f"  G4: {d_g4['assigned']} D, {c_g4['assigned']} C, {a_g4['assigned']} A.")

    report.append(
        f"- Difensori: {d_g1['assigned']} (G1) + {d_g3['assigned']} (G3) + {d_g4['assigned']} (G4) = "
        f"{d_g1['assigned'] + d_g3['assigned'] + d_g4['assigned']} / {ruleset.teams * ruleset.roster.defenders} attesi."
    )
    report.append(
        f"- Centrocampisti: {c_g2['assigned']} (G2) + {c_g3['assigned']} (G3) + {c_g4['assigned']} (G4) = "
        f"{c_g2['assigned'] + c_g3['assigned'] + c_g4['assigned']} / {ruleset.teams * ruleset.roster.midfielders} attesi."
    )
    total_a = a_g2["assigned"] + a_g3["assigned"] + a_g4["assigned"]
    report.append(
        f"- Attaccanti: {a_g2['assigned']} (G2) + {a_g3['assigned']} (G3) + {a_g4['assigned']} (G4) = "
        f"{total_a} / {ruleset.teams * ruleset.roster.forwards} attesi "
        f"(carenza reale nota, ADR-2026-019: solo {88} disponibili nel listone contro {ruleset.teams * ruleset.roster.forwards} richiesti)."
    )

    # --- Verifica invarianti ---
    print("\n=== Verifica invarianti ===")
    final_state = _current_state()
    invariant_failures = []

    for team_id in team_ids:
        team = final_state.team(team_id)
        for round_id, budget in team.budgets.items():
            if budget.spent > budget.available:
                invariant_failures.append(f"{team_id}/{round_id}: speso {budget.spent} > disponibile {budget.available}")
            if budget.remaining < 0:
                invariant_failures.append(f"{team_id}/{round_id}: budget residuo negativo ({budget.remaining})")
        for role, cap_field in [(Role.DEF, "defenders"), (Role.MID, "midfielders"), (Role.FWD, "forwards")]:
            cap = getattr(ruleset.roster, cap_field)
            if team.role_count(role) > cap:
                invariant_failures.append(f"{team_id}: ruolo {role.value} supera il tetto ({team.role_count(role)} > {cap})")

    all_assigned = list(final_state.assigned_players)
    if len(all_assigned) != len(set(all_assigned)):
        invariant_failures.append("Giocatore assegnato più di una volta (duplicato in assigned_players).")

    replay_a = replay(ruleset, effective_events(_current_events()))
    replay_b = replay(ruleset, effective_events(_current_events()))
    if replay_a.assigned_players != replay_b.assigned_players:
        invariant_failures.append("Replay non deterministico: due repliche dello stesso ledger danno risultati diversi.")

    if invariant_failures:
        print(f"  [!] {len(invariant_failures)} invarianti violati:")
        for f in invariant_failures:
            print(f"    - {f}")
    else:
        print("  Tutti gli invarianti rispettati: budget mai negativo/sforato, nessun ruolo oltre il tetto, nessun doppio acquisto, replay deterministico.")
    report.append("")
    report.append(f"## Invarianti: {'FALLITI' if invariant_failures else 'tutti rispettati'}")
    report.extend(f"- {f}" for f in invariant_failures)

    if errors:
        print(f"\n  {len(errors)} eventi rifiutati durante la simulazione (attesi: pool/slot pieni, non errori):")
        for e in errors[:10]:
            print(f"    - {e}")
        if len(errors) > 10:
            print(f"    ... e altri {len(errors) - 10}")

    # --- Test lock + fattibilità su una squadra reale ---
    print("\n=== Test lock e fattibilità (team_01) ===")
    test_team = team_ids[0]
    state_now = _current_state()
    still_free = pool[~pool["player_code"].astype(str).isin(state_now.assigned_players)]
    if not still_free.empty:
        target_row = still_free.iloc[0]
        feas = check_lock_feasibility(
            test_team, int(target_row["player_code"]), target_row["role"], ruleset, state_now, list_locks(locks_conn, test_team)
        )
        print(f"  Lock su giocatore libero: {'OK' if feas.ok else 'RIFIUTATO: ' + feas.reason}")
        if feas.ok:
            add_lock(locks_conn, test_team, int(target_row["player_code"]), target_row["role"])
        # Cerca specificamente un giocatore assegnato a UN'ALTRA squadra (non
        # test_team stesso) -- altrimenti si rischia di pescare il miglior
        # giocatore in assoluto, che nella simulazione tende a finire proprio a
        # test_team (primo a scegliere), testando per sbaglio il ramo "già nella
        # tua rosa" invece del ramo "assegnato a un'altra squadra".
        other_team = None
        taken_row = None
        for tid in team_ids:
            if tid == test_team:
                continue
            for role_code, domain_role in VOTI_TO_DOMAIN_ROLE.items():
                roster = final_state.team(tid).roster[domain_role]
                if roster:
                    candidate_pid = roster[0]
                    match = pool[pool["player_code"].astype(str) == candidate_pid]
                    if not match.empty:
                        other_team = tid
                        taken_row = match.iloc[0]
                        break
            if other_team:
                break

        if other_team and taken_row is not None:
            feas2 = check_lock_feasibility(
                test_team, int(taken_row["player_code"]), taken_row["role"], ruleset, state_now, list_locks(locks_conn, test_team)
            )
            correct_rejection = not feas2.ok and other_team in (feas2.reason or "")
            print(f"  Lock su giocatore già assegnato (a {other_team}): {'correttamente rifiutato' if not feas2.ok else '[!] ACCETTATO PER ERRORE'}")
            if not correct_rejection:
                invariant_failures.append(
                    f"Lock su giocatore già assegnato a {other_team} non rifiutato correttamente: reason={feas2.reason!r}"
                )
        else:
            print("  [skip] Nessun giocatore assegnato a un'altra squadra trovato per il test.")

    # --- Test ottimizzatore rosa ideale su una squadra con slot davvero mancanti ---
    # Dopo tutti i turni, D/C sono tipicamente al completo per ogni squadra (160/160
    # in entrambi i casi): sceglie dinamicamente la squadra con più slot mancanti in
    # totale, quasi certamente una che non ha completato gli attaccanti (carenza
    # reale nota), invece di una squadra scelta a caso e magari già completa.
    state_now = _current_state()
    needs_by_team = {
        team_id: {
            r: max(0, getattr(ruleset.roster, ROLE_TARGET_FIELD[r]) - state_now.team(team_id).role_count(VOTI_TO_DOMAIN_ROLE[r]))
            for r in ["D", "C", "A"]
        }
        for team_id in team_ids
    }
    opt_team = max(team_ids, key=lambda t: sum(needs_by_team[t].values()))
    print(f"\n=== Test ottimizzatore 'rosa ideale' ({opt_team}, G3) ===")
    opt_team_state = state_now.team(opt_team)
    role_slots_needed = needs_by_team[opt_team]
    g3g4_pool = pool[(pool["round_pool"] == "G3_G4") & (pool["role"].isin(["D", "C", "A"]))]
    g3g4_pool = g3g4_pool[~g3g4_pool["player_code"].astype(str).isin(state_now.assigned_players)]
    candidates = [
        Candidate(player_code=int(r.player_code), role=r.role, var_mean=float(r.var_mean), cost=int(r.quotazione_asta))
        for r in g3g4_pool.itertuples(index=False)
    ]
    from fantacalcio.auction.bid_recommendation import budget_remaining_for_round
    try:
        budget_g3 = budget_remaining_for_round(opt_team_state, "G3", ruleset)
        opt_result = optimize_roster_completion(candidates, role_slots_needed, budget_g3)
        print(f"  Slot cercati: {role_slots_needed}. Budget: {budget_g3}. Selezionati: {len(opt_result.selected)}, VAR totale: {opt_result.total_var:.2f}, costo: {opt_result.total_cost}")
        if opt_result.total_cost > budget_g3:
            invariant_failures.append(f"Ottimizzatore ha superato il budget: costo {opt_result.total_cost} > budget {budget_g3}")
    except ConfigError as exc:
        print(f"  Budget non calcolabile: {exc}")

    lock_opt_failures = [f for f in invariant_failures if "Lock" in f or "Ottimizzatore" in f]
    report.append("")
    report.append(f"## Test lock/fattibilità/ottimizzatore: {'problemi trovati' if lock_opt_failures else 'ok'}")
    report.extend(f"- {f}" for f in lock_opt_failures)

    report.append("")
    report.append(f"## Riepilogo finale: {len(invariant_failures)} problema/i totali" if invariant_failures else "## Riepilogo finale: nessun problema")
    report.extend(f"- {f}" for f in invariant_failures)

    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    print(f"\nReport: {REPORT_PATH}")
    if invariant_failures:
        print("\nDettaglio di tutti i problemi trovati:")
        for f in invariant_failures:
            print(f"  - {f}")

    ledger_conn.close()
    locks_conn.close()
    _fresh_db(SIM_DB_PATH)
    _fresh_db(SIM_LOCKS_DB_PATH)
    print("Database di simulazione temporanei rimossi (mai stato toccato il ledger reale dell'utente).")

    if invariant_failures:
        print(f"\n[!] SIMULAZIONE COMPLETATA CON {len(invariant_failures)} PROBLEMI DA INVESTIGARE.")
        sys.exit(1)
    print("\nSimulazione completata senza violazioni di invarianti.")


if __name__ == "__main__":
    main()
