"""Ricerca/filtri + scheda giocatore (docs/UX_PRODUCT.md, area "Giocatori", P0).

Sola lettura: legge la tabella DuckDB già costruita da
scripts/build_player_table.py, non ricalcola nulla (CLAUDE.md: la UI non
duplica formule del motore). Campi non ancora disponibili in questa slice sono
mostrati esplicitamente come tali, mai inventati.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from fantacalcio.persistence.player_table import (
    DEFAULT_DB_PATH,
    connect,
    distinct_values,
    get_build_meta,
    search_players,
)

st.set_page_config(page_title="Fantacalcio — Giocatori", layout="wide")
st.title("Giocatori")

if not DEFAULT_DB_PATH.is_file():
    st.error("Tabella locale non trovata. Esegui `python scripts/build_player_table.py` prima.")
    st.stop()


@st.cache_resource
def _get_connection():
    return connect()


conn = _get_connection()
meta = get_build_meta(conn)
st.caption(
    f"Dati costruiti il {meta.get('built_at', '?')[:19]} UTC da "
    f"`{meta.get('source_path', '?')}` — lista **provvisoria** del modello, non quella "
    "ufficiale dell'admin."
)

TIER_LABELS = {
    "full_history": "Storico completo",
    "partial_history": "Storico parziale",
    "no_history_transfer": "Zero storico — trasferimento reale (cautela)",
    "no_history_new_team": "Zero storico — squadra neopromossa",
}

with st.sidebar:
    st.header("Filtri")
    name_query = st.text_input("Cerca per nome")
    role = st.selectbox("Ruolo", ["Tutti"] + distinct_values(conn, "role"))
    team_name = st.selectbox("Squadra", ["Tutte"] + distinct_values(conn, "team_name"))
    round_pool = st.selectbox("Round pool", ["Tutti"] + distinct_values(conn, "round_pool"))
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
    "round_pool": "Round",
    "data_quality_tier": "Qualità dati",
}
table = results[list(display_cols.keys())].rename(columns=display_cols)
st.dataframe(table, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Scheda giocatore")

if results.empty:
    st.write("Nessun giocatore corrisponde ai filtri.")
    st.stop()

options = {f"{r.display_name} ({r.team_name}, {r.role})": r.player_code for r in results.itertuples(index=False)}
selected_label = st.selectbox("Seleziona un giocatore", list(options.keys()))
player = results[results["player_code"] == options[selected_label]].iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("Fantavoto atteso (media simulata)", f"{player['sim_mean']:.2f}")
col2.metric("Mediana", f"{player['sim_median']:.2f}")
col3.metric("P10 – P90", f"{player['sim_p10']:.2f} – {player['sim_p90']:.2f}")

col4, col5, col6 = st.columns(3)
col4.metric("Valore sopra replacement (VAR)", f"{player['var_mean']:.2f}")
col5.metric("VAR range (P10–P90)", f"{player['var_p10']:.2f} – {player['var_p90']:.2f}")
col6.metric("Quotazione asta", f"{player['quotazione_asta']}")

st.markdown(f"**Round pool**: {player['round_pool']} ({player['list_pool_name']}) — lista `{player['list_state']}`")
st.markdown(f"**Qualità dati**: {TIER_LABELS.get(player['data_quality_tier'], player['data_quality_tier'])}")
st.markdown(f"**Partite nello storico usate dal modello**: {int(player['player_games_in_pool'])}")

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

with st.expander("Non ancora disponibile in questa vista"):
    st.write(
        "- Offerta consigliata / massimo dinamico: richiedono il ledger vivo dell'asta "
        "(collegamento previsto in una slice M4 successiva).\n"
        "- Probabilità di voto (rischio SV): non ancora esposta in questa tabella.\n"
        "- Valore marginale per la propria rosa, compatibilità slot/moduli: richiedono "
        "il costruttore rosa (fuori scope in questa slice).\n"
        "- Confronto con fino a tre alternative: non ancora implementato."
    )
