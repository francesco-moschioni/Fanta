"""Pagina Formazione & Consigli Giornata (Matchday Projections & Lineup Assistant).

Fornisce consigli di schieramento e formazione titolare per la prossima giornata di Serie A:
- Proiezioni probabilistiche di giornata (fantavoto atteso, probabilità titolare, range P10-P90, probabilità gol/assist/clean sheet);
- Consiglio dell'Undici Ideale Titolare e modulo tattico ottimale tra quelli ammessi (3-4-3, 4-3-3, 3-5-2, 4-4-2, 5-3-2, 5-4-1, 4-5-1, 3-4-1-2);
- Consultazione proiezioni di giornata per qualunque giocatore del listone.
"""

from __future__ import annotations

from pathlib import Path
import streamlit as st
import pandas as pd

from fantacalcio.persistence.ledger_store import connect as connect_ledger, load_events, DEFAULT_DB_PATH as DEFAULT_LEDGER_PATH
from fantacalcio.persistence.team_labels_store import connect as connect_labels, load_labels_config, seed_missing_labels, get_all_labels
from fantacalcio.persistence.player_table import connect as connect_player_table, search_players, search_players_fuzzy, DEFAULT_DB_PATH as DEFAULT_DUCKDB_PATH
from fantacalcio.domain import replay, effective_events
from fantacalcio.config import load_ruleset
from fantacalcio.modeling.matchday_event_model import project_player_matchday
from fantacalcio.scoring.matchday_monte_carlo import simulate_player_matchday


RULESET_PATH = Path("config/auction_rules.v1.yaml")

st.set_page_config(page_title="Formazione & Consigli Giornata", page_icon="⚽", layout="wide")

st.title("⚽ Formazione & Consigli Giornata")
st.markdown(
    "In questa pagina trovi i **consigli di schieramento per la prossima giornata**: "
    "proiezioni probabilistiche del fantavoto, probabilità di titolarità, stime di gol e assist, "
    "e il modulo con l'**Undici Ideale Titolare** più forte per la tua rosa."
)

ruleset = load_ruleset(RULESET_PATH)

# Seed team labels & load ledger events
if DEFAULT_LEDGER_PATH.exists():
    conn_ledger = connect_ledger(DEFAULT_LEDGER_PATH)
    conn_labels = connect_labels()
    seed_missing_labels(conn_labels, load_labels_config())
    team_labels = get_all_labels(conn_labels)
    raw_events = load_events(conn_ledger)
    eff_events = effective_events(raw_events)
    state = replay(ruleset, eff_events) if raw_events else None
else:
    team_labels = {}
    state = None

if not DEFAULT_DUCKDB_PATH.exists():
    st.error("Tabella DuckDB non trovata. Esegui `python scripts/build_player_table.py` prima.")
    st.stop()

conn_pt = connect_player_table(DEFAULT_DUCKDB_PATH)

if not state or not state.teams:
    st.info("Nessuna squadra con acquisti trovata nel ledger. Registra gli acquisti nella pagina Squadre per sbloccare l'Undici Ideale Titolare della tua rosa.")
