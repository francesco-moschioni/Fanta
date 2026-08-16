"""La mia rosa: rosa reale (dal ledger) + lock di obiettivi pre-asta + rischi
+ confronto moduli (docs/CURRENT_TASK.md, M4 slice 5/7/8, costruttore rosa,
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
from fantacalcio.auction.formation_strength import RosterPlayer, compute_formation_strength
from fantacalcio.auction.lock_feasibility import check_lock_feasibility
from fantacalcio.auction.roster_optimizer import TOP_N_PER_ROLE, Candidate, optimize_roster_completion
from fantacalcio.auction.roster_risk import DEFAULT_WARNING_THRESHOLD, compute_club_concentration
from fantacalcio.config import ConfigError, load_ruleset
from fantacalcio.domain import Role
from fantacalcio.persistence.avoid_list_store import add_avoid, connect as connect_avoid, list_avoided, remove_avoid
from fantacalcio.persistence.ledger_store import connect as connect_ledger, load_current_league_state
from fantacalcio.persistence.locks_store import add_lock, connect as connect_locks, list_locks, remove_lock
from fantacalcio.persistence.player_table import DEFAULT_DB_PATH, connect as connect_players, get_player, search_players
from fantacalcio.persistence.team_labels_store import (
    connect as connect_labels,
    display_name,
    get_all_labels,
    load_labels_config,
    seed_missing_labels,
)

st.set_page_config(page_title="Fantacalcio — Rosa", page_icon="⭐", layout="wide")
st.title("La mia rosa")
st.markdown(
    "La tua situazione in un colpo d'occhio: cosa hai **già vinto per davvero** "
    "(dal registro delle aste), quali **obiettivi** hai bloccato per pianificare, "
    "chi hai segnato **da evitare**, e — se vuoi — un calcolo automatico di quale "
    "combinazione di giocatori conviene di più per completare quello che ti manca."
)

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
def _avoid_conn():
    return connect_avoid()


@st.cache_resource
def _player_conn():
    return connect_players()


@st.cache_resource
def _labels_conn():
    return connect_labels()


ruleset = _ruleset()
ledger_conn = _ledger_conn()
locks_conn = _locks_conn()
avoid_conn = _avoid_conn()
player_conn = _player_conn()
labels_conn = _labels_conn()
seed_missing_labels(labels_conn, load_labels_config())
team_labels = get_all_labels(labels_conn)

TEAM_IDS = [f"team_{i:02d}" for i in range(1, ruleset.teams + 1)]
if "my_team_id" not in st.session_state:
    st.session_state["my_team_id"] = TEAM_IDS[0]

st.selectbox("La mia squadra", TEAM_IDS, key="my_team_id", format_func=lambda t: display_name(t, team_labels))
my_team_id = st.session_state["my_team_id"]
my_team_label = display_name(my_team_id, team_labels)

state = load_current_league_state(ledger_conn, ruleset)
team = state.team(my_team_id)
my_locks = list_locks(locks_conn, my_team_id)
my_avoided = list_avoided(avoid_conn, my_team_id)

ROLE_CODES = ["P", "D", "C", "A"]
ROLE_LABELS = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}
ROLE_LABELS_SINGULAR = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}
DOMAIN_ROLE = {"P": Role.GK, "D": Role.DEF, "C": Role.MID, "A": Role.FWD}
ROLE_TARGET_FIELD = {"P": "goalkeeper_block_size", "D": "defenders", "C": "midfielders", "A": "forwards"}
ROUND_LABELS = {
    "G1": "1° turno — portieri + difensori",
    "G2": "2° turno — centrocampisti + attaccanti",
    "G3": "3° turno — chiunque sia rimasto",
    "G4": "4° turno — chiunque sia rimasto",
}


def _player_label(player_code: int) -> str:
    row = get_player(player_conn, player_code)
    if row is None:
        return f"#{player_code} (non trovato nella tabella giocatori)"
    return f"{row['display_name']} ({row['team_name']})"


st.subheader("Rosa reale")
st.caption(f"Giocatori che {my_team_label} ha effettivamente vinto, dal registro delle aste. Non include i lock (sotto).")

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

st.caption("Budget per turno: quanto avevi a disposizione, quanto hai speso, quanto ti resta.")
budget_rows = []
for round_ in ruleset.rounds:
    budget = team.budgets.get(round_.id)
    budget_rows.append(
        {
            "Turno": ROUND_LABELS.get(round_.id, round_.id),
            "Disponibile": str(budget.available) if budget else "—",
            "Speso": str(budget.spent) if budget else "—",
            "Residuo": str(budget.remaining) if budget else "—",
        }
    )
st.dataframe(budget_rows, width="stretch", hide_index=True)

st.divider()
st.subheader("Obiettivi bloccati")
st.caption(
    "Ipotetico, non ancora acquistato. Lock = intenzione di puntare su questo "
    "giocatore, per pianificazione. Non è un'offerta né un acquisto: non tocca "
    "il registro delle aste, non riserva budget reale. Verificato solo per "
    "fattibilità (ruolo/capacità/disponibilità), non per prezzo."
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
                "Ruolo": ROLE_LABELS_SINGULAR.get(lock.role, lock.role),
                "Quotazione": str(quotazione) if quotazione is not None else "—",
                "Nota": lock.note,
            }
        )
    st.dataframe(lock_rows, width="stretch", hide_index=True)
    st.caption(
        f"Costo stimato totale dei lock (somma quotazioni asta): **{total_estimated_cost}** crediti. "
        "Stima, non un'offerta garantita: il prezzo reale dipende dalla dinamica dell'asta."
    )

    with st.form("unlock"):
        options = {f"{_player_label(lock.player_code)} ({ROLE_LABELS_SINGULAR.get(lock.role, lock.role)})": lock.player_code for lock in my_locks}
        to_unlock_label = st.selectbox("Sblocca", list(options.keys()))
        unlock_submitted = st.form_submit_button("Sblocca")
    if unlock_submitted:
        remove_lock(locks_conn, my_team_id, options[to_unlock_label])
        st.success("Sbloccato.")
        st.rerun()
else:
    st.caption("Nessun obiettivo bloccato. Puoi bloccarne uno qui sotto, oppure dalla scheda giocatore nella pagina Giocatori.")

with st.expander("Blocca un nuovo obiettivo"):
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
st.subheader("Giocatori da evitare")
st.caption(
    "Promemoria personale — infortuni, dubbi, o semplicemente giocatori su cui "
    "non vuoi puntare. Compare come avviso quando apri la scheda di questo "
    "giocatore nella pagina Giocatori. Non impedisce nulla, è solo un promemoria."
)

if my_avoided:
    avoid_rows = [
        {
            "Giocatore": _player_label(a.player_code),
            "Ruolo": ROLE_LABELS_SINGULAR.get(a.role, a.role),
            "Motivo": a.reason,
        }
        for a in my_avoided
    ]
    st.dataframe(avoid_rows, width="stretch", hide_index=True)

    with st.form("remove_avoid"):
        avoid_options = {f"{_player_label(a.player_code)} ({ROLE_LABELS_SINGULAR.get(a.role, a.role)})": a.player_code for a in my_avoided}
        to_remove_label = st.selectbox("Rimuovi dalla lista da evitare", list(avoid_options.keys()))
        remove_avoid_submitted = st.form_submit_button("Rimuovi")
    if remove_avoid_submitted:
        remove_avoid(avoid_conn, my_team_id, avoid_options[to_remove_label])
        st.success("Rimosso dalla lista da evitare.")
        st.rerun()
else:
    st.caption("Nessun giocatore segnato come da evitare.")

with st.expander("Segna un giocatore da evitare"):
    with st.form("add_avoid"):
        avoid_name_query = st.text_input("Cerca giocatore per nome", key="avoid_name_query")
        avoid_reason = st.text_input("Motivo (opzionale)", key="avoid_reason")
        add_avoid_submitted = st.form_submit_button("Cerca e segna")

    if add_avoid_submitted:
        if not avoid_name_query:
            st.error("Inserisci un nome per cercare il giocatore.")
        else:
            matches = search_players(player_conn, name_query=avoid_name_query)
            if matches.empty:
                st.error(f"Nessun giocatore trovato per {avoid_name_query!r}.")
            elif len(matches) > 1:
                st.error(
                    f"{len(matches)} giocatori corrispondono a {avoid_name_query!r}: "
                    f"{', '.join(matches['display_name'].tolist())}. Restringi la ricerca."
                )
            else:
                player = matches.iloc[0]
                add_avoid(avoid_conn, my_team_id, int(player["player_code"]), player["role"], avoid_reason)
                st.success(f"Segnato come da evitare: {player['display_name']}")
                st.rerun()

st.divider()
st.subheader("Concentrazione di squadra")
st.caption(
    "Se troppi tuoi giocatori vengono dallo stesso club reale, un loro singolo "
    "risultato negativo può trascinarne giù più di uno nella stessa giornata. "
    "Conta la rosa reale + gli obiettivi bloccati insieme (non è una previsione, "
    "solo un conteggio)."
)

club_pairs = []
for role_code in ROLE_CODES:
    for pid in team.roster[DOMAIN_ROLE[role_code]]:
        row = get_player(player_conn, int(pid))
        if row is not None:
            club_pairs.append((int(pid), row["team_name"]))
for lock in my_locks:
    row = get_player(player_conn, lock.player_code)
    if row is not None:
        club_pairs.append((lock.player_code, row["team_name"]))

concentration = compute_club_concentration(club_pairs)
if not concentration:
    st.caption("Nessuna concentrazione: al massimo un giocatore per club, per ora.")
else:
    for c in concentration:
        names = ", ".join(_player_label(pid) for pid in c.player_codes)
        if c.player_count >= DEFAULT_WARNING_THRESHOLD:
            st.warning(f"**{c.team_name}**: {c.player_count} giocatori ({names})")
        else:
            st.caption(f"{c.team_name}: {c.player_count} giocatori ({names})")

st.divider()
st.subheader("Confronto moduli")
st.caption(
    "Con quale dei moduli ammessi la tua rosa reale rende di più, **in media sulla "
    "stagione**? Prende i tuoi migliori giocatori per ruolo (rosa reale + obiettivi "
    "bloccati) e somma il loro VAR per ciascun modulo. **Non è l'undici della "
    "prossima giornata**: non usa infortuni, probabili formazioni né avversario — "
    "quei dati non esistono ancora in questo strumento (vedi Home). Comprare per "
    "l'asta non cambia in base al modulo: la rosa fissa (3 portieri, 8 difensori, "
    "8 centrocampisti, 5 attaccanti) è già dimensionata per coprirli tutti insieme."
)

formation_pool: list[RosterPlayer] = []
for role_code in ROLE_CODES:
    for pid in team.roster[DOMAIN_ROLE[role_code]]:
        row = get_player(player_conn, int(pid))
        if row is not None:
            formation_pool.append(RosterPlayer(int(pid), role_code, float(row["var_mean"])))
for lock in my_locks:
    row = get_player(player_conn, lock.player_code)
    if row is not None:
        formation_pool.append(RosterPlayer(lock.player_code, lock.role, float(row["var_mean"])))

if not formation_pool:
    st.caption("Nessun giocatore ancora in rosa o bloccato: niente da confrontare.")
else:
    formation_results = compute_formation_strength(formation_pool, ruleset)
    formation_rows = [
        {
            "Modulo": r.formation,
            "VAR totale titolari": round(r.total_var, 2),
            "Copertura completa": "Sì" if r.fully_coverable else "No",
            "Mancano": ", ".join(f"{n} {ROLE_LABELS_SINGULAR.get(role, role).lower()}" for role, n in r.missing_by_role.items()) or "—",
        }
        for r in formation_results
    ]
    st.dataframe(formation_rows, width="stretch", hide_index=True)

    best = formation_results[0]
    if best.fully_coverable:
        starters_label = ", ".join(_player_label(p.player_code) for p in best.starters)
        st.markdown(f"**Modulo più forte con quello che hai ora: {best.formation}** — titolari: {starters_label}")
    else:
        st.caption(
            f"Il modulo con VAR totale più alto ({best.formation}) non è ancora coprib"
            "ile del tutto con quello che possiedi: alcune caselle andrebbero riempite "
            "con giocatori sotto la media di ruolo o lasciate vuote."
        )

st.divider()
st.subheader("Rosa ideale")
st.caption(
    "Calcola automaticamente quale combinazione di giocatori ancora disponibili "
    "conviene di più (il VAR totale più alto) per completare gli slot che ti "
    "mancano in un turno, senza sforare il budget. Non è una previsione di chi "
    "vincerà — i turni sono a busta chiusa — solo un punto di partenza per la "
    "tua lista. Gli obiettivi già bloccati contano come già impegnati (slot e budget)."
)

# Il pool individuale del 1° turno è solo i difensori (i portieri si comprano in
# blocco, fuori scope qui); 3°/4° turno condividono un pool ma il registro
# richiede comunque i portieri in blocchi di 3 anche lì, quindi i portieri sono
# esclusi da ogni turno di questo calcolo.
ROUND_TO_ROUND_POOL = {"G1": "G1", "G2": "G2", "G3": "G3_G4", "G4": "G3_G4"}
ROUND_ROLES = {"G1": ["D"], "G2": ["C", "A"], "G3": ["D", "C", "A"], "G4": ["D", "C", "A"]}

optimize_round = st.selectbox("Turno da ottimizzare", [r.id for r in ruleset.rounds], key="optimize_round", format_func=lambda r: ROUND_LABELS.get(r, r))

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
            f"Budget non calcolabile per {ROUND_LABELS.get(optimize_round, optimize_round)}: "
            f"{my_team_label} non ha ancora eventi nel turno precedente necessario ({exc})."
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
            st.caption(f"Nessuno slot residuo per {ROUND_LABELS.get(optimize_round, optimize_round)} (rosa reale + lock già coprono i ruoli di questo turno).")
        else:
            result = optimize_roster_completion(candidates, role_slots_needed, available_budget)
            slots_summary = ", ".join(f"{v} {ROLE_LABELS_SINGULAR.get(k, k).lower()}" for k, v in role_slots_needed.items() if v > 0)
            st.markdown(
                f"Budget considerato: **{round_budget}** residuo"
                f"{f' − {locked_cost_this_round} già impegnato dagli obiettivi bloccati' if locked_cost_this_round else ''} "
                f"= **{available_budget}** disponibile. Slot cercati: {slots_summary}."
            )
            if result.candidate_pool_capped:
                st.caption(
                    f"Confronto limitato ai migliori {TOP_N_PER_ROLE} candidati per VAR **per ciascun "
                    f"ruolo cercato** ({result.candidates_considered} candidati in totale), per restare "
                    "veloce — non è una ricerca su tutti i giocatori disponibili."
                )
            if not result.selected:
                st.caption("Nessuna combinazione trovata entro il budget disponibile.")
            else:
                opt_rows = [
                    {
                        "Giocatore": _player_label(c.player_code),
                        "Ruolo": ROLE_LABELS_SINGULAR.get(c.role, c.role),
                        "VAR": round(c.var_mean, 2),
                        "Quotazione": c.cost,
                    }
                    for c in result.selected
                ]
                st.dataframe(opt_rows, width="stretch", hide_index=True)
                st.caption(f"VAR totale: **{result.total_var:.2f}** — costo totale (quotazioni): **{result.total_cost}**")
