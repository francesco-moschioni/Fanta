"""Giornata / Formazione: scegli l'undici titolare per una giornata dalla tua
rosa reale (M6, docs/UX_PRODUCT.md; ADR-2026-080).

Come le altre pagine, qui non si calcola nulla che appartenga al motore: la
pagina chiama solo `fantacalcio.lineup.*`. I numeri per-giocatore (media
simulata, floor/ceiling, probabilità di voto) arrivano dalla tabella giocatori
DuckDB, la rosa dal registro delle aste (come nella pagina Rosa). Il
modificatore difesa e il bonus capitano NON sono regole approvate: il
modificatore compare solo se lo attivi, con avviso in chiaro; il capitano
suggerito è "chi rende di più in media", non "ottimo secondo il bonus".
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from fantacalcio.config import load_ruleset
from fantacalcio.domain import Role
from fantacalcio.lineup import (
    MODIFIER_DISCLAIMER,
    PRESETS,
    PlayerSlot,
    bench_notes,
    best_xi,
    compare_formations,
    load_formations,
    parse_formation,
    player_score,
    suggest_captain,
)
from fantacalcio.lineup.sv_risk import flag_sv_risk
from fantacalcio.persistence.ledger_store import (
    SeedFromSecretsError,
    connect as connect_ledger,
    load_current_league_state,
    seed_missing_events_from_streamlit_secrets,
)
from fantacalcio.persistence.locks_store import connect as connect_locks, list_locks
from fantacalcio.persistence.player_table import (
    DEFAULT_DB_PATH,
    connect as connect_players,
    get_player,
)
from fantacalcio.persistence.team_labels_store import (
    connect as connect_labels,
    display_name,
    get_all_labels,
    load_labels_config,
    seed_missing_labels,
)

st.set_page_config(page_title="Fantacalcio — Formazione", page_icon="⚽", layout="wide")
st.title("Giornata / Formazione")
st.markdown(
    "**Cosa fa:** prende la tua rosa reale (dal registro delle aste) e sceglie "
    "l'undici titolare che rende di più per una giornata tipo, con capitano "
    "consigliato, ordine della panchina e avvisi su chi rischia di non prendere "
    "voto. **Quando usarla:** dopo l'asta, per preparare la formazione. "
    "**Attenzione:** usa la *media di una giornata qualunque* (`sim_mean`), non "
    "l'avversario specifico di quel turno — non esistono ancora calendario, "
    "infortuni o probabili formazioni in questo strumento."
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
def _player_conn():
    return connect_players()


@st.cache_resource
def _labels_conn():
    return connect_labels()


ruleset = _ruleset()
ledger_conn = _ledger_conn()
locks_conn = _locks_conn()
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
if "my_team_id" not in st.session_state:
    st.session_state["my_team_id"] = TEAM_IDS[0]

st.selectbox(
    "La mia squadra", TEAM_IDS, key="my_team_id",
    format_func=lambda t: display_name(t, team_labels),
)
my_team_id = st.session_state["my_team_id"]
my_team_label = display_name(my_team_id, team_labels)

state = load_current_league_state(ledger_conn, ruleset)
team = state.team(my_team_id)
my_locks = list_locks(locks_conn, my_team_id)

DOMAIN_TO_CODE = {Role.GK: "P", Role.DEF: "D", Role.MID: "C", Role.FWD: "A"}
ROLE_LABEL = {"P": "Portiere", "D": "Difensore", "C": "Centrocampista", "A": "Attaccante"}

st.divider()
st.subheader("1. Come vuoi rischiare")
st.caption(
    "**Prudente**: premia chi ha un rendimento minimo affidabile e gioca sempre. "
    "**Bilanciato**: solo la media attesa. **Aggressivo**: premia chi può fare la "
    "partitona anche se incostante."
)
profile_name = st.radio(
    "Profilo di rischio", list(PRESETS.keys()), index=1, horizontal=True,
    format_func=str.capitalize,
)
profile = PRESETS[profile_name]

# --- build PlayerSlots from the real roster ---------------------------------
include_locks = st.checkbox(
    "Includi anche gli obiettivi bloccati (lock) come se fossero in rosa",
    value=False,
    help="I lock sono ipotetici, non ancora vinti. Attiva solo per simulare.",
)

seen: set[int] = set()
slots: list[PlayerSlot] = []
missing_rows: list[int] = []


def _add_player(code: int, fallback_role_code: str | None = None) -> None:
    if code in seen:
        return
    seen.add(code)
    row = get_player(player_conn, code)
    if row is None:
        missing_rows.append(code)
        return
    role_code = str(row["role"]) if str(row["role"]) in ROLE_LABEL else fallback_role_code
    if role_code not in ROLE_LABEL:
        missing_rows.append(code)
        return
    slots.append(
        PlayerSlot(
            player_code=int(code),
            role=role_code,
            score=float(player_score(row, profile)),
            sim_mean=float(row["sim_mean"]),
            p10=float(row["sim_p10"]),
            p90=float(row["sim_p90"]),
            # participation_rate is NaN/None for new signings with no Serie A
            # history -- show it as unknown rather than "nan%".
            p_vote=(
                float(row["participation_rate"])
                if row["participation_rate"] is not None
                and float(row["participation_rate"]) == float(row["participation_rate"])
                else float("nan")
            ),
            display_name=str(row["display_name"]),
            data_quality_tier=str(row["data_quality_tier"]),
        )
    )


for domain_role, codes in team.roster.items():
    for pid in codes:
        _add_player(int(pid), DOMAIN_TO_CODE.get(domain_role))

if include_locks:
    for lock in my_locks:
        _add_player(int(lock.player_code), lock.role)

if missing_rows:
    st.caption(
        f"{len(missing_rows)} giocatori in rosa non hanno una riga nella tabella "
        "giocatori e sono stati esclusi dal calcolo."
    )

fielded = len(slots)
if fielded < 11:
    st.warning(
        f"La rosa nel registro è **parziale** ({fielded} giocatori con dati "
        "utilizzabili): su questo ramo il ledger contiene solo G1+G2, G3/G4 non "
        "sono ancora riconciliati. Lo strumento gira lo stesso con quello che c'è."
    )

if fielded == 0:
    st.info("Nessun giocatore utilizzabile in rosa: niente da calcolare.")
    st.stop()

by_role_count = {rc: sum(1 for s in slots if s.role == rc) for rc in ROLE_LABEL}
st.caption(
    "Giocatori disponibili per il calcolo: "
    + ", ".join(f"{by_role_count[rc]} {ROLE_LABEL[rc].lower()}" for rc in ROLE_LABEL)
)

st.divider()
st.subheader("2. Modulo")
mode = st.radio(
    "Come scegliere il modulo",
    ["Modulo fisso", "Modulo libero (confronta tutti)"],
    horizontal=True,
)
all_formations = load_formations(ruleset)
fixed_formation = None
if mode == "Modulo fisso":
    fixed_name = st.selectbox("Modulo", [f.name for f in all_formations])
    fixed_formation = parse_formation(fixed_name)

use_modifier = st.checkbox("Considera il modificatore difesa", value=False)
if use_modifier:
    st.warning(MODIFIER_DISCLAIMER)

st.divider()
st.subheader("3. Formazione consigliata")


def _render_lineup(res) -> None:
    if not res.feasible:
        st.error(f"Modulo {res.formation.name} non fattibile: {res.infeasible_reason}")
        return
    flagged = set(flag_sv_risk(res.starters))
    rows = []
    for s in res.starters:
        rows.append(
            {
                "Titolare": s.display_name,
                "Ruolo": ROLE_LABEL[s.role],
                "E[punti]": round(s.sim_mean, 2),
                "Floor (p10)": round(s.p10, 2),
                "Ceiling (p90)": round(s.p90, 2),
                "Prob. voto": "n/d" if s.p_vote != s.p_vote else f"{s.p_vote:.0%}",
                "Rischio SV": "⚠️" if s.player_code in flagged else "",
                "Qualità dati": s.data_quality_tier,
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption(
        f"Punteggio totale (profilo {profile.name}): **{res.total_score:.2f}** — "
        f"somma E[punti] titolari: **{res.expected_points:.2f}**"
        + (
            f" — stima modificatore difesa (storico, non ratificato): **+{res.defence_modifier_estimate:.2f}**"
            if res.defence_modifier_estimate is not None
            else ""
        )
    )

    captain = suggest_captain(res.starters, profile)
    if captain is not None:
        st.markdown(f"**Capitano consigliato:** {captain.display_name}")
        st.caption(captain.reason)

    st.markdown("**Panchina (ordine consigliato per la regola max 5 sostituzioni, no switch):**")
    if res.bench:
        st.dataframe(
            [
                {"Riserva": s.display_name, "Ruolo": ROLE_LABEL[s.role], "E[punti]": round(s.sim_mean, 2)}
                for s in res.bench
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("Nessuna riserva disponibile.")
    for note in bench_notes(res.bench, res.formation):
        st.caption(f"• {note}")


if mode == "Modulo fisso":
    result = best_xi(slots, fixed_formation, defence_modifier=use_modifier)
    _render_lineup(result)
else:
    results = compare_formations(
        slots, all_formations, profile=profile, defence_modifier=use_modifier
    )
    feasible = [r for r in results if r.feasible]
    if not feasible:
        st.warning(
            "Nessun modulo è fattibile con la rosa attualmente nel registro "
            "(su questo ramo mancano G3/G4): servono più difensori/attaccanti di "
            "quanti ne risultino vinti. Qui sotto il motivo per ciascun modulo."
        )
        st.dataframe(
            [
                {"Modulo": r.formation.name, "Motivo": r.infeasible_reason}
                for r in results
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        table = []
        for r in results:
            table.append(
                {
                    "Modulo": r.formation.name,
                    "Fattibile": "Sì" if r.feasible else "No",
                    "Punteggio totale": round(r.total_score, 2) if r.feasible else None,
                    "E[punti] titolari": round(r.expected_points, 2) if r.feasible else None,
                    "Mod. difesa (stima)": (
                        round(r.defence_modifier_estimate, 2)
                        if r.defence_modifier_estimate is not None
                        else None
                    ),
                    "Nota": r.infeasible_reason if not r.feasible else "",
                }
            )
        st.dataframe(table, width="stretch", hide_index=True)
        st.markdown(f"### Modulo migliore: {feasible[0].formation.name}")
        _render_lineup(feasible[0])
