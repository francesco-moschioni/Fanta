"""Guida iniziale + gestione etichetta squadra (docs/CURRENT_TASK.md, M4 slice 7:
passata di chiarezza UI su richiesta esplicita dell'utente dopo test reale)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from fantacalcio.auction.market_supply import compute_goalkeeper_club_supply, compute_role_supply
from fantacalcio.config import load_ruleset
from fantacalcio.persistence.player_table import DEFAULT_DB_PATH, connect, get_build_meta, search_players
from fantacalcio.persistence.team_labels_store import connect as connect_labels, get_label, set_label

st.set_page_config(page_title="Fantacalcio — Home", layout="wide")

RULESET_PATH = Path("config/auction_rules.v1.yaml")

st.title("Assistente per l'asta del Fantacalcio")
st.caption("Strumento privato, solo per te. Nessun dato esce da questo computer.")

st.markdown(
    """
Questo strumento **non decide al posto tuo**. Ti mostra numeri calcolati in modo
trasparente (ogni numero ha una spiegazione, visibile passandoci sopra il mouse
o aprendo il pannello "come si calcola"), e ti aiuta a tenere traccia di budget,
rosa e obiettivi mentre l'asta procede — così non devi ricordarti tutto a mente
o su un foglio a parte.

## Le tre pagine, in breve

- **Giocatori** — cerca un giocatore, guarda quanto ci si aspetta che renda e
  quanto vale rispetto agli altri del suo ruolo. Da qui puoi anche segnarlo
  come tuo obiettivo, o come uno da evitare.
- **Squadre** — quando l'admin pubblica i risultati di un turno (chi ha vinto
  quale giocatore, a che prezzo), registrali qui. Tiene aggiornati in tempo
  reale budget e rosa di tutte le squadre.
- **Rosa** — la tua situazione: cosa hai già vinto per davvero, quali obiettivi
  hai bloccato, e un calcolo automatico di quale combinazione di giocatori
  conviene di più per completare quello che ti manca.

## Come usarlo, in pratica

1. **Prima dell'asta**: vai su *Giocatori*, guardati intorno, blocca i tuoi
   obiettivi principali (bottone "Blocca come obiettivo" nella scheda di ogni
   giocatore).
2. **Durante l'asta**: appena l'admin pubblica i risultati di un turno,
   registrali su *Squadre* — un evento per ogni giocatore assegnato (o il
   blocco portieri, che si registra insieme).
3. **Tra un turno e l'altro**: apri *Rosa* per vedere cosa ti manca, quanto
   budget hai per il turno dopo, e se vuoi un suggerimento su come completarla.

