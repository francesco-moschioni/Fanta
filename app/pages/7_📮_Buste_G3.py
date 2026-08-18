"""Buste G3: componi la busta libera della fase finale (docs/CURRENT_TASK.md
2026-08-18) e verifica la fattibilità di budget.

A differenza di G2 (fasce, preferenza-poi-offerta, si vince al più UN
giocatore per fascia), in G3 non ci sono liste: fino a
`max_players_this_phase` (config) giocatori liberi qualsiasi, un'offerta
secca ciascuno, ognuna indipendente dalle altre -- potenzialmente si vincono
TUTTI. Il minimo d'offerta è la quotazione del giocatore, non 1 credito. Come
per le buste G2, questa pagina è solo pianificazione: salvare una busta qui
non tocca il ledger reale, il budget o la rosa -- lo stato reale continua a
leggersi solo da `domain.replay()` sugli eventi effettivamente registrati in
Squadre.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from fantacalcio.auction.g3_envelope_feasibility import check_pick_feasibility, summarize_g3_feasibility
from fantacalcio.auction.g3_simulation import simulate_opponent_competition, win_probability_for_bid
from fantacalcio.auction.market_model import team_preference_profiles
from fantacalcio.config import load_ruleset
from fantacalcio.persistence.g3_envelopes_store import connect as connect_envelopes, list_picks, remove_pick, save_pick
from fantacalcio.persistence.ledger_store import connect as connect_ledger, load_current_league_state, load_events
from fantacalcio.persistence.player_table import connect as connect_players, get_player, search_players
from fantacalcio.persistence.team_labels_store import connect as connect_labels, display_name, get_all_labels

st.set_page_config(page_title="Fantacalcio — Buste G3", page_icon="📮", layout="wide")
st.title("Buste G3")

RULESET_PATH = Path("config/auction_rules.v1.yaml")
ruleset = load_ruleset(RULESET_PATH)
ledger_conn = connect_ledger()
envelope_conn = connect_envelopes()
player_conn = connect_players()
labels_conn = connect_labels()

MAX_PLAYERS = ruleset.round_by_id("G3").max_players_this_phase

st.markdown(
    f"G3 è la fase a busta chiusa **senza liste**: scegli fino a **{MAX_PLAYERS} giocatori liberi** "
    f"qualsiasi tra chi resta non assegnato, un'offerta secca ciascuno. Ogni offerta è indipendente "
    f"dalle altre — potenzialmente vinci tutti e {MAX_PLAYERS} i giocatori, non al più uno come in G2. "
    "Il minimo d'offerta è la **quotazione** del giocatore, non 1 credito. Nessuna offerta qui è reale "
    "finché non registri il risultato in Squadre."
)

TEAM_IDS = [f"team_{i:02d}" for i in range(1, ruleset.teams + 1)]
my_team_id = st.session_state.get("my_team_id", TEAM_IDS[0])
st.caption(f"Squadra: **{display_name(my_team_id, get_all_labels(labels_conn))}** (cambiala nella Home)")

league_state = load_current_league_state(ledger_conn, ruleset)
picks = list_picks(envelope_conn, my_team_id)
all_events = load_events(ledger_conn)
opponent_ids = [t for t in TEAM_IDS if t != my_team_id]
all_players_for_sim = search_players(player_conn)
undrafted_for_sim = all_players_for_sim[
    ~all_players_for_sim["player_code"].astype(str).isin(league_state.assigned_players)
]

PREFERENCE_HISTORY_PATH = Path("data/curated/preference_bid_history/preference_bids.csv")


@st.cache_data(ttl=600)
def _load_preference_profiles(_player_conn, csv_mtime: float):
    """Cached on the CSV's mtime: recomputes only when the curated file
    actually changes (a fresh ingest run), not on every widget rerun --
    per-row DB lookups over ~600 rows made this a multi-second cost otherwise."""
    history = pd.read_csv(PREFERENCE_HISTORY_PATH)
    return {p.team_id: p for p in team_preference_profiles(history, _player_conn)}


preference_profiles = (
    _load_preference_profiles(player_conn, PREFERENCE_HISTORY_PATH.stat().st_mtime)
    if PREFERENCE_HISTORY_PATH.is_file() else {}
)

report = summarize_g3_feasibility(my_team_id, ruleset, league_state, picks)

st.subheader("Fattibilità G3")
col1, col2, col3 = st.columns(3)
col1.metric("Budget G3 disponibile", report.g3_budget_available)
col2.metric("Spesa peggiore (vinci tutto)", report.worst_case_total_spend)
col3.metric("Margine (caso peggiore)", report.margin, delta_color="normal" if report.ok else "inverse")
if report.ok:
    st.success("Anche vincendo TUTTE le offerte in busta, la spesa sta nel budget G3.")
else:
    st.error(f"Sforamento di {-report.margin} crediti se vincessi tutte le offerte: abbassa qualche offerta o rimuovine una.")
with st.expander("Come è calcolato (G3)"):
    for line in report.explanation:
        st.markdown(f"- {line}")

st.divider()
st.subheader("Busta")

if picks:
    st.caption(f"{len(picks)}/{MAX_PLAYERS or '—'} offerte salvate")
    for pick in picks:
        player_row = get_player(player_conn, pick.player_code)
        name = player_row["display_name"] if player_row is not None else str(pick.player_code)
        pcol1, pcol2, pcol3 = st.columns([3, 1, 1])
        pcol1.write(name)
        pcol2.write(f"{pick.bid_amount} crediti")
        if pcol3.button("Rimuovi", key=f"remove_g3_{pick.player_code}"):
            remove_pick(envelope_conn, my_team_id, pick.player_code)
            st.rerun()
        if player_row is not None:
            sim = simulate_opponent_competition(
                player_row, ruleset, league_state, player_conn, all_events, opponent_ids, undrafted_for_sim,
                preference_profiles=preference_profiles,
            )
            win_prob = win_probability_for_bid(sim, pick.bid_amount)
            st.caption(
                f"Simulazione: con {pick.bid_amount} crediti, probabilità stimata di vincere **{win_prob:.0%}** "
                f"({sim.n_eligible_opponents} avversari eleggibili, offerta avversaria mediana simulata "
                f"{sim.max_opponent_bid_p50}, 90° percentile {sim.max_opponent_bid_p90})."
            )
            with st.expander(f"Come è simulato — {name}"):
                for line in sim.explanation:
                    st.markdown(f"- {line}")
else:
    st.caption("Nessuna offerta salvata.")

if MAX_PLAYERS is not None and len(picks) >= MAX_PLAYERS:
    st.info(f"Busta completa ({MAX_PLAYERS}/{MAX_PLAYERS}). Rimuovi un'offerta per aggiungerne un'altra.")
else:
    all_players = search_players(player_conn)
    undrafted = all_players[~all_players["player_code"].astype(str).isin(league_state.assigned_players)]
    already_picked = {p.player_code for p in picks}
    undrafted = undrafted[~undrafted["player_code"].astype(int).isin(already_picked)]

    if undrafted.empty:
        st.warning("Nessun giocatore libero disponibile.")
    else:
        options = {
            f"{row.display_name} ({row.team_name}, {row.role}) — quot. {row.quotazione_asta:.0f}": row
            for row in undrafted.sort_values("quotazione_asta", ascending=False).itertuples(index=False)
        }
        choice_label = st.selectbox("Giocatore", list(options.keys()), key="select_g3")
        row = options[choice_label]
        player_row_candidate = get_player(player_conn, int(row.player_code))
        min_bid = int(player_row_candidate["quotazione_asta"]) if player_row_candidate is not None else 1
        bid_amount = st.number_input("Offerta (crediti)", min_value=1, value=max(1, min_bid), key="bid_g3")

        if player_row_candidate is not None:
            sim = simulate_opponent_competition(
                player_row_candidate, ruleset, league_state, player_conn, all_events, opponent_ids, undrafted_for_sim,
                preference_profiles=preference_profiles,
            )
            win_prob = win_probability_for_bid(sim, int(bid_amount))
            st.info(
                f"Simulazione: con {int(bid_amount)} crediti, probabilità stimata di vincere **{win_prob:.0%}** "
                f"({sim.n_eligible_opponents} avversari eleggibili, offerta avversaria mediana simulata "
                f"{sim.max_opponent_bid_p50}, 90° percentile {sim.max_opponent_bid_p90}, probabilità che "
                f"nessuno faccia offerta {sim.prob_no_competition:.0%})."
            )
            with st.expander("Come è simulato"):
                for line in sim.explanation:
                    st.markdown(f"- {line}")

        if st.button("Aggiungi alla busta", key="add_g3_pick"):
            result = check_pick_feasibility(
                my_team_id, int(row.player_code), row.role, int(bid_amount), player_row_candidate, ruleset,
                league_state, picks,
            )
            if not result.ok:
                st.error(result.reason)
            else:
                save_pick(envelope_conn, my_team_id, int(row.player_code), row.role, int(bid_amount))
                st.rerun()
