"""Profilo di mercato per turno chiuso: cosa dicono i risultati già registrati
sullo stato delle 19 squadre avversarie -- slot ancora scoperti, budget residuo
per slot, qualità di quanto hanno già comprato, inflazione osservata per ruolo
(ADR-2026-056). Descrittivo, non un'offerta: non sostituisce la Rosa ideale né
un futuro consiglio di offerta, aiuta a leggere il turno appena chiuso prima di
decidere come muoversi nel prossimo.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from fantacalcio.auction.market_model import (
    MIN_RELIABLE_SAMPLE,
    all_opponent_profiles,
    market_regime_ratio,
    price_tier_inflation,
    round_role_inflation,
    team_aggressiveness_index,
)
from fantacalcio.config import load_ruleset
from fantacalcio.persistence.ledger_store import (
    SeedFromSecretsError,
    connect as connect_ledger,
    load_current_league_state,
    load_events,
    seed_missing_events_from_streamlit_secrets,
)
from fantacalcio.persistence.player_table import DEFAULT_DB_PATH, connect as connect_players
from fantacalcio.persistence.team_labels_store import (
    connect as connect_labels,
    display_name,
    get_all_labels,
    load_labels_config,
    seed_missing_labels,
)

st.set_page_config(page_title="Fantacalcio — Mercato", page_icon="📊", layout="wide")
st.title("Mercato")
st.markdown(
    "Dopo che un turno viene chiuso e registrato in **Squadre**, questa pagina legge "
    "quei risultati e ti dice cosa implicano per le altre 19 squadre: a chi manca "
    "ancora un ruolo, chi ha molto budget rispetto a quanto gli resta da comprare, "
    "chi ha comprato solo giocatori economici (probabile riserva) e chi invece ha "
    "già speso su nomi sopra la media (probabile titolare), e come si è comportata "
    "ciascuna finora (aggressiva o cauta) — un segnale che vale anche per i turni "
    "successivi, coi ruoli nuovi che ancora non hanno dati propri. Serve a leggere "
    "il mercato prima di decidere come muoverti nel turno dopo — non è un consiglio "
    "di offerta pronto, quello resta una lettura tua (per quello vedi la scheda "
    "giocatore nella pagina Giocatori, che usa già questi stessi dati)."
)

ROUND_LABELS = {
    "G1": "1° turno — portieri + difensori",
    "G2": "2° turno — centrocampisti + attaccanti",
    "G3": "3° turno — chiunque sia rimasto",
    "G4": "4° turno — chiunque sia rimasto",
}
ROLE_LABELS = {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}

if not DEFAULT_DB_PATH.is_file():
    st.error("Tabella giocatori non trovata. Esegui `python scripts/build_player_table.py` prima.")
    st.stop()


@st.cache_resource
def _ruleset():
    return load_ruleset(Path("config/auction_rules.v1.yaml"))


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
try:
    _n_seeded = seed_missing_events_from_streamlit_secrets(ledger_conn, ruleset)
    if _n_seeded:
        st.toast(f"Importati automaticamente {_n_seeded} eventi dal ledger privato (secrets).")
except SeedFromSecretsError as exc:
    st.error(f"Seed automatico del ledger da secrets fallito: {exc}")
team_labels = get_all_labels(labels_conn)

TEAM_IDS = [f"team_{i:02d}" for i in range(1, ruleset.teams + 1)]
ROUND_IDS = [r.id for r in ruleset.rounds]


def _team_label(team_id: str) -> str:
    return display_name(team_id, team_labels)


all_events = load_events(ledger_conn)
state = load_current_league_state(ledger_conn, ruleset)

closed_rounds = [rid for rid in ROUND_IDS if any(rid in state.team(t).budgets for t in TEAM_IDS)]
if not closed_rounds:
    st.info("Nessun turno ancora registrato: vai su **Squadre** per registrare i risultati del primo turno.")
    st.stop()

round_id = st.selectbox(
    "Turno da leggere",
    closed_rounds,
    index=len(closed_rounds) - 1,
    format_func=lambda r: ROUND_LABELS.get(r, r),
    help="Il profilo mostra lo stato delle squadre DOPO l'ultimo evento registrato per questo turno, non una proiezione.",
)

my_team_id = st.session_state.get("my_team_id", TEAM_IDS[0])
opponent_ids = [t for t in TEAM_IDS if t != my_team_id]

st.subheader("Profilo squadre avversarie")
st.caption(
    "Slot ancora scoperti per ruolo, budget residuo diviso per gli slot che restano "
    "(più alto = più margine per offrire aggressivo su un singolo giocatore), e "
    "segnale di qualità (differenza tra il prezzo medio pagato finora in quel ruolo "
    "e la quotazione media dell'intero pool di quel ruolo — positivo vuol dire che "
    "ha comprato sopra la media, probabile titolare; negativo, probabile riserva "
    "ancora in cerca di un titolare)."
)

aggressiveness = team_aggressiveness_index(all_events, player_conn, opponent_ids)

profiles = all_opponent_profiles(state, ruleset, player_conn, round_id, opponent_ids)
rows = []
for p in profiles:
    row = {"Squadra": _team_label(p.team_id), "Budget residuo": p.budget_remaining}
    row["Budget / slot libero"] = f"{p.budget_per_open_slot:.1f}" if p.budget_per_open_slot is not None else "rosa completa"
    agg = aggressiveness.get(p.team_id)
    if agg is not None:
        tag = "" if agg.reliable else " (poca affidabilità)"
        row["Stile di offerta"] = f"{agg.delta_vs_market:+.2f}{tag}"
    else:
        row["Stile di offerta"] = "—"
    for voti_role, label in ROLE_LABELS.items():
        row[f"{label} mancanti"] = p.slots_needed.get(voti_role, 0)
    for voti_role, label in ROLE_LABELS.items():
        signal = p.quality_signal.get(voti_role)
        row[f"Qualità {label.lower()}"] = f"{signal:+.1f}" if signal is not None else "—"
    rows.append(row)

st.dataframe(
    rows, width="stretch", hide_index=True,
    column_config={
        "Stile di offerta": st.column_config.TextColumn(
            help="Quanto questa squadra ha pagato sopra/sotto la quotazione, in media, rispetto "
            "al resto della lega, su TUTTI gli acquisti fatti finora (qualsiasi ruolo/turno). "
            "Positivo = più aggressiva della media, negativo = più cauta. È un segnale sullo "
            "stile della squadra, non sul ruolo — utile anche per i turni con ruoli nuovi."
        ),
    },
)

st.divider()
st.subheader("Regime di mercato generale")
regime = market_regime_ratio(all_events, player_conn)
if regime is None:
    st.info("Nessuna compravendita ancora registrata.")
else:
    note = "" if regime.reliable else f" — solo {regime.n} osservazioni, poca affidabilità"
    st.metric(
        "Prezzo medio / quotazione, tutta la lega, tutti i turni chiusi finora",
        f"{regime.mean_ratio:.2f}×",
        help=f"Range osservato {regime.low_ratio:.2f}×–{regime.high_ratio:.2f}× su {regime.n} "
        f"compravendite (blocchi portiere inclusi, prezzati contro la somma delle quotazioni dei "
        f"3 portieri).{note} È la stima più generica possibile: si usa quando non c'è ancora nulla "
        "di più specifico (per ruolo o per fascia di prezzo) per i ruoli di un turno futuro."
    )

st.divider()
st.subheader("Inflazione per ruolo e fascia di prezzo")
st.caption(
    "Non un solo moltiplicatore per ruolo: qui il ruolo è diviso in fasce di quotazione "
    "(bassa/media/alta), perché nella pratica i giocatori economici spesso vengono pagati "
    "molto più sopra quotazione di quelli costosi (effetto offerta minima). Include TUTTI "
    "i turni chiusi finora (non solo quello selezionato sopra), perché più dati storici "
    "raccogliamo più la stima per fascia diventa affidabile. Il blocco portieri resta escluso."
)

any_tier_data = False
for voti_role, label in ROLE_LABELS.items():
    if voti_role == "P":
        continue
    tiers = price_tier_inflation(all_events, player_conn, voti_role=voti_role)
    if not tiers:
        continue
    any_tier_data = True
    st.markdown(f"**{label}**")
    tier_rows = [
        {
            "Fascia": t.tier_label,
            "Quotazione": f"{t.quotazione_min}–{t.quotazione_max}",
            "Rapporto medio": f"{t.mean_ratio:.2f}×",
            "Range": f"{t.low_ratio:.2f}×–{t.high_ratio:.2f}×",
            "Osservazioni": t.n,
            "Affidabilità": "buona" if t.reliable else "bassa",
        }
        for t in tiers
    ]
    st.dataframe(tier_rows, width="stretch", hide_index=True)

if not any_tier_data:
    st.info(
        "Non ci sono ancora abbastanza compravendite individuali per suddividere in fasce di "
        "prezzo (serve un minimo di osservazioni per turno/ruolo)."
    )

st.divider()
st.subheader("Inflazione per ruolo (turno selezionato sopra)")
st.caption(
    "Vista sintetica per il solo turno scelto in cima alla pagina — un numero unico per ruolo, "
    "senza la suddivisione in fasce (utile per un confronto rapido tra turni)."
)

inflation = round_role_inflation(all_events, player_conn, round_id)
if not inflation:
    st.info("Nessuna compravendita individuale (non-portiere) in questo turno da cui stimare un'inflazione.")
else:
    for r in inflation:
        label = ROLE_LABELS.get(r.role, r.role)
        cols = st.columns([2, 3, 5])
        cols[0].metric(label, f"{r.mean_ratio:.2f}×")
        cols[1].caption(f"range osservato: {r.low_ratio:.2f}× – {r.high_ratio:.2f}× (n={r.n})")
        if not r.reliable:
            cols[2].warning(
                f"Solo {r.n} osservazioni (sotto {MIN_RELIABLE_SAMPLE}): stima rumorosa, "
                "da prendere come indicazione di direzione, non come numero preciso."
            )
        else:
            cols[2].caption(f"{r.n} osservazioni: stima ragionevolmente stabile.")