else:
    # Team selector
    team_ids = sorted(list(state.teams.keys()))
    team_options = {tid: f"{team_labels.get(tid, tid)} ({tid})" for tid in team_ids}
    selected_team_id = st.selectbox(
        "Seleziona la tua squadra:",
        options=team_ids,
        format_func=lambda x: team_options[x],
        index=0,
    )

    team_state = state.teams[selected_team_id]
    roster_player_ids = team_state.all_player_ids

    if roster_player_ids:
        all_players_df = conn_pt.execute("SELECT * FROM players").df()
        roster_df = all_players_df[all_players_df["player_code"].isin(roster_player_ids)].copy()

        if not roster_df.empty:
            # Run projections and Monte Carlo simulations for each player in roster
            projections = []
            simulations = []

            for row in roster_df.itertuples(index=False):
                part_rate = float(getattr(row, "participation_rate", 0.75)) if not pd.isna(getattr(row, "participation_rate", 0.75)) else 0.75
                base_voto = float(getattr(row, "voti_mean", 6.10)) if hasattr(row, "voti_mean") and not pd.isna(getattr(row, "voti_mean", 6.10)) else 6.10

                opp_team = "Avversario"
                is_home = True

                proj = project_player_matchday(
                    player_code=row.player_code,
                    player_name=row.display_name,
                    role=row.role,
                    team=getattr(row, "team_name", "Serie A"),
                    opponent=opp_team,
                    is_home=is_home,
                    participation_rate=part_rate,
                    base_voto=base_voto,
                )
                sim = simulate_player_matchday(proj, n_sims=2000, seed=int(row.player_code))
                projections.append(proj)
                simulations.append(sim)

            data = []
            for p, s in zip(projections, simulations):
                data.append({
                    "player_code": p.player_code,
                    "Nome": p.player_name,
                    "Ruolo": p.role,
                    "Titolare %": f"{p.event_rates.starter_prob*100:.0f}%",
                    "Fantavoto Atteso": s.mean_fantavoto,
                    "Mediana (P50)": s.median_fantavoto,
                    "Intervallo [P10 - P90]": f"[{s.p10_fantavoto:.1f} - {s.p90_fantavoto:.1f}]",
                    "Gol %": f"{s.prob_at_least_1_goal*100:.1f}%",
                    "Assist %": f"{s.prob_at_least_1_assist*100:.1f}%",
                    "Clean Sheet %": f"{s.prob_clean_sheet*100:.1f}%" if p.role in ("P", "D") else "—",
                    "Rischio SV %": f"{s.prob_no_vote*100:.0f}%",
                    "Upside": s.upside_bonus,
                    "Downside": s.downside_risk,
                })

            proj_df = pd.DataFrame(data).sort_values("Fantavoto Atteso", ascending=False)

            # Module selection and Undici Ideale optimization
            st.markdown("---")
            st.subheader("⭐ Undici Ideale Titolare Consigliato")

            FORMATIONS = {
                "3-4-3": {"D": 3, "C": 4, "A": 3},
                "4-3-3": {"D": 4, "C": 3, "A": 3},
                "3-5-2": {"D": 3, "C": 5, "A": 2},
                "4-4-2": {"D": 4, "C": 4, "A": 2},
                "4-5-1": {"D": 4, "C": 5, "A": 1},
                "5-3-2": {"D": 5, "C": 3, "A": 2},
                "5-4-1": {"D": 5, "C": 4, "A": 1},
            }

            best_module = None
            best_score = -1.0
            best_xi = []
            best_bench = []

            for mod_name, req in FORMATIONS.items():
                gks = proj_df[proj_df["Ruolo"] == "P"].head(1)
                defs = proj_df[proj_df["Ruolo"] == "D"].head(req["D"])
                mids = proj_df[proj_df["Ruolo"] == "C"].head(req["C"])
                fwds = proj_df[proj_df["Ruolo"] == "A"].head(req["A"])

                if len(gks) < 1 or len(defs) < req["D"] or len(mids) < req["C"] or len(fwds) < req["A"]:
                    continue

                xi = pd.concat([gks, defs, mids, fwds])
                score = xi["Fantavoto Atteso"].sum()

                if score > best_score:
                    best_score = score
                    best_module = mod_name
                    best_xi = xi
                    best_bench = proj_df[~proj_df["player_code"].isin(xi["player_code"])]

            if best_module and not best_xi.empty:
                st.success(f"**Modulo Titolare Consigliato: {best_module}** (Fantavoto Atteso Totale Titolari: **{best_score:.2f}**)")
                col1, col2 = st.columns([3, 2])
                with col1:
                    st.write("### 🟢 Titolari (11)")
                    st.dataframe(
                        best_xi[["Nome", "Ruolo", "Titolare %", "Fantavoto Atteso", "Intervallo [P10 - P90]", "Gol %", "Assist %"]],
                        use_container_width=True,
                        hide_index=True,
                    )
                with col2:
                    st.write("### 🟡 Panchina")
                    st.dataframe(
                        best_bench[["Nome", "Ruolo", "Titolare %", "Fantavoto Atteso", "Rischio SV %"]],
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.warning("Rosa insufficiente per completare un modulo titolare valido (1P + 10 giocatori di movimento nei moduli ammessi).")

            # Full roster projection table
            st.markdown("---")
            st.subheader("📊 Tabella Completa Proiezioni Rosa")
            st.dataframe(
                proj_df[["Nome", "Ruolo", "Titolare %", "Fantavoto Atteso", "Mediana (P50)", "Intervallo [P10 - P90]", "Gol %", "Assist %", "Clean Sheet %", "Rischio SV %"]],
                use_container_width=True,
                hide_index=True,
            )

# Individual Player Query (Always available)
st.markdown("---")
st.subheader("🔍 Cerca Proiezione per un Giocatore Qualsiasi (Listone Serie A)")
search_q = st.text_input("Nome giocatore:", placeholder="es. Lautaro, Dybala, Kvaratskhelia...")

if search_q.strip():
    matches = search_players(conn_pt, name_query=search_q)
    if matches.empty:
        matches = search_players_fuzzy(conn_pt, name_query=search_q)

    if not matches.empty:
        p_row = matches.iloc[0]
        st.write(f"**{p_row['display_name']}** ({p_row['role']} - {p_row['team_name']})")

        part_rate = float(getattr(p_row, "participation_rate", 0.75)) if not pd.isna(getattr(p_row, "participation_rate", 0.75)) else 0.75
        base_v = float(getattr(p_row, "voti_mean", 6.10)) if hasattr(p_row, "voti_mean") and not pd.isna(getattr(p_row, "voti_mean", 6.10)) else 6.10

        p_proj = project_player_matchday(
            player_code=p_row.player_code,
            player_name=p_row.display_name,
            role=p_row.role,
            team=p_row.team_name,
            opponent="Avversario",
            is_home=True,
            participation_rate=part_rate,
            base_voto=base_v,
        )
        p_sim = simulate_player_matchday(p_proj, n_sims=5000, seed=42)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Fantavoto Atteso", f"{p_sim.mean_fantavoto:.2f}")
        m2.metric("Titolare %", f"{p_proj.event_rates.starter_prob*100:.0f}%")
        m3.metric("Probabilità Gol", f"{p_sim.prob_at_least_1_goal*100:.1f}%")
        m4.metric("Range [P10 - P90]", f"[{p_sim.p10_fantavoto:.1f} - {p_sim.p90_fantavoto:.1f}]")
    else:
        st.info("Nessun giocatore trovato con questo nome.")
