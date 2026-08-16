"""Confronto giocatori per fase d'asta (docs/UX_PRODUCT.md).

Sola lettura sui numeri già calcolati dal motore (stessa tabella DuckDB delle
altre pagine, nessun ricalcolo qui — CLAUDE.md: la UI non duplica formule del
motore). `round_pool` distingue solo G1 / G2 / G3_G4 nei dati (G3 e G4
condividono lo stesso pool di "tutti i rimanenti", per costruzione del motore:
`src/fantacalcio/auction/round_pools.py`) — lo si dichiara esplicitamente
invece di far finta di avere una separazione G3/G4 che i dati non hanno.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from fantacalcio.persistence.player_table import DEFAULT_DB_PATH, connect, distinct_values, get_build_meta, search_players
from fantacalcio.persistence.team_labels_store import (
    connect as connect_labels,
    load_labels_config,
    seed_missing_labels,
)

RULESET_PATH = Path("config/auction_rules.v1.yaml")

ROLE_LABELS = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}
TIER_LABELS = {
    "full_history": "Storico completo",
    "partial_history": "Storico parziale",
    "no_history_transfer": "Zero storico — trasferimento reale (cautela)",
    "no_history_new_team": "Zero storico — squadra neopromossa",
}
ROUND_POOL_LABELS = {
    "G1": "1° turno (blocco portieri + difensori 1-60)",
    "G2": "2° turno (centrocampisti + attaccanti)",
    "G3_G4": "3°/4° turno (chiunque sia rimasto)",
}
MAX_COMPARE = 6

st.set_page_config(page_title="Fantacalcio — Confronto", page_icon="⚖️", layout="wide")
st.title("⚖️ Confronto giocatori per fase d'asta")
st.markdown(
    "Scegli una fase dell'asta (o guardale tutte insieme) e confronta i "
    "giocatori di quel turno: prima una tabella completa per scorrere tutti "
    "i numeri, poi puoi selezionarne fino a **6** per un confronto fianco a "
    "fianco più leggibile."
)
st.caption(
    "Nota: il 3° e il 4° turno condividono lo stesso insieme di giocatori "
    "\"tutti i rimanenti\" — i dati non distinguono chi finirà esattamente "
    "nel 3° o nel 4°, dipende da cosa resta libero quando si arriva a quel turno."
)

if not DEFAULT_DB_PATH.is_file():
    st.error("Tabella locale non trovata. Esegui `python scripts/build_player_table.py` prima.")
    st.stop()


@st.cache_resource
def _get_connection():
    return connect()


@st.cache_resource
def _get_labels_conn():
    return connect_labels()


conn = _get_connection()
labels_conn = _get_labels_conn()
seed_missing_labels(labels_conn, load_labels_config())
meta = get_build_meta(conn)
st.caption(
    f"Dati costruiti il {meta.get('built_at', '?')[:19]} UTC — alcuni giocatori hanno la "
    "quotazione **ufficiale** dell'admin, altri restano **provvisori** (solo stima del modello)."
)

with st.sidebar:
    st.header("Filtri")
    round_pool = st.selectbox(
        "Turno d'asta",
        ["Tutti"] + distinct_values(conn, "round_pool"),
        format_func=lambda r: ROUND_POOL_LABELS.get(r, r),
    )
    role = st.selectbox("Ruolo", ["Tutti"] + distinct_values(conn, "role"), format_func=lambda r: ROLE_LABELS.get(r, r))
    team_name = st.selectbox("Squadra reale", ["Tutte"] + distinct_values(conn, "team_name"))
    tier = st.selectbox(
        "Qualità dati",
        ["Tutti"] + distinct_values(conn, "data_quality_tier"),
        format_func=lambda t: TIER_LABELS.get(t, t),
    )

results = search_players(
    conn,
    role=None if role == "Tutti" else role,
    team_name=None if team_name == "Tutte" else team_name,
    round_pool=None if round_pool == "Tutti" else round_pool,
    data_quality_tier=None if tier == "Tutti" else tier,
)

st.subheader(f"{len(results)} giocatori in questa fase")

has_admin_columns = "admin_rank" in results.columns

display_cols = {
    "display_name": "Nome",
    "role": "Ruolo",
    "team_name": "Squadra",
    "quotazione_asta": "Quotazione",
    "sim_mean": "Fantavoto atteso",
    "var_mean": "VAR",
    "list_state": "Lista",
    "data_quality_tier": "Qualità dati",
}
if has_admin_columns:
    display_cols["admin_rank"] = "Rank admin"
    display_cols["admin_score"] = "Punteggio admin"

table = results[list(display_cols.keys())].rename(columns=display_cols)
table["Ruolo"] = table["Ruolo"].map(lambda r: ROLE_LABELS.get(r, r))
table["Qualità dati"] = table["Qualità dati"].map(lambda t: TIER_LABELS.get(t, t))
table["Lista"] = table["Lista"].map({"official": "ufficiale", "provisional": "provvisoria"}).fillna(table["Lista"])
st.dataframe(table, width="stretch", hide_index=True)

st.divider()
st.subheader("Confronto fianco a fianco")

if results.empty:
    st.info("Nessun giocatore in questa selezione: allarga i filtri per confrontare qualcuno.")
    st.stop()

default_selection = list(results.sort_values("var_mean", ascending=False)["display_name"].head(3))
selected_names = st.multiselect(
    f"Scegli fino a {MAX_COMPARE} giocatori da mettere fianco a fianco",
    options=list(results["display_name"]),
    default=default_selection,
    max_selections=MAX_COMPARE,
)

if not selected_names:
    st.info("Seleziona almeno un giocatore qui sopra per vedere il confronto.")
    st.stop()

by_name = results[results["display_name"].isin(selected_names)]
# Rispetta l'ordine di selezione dell'utente, non l'ordine del filtro SQL.
# .drop_duplicates tiene la prima riga per nome, nel raro caso di due
# giocatori con lo stesso display_name (non ancora capitato nei dati reali).
by_name = by_name.drop_duplicates(subset="display_name").set_index("display_name")
selected_rows = by_name.loc[selected_names].reset_index()

columns = st.columns(len(selected_rows))
for col, (_, player) in zip(columns, selected_rows.iterrows()):
    with col:
        with st.container(border=True):
            st.markdown(f"#### {player['display_name']}")
            st.caption(f"{ROLE_LABELS.get(player['role'], player['role'])} — {player['team_name']}")
            st.metric("Fantavoto atteso", f"{player['sim_mean']:.2f}")
            st.caption(f"Mediana {player['sim_median']:.2f} · P10–P90 {player['sim_p10']:.2f} – {player['sim_p90']:.2f}")
            st.metric("VAR", f"{player['var_mean']:.2f}")
            st.caption(f"Range VAR {player['var_p10']:.2f} – {player['var_p90']:.2f}")
            st.metric("Quotazione", int(player["quotazione_asta"]))
            if has_admin_columns and pd.notna(player.get("admin_rank")):
                st.caption(f"Lista ufficiale: rank {int(player['admin_rank'])}, punteggio {player['admin_score']:.0f}")
            st.caption(f"Qualità dati: {TIER_LABELS.get(player['data_quality_tier'], player['data_quality_tier'])}")
            st.caption(f"Turno: {ROUND_POOL_LABELS.get(player['round_pool'], player['round_pool'])}")

st.info(
    "Per il tetto massimo di offerta consigliato (dipende dal budget/rosa della "
    "tua squadra) apri il giocatore nella pagina **🔍 Giocatori** — qui il "
    "confronto mostra solo i numeri intrinseci del giocatore, non legati a una squadra."
)
