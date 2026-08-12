"""Ricerca/filtri + scheda giocatore (docs/UX_PRODUCT.md, area "Giocatori", P0).

Sola lettura sui numeri del motore: legge la tabella DuckDB già costruita da
scripts/build_player_table.py, non ricalcola nulla (CLAUDE.md: la UI non
duplica formule del motore). Campi non ancora disponibili sono mostrati
esplicitamente come tali, mai inventati. Passata di chiarezza (M4 slice 7):
ogni pagina spiega in linguaggio semplice cosa fa, in cima, e non mostra mai
un `team_id` grezzo se esiste un'etichetta personale.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from fantacalcio.auction.bid_recommendation import BidRecommendationError, recommend_max_bid
from fantacalcio.auction.lock_feasibility import check_lock_feasibility
from fantacalcio.auction.replacement import league_slots_per_role
from fantacalcio.config import ConfigError, load_ruleset
from fantacalcio.persistence.avoid_list_store import add_avoid, connect as connect_avoid, is_avoided, remove_avoid
from fantacalcio.persistence.ledger_store import connect as connect_ledger, load_current_league_state
from fantacalcio.persistence.locks_store import add_lock, connect as connect_locks, is_locked, list_locks, remove_lock
from fantacalcio.persistence.player_table import (
    DEFAULT_DB_PATH,
    connect,
    distinct_values,
    get_build_meta,
    search_players,
)
from fantacalcio.persistence.team_labels_store import connect as connect_labels, display_name, get_all_labels
from fantacalcio.scoring.monte_carlo import DEFAULT_PRIOR_GAMES, load_calibration_meta

RULESET_PATH = Path("config/auction_rules.v1.yaml")

ROLE_LABELS = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}
TIER_LABELS = {
    "full_history": "Storico completo",
    "partial_history": "Storico parziale",
    "no_history_transfer": "Zero storico — trasferimento reale (cautela)",
    "no_history_new_team": "Zero storico — squadra neopromossa",
}
ROUND_POOL_LABELS = {
    "G1": "1° turno (portieri + difensori)",
    "G2": "2° turno (centrocampisti + attaccanti)",
    "G3_G4": "3°/4° turno (chiunque sia rimasto)",
}

st.set_page_config(page_title="Fantacalcio — Giocatori", layout="wide")
st.title("Giocatori")
st.markdown(
    "Cerca un giocatore, guarda quanto ci si aspetta che renda e quanto vale "
    "rispetto agli altri del suo ruolo (**VAR** = valore sopra il livello di "
    "rimpiazzo — ogni numero ha una spiegazione se ci passi sopra il mouse o "
    "apri il pannello \"come si calcola\"). Da qui puoi anche segnare un "
    "giocatore come tuo **obiettivo** o come uno **da evitare**."
)

if not DEFAULT_DB_PATH.is_file():
    st.error("Tabella locale non trovata. Esegui `python scripts/build_player_table.py` prima.")
    st.stop()


@st.cache_resource
def _get_connection():
    return connect()


@st.cache_resource
def _get_ruleset():
    return load_ruleset(RULESET_PATH)


@st.cache_resource
def _get_locks_conn():
    return connect_locks()


@st.cache_resource
def _get_avoid_conn():
    return connect_avoid()


@st.cache_resource
def _get_ledger_conn():
    return connect_ledger()  # auto-crea un ledger vuoto se non esiste ancora


@st.cache_resource
def _get_labels_conn():
    return connect_labels()


conn = _get_connection()
ruleset = _get_ruleset()
locks_conn = _get_locks_conn()
avoid_conn = _get_avoid_conn()
ledger_conn = _get_ledger_conn()
labels_conn = _get_labels_conn()
league_state = load_current_league_state(ledger_conn, ruleset)
team_labels = get_all_labels(labels_conn)
meta = get_build_meta(conn)
st.caption(
    f"Dati costruiti il {meta.get('built_at', '?')[:19]} UTC — lista **provvisoria** "
    "del modello, non quella ufficiale dell'admin (vedi pagina Home per i dettagli)."
)

with st.sidebar:
    st.header("Filtri")
    name_query = st.text_input("Cerca per nome")
    role = st.selectbox("Ruolo", ["Tutti"] + distinct_values(conn, "role"), format_func=lambda r: ROLE_LABELS.get(r, r))
    team_name = st.selectbox("Squadra reale", ["Tutte"] + distinct_values(conn, "team_name"))
    round_pool = st.selectbox(
        "Turno d'asta",
        ["Tutti"] + distinct_values(conn, "round_pool"),
        format_func=lambda r: ROUND_POOL_LABELS.get(r, r),
    )
    tier = st.selectbox(
        "Qualità dati",
        ["Tutti"] + distinct_values(conn, "data_quality_tier"),
        format_func=lambda t: TIER_LABELS.get(t, t),
    )

results = search_players(
    conn,
    name_query=name_query or None,
    role=None if role == "Tutti" else role,
    team_name=None if team_name == "Tutte" else team_name,
    round_pool=None if round_pool == "Tutti" else round_pool,
    data_quality_tier=None if tier == "Tutti" else tier,
)

st.subheader(f"{len(results)} giocatori")

display_cols = {
    "display_name": "Nome",
    "role": "Ruolo",
    "team_name": "Squadra",
    "quotazione_asta": "Quotazione",
    "sim_mean": "Fantavoto atteso",
    "var_mean": "VAR",
    "round_pool": "Turno",
    "data_quality_tier": "Qualità dati",
}
table = results[list(display_cols.keys())].rename(columns=display_cols)
table["Ruolo"] = table["Ruolo"].map(lambda r: ROLE_LABELS.get(r, r))
table["Turno"] = table["Turno"].map(lambda r: ROUND_POOL_LABELS.get(r, r))
table["Qualità dati"] = table["Qualità dati"].map(lambda t: TIER_LABELS.get(t, t))
st.dataframe(
    table,
    width="stretch",
    hide_index=True,
    column_config={
        "Fantavoto atteso": st.column_config.NumberColumn(
            help="Media delle simulazioni Monte Carlo (bootstrap sulla storia reale del giocatore/ruolo). Dettagli nella scheda sotto."
        ),
        "VAR": st.column_config.NumberColumn(
            help="Valore sopra replacement: fantavoto atteso meno il livello di replacement del ruolo. Dettagli nella scheda sotto."
        ),
    },
)

st.divider()
st.subheader("Scheda giocatore")

if results.empty:
    st.write("Nessun giocatore corrisponde ai filtri.")
    st.stop()

options = {f"{r.display_name} ({r.team_name}, {ROLE_LABELS.get(r.role, r.role)})": r.player_code for r in results.itertuples(index=False)}
selected_label = st.selectbox("Seleziona un giocatore", list(options.keys()))
player = results[results["player_code"] == options[selected_label]].iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric(
    "Fantavoto atteso (media simulata)",
    f"{player['sim_mean']:.2f}",
    help="Media di 1000 simulazioni Monte Carlo (bootstrap su righe storiche reali voto+eventi, non una formula chiusa). Traccia di calcolo sotto.",
)
col2.metric("Mediana", f"{player['sim_median']:.2f}", help="Mediana delle stesse 1000 simulazioni.")
calibration = load_calibration_meta()
if calibration:
    _coverage_pct = calibration["p10_p90_empirical_coverage"]
    p10_p90_help = (
        f"Intervallo tra il 10° e il 90° percentile delle 1000 simulazioni per questo "
        f"giocatore. In un test retrospettivo su {calibration['n_players_validated']} "
        f"giocatori reali (stagione 2025/26, mai vista dal modello), la fantamedia "
        f"reale è caduta in un intervallo P10-P90 così costruito il **{_coverage_pct:.0%}** "
        "delle volte (obiettivo nominale 80%) — usa questo come guida reale alla "
        "precisione, non l'80% nominale come garanzia."
    )
else:
    p10_p90_help = (
        "Intervallo tra il 10° e il 90° percentile delle simulazioni (obiettivo "
        "nominale: 80% degli esiti). Nessun test retrospettivo di calibrazione "
        "disponibile ancora — esegui scripts/run_monte_carlo_fantavoto.py per "
        "generarlo."
    )
col3.metric("P10 – P90", f"{player['sim_p10']:.2f} – {player['sim_p90']:.2f}", help=p10_p90_help)

col4, col5, col6 = st.columns(3)
col4.metric(
    "Valore sopra replacement (VAR)",
    f"{player['var_mean']:.2f}",
    help="Fantavoto atteso meno il livello di replacement del ruolo (il valore del miglior giocatore che NON verrebbe rosterizzato). Traccia di calcolo sotto.",
)
col5.metric(
    "VAR range (P10–P90)",
    f"{player['var_p10']:.2f} – {player['var_p90']:.2f}",
    help="P10/P90 del giocatore meno il livello di replacement medio del ruolo (non una convoluzione completa delle due distribuzioni).",
)
col6.metric("Quotazione asta", f"{player['quotazione_asta']}", help="Quotazione dal listone ufficiale 2026/27 (non calcolata dal modello).")

with st.expander("Come si calcola questo numero? (VAR e fantavoto atteso)"):
    n_own = int(player["player_games_in_pool"])
    weight_own = n_own / (n_own + DEFAULT_PRIOR_GAMES) if n_own > 0 else 0.0
    st.markdown("**Fantavoto atteso (bootstrap Monte Carlo)**")
    if player["used_role_pool_only"]:
        st.markdown(
            f"- {player['display_name']} non ha partite nello storico usato dal modello "
            f"(0 partite): ogni simulazione pesca dal pool generico del ruolo "
            f"{ROLE_LABELS.get(player['role'], player['role'])}, non dalla sua storia (che non esiste)."
        )
    else:
        st.markdown(
            f"- Partite proprie nello storico: **{n_own}**. Peso storia propria = "
            f"n / (n + {DEFAULT_PRIOR_GAMES:.0f}) = {n_own} / ({n_own} + {DEFAULT_PRIOR_GAMES:.0f}) "
            f"= **{weight_own:.1%}** — con questa probabilità ogni simulazione pesca da una "
            f"partita reale di {player['display_name']}, altrimenti dal pool generico del ruolo."
        )
    if player.get("used_fvm_prior"):
        st.markdown(
            "- Storico troppo basso (< 10 partite): il pool generico usato non è la media "
            "piatta di ruolo ma un pool segmentato per FVM (valutazione di mercato Fantacalcio) "
            "— vedi ADR-2026-024."
        )
    adj = pd.to_numeric(player.get("team_strength_adjustment"), errors="coerce")
    if pd.notna(adj) and abs(adj) > 1e-9:
        st.markdown(
            f"- Aggiustamento forza-squadra (Dixon-Coles): **{adj:+.2f}** aggiunto a ogni "
            f"simulazione, perché la squadra attuale ({player['team_name']}) ha una forza "
            "diversa dal contesto-squadra storico medio del giocatore — vedi ADR-2026-023."
        )

    st.markdown("**VAR = fantavoto atteso − livello di replacement**")
    n_slots = league_slots_per_role(ruleset)[player["role"]]
    role_label = ROLE_LABELS.get(player["role"], player["role"])
    st.markdown(
        f"- Livello di replacement per il ruolo {role_label}: fantavoto atteso del "
        f"giocatore classificato esattamente al **{n_slots}° posto** per quel ruolo "
        f"({n_slots} slot totali in lega per questo ruolo) — il miglior giocatore che "
        f"NON verrebbe rosterizzato se ogni squadra pescasse dallo stesso pool ordinato. "
        f"Valore: **{player['replacement_level']:.2f}**."
    )
    st.markdown(
        f"- VAR = {player['sim_mean']:.2f} − {player['replacement_level']:.2f} = "
        f"**{player['var_mean']:.2f}**"
    )
    if bool(player.get("degenerate_replacement")):
        st.warning(
            f"Attenzione: nel listone 2026/27 ci sono **meno giocatori {role_label.lower()} "
            f"disponibili di quanti slot servano** a tutta la lega ({n_slots} richiesti). "
            "Il livello di replacement qui sopra è quindi il peggior giocatore ancora "
            "disponibile, non il miglior giocatore escluso come nelle altre posizioni — "
            "il VAR di tutti i giocatori di questo ruolo è probabilmente sovrastimato "
            "rispetto a un ruolo senza carenza (vedi \"Avvisi di mercato\" in Home)."
        )

st.markdown(
    f"**Turno d'asta**: {ROUND_POOL_LABELS.get(player['round_pool'], player['round_pool'])} "
    f"— lista `{player['list_state']}` (provvisoria del modello)"
)
st.markdown(f"**Qualità dati**: {TIER_LABELS.get(player['data_quality_tier'], player['data_quality_tier'])}")
st.markdown(f"**Partite nello storico usate dal modello**: {int(player['player_games_in_pool'])}")

participation_rate = pd.to_numeric(player.get("participation_rate"), errors="coerce")
if pd.notna(participation_rate):
    season = player.get("participation_season", "?")
    n_seasons = player.get("participation_seasons_of_history")
    st.markdown(
        f"**Probabilità di voto (rischio SV), stima**: {participation_rate:.0%} — "
        f"quota di giornate con voto nell'ultima stagione nota ({season}), "
        f"{int(n_seasons) if pd.notna(n_seasons) else '?'} stagioni di storico disponibili. "
        "Non una previsione di formazione titolare, solo la persistenza storica di essere schierato."
    )
else:
    st.caption(
        "Probabilità di voto (rischio SV): non disponibile, nessuna stagione storica per questo giocatore."
    )

drivers = []
if player.get("used_fvm_prior"):
    drivers.append("Prior FVM usato (basso storico) — vedi ADR-2026-024")

adj = pd.to_numeric(player.get("team_strength_adjustment"), errors="coerce")
if pd.notna(adj) and abs(adj) > 1e-9:
    direction = "positivo" if adj > 0 else "negativo"
    drivers.append(f"Aggiustamento forza-squadra Dixon-Coles: {adj:+.2f} ({direction}) — vedi ADR-2026-023")

if player["data_quality_tier"] == "no_history_transfer":
    drivers.append(
        "[!] Trasferimento reale senza storico Serie A: il VAR qui è un prior debole, "
        "non una stima informata — valutare individualmente prima di puntare."
    )

if drivers:
    st.markdown("**Driver e segnali oggettivi:**")
    for d in drivers:
        st.markdown(f"- {d}")
else:
    st.caption("Nessun driver aggiuntivo oltre allo storico diretto del giocatore.")

my_team_id_for_lock = st.session_state.get("my_team_id", "team_01")
my_team_label = display_name(my_team_id_for_lock, team_labels)
currently_locked = is_locked(locks_conn, my_team_id_for_lock, int(player["player_code"]))
currently_avoided = is_avoided(avoid_conn, my_team_id_for_lock, int(player["player_code"]))

if currently_avoided:
    st.warning(f"Segnato come **da evitare** per {my_team_label}.")

lock_col, avoid_col = st.columns(2)
with lock_col:
    if currently_locked:
        if st.button(f"Sblocca (era obiettivo di {my_team_label})"):
            remove_lock(locks_conn, my_team_id_for_lock, int(player["player_code"]))
            st.success("Sbloccato.")
            st.rerun()
    else:
        if st.button(f"Blocca come obiettivo di {my_team_label}"):
            feasibility = check_lock_feasibility(
                my_team_id_for_lock, int(player["player_code"]), player["role"], ruleset,
                league_state, list_locks(locks_conn, my_team_id_for_lock),
            )
            if not feasibility.ok:
                st.error(f"Blocco non applicato: {feasibility.reason}")
            else:
                add_lock(locks_conn, my_team_id_for_lock, int(player["player_code"]), player["role"])
                st.success(f"Bloccato come obiettivo di {my_team_label}. Vedi pagina **Rosa**.")
                st.rerun()
with avoid_col:
    if currently_avoided:
        if st.button("Rimuovi dalla lista da evitare"):
            remove_avoid(avoid_conn, my_team_id_for_lock, int(player["player_code"]))
            st.success("Rimosso dalla lista da evitare.")
            st.rerun()
    else:
        if st.button("Segna come da evitare"):
            add_avoid(avoid_conn, my_team_id_for_lock, int(player["player_code"]), player["role"])
            st.success(f"Segnato come da evitare per {my_team_label}. Vedi pagina **Rosa**.")
            st.rerun()

st.divider()
st.subheader("Tetto di riferimento (massimo consigliato)")
st.caption(
    "Non è una previsione di chi vincerà: i turni sono a busta chiusa, decisi "
    "dall'admin (preferenza, poi offerta), non un'asta al miglior offerente in "
    "tempo reale. È un tetto di riferimento da scrivere sulla propria lista, "
    "basato sul budget/rosa residui reali (formula dollar-rule, ADR-2026-022)."
)

my_team_id = st.session_state.get("my_team_id", "team_01")
round_pool = player["round_pool"]
round_choice = round_pool
if round_pool == "G3_G4":
    round_choice = st.radio("Quale turno (3° o 4°, condividono lo stesso pool)", ["G3", "G4"], horizontal=True)

pool_df = search_players(conn, role=player["role"], round_pool=round_pool)[["player_code", "var_mean"]]

try:
    rec = recommend_max_bid(
        league_state, ruleset, my_team_id, round_choice, int(player["player_code"]), float(player["var_mean"]), pool_df
    )
except BidRecommendationError as exc:
    st.info(f"Massimo consigliato non disponibile per questo giocatore/squadra: {exc}")
except ConfigError as exc:
    st.info(
        f"Massimo consigliato non disponibile: {my_team_label} non ha ancora eventi registrati "
        f"nel turno precedente necessario per la formula di budget di `{round_choice}` "
        f"({exc}). Registra i risultati dei turni precedenti nella pagina **Squadre** prima."
    )
else:
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Massimo consigliato (tetto)", rec.max_bid,
        help="Formula 'dollar rule' standard delle aste fantasy: budget discrezionale distribuito per quota di VAR positivo. Traccia sotto.",
    )
    c2.metric("Budget residuo squadra", rec.remaining_budget, help=f"Budget rimanente di {my_team_label} per questo turno, dal ledger vivo.")
    c3.metric("Slot ancora da riempire", rec.remaining_slots_total, help="Slot di rosa non ancora coperti, per tutti i ruoli, letti dal ledger vivo.")

    with st.expander("Come si calcola questo numero? (massimo consigliato)"):
        st.markdown(
            f"1. Budget residuo di {my_team_label} per questo turno: **{rec.remaining_budget}**\n"
            f"2. Slot ancora da riempire (incluso questo): **{rec.remaining_slots_total}** → riserva "
            f"1 credito per ciascuno degli altri **{rec.reserve_for_other_slots}** slot\n"
            f"3. Budget discrezionale = {rec.remaining_budget} − {rec.reserve_for_other_slots} = "
            f"**{rec.discretionary_budget}**\n"
            f"4. VAR di {player['display_name']}: **{rec.player_var:.2f}**; somma VAR positivo nel "
            f"pool residuo dello stesso turno/ruolo: **{rec.pool_var_sum:.2f}**\n"
            f"5. Quota VAR = {rec.player_var:.2f} / {rec.pool_var_sum:.2f} = **{rec.var_share:.1%}**\n"
            f"6. Massimo consigliato = 1 + {rec.var_share:.1%} × {rec.discretionary_budget} = "
            f"**{rec.max_bid}**"
        )

with st.expander("Non ancora disponibile in questa vista"):
    st.write(
        "- Valore marginale per la propria rosa (aggiungendo proprio questo giocatore): "
        "vedi invece la sezione **Rosa ideale** nella pagina Rosa, che ottimizza su tutta "
        "la rosa insieme, non giocatore per giocatore.\n"
        "- Compatibilità slot/moduli, confronto con fino a tre alternative: non ancora implementato."
    )
