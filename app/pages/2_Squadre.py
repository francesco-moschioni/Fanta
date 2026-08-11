"""Tabellone squadre + registrazione manuale dei risultati pubblicati dall'admin
(docs/CURRENT_TASK.md, M4 slice 2).

Importante (vedi CURRENT_TASK.md): i round G1-G4 sono sealed bid, risolti
dall'admin -- questa pagina NON è un'asta live interattiva. Registra i risultati
già decisi altrove. Il ledger è append-only (src/fantacalcio/domain.py): un
errore si corregge registrando un VoidEvent, mai modificando un evento esistente.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from fantacalcio.auction.bid_recommendation import VOTI_TO_DOMAIN_ROLE
from fantacalcio.config import ConfigError, load_ruleset
from fantacalcio.domain import (
    AssignmentEvent,
    AssignmentItem,
    BudgetAdjustmentEvent,
    DomainError,
    Role,
    VoidEvent,
    effective_events,
    replay,
)
from fantacalcio.persistence.ledger_store import (
    append_event,
    connect as connect_ledger,
    load_current_league_state,
    load_events,
)
from fantacalcio.persistence.player_table import DEFAULT_DB_PATH, connect as connect_players, search_players

st.set_page_config(page_title="Fantacalcio — Squadre", layout="wide")
st.title("Squadre")

RULESET_PATH = Path("config/auction_rules.v1.yaml")

st.warning(
    "I round G1-G4 sono **sealed bid**, risolti dall'admin dopo la chiusura di ogni "
    "turno — questa pagina non è un'asta live interattiva. Registra qui i risultati "
    "**già decisi** (pubblicati dall'admin), per tenere aggiornati budget e rose."
)

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
def _player_conn():
    return connect_players()


ruleset = _ruleset()
ledger_conn = _ledger_conn()
player_conn = _player_conn()

TEAM_IDS = [f"team_{i:02d}" for i in range(1, ruleset.teams + 1)]
ROUND_IDS = [r.id for r in ruleset.rounds]

if "my_team_id" not in st.session_state:
    st.session_state["my_team_id"] = TEAM_IDS[0]

st.selectbox(
    "La mia squadra",
    TEAM_IDS,
    key="my_team_id",
    help="Nessun nome reale di squadra/manager è ancora in repo — identificativi generici finché non arrivano.",
)

all_events = load_events(ledger_conn)
active_events = effective_events(all_events)
state = load_current_league_state(ledger_conn, ruleset)

teams_with_logo_bonus = {
    e.team_id for e in active_events if isinstance(e, BudgetAdjustmentEvent) and e.reason == "custom_logo_bonus"
}

st.subheader("Tabellone")
rows = []
role_targets = {
    Role.GK: ruleset.roster.goalkeeper_block_size,
    Role.DEF: ruleset.roster.defenders,
    Role.MID: ruleset.roster.midfielders,
    Role.FWD: ruleset.roster.forwards,
}
for team_id in TEAM_IDS:
    team = state.team(team_id)
    latest_round = None
    for round_id in reversed(ROUND_IDS):
        if round_id in team.budgets:
            latest_round = round_id
            break
    budget = team.budgets.get(latest_round) if latest_round else None
    rows.append(
        {
            "Squadra": team_id + (" (tu)" if team_id == st.session_state["my_team_id"] else ""),
            "Round corrente": latest_round or "—",
            "Budget residuo": budget.remaining if budget else "—",
            "P": f"{team.role_count(Role.GK)}/{role_targets[Role.GK]}",
            "D": f"{team.role_count(Role.DEF)}/{role_targets[Role.DEF]}",
            "C": f"{team.role_count(Role.MID)}/{role_targets[Role.MID]}",
            "A": f"{team.role_count(Role.FWD)}/{role_targets[Role.FWD]}",
            "Bonus logo": "Sì" if team_id in teams_with_logo_bonus else "—",
        }
    )
st.dataframe(
    rows,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Round corrente": st.column_config.TextColumn(
            help="Ultimo round in cui questa squadra ha almeno un evento registrato nel ledger."
        ),
        "Budget residuo": st.column_config.TextColumn(
            help="Budget disponibile meno speso per il round corrente, dal replay del ledger vivo (eventi annullati esclusi)."
        ),
        "P": st.column_config.TextColumn(help="Portieri acquistati / slot totali (blocco portieri, config/auction_rules.v1.yaml)."),
        "D": st.column_config.TextColumn(help="Difensori acquistati / slot totali di ruolo."),
        "C": st.column_config.TextColumn(help="Centrocampisti acquistati / slot totali di ruolo."),
        "A": st.column_config.TextColumn(help="Attaccanti acquistati / slot totali di ruolo."),
        "Bonus logo": st.column_config.TextColumn(
            help=f"+{ruleset.custom_logo_bonus_credits} crediti per logo/immagine personalizzata invece dello stemma di stock (postilla admin 2026-08-11), già incluso nel budget."
        ),
    },
)

st.divider()
st.subheader("Registra un risultato")

with st.form("register_result"):
    round_id = st.selectbox("Round", ROUND_IDS)
    winning_team = st.selectbox("Squadra vincitrice", TEAM_IDS)
    name_query = st.text_input("Cerca giocatore per nome")
    amount = st.number_input("Prezzo pagato (crediti)", min_value=0, step=1)
    submitted = st.form_submit_button("Cerca e registra")

if submitted:
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
            domain_role = VOTI_TO_DOMAIN_ROLE[player["role"]]
            pool_id = player["list_pool_name"]

            if domain_role is Role.GK:
                st.error(
                    "Blocco portieri (3 giocatori dello stesso club, un solo evento): "
                    "non ancora gestito da questo form. Registra manualmente via "
                    "script se necessario."
                )
            else:
                candidate = AssignmentEvent(
                    event_id=uuid.uuid4().hex,
                    ts=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    round_id=round_id,
                    team_id=winning_team,
                    pool_id=pool_id,
                    role=domain_role,
                    item=AssignmentItem(player_ids=(str(player["player_code"]),)),
                    amount=int(amount),
                    source="admin_result_manual_entry",
                    author="utente",
                )
                try:
                    replay(ruleset, load_events(ledger_conn) + [candidate])
                except (DomainError, ConfigError) as exc:
                    st.error(f"Evento non valido, non registrato: {exc}")
                else:
                    append_event(ledger_conn, candidate)
                    st.success(f"Registrato: {winning_team} — {player['display_name']} — {amount} crediti — {round_id}")
                    st.rerun()

st.divider()
st.subheader("Bonus logo personalizzato")
st.caption(
    f"Postilla admin, 2026-08-11: +{ruleset.custom_logo_bonus_credits} crediti a ogni squadra che "
    "imposta un'immagine/logo personalizzato invece dello stemma di stock Fantacalcio "
    "(come lo scorso anno). Applicato al budget G1: si propaga automaticamente a "
    "G2/G3/G4 tramite la catena `remaining_G1`, nessun'altra azione necessaria."
)
teams_without_bonus = [t for t in TEAM_IDS if t not in teams_with_logo_bonus]
if not teams_without_bonus:
    st.caption("Tutte le squadre hanno già ricevuto il bonus.")
else:
    with st.form("assign_logo_bonus"):
        bonus_team = st.selectbox("Squadra", teams_without_bonus)
        bonus_submitted = st.form_submit_button(f"Assegna +{ruleset.custom_logo_bonus_credits} crediti")
    if bonus_submitted:
        bonus_event = BudgetAdjustmentEvent(
            event_id=uuid.uuid4().hex,
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            round_id="G1",
            team_id=bonus_team,
            amount=ruleset.custom_logo_bonus_credits,
            reason="custom_logo_bonus",
            author="utente",
        )
        try:
            replay(ruleset, load_events(ledger_conn) + [bonus_event])
        except (DomainError, ConfigError) as exc:
            st.error(f"Evento non valido, non registrato: {exc}")
        else:
            append_event(ledger_conn, bonus_event)
            st.success(f"Bonus assegnato a {bonus_team}: +{ruleset.custom_logo_bonus_credits} crediti.")
            st.rerun()

st.divider()
st.subheader("Annulla un risultato (undo)")

active = [e for e in active_events if isinstance(e, (AssignmentEvent, BudgetAdjustmentEvent))]

if not active:
    st.caption("Nessun evento attivo da annullare.")
else:
    def _describe(e):
        if isinstance(e, BudgetAdjustmentEvent):
            return f"{e.team_id} — bonus {e.reason} +{e.amount} crediti — {e.round_id} ({e.event_id[:8]})"
        return f"{e.team_id} — {e.item.player_ids} — {e.amount} crediti — {e.round_id} ({e.event_id[:8]})"

    options = {_describe(e): e.event_id for e in active}
    with st.form("void_event"):
        selected_label = st.selectbox("Evento da annullare", list(options.keys()))
        reason = st.text_input("Motivo")
        void_submitted = st.form_submit_button("Annulla")
    if void_submitted:
        if not reason:
            st.error("Indica un motivo.")
        else:
            void = VoidEvent(
                event_id=uuid.uuid4().hex,
                ts=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                voids=options[selected_label],
                author="utente",
                reason=reason,
            )
            append_event(ledger_conn, void)
            st.success("Evento annullato.")
            st.rerun()
