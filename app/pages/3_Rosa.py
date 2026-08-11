"""La mia rosa: rosa reale (dal ledger) + lock di obiettivi pre-asta
(docs/CURRENT_TASK.md, M4 slice 5, prima fetta del costruttore rosa,
docs/UX_PRODUCT.md).

CLAUDE.md: "Distingui sempre acquistato da ipotetico." Questa pagina separa
sempre visivamente la rosa reale (eventi nel ledger, già vinti) dai lock
(obiettivi bloccati per pianificazione, non ancora acquistati). Un lock non
tocca mai il ledger/replay -- è puro stato di pianificazione, verificato per
fattibilità prima di essere salvato (src/fantacalcio/auction/lock_feasibility.py).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from fantacalcio.auction.lock_feasibility import check_lock_feasibility
from fantacalcio.config import load_ruleset
from fantacalcio.domain import Role
from fantacalcio.persistence.ledger_store import connect as connect_ledger, load_current_league_state
from fantacalcio.persistence.locks_store import add_lock, connect as connect_locks, list_locks, remove_lock
from fantacalcio.persistence.player_table import DEFAULT_DB_PATH, connect as connect_players, get_player, search_players

st.set_page_config(page_title="Fantacalcio — Rosa", layout="wide")
st.title("La mia rosa")

RULESET_PATH = Path("config/auction_rules.v1.yaml")

if not DEFAULT_DB_PATH.is_file():
    st.error("Tabella giocatori non trovata. Esegui `python scripts/build_player_table.py` prima.")
    st.stop()


@st.cache_resource
def _ruleset():
    return load_ruleset(RULESET_PATH)


@st.cache_resource
def _ledger_conn():
    return connect_ledger()


@st.cache_resource
def _locks_conn():
    return connect_locks()


@st.cache_resource
def _player_conn():
    return connect_players()


ruleset = _ruleset()
ledger_conn = _ledger_conn()
locks_conn = _locks_conn()
player_conn = _player_conn()

TEAM_IDS = [f"team_{i:02d}" for i in range(1, ruleset.teams + 1)]
if "my_team_id" not in st.session_state:
    st.session_state["my_team_id"] = TEAM_IDS[0]

st.selectbox("La mia squadra", TEAM_IDS, key="my_team_id")
my_team_id = st.session_state["my_team_id"]

state = load_current_league_state(ledger_conn, ruleset)
team = state.team(my_team_id)
my_locks = list_locks(locks_conn, my_team_id)

ROLE_CODES = ["P", "D", "C", "A"]
ROLE_LABELS = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
DOMAIN_ROLE = {"P": Role.GK, "D": Role.DEF, "C": Role.MID, "A": Role.FWD}
ROLE_TARGET_FIELD = {"P": "goalkeeper_block_size", "D": "defenders", "C": "midfielders", "A": "forwards"}


def _player_label(player_code: int) -> str:
    row = get_player(player_conn, player_code)
    if row is None:
        return f"#{player_code} (non trovato nella tabella giocatori)"
    return f"{row['display_name']} ({row['team_name']})"


st.subheader("Rosa reale (dal ledger)")
st.caption("Giocatori effettivamente vinti, dal replay del ledger vivo. Non include i lock (sotto).")

cols = st.columns(4)
for col, role_code in zip(cols, ROLE_CODES):
    domain_role = DOMAIN_ROLE[role_code]
    target = getattr(ruleset.roster, ROLE_TARGET_FIELD[role_code])
    player_ids = team.roster[domain_role]
    with col:
        st.markdown(f"**{ROLE_LABELS[role_code]}** ({len(player_ids)}/{target})")
        if not player_ids:
            st.caption("Nessuno ancora")
        for pid in player_ids:
            st.write(_player_label(int(pid)))

budget_rows = []
for round_ in ruleset.rounds:
    budget = team.budgets.get(round_.id)
    budget_rows.append(
        {
            "Round": round_.id,
            "Disponibile": budget.available if budget else "—",
            "Speso": budget.spent if budget else "—",
            "Residuo": budget.remaining if budget else "—",
        }
    )
st.dataframe(budget_rows, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Obiettivi bloccati (ipotetico, non ancora acquistato)")
st.caption(
    "Lock = intenzione di puntare su questo giocatore, per pianificazione. Non è "
    "un'offerta né un acquisto: non tocca il ledger, non riserva budget reale. "
    "Verificato solo per fattibilità (ruolo/capacità/disponibilità), non per prezzo."
)

if my_locks:
    total_estimated_cost = 0
    lock_rows = []
    for lock in my_locks:
        row = get_player(player_conn, lock.player_code)
        quotazione = int(row["quotazione_asta"]) if row is not None else None
        if quotazione is not None:
            total_estimated_cost += quotazione
        lock_rows.append(
            {
                "Giocatore": _player_label(lock.player_code),
                "Ruolo": lock.role,
                "Quotazione": quotazione if quotazione is not None else "—",
                "Nota": lock.note,
            }
        )
    st.dataframe(lock_rows, use_container_width=True, hide_index=True)
    st.caption(
        f"Costo stimato totale dei lock (somma quotazioni asta): **{total_estimated_cost}** crediti. "
        "Stima, non un'offerta garantita: il prezzo reale dipende dalla dinamica dell'asta."
    )

    with st.form("unlock"):
        options = {f"{_player_label(lock.player_code)} ({lock.role})": lock.player_code for lock in my_locks}
        to_unlock_label = st.selectbox("Sblocca", list(options.keys()))
        unlock_submitted = st.form_submit_button("Sblocca")
    if unlock_submitted:
        remove_lock(locks_conn, my_team_id, options[to_unlock_label])
        st.success("Sbloccato.")
        st.rerun()
else:
    st.caption("Nessun obiettivo bloccato.")

st.divider()
st.subheader("Blocca un nuovo obiettivo")

with st.form("lock_player"):
    name_query = st.text_input("Cerca giocatore per nome")
    note = st.text_input("Nota (opzionale)")
    lock_submitted = st.form_submit_button("Cerca e blocca")

if lock_submitted:
    if not name_query:
        st.error("Inserisci un nome per cercare il giocatore.")
    else:
        matches = search_players(player_conn, name_query=name_query)
        if matches.empty:
            st.error(f"Nessun giocatore trovato per {name_query!r}.")
        elif len(matches) > 1:
            st.error(
                f"{len(matches)} giocatori corrispondono a {name_query!r}: "
                f"{', '.join(matches['display_name'].tolist())}. Restringi la ricerca."
            )
        else:
            player = matches.iloc[0]
            feasibility = check_lock_feasibility(
                my_team_id, int(player["player_code"]), player["role"], ruleset, state, my_locks
            )
            if not feasibility.ok:
                st.error(f"Blocco non applicato: {feasibility.reason}")
            else:
                add_lock(locks_conn, my_team_id, int(player["player_code"]), player["role"], note)
                st.success(f"Bloccato: {player['display_name']}")
                st.rerun()
