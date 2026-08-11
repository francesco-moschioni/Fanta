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

from fantacalcio.auction.bid_recommendation import budget_remaining_for_round
from fantacalcio.auction.lock_feasibility import check_lock_feasibility
from fantacalcio.auction.roster_optimizer import Candidate, optimize_roster_completion
from fantacalcio.config import ConfigError, load_ruleset
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

st.divider()
st.subheader("Rosa ideale (completamento ottimale degli slot residui)")
st.caption(
    "Suggerimento che massimizza il VAR totale entro il budget e i limiti di ruolo "
    "residui del round scelto (ricerca esatta su un pool di candidati, non una "
    "formula d'offerta). Non è una previsione di chi vincerà — i round sono sealed "
    "bid — solo un punto di partenza per la propria lista. I lock già bloccati "
    "sono trattati come già impegnati (slot e budget)."
)

# G1's individual pool is defenders only (goalkeepers are a block purchase, out
# of scope here); G3/G4 share one pool but domain.replay() still requires
# goalkeepers in blocks of 3 even there, so P is excluded from every round.
ROUND_TO_ROUND_POOL = {"G1": "G1", "G2": "G2", "G3": "G3_G4", "G4": "G3_G4"}
ROUND_ROLES = {"G1": ["D"], "G2": ["C", "A"], "G3": ["D", "C", "A"], "G4": ["D", "C", "A"]}

optimize_round = st.selectbox("Round da ottimizzare", [r.id for r in ruleset.rounds], key="optimize_round")

if st.button("Calcola rosa ideale"):
    round_pool_label = ROUND_TO_ROUND_POOL[optimize_round]
    eligible_roles = ROUND_ROLES[optimize_round]

    locked_role_counts: dict[str, int] = {}
    locked_role_cost: dict[str, int] = {}
    locked_player_codes = set()
    for lock in my_locks:
        locked_player_codes.add(lock.player_code)
        locked_role_counts[lock.role] = locked_role_counts.get(lock.role, 0) + 1
        row = get_player(player_conn, lock.player_code)
        if row is not None:
            locked_role_cost[lock.role] = locked_role_cost.get(lock.role, 0) + int(row["quotazione_asta"])

    role_slots_needed = {}
    for role_code in eligible_roles:
        target = getattr(ruleset.roster, ROLE_TARGET_FIELD[role_code])
        real_count = team.role_count(DOMAIN_ROLE[role_code])
        role_slots_needed[role_code] = max(0, target - real_count - locked_role_counts.get(role_code, 0))

    try:
        round_budget = budget_remaining_for_round(team, optimize_round, ruleset)
    except ConfigError as exc:
        st.info(
            f"Budget non calcolabile per {optimize_round}: `{my_team_id}` non ha ancora eventi "
            f"nel round precedente necessario ({exc})."
        )
    else:
        locked_cost_this_round = sum(locked_role_cost.get(r, 0) for r in eligible_roles)
        available_budget = max(0, round_budget - locked_cost_this_round)

        pool_df = search_players(player_conn, round_pool=round_pool_label)
        pool_df = pool_df[pool_df["role"].isin(eligible_roles)]
        pool_df = pool_df[~pool_df["player_code"].astype(str).isin(state.assigned_players)]
        pool_df = pool_df[~pool_df["player_code"].isin(locked_player_codes)]

        candidates = [
            Candidate(player_code=int(r.player_code), role=r.role, var_mean=float(r.var_mean), cost=int(r.quotazione_asta))
            for r in pool_df.itertuples(index=False)
        ]

        if not any(need > 0 for need in role_slots_needed.values()):
            st.caption(f"Nessuno slot residuo per {optimize_round} (rosa reale + lock già coprono i ruoli di questo round).")
        else:
            result = optimize_roster_completion(candidates, role_slots_needed, available_budget)
            st.markdown(
                f"Budget considerato: **{round_budget}** residuo{f' − {locked_cost_this_round} già impegnato dai lock' if locked_cost_this_round else ''} "
                f"= **{available_budget}** disponibile. Slot cercati: "
                f"{', '.join(f'{v} {k}' for k, v in role_slots_needed.items() if v > 0)}."
            )
            if result.candidate_pool_capped:
                st.caption(
                    f"Pool di candidati limitato ai migliori {result.candidates_considered} per VAR per ruolo, "
                    "per trattabilità — non è una ricerca su tutti i giocatori disponibili."
                )
            if not result.selected:
                st.caption("Nessuna combinazione trovata entro il budget disponibile.")
            else:
                opt_rows = [
                    {
                        "Giocatore": _player_label(c.player_code),
                        "Ruolo": c.role,
                        "VAR": round(c.var_mean, 2),
                        "Quotazione": c.cost,
                    }
                    for c in result.selected
                ]
                st.dataframe(opt_rows, use_container_width=True, hide_index=True)
                st.caption(f"VAR totale: **{result.total_var:.2f}** — costo totale (quotazioni): **{result.total_cost}**")
