"""Tabellone squadre + registrazione manuale dei risultati pubblicati dall'admin
(docs/CURRENT_TASK.md, M4 slice 2; passata di chiarezza M4 slice 7).

Importante: i turni dell'asta sono a busta chiusa, risolti dall'admin -- questa
pagina NON è un'asta live interattiva. Registra i risultati già decisi altrove.
Il ledger è append-only (src/fantacalcio/domain.py): un errore si corregge
registrando un VoidEvent, mai modificando un evento esistente.
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
from fantacalcio.persistence.player_table import DEFAULT_DB_PATH, connect as connect_players, get_player, search_players
from fantacalcio.persistence.team_labels_store import (
    connect as connect_labels,
    display_name,
    get_all_labels,
    load_labels_config,
    seed_missing_labels,
)

st.set_page_config(page_title="Fantacalcio — Squadre", page_icon="📋", layout="wide")
st.title("Squadre")
st.markdown(
    "Quando l'admin pubblica i risultati di un turno (chi ha vinto quale "
    "giocatore, a che prezzo), registrali qui: uno per volta, oppure il "
    "blocco portieri tutto insieme. Il tabellone sotto si aggiorna da solo, "
    "per tutte le squadre, in base a quello che registri."
)

RULESET_PATH = Path("config/auction_rules.v1.yaml")

ROUND_LABELS = {
    "G1": "1° turno — portieri + difensori",
    "G2": "2° turno — centrocampisti + attaccanti",
    "G3": "3° turno — chiunque sia rimasto",
    "G4": "4° turno — chiunque sia rimasto",
}

st.info(
    "I turni sono a **busta chiusa**: l'admin li chiude e pubblica i risultati, "
    "non si offre in tempo reale dentro questa pagina. Registra qui solo "
    "risultati **già decisi e pubblicati**."
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


@st.cache_resource
def _labels_conn():
    return connect_labels()


ruleset = _ruleset()
ledger_conn = _ledger_conn()
player_conn = _player_conn()
labels_conn = _labels_conn()
seed_missing_labels(labels_conn, load_labels_config())
team_labels = get_all_labels(labels_conn)

TEAM_IDS = [f"team_{i:02d}" for i in range(1, ruleset.teams + 1)]
ROUND_IDS = [r.id for r in ruleset.rounds]


def _team_label(team_id: str) -> str:
    return display_name(team_id, team_labels)


if "my_team_id" not in st.session_state:
    st.session_state["my_team_id"] = TEAM_IDS[0]

st.selectbox(
    "La mia squadra",
    TEAM_IDS,
    key="my_team_id",
    format_func=_team_label,
    help="Puoi darle un nome nella pagina Home invece di usare l'identificativo grezzo.",
)

all_events = load_events(ledger_conn)
active_events = effective_events(all_events)
state = load_current_league_state(ledger_conn, ruleset)

teams_with_logo_bonus = {
    e.team_id for e in active_events if isinstance(e, BudgetAdjustmentEvent) and e.reason == "custom_logo_bonus"
}

st.subheader("Tabellone")
st.caption("Una riga per squadra: turno più avanzato registrato, budget residuo, quanti slot di rosa sono già coperti per ruolo.")
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
            "Squadra": _team_label(team_id) + (" (tu)" if team_id == st.session_state["my_team_id"] else ""),
            "Turno più avanzato": ROUND_LABELS.get(latest_round, "—") if latest_round else "Ancora nessun risultato",
            "Budget residuo": str(budget.remaining) if budget else "—",
            "Portieri": f"{team.role_count(Role.GK)}/{role_targets[Role.GK]}",
            "Difensori": f"{team.role_count(Role.DEF)}/{role_targets[Role.DEF]}",
            "Centrocampisti": f"{team.role_count(Role.MID)}/{role_targets[Role.MID]}",
            "Attaccanti": f"{team.role_count(Role.FWD)}/{role_targets[Role.FWD]}",
            "Bonus logo": "Sì" if team_id in teams_with_logo_bonus else "—",
        }
    )
st.dataframe(
    rows,
    width="stretch",
    hide_index=True,
    column_config={
        "Turno più avanzato": st.column_config.TextColumn(
            help="L'ultimo turno in cui questa squadra ha almeno un evento registrato nel ledger."
        ),
        "Budget residuo": st.column_config.TextColumn(
            help="Budget disponibile meno speso per il turno più avanzato, dal replay del ledger vivo (eventi annullati esclusi)."
        ),
        "Portieri": st.column_config.TextColumn(help="Portieri acquistati / slot totali (blocco portieri, config/auction_rules.v1.yaml)."),
        "Difensori": st.column_config.TextColumn(help="Difensori acquistati / slot totali di ruolo."),
        "Centrocampisti": st.column_config.TextColumn(help="Centrocampisti acquistati / slot totali di ruolo."),
        "Attaccanti": st.column_config.TextColumn(help="Attaccanti acquistati / slot totali di ruolo."),
        "Bonus logo": st.column_config.TextColumn(
            help=f"+{ruleset.custom_logo_bonus_credits} crediti per logo/immagine personalizzata invece dello stemma di stock (postilla admin 2026-08-11), già incluso nel budget."
        ),
    },
)

st.divider()
st.subheader("Registra un risultato")
st.caption("Un giocatore alla volta (non i portieri, che si comprano in blocco: vedi il modulo dedicato sotto).")

with st.form("register_result"):
    round_id = st.selectbox("Turno", ROUND_IDS, format_func=lambda r: ROUND_LABELS.get(r, r))
    winning_team = st.selectbox("Squadra vincitrice", TEAM_IDS, format_func=_team_label)
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
                    "I portieri si registrano come blocco di 3 (un solo evento, un solo "
                    "prezzo): usa il modulo **Registra blocco portieri** qui sotto, non questo."
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
                    st.success(f"Registrato: {_team_label(winning_team)} — {player['display_name']} — {amount} crediti — {ROUND_LABELS.get(round_id, round_id)}")
                    st.rerun()

st.divider()
st.subheader("Registra blocco portieri")
st.caption(
    f"I portieri si comprano come blocco di {ruleset.roster.goalkeeper_block_size}, un solo "
    "evento e un solo prezzo per il blocco intero (sempre nel 1° turno, l'unico con i portieri)."
    + (" Regola: devono essere dello stesso club (avviso, non ancora imposto automaticamente)." if ruleset.roster.goalkeeper_same_club else "")
)

with st.form("register_gk_block"):
    gk_team = st.selectbox("Squadra vincitrice", TEAM_IDS, key="gk_team", format_func=_team_label)
    gk_names = [
        st.text_input(f"Portiere {i + 1} (nome)", key=f"gk_name_{i}")
        for i in range(ruleset.roster.goalkeeper_block_size)
    ]
    gk_amount = st.number_input("Prezzo pagato per il blocco intero (crediti)", min_value=0, step=1, key="gk_amount")
    gk_submitted = st.form_submit_button("Cerca e registra blocco")

if gk_submitted:
    if any(not name for name in gk_names):
        st.error(f"Inserisci tutti i {ruleset.roster.goalkeeper_block_size} nomi.")
    else:
        resolved = []
        errors = []
        for name in gk_names:
            matches = search_players(player_conn, name_query=name, role="P")
            if matches.empty:
                errors.append(f"Nessun portiere trovato per {name!r}.")
            elif len(matches) > 1:
                errors.append(
                    f"{len(matches)} portieri corrispondono a {name!r}: "
                    f"{', '.join(matches['display_name'].tolist())}. Restringi la ricerca."
                )
            else:
                resolved.append(matches.iloc[0])

        if errors:
            for e in errors:
                st.error(e)
        elif len({p["player_code"] for p in resolved}) != len(resolved):
            st.error("Hai indicato lo stesso portiere più di una volta.")
        else:
            team_names = {p["team_name"] for p in resolved}
            if ruleset.roster.goalkeeper_same_club and len(team_names) > 1:
                st.warning(
                    f"Attenzione: i portieri selezionati sono di club diversi ({', '.join(team_names)}) "
                    f"— la regola richiede lo stesso club. Registrato comunque, ma verifica prima di "
                    "confermarlo con l'admin."
                )
            gk_candidate = AssignmentEvent(
                event_id=uuid.uuid4().hex,
                ts=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                round_id="G1",
                team_id=gk_team,
                pool_id="goalkeeper_blocks",
                role=Role.GK,
                item=AssignmentItem(player_ids=tuple(str(p["player_code"]) for p in resolved)),
                amount=int(gk_amount),
                source="admin_result_manual_entry",
                author="utente",
            )
            try:
                replay(ruleset, load_events(ledger_conn) + [gk_candidate])
            except (DomainError, ConfigError) as exc:
                st.error(f"Evento non valido, non registrato: {exc}")
            else:
                append_event(ledger_conn, gk_candidate)
                names = ", ".join(p["display_name"] for p in resolved)
                st.success(f"Registrato blocco portieri: {_team_label(gk_team)} — {names} — {gk_amount} crediti")
                st.rerun()

st.divider()
st.subheader("Bonus logo personalizzato")
st.caption(
    f"Postilla admin, 2026-08-11: +{ruleset.custom_logo_bonus_credits} crediti a ogni squadra che "
    "imposta un'immagine/logo personalizzato invece dello stemma di stock Fantacalcio "
    "(come lo scorso anno). Applicato al 1° turno: si propaga automaticamente ai turni "
    "successivi, nessun'altra azione necessaria."
)
teams_without_bonus = [t for t in TEAM_IDS if t not in teams_with_logo_bonus]
if not teams_without_bonus:
    st.caption("Tutte le squadre hanno già ricevuto il bonus.")
else:
    with st.form("assign_logo_bonus"):
        bonus_team = st.selectbox("Squadra", teams_without_bonus, format_func=_team_label)
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
            st.success(f"Bonus assegnato a {_team_label(bonus_team)}: +{ruleset.custom_logo_bonus_credits} crediti.")
            st.rerun()

st.divider()
st.subheader("Annulla un risultato")
st.caption(
    "Il ledger non cancella mai nulla: annullare aggiunge un evento di annullamento "
    "che sovrascrive l'effetto di quello scelto, restano entrambi nella storia."
)


def _describe(e) -> str:
    team = _team_label(e.team_id)
    if isinstance(e, BudgetAdjustmentEvent):
        return f"{team} — bonus {e.reason} +{e.amount} crediti — {ROUND_LABELS.get(e.round_id, e.round_id)}"
    names = []
    for pid in e.item.player_ids:
        row = get_player(player_conn, int(pid))
        names.append(row["display_name"] if row is not None else f"#{pid}")
    return f"{team} — {', '.join(names)} — {e.amount} crediti — {ROUND_LABELS.get(e.round_id, e.round_id)}"


active = [e for e in active_events if isinstance(e, (AssignmentEvent, BudgetAdjustmentEvent))]

if not active:
    st.caption("Nessun evento attivo da annullare.")
else:
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
