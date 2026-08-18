"""Buste G2: componi le 5 liste (3 fasce centrocampisti + 2 fasce attaccanti,
ADR-2026-060) e verifica la fattibilità di budget prima che G2 inizi davvero.

Ogni fascia è una busta indipendente: fino a 6 preferenze, si vince al più UN
giocatore per fascia (quello con la preferenza più alta tra chi risolve a tuo
favore). Questa pagina è solo pianificazione (docs/CURRENT_TASK.md, stesso
principio di locks_store.py): salvare una preferenza qui non tocca il ledger
reale, il budget o la rosa -- lo stato reale continua a leggersi solo da
`domain.replay()` sugli eventi effettivamente registrati in Squadre.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from fantacalcio.auction.g2_envelope_feasibility import (
    G2_BAND_ROLE,
    MAX_PREFERENCES_PER_BAND,
    check_pick_feasibility,
    project_downstream_budget,
    summarize_g2_feasibility,
)
from fantacalcio.config import ConfigError, load_ruleset
from fantacalcio.persistence.g2_envelopes_store import connect as connect_envelopes, list_picks, remove_pick, save_pick
from fantacalcio.persistence.ledger_store import (
    SeedFromSecretsError,
    connect as connect_ledger,
    load_current_league_state,
    seed_missing_events_from_streamlit_secrets,
)
from fantacalcio.persistence.player_table import connect as connect_players, get_player, search_players
from fantacalcio.persistence.team_labels_store import (
    connect as connect_labels,
    display_name,
    get_all_labels,
    load_labels_config,
    seed_missing_labels,
)

st.set_page_config(page_title="Fantacalcio — Buste G2", page_icon="📝", layout="wide")
st.title("Buste G2")
st.markdown(
    "G2 non è un pool unico per ruolo: i centrocampisti (60) e gli attaccanti "
    "(40) della lista admin sono divisi in **fasce da 20**, ciascuna una busta "
    "indipendente con le sue 6 preferenze (prima la preferenza, poi l'offerta, "
    "in caso di parità). Componi qui le 5 buste e controlla se il budget "
    "residuo regge — nessuna offerta qui è reale finché non registri il "
    "risultato in Squadre."
)

RULESET_PATH = Path("config/auction_rules.v1.yaml")
BAND_LABELS = {
    "midfielders_top_1_20": "Centrocampisti 1-20",
    "midfielders_top_21_40": "Centrocampisti 21-40",
    "midfielders_top_41_60": "Centrocampisti 41-60",
    "forwards_top_1_20": "Attaccanti 1-20",
    "forwards_top_21_40": "Attaccanti 21-40",
}

ruleset = load_ruleset(RULESET_PATH)
ledger_conn = connect_ledger()
envelope_conn = connect_envelopes()
player_conn = connect_players()
labels_conn = connect_labels()

seed_missing_labels(labels_conn, load_labels_config())
try:
    _n_seeded = seed_missing_events_from_streamlit_secrets(ledger_conn, ruleset)
    if _n_seeded:
        st.toast(f"Importati automaticamente {_n_seeded} eventi dal ledger privato (secrets).")
except SeedFromSecretsError as exc:
    st.error(f"Seed automatico del ledger da secrets fallito: {exc}")

TEAM_IDS = [f"team_{i:02d}" for i in range(1, ruleset.teams + 1)]
my_team_id = st.session_state.get("my_team_id", TEAM_IDS[0])
st.caption(f"Squadra: **{display_name(my_team_id, get_all_labels(labels_conn))}** (cambiala nella Home)")

league_state = load_current_league_state(ledger_conn, ruleset)
all_picks = list_picks(envelope_conn, my_team_id)

try:
    report = summarize_g2_feasibility(my_team_id, ruleset, league_state, all_picks)
except ConfigError:
    st.warning(
        "G2 non è ancora raggiungibile per questa squadra: nel ledger non risulta ancora nessun evento "
        "G1 per lei, quindi il budget G2 (che dipende dal residuo di G1) non è calcolabile. Se hai "
        "appena importato o aggiornato dati reali, verifica di aver ricaricato/riseedato il ledger su "
        "questa istanza (pagina Squadre, sezione Importa/esporta ledger)."
    )
    st.stop()

st.subheader("Fattibilità G2")
col1, col2, col3 = st.columns(3)
col1.metric("Budget G2 disponibile", report.g2_budget_available)
col2.metric("Spesa peggiore stimata", report.worst_case_total_spend)
col3.metric("Margine (caso peggiore)", report.margin, delta_color="normal" if report.ok else "inverse")
if report.ok:
    st.success("Le 5 buste, anche nel caso peggiore (vinci sempre la preferenza più cara di ogni fascia), stanno nel budget G2.")
else:
    st.error(
        f"Sforamento di {-report.margin} crediti nel caso peggiore: abbassa qualche offerta o rimuovi una preferenza."
    )
col4, col5 = st.columns(2)
col4.metric("Spesa se vinci sempre la #1", report.first_choice_total_spend)
col5.metric("Margine (tutte prime scelte)", report.first_choice_margin, delta_color="normal" if report.first_choice_ok else "inverse")
with st.expander("Come è calcolato (G2)"):
    for line in report.explanation:
        st.markdown(f"- {line}")

st.subheader("E dopo G2? Proiezione su G3/G4")
st.caption(
    "In G3/G4 non ci sono più liste: offerta libera, ma il minimo è la "
    "quotazione del giocatore (non 1 credito come in G1/G2). Questa proiezione "
    "controlla se, dopo lo scenario G2 scelto, resta abbastanza budget per "
    "completare la rosa comprando anche solo i giocatori più economici ancora "
    "liberi."
)

all_players = search_players(player_conn)
undrafted_pool = all_players[~all_players["player_code"].astype(str).isin(league_state.assigned_players)]

scenarios = [
    (
        "Caso peggiore (vinci sempre l'offerta più cara di ogni fascia)",
        report.worst_case_total_spend,
        [b.top_preference_player_code for b in report.bands if b.top_preference_player_code is not None],
    ),
    (
        "Vinci sempre la preferenza #1 di ogni fascia",
        report.first_choice_total_spend,
        [b.first_choice_player_code for b in report.bands if b.first_choice_player_code is not None],
    ),
]
for label, spend, won_codes in scenarios:
    projection = project_downstream_budget(my_team_id, ruleset, league_state, label, spend, won_codes, undrafted_pool)
    pcol1, pcol2, pcol3 = st.columns(3)
    pcol1.metric(f"{label} — budget G3+G4", projection.g3_g4_budget)
    pcol2.metric("Minimo per completare la rosa", projection.min_required_credits)
    pcol3.metric("Margine G3/G4", projection.shortfall, delta_color="normal" if projection.ok else "inverse")
    if not projection.ok:
        st.error(
            f"**{label}**: mancano {-projection.shortfall} crediti anche solo per prendere i giocatori più "
            "economici rimasti. Con questo scenario di offerte G2 sei in difficoltà — abbassa qualche "
            "offerta o punta giocatori più economici."
        )
    with st.expander(f"Come è calcolato — {label}"):
        for line in projection.explanation:
            st.markdown(f"- {line}")

st.divider()

for band_name in G2_BAND_ROLE:
    role = G2_BAND_ROLE[band_name]
    st.subheader(BAND_LABELS[band_name])

    band_players = search_players(player_conn, role=role, round_pool="G2")
    band_players = band_players[band_players["list_pool_name"] == band_name]

    existing_band_picks = [p for p in all_picks if p.list_pool_name == band_name]
    existing_by_code = {p.player_code: p for p in existing_band_picks}

    if existing_band_picks:
        st.caption(f"{len(existing_band_picks)}/{MAX_PREFERENCES_PER_BAND} preferenze salvate")
        for pick in sorted(existing_band_picks, key=lambda p: p.preference_rank):
            player_row = get_player(player_conn, pick.player_code)
            name = player_row["display_name"] if player_row is not None else str(pick.player_code)
            pcol1, pcol2, pcol3 = st.columns([3, 1, 1])
            pcol1.write(f"**#{pick.preference_rank}** {name}")
            pcol2.write(f"{pick.bid_amount} crediti")
            if pcol3.button("Rimuovi", key=f"remove_{band_name}_{pick.player_code}"):
                remove_pick(envelope_conn, my_team_id, band_name, pick.player_code)
                st.rerun()
    else:
        st.caption("Nessuna preferenza salvata per questa fascia.")

    if len(existing_band_picks) >= MAX_PREFERENCES_PER_BAND:
        st.info("Fascia completa (6/6). Rimuovi una preferenza per aggiungerne un'altra.")
        continue

    available = band_players[~band_players["player_code"].astype(int).isin(existing_by_code.keys())]
    if available.empty:
        st.warning("Nessun giocatore disponibile in questa fascia (già assegnati o già in busta).")
        continue

    options = {
        f"{row.display_name} ({row.team_name}) — rank admin {int(row.admin_rank) if row.admin_rank == row.admin_rank else '—'}, "
        f"VAR {row.var_mean:.2f}, quot. {row.quotazione_asta:.0f}": row
        for row in available.sort_values("admin_rank").itertuples(index=False)
    }
    with st.form(key=f"add_{band_name}"):
        choice_label = st.selectbox("Aggiungi giocatore", list(options.keys()), key=f"select_{band_name}")
        add_col1, add_col2 = st.columns([1, 1])
        preference_rank = add_col1.number_input(
            "Preferenza (1 = più alta)", min_value=1, max_value=MAX_PREFERENCES_PER_BAND,
            value=len(existing_band_picks) + 1, key=f"rank_{band_name}",
        )
        bid_amount = add_col2.number_input("Offerta (crediti)", min_value=1, value=1, key=f"bid_{band_name}")
        submitted = st.form_submit_button("Aggiungi alla busta")

    if submitted:
        row = options[choice_label]
        admin_rank = None if row.admin_rank != row.admin_rank else float(row.admin_rank)  # NaN check
        result = check_pick_feasibility(
            my_team_id, band_name, int(row.player_code), admin_rank, ruleset, league_state, all_picks,
        )
        if not result.ok:
            st.error(result.reason)
        else:
            save_pick(
                envelope_conn, my_team_id, band_name, int(row.player_code), role,
                int(preference_rank), int(bid_amount),
            )
            st.rerun()

    st.divider()
