#!/usr/bin/env python3
"""Validate the Dixon-Coles -> Monte Carlo team-strength adjustment, honestly.

Walk-forward: fit everything (Dixon-Coles, voto bootstrap pools, team ratings) on
2021/22-2024/25, predict 2025/26 (never seen). Compares correlation with real Fm
for several k values against the unadjusted baseline (k=0, i.e. ADR-2026-018's
existing validation). If no k beats the baseline, that's reported and the
adjustment is NOT adopted -- same honesty standard as ADR-2026-017's reverted
defender clean-sheet attempt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fantacalcio.modeling.dixon_coles import fit_dixon_coles
from fantacalcio.modeling.player_voto import load_player_matchday_panel
from fantacalcio.modeling.team_matchday import build_all_seasons
from fantacalcio.scoring.monte_carlo import build_event_pools, simulate_fantavoto
from fantacalcio.scoring.team_strength_adjustment import (
    apply_adjustment,
    compute_adjustments,
    historical_avg_team_rating,
    team_ratings_from_model,
)

SEASONS = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]
FD_SEASON_CODES = {"2021_22": "2122", "2022_23": "2223", "2023_24": "2324", "2024_25": "2425", "2025_26": "2526"}
N_SIMS = 500  # smaller than the main script (1000) to keep the k-sweep tractable
SEED = 42
K_VALUES = [0.0, 0.1, 0.25, 0.5, 1.0]


def main() -> None:
    print("Loading voti panel and joining team data...")
    voti = load_player_matchday_panel()
    rated = voti[~voti["voto_no_vote"]].copy()

    frames = []
    for season in SEASONS:
        path = f"data/staged/fantacalcio_quotazioni_manual/{season}.csv"
        df = pd.read_csv(path)[["player_code", "team_name"]].copy()
        df["season_label"] = season
        frames.append(df)
    player_team = pd.concat(frames, ignore_index=True)
    rated = rated.merge(player_team, on=["player_code", "season_label"], how="left")

    team_matchday = build_all_seasons().frame
    rated = rated.merge(
        team_matchday[["team_name", "season_label", "matchday", "goals_conceded"]].rename(
            columns={"goals_conceded": "team_goals_conceded"}
        ),
        on=["team_name", "season_label", "matchday"],
        how="left",
    )

    train = rated[rated["season_label"] != "2025_26"]
    target = rated[rated["season_label"] == "2025_26"]

    print("Fitting Dixon-Coles on training seasons...")
    fd_train = pd.concat(
        [pd.read_csv(f"data/staged/football_data_co_uk/serie_a_{FD_SEASON_CODES[s]}.csv", parse_dates=["Date"]) for s in SEASONS if s != "2025_26"],
        ignore_index=True,
    )
    dc_model = fit_dixon_coles(fd_train)
    ratings = team_ratings_from_model(dc_model)

    print("Building voto pools and historical team-rating context...")
    player_pools, role_pools = build_event_pools(train)
    hist_attack = historical_avg_team_rating(train, ratings, "attack")
    hist_defense = historical_avg_team_rating(train, ratings, "defense")

    target_players = target[["player_code", "role", "team_name"]].drop_duplicates("player_code").set_index("player_code")
    adjustments_by_k = {
        k: compute_adjustments(target_players["team_name"], target_players["role"], hist_attack, hist_defense, ratings, k)
        for k in K_VALUES
    }

    statistiche = pd.read_csv("data/staged/fantacalcio_statistiche_manual/2025_26.csv").astype({"player_code": "int64"})

    print(f"Simulating {len(target_players)} players x {len(K_VALUES)} k-values x {N_SIMS} sims...")
    rows = []
    rng = np.random.default_rng(SEED)
    for player_code, r in target_players.iterrows():
        base_result = simulate_fantavoto(player_code, r["role"], player_pools, role_pools, n_sims=N_SIMS, rng=rng)
        for k in K_VALUES:
            adj = adjustments_by_k[k].get(player_code, 0.0)
            adjusted = apply_adjustment(base_result, adj) if adj != 0.0 else base_result
            rows.append({"player_code": player_code, "k": k, "sim_mean": adjusted.mean})

    sim_df = pd.DataFrame(rows).astype({"player_code": "int64"})
    merged = sim_df.merge(statistiche[["player_code", "fantamedia"]], on="player_code", how="inner").dropna(subset=["fantamedia"])

    print("\n=== Results ===")
    lines = ["# Team-strength adjustment validation (walk-forward, honest)", "", "| k | Correlation with real Fm | Mean gap |", "|---:|---:|---:|"]
    for k in K_VALUES:
        subset = merged[merged["k"] == k]
        corr = subset["sim_mean"].corr(subset["fantamedia"])
        gap = (subset["fantamedia"] - subset["sim_mean"]).mean()
        print(f"k={k}: correlation={corr:.4f}, mean gap={gap:.4f}")
        lines.append(f"| {k} | {corr:.4f} | {gap:.4f} |")

    baseline_corr = merged[merged["k"] == 0.0]["sim_mean"].corr(merged[merged["k"] == 0.0]["fantamedia"])
    best_k = max(K_VALUES, key=lambda k: merged[merged["k"] == k]["sim_mean"].corr(merged[merged["k"] == k]["fantamedia"]))
    best_corr = merged[merged["k"] == best_k]["sim_mean"].corr(merged[merged["k"] == best_k]["fantamedia"])
    verdict = "ADOPT" if best_k != 0.0 and best_corr > baseline_corr + 0.005 else "DO NOT ADOPT (no meaningful improvement)"
    print(f"\nBaseline (k=0) correlation: {baseline_corr:.4f}. Best: k={best_k}, correlation={best_corr:.4f}. Verdict: {verdict}")
    lines += ["", f"**Verdict: {verdict}** (baseline k=0 correlation={baseline_corr:.4f}, best k={best_k} correlation={best_corr:.4f})"]

    from pathlib import Path
    Path("data/staged/fantacalcio_voti_manual/_team_strength_adjustment_validation.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