**Importante**: i turni dell'asta sono a **busta chiusa**, decisi dall'admin
dopo la chiusura di ciascuno — questo strumento non è un'asta dal vivo dentro
l'app, registra e pianifica, non fa offerte per te.
"""
)

st.divider()
st.subheader("La tua squadra")
st.caption(
    "L'asta usa identificativi generici (`team_01`, `team_02`, ...) perché non ci "
    "sono ancora nomi reali delle squadre in questo strumento. Puoi darle un nome "
    "tuo, solo per comodità — non cambia nulla nei calcoli, è solo un'etichetta "
    "che compare al posto dell'identificativo grezzo in tutte le pagine."
)


@st.cache_resource
def _ruleset():
    return load_ruleset(RULESET_PATH)


@st.cache_resource
def _labels_conn():
    return connect_labels()


ruleset = _ruleset()
labels_conn = _labels_conn()
TEAM_IDS = [f"team_{i:02d}" for i in range(1, ruleset.teams + 1)]

if "my_team_id" not in st.session_state:
    st.session_state["my_team_id"] = TEAM_IDS[0]

st.selectbox("Quale squadra sei tu", TEAM_IDS, key="my_team_id")
current_label = get_label(labels_conn, st.session_state["my_team_id"]) or ""

with st.form("rename_team"):
    new_label = st.text_input("Nome per la tua squadra (facoltativo)", value=current_label)
    rename_submitted = st.form_submit_button("Salva nome")
if rename_submitted:
    if new_label.strip():
        set_label(labels_conn, st.session_state["my_team_id"], new_label.strip())
        st.success(f"Fatto: {st.session_state['my_team_id']} ora appare come \"{new_label.strip()}\".")
    else:
        st.warning("Nome vuoto, non salvato.")

st.divider()
st.subheader("Stato dei dati")

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

col1, col2, col3, col4 = st.columns(4)
col1.metric("Giocatori nella tabella", meta.get("n_players", "?"), help="Quanti giocatori del listone 2026/27 hanno una previsione calcolata.")
col2.metric(
    "Calcolo generato il (UTC)",
    meta.get("source_generated_at", "?")[:19],
    help="Quando è stato effettivamente calcolato il file con le previsioni "
    "(simulazione Monte Carlo + valori di rimpiazzo) — la data che conta per "
    "capire quanto sono \"freschi\" i numeri che vedi.",
)
col3.metric(
    "Caricato in questa app il (UTC)",
    meta.get("built_at", "?")[:19],
    help="Quando questo strumento ha letto l'ultima volta il file di calcolo per "
    "mostrartelo — può essere più recente del calcolo stesso se il file non è "
    "cambiato nel frattempo.",
)
col4.metric("Fonte", "M3 replacement values", help="Il file da cui provengono i numeri: fantavoto atteso, VAR, tier di qualità dati.")

st.caption(f"File sorgente: `{meta.get('source_path', '?')}` (hash `{meta.get('source_sha256', '?')[:12]}`)")

st.warning(
    "Il ranking dei giocatori per turno (G1-G4) è **provvisorio**, prodotto da questo "
    "strumento — non è ancora la lista ufficiale dell'admin (arriva via Google Form). "
    "Fidati per farti un'idea, ma verifica sulla lista reale quando arriva."
)

st.divider()
st.subheader("Avvisi di mercato")
st.caption(
    "Quanti giocatori esistono davvero nel listone 2026/27 per ciascun ruolo, "
    "confrontati con quanti ne servirebbero in tutto per riempire le rose di "
    "tutte le 20 squadre (dato reale, non una previsione — trovato eseguendo "
    "una simulazione completa dell'asta, non solo osservando il listone)."
)

ROLE_LABELS_HOME = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
full_pool = search_players(conn)
supply_rows = [
    {
        "Ruolo": ROLE_LABELS_HOME.get(s.role, s.role),
        "Disponibili nel listone": s.available,
        "Richiesti in lega": s.required,
        "Carenza": str(s.shortfall) if s.shortfall > 0 else "—",
    }
    for s in compute_role_supply(full_pool, ruleset)
]
st.dataframe(supply_rows, width="stretch", hide_index=True)

shortages = [s for s in compute_role_supply(full_pool, ruleset) if s.shortfall > 0]
if shortages:
    for s in shortages:
        st.warning(
            f"**{ROLE_LABELS_HOME.get(s.role, s.role)}**: mancano {s.shortfall} giocatori "
            f"({s.available} disponibili contro {s.required} richiesti in tutta la lega) — "
            "non tutte le squadre riusciranno a completare questo ruolo, indipendentemente "
            "da quanto spendono."
        )

thin_clubs = [c for c in compute_goalkeeper_club_supply(full_pool, ruleset) if not c.can_form_same_club_block]
if thin_clubs:
    club_list = ", ".join(f"{c.team_name} ({c.goalkeeper_count})" for c in thin_clubs)
    st.warning(
        f"**Blocco portieri dello stesso club**: {club_list} non hanno abbastanza portieri "
        f"nel listone per formare un blocco da {ruleset.roster.goalkeeper_block_size} dello "
        "stesso club — chi punta a un blocco di uno di questi club dovrà per forza mescolare club diversi."
    )
