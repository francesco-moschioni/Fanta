"""Landing page: data freshness/provenance only (docs/UX_PRODUCT.md's "Dati/modello"
row: quanto fidarsi). No forecasts shown here -- that's the Giocatori page."""

from __future__ import annotations

import streamlit as st

from fantacalcio.persistence.player_table import DEFAULT_DB_PATH, connect, get_build_meta

st.set_page_config(page_title="Fantacalcio — Home", layout="wide")

st.title("Fantacalcio auction assistant")
st.caption("Strumento privato di supporto decisionale. Nessun dato viene inviato altrove.")

if not DEFAULT_DB_PATH.is_file():
    st.error(
        "Nessun dato disponibile: la tabella locale non è stata costruita. "
        "Esegui `python scripts/build_player_table.py` (dopo "
        "`scripts/run_monte_carlo_fantavoto.py` e `scripts/run_m3_replacement_values.py` "
        "se non già fatto) e ricarica questa pagina."
    )
    st.stop()

@st.cache_resource
def _get_connection():
    return connect()


conn = _get_connection()
meta = get_build_meta(conn)

st.subheader("Stato dati")
col1, col2, col3 = st.columns(3)
col1.metric("Giocatori nella tabella", meta.get("n_players", "?"))
col2.metric("Costruita il (UTC)", meta.get("built_at", "?")[:19])
col3.metric("Fonte", "M3 replacement values")

st.caption(f"Hash sorgente (sha256, primi 12 caratteri): `{meta.get('source_sha256', '?')[:12]}`")
st.caption(f"File sorgente: `{meta.get('source_path', '?')}`")

st.warning(
    "Ranking dei pool (G1-G4) **provvisorio**, prodotto dal modello — non è la lista "
    "ufficiale dell'admin (arriva via Google Form, vedi "
    "`docs/archive/Recap_regole_asta_admin_20260811.txt`). "
    "Vai a **Giocatori** nella barra laterale per la ricerca e la scheda dettaglio."
)

st.info(
    "Questa build della UI è sola lettura (M4 slice 1): niente costruttore rosa, "
    "cockpit asta live, offerta consigliata o massimo dinamico — richiedono il ledger "
    "vivo, non ancora collegato qui. Solo ricerca e scheda giocatore per ora."
)
