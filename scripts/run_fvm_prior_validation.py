#!/usr/bin/env python3
"""Validate FVM-bucketed role pools as a secondary prior for low/no-history
players, honestly.

Walk-forward: fit everything on 2021/22-2024/25, predict 2025/26. Restricted to
players with < LOW_HISTORY_GAMES own-history rows in the training window (where
the flat role-average fallback is weakest, per ADR-2026-020) -- comparing across
*all* players would dilute any effect, since most players aren't in this bucket.
If FVM-bucketed pools don't beat the flat role-pool baseline on this subset,
that's reported and the change is NOT adopted, same standard as ADR-2026-017.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fantacalcio.modeling.player_voto import load_player_matchday_panel
from fantacalcio.modeling.team_matchday import build_all_seasons
from fantacalcio.scoring.fvm_prior import (
    build_fvm_bucketed_role_pools,
    fit_fvm_bucket_edges,
    load_fvm_lookup,
)
from fantacalcio.scoring.monte_carlo import build_event_pools, simulate_fantavoto

SEASONS = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]
TRAIN_SEASONS = SEASONS[:-1]
N_SIMS = 500
SEED = 42
LOW_HISTORY_GAMES = 10


def main() -> None:
    print("Loading voti panel and joining team + FVM data...")
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

    fvm = load_fvm_lookup(SEASONS)
    rated = rated.merge(fvm, on=["player_code", "season_label"], how="left")

    train = rated[rated["season_label"] != "2025_26"]
    target = rated[rated["season_label"] == "2025_26"]

    print("Building flat role pools (baseline) and FVM-bucketed role pools...")
    player_pools, role_pools = build_event_pools(train)
    edges = fit_fvm_bucket_edges(fvm[fvm["season_label"].isin(TRAIN_SEASONS)].merge(
        train[["player_code", "season_label", "role"]].drop_duplicates(), on=["player_code", "season_label"]
    )[["role", "fvm_classic"]], n_buckets=4)
    fvm_pools = build_fvm_bucketed_role_pools(train, edges)

    target_players = target[["player_code", "role"]].drop_duplicates()
    target_players["games"] = target_players["player_code"].map(lambda p: len(player_pools.get(p, [])))
    target_fvm = target[["player_code", "fvm_classic"]].drop_duplicates("player_code").set_index("player_code")["fvm_classic"]

    low_history = target_players[target_players["games"] < LOW_HISTORY_GAMES].copy()
    low_history["fvm_classic"] = low_history["player_code"].map(target_fvm)
    low_history = low_history.dropna(subset=["fvm_classic"])
    print(f"Low/no-history subset (< {LOW_HISTORY_GAMES} games, FVM known): {len(low_history)} players")

    statistiche = pd.read_csv("data/staged/fantacalcio_statistiche_manual/2025_26.csv").astype({"player_code": "int64"})

    rows = []
    rng_baseline = np.random.default_rng(SEED)
    rng_fvm = np.random.default_rng(SEED)
    for r in low_history.itertuples(index=False):
        baseline = simulate_fantavoto(r.player_code, r.role, player_pools, role_pools, n_sims=N_SIMS, rng=rng_baseline)
        bucket = edges.get(r.role)
        bucket_idx = None
        if bucket is not None:
            from fantacalcio.scoring.fvm_prior import assign_bucket
            bucket_idx = assign_bucket(r.fvm_classic, r.role, edges)
        substitute_role_pools = dict(role_pools)
        pool_key = (r.role, bucket_idx)
        if bucket_idx is not None and fvm_pools.get(pool_key):
            substitute_role_pools[r.role] = fvm_pools[pool_key]
            fvm_result = simulate_fantavoto(r.player_code, r.role, player_pools, substitute_role_pools, n_sims=N_SIMS, rng=rng_fvm)
        else:
            fvm_result = baseline  # no FVM-bucket data available, falls back to same baseline
        rows.append({"player_code": r.player_code, "baseline_mean": baseline.mean, "fvm_mean": fvm_result.mean})

    sim_df = pd.DataFrame(rows).astype({"player_code": "int64"})
    merged = sim_df.merge(statistiche[["player_code", "fantamedia"]], on="player_code", how="inner").dropna(subset=["fantamedia"])

    baseline_corr = merged["baseline_mean"].corr(merged["fantamedia"])
    fvm_corr = merged["fvm_mean"].corr(merged["fantamedia"])
    baseline_gap = (merged["fantamedia"] - merged["baseline_mean"]).abs().mean()
    fvm_gap = (merged["fantamedia"] - merged["fvm_mean"]).abs().mean()

    print(f"\nMatched {len(merged)} low/no-history players against real Fm.")
    print(f"Baseline (flat role pool): correlation={baseline_corr:.4f}, mean abs gap={baseline_gap:.4f}")
    print(f"FVM-bucketed pool:         correlation={fvm_corr:.4f}, mean abs gap={fvm_gap:.4f}")

    verdict = "ADOPT" if fvm_corr > baseline_corr + 0.01 else "DO NOT ADOPT (no meaningful improvement)"
    print(f"\nVerdict: {verdict}")

    lines = [
        "# FVM-bucketed role pool validation (walk-forward, low/no-history subset, honest)",
        "",
        f"Trained on {TRAIN_SEASONS}, predicted 2025/26, restricted to players with "
        f"< {LOW_HISTORY_GAMES} pre-2025/26 games ({len(merged)} matched against real Fm).",
        "",
        "| Method | Correlation with real Fm | Mean abs gap |",
        "|---|---:|---:|",
        f"| Baseline (flat role pool) | {baseline_corr:.4f} | {baseline_gap:.4f} |",
        f"| FVM-bucketed pool | {fvm_corr:.4f} | {fvm_gap:.4f} |",
        "",
        f"**Verdict: {verdict}**",
    ]
    from pathlib import Path
    Path("data/staged/fantacalcio_voti_manual/_fvm_prior_validation.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
