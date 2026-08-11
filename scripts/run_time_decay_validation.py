#!/usr/bin/env python3
"""Validate recency-weighted bootstrap sampling (docs/CURRENT_TASK.md block 4),
honestly.

Walk-forward: fit on 2021/22-2024/25, predict 2025/26 (never seen). Sweeps
half_life_matchdays in {None (baseline, uniform sampling), 19 (~half season), 38
(~1 season), 76 (~2 seasons)} and compares correlation with real Fm. If no decay
setting beats the no-decay baseline, that's reported and the change is NOT
adopted, same standard as ADR-2026-017.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fantacalcio.modeling.player_voto import load_player_matchday_panel
from fantacalcio.modeling.team_matchday import build_all_seasons
from fantacalcio.modeling.time_decay import add_global_matchday_index, add_recency_weight
from fantacalcio.scoring.monte_carlo import build_event_pools, simulate_fantavoto

SEASONS = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]
N_SIMS = 500
SEED = 42
HALF_LIFE_VALUES = [None, 19.0, 38.0, 76.0, 150.0, 300.0, 1000.0]


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

    train = rated[rated["season_label"] != "2025_26"].copy()
    train = add_global_matchday_index(train)
    target_players = rated[rated["season_label"] == "2025_26"][["player_code", "role"]].drop_duplicates()

    statistiche = pd.read_csv("data/staged/fantacalcio_statistiche_manual/2025_26.csv").astype({"player_code": "int64"})

    # Includes a same-code-path control: uniform weights (no real decay) run
    # through the *weighted* sampler (rng.choice(p=...)), not the default
    # rng.integers() path. rng.choice and rng.integers consume the RNG stream
    # differently even when the underlying distribution is identical, so
    # comparing decayed runs only against the rng.integers baseline would
    # conflate "decay helped" with "switching sampler implementation happened
    # to draw a luckier sequence". This isolates the two.
    print(f"Simulating {len(target_players)} players x {len(HALF_LIFE_VALUES) + 1} settings x {N_SIMS} sims...")
    rows = []
    settings = [("baseline_no_decay", None, False)] + [
        (str(h), h, True) for h in HALF_LIFE_VALUES if h is not None
    ] + [("uniform_weighted_control", None, True)]
    for label, half_life, use_weights in settings:
        weighted_train = add_recency_weight(train, half_life)
        player_pools, role_pools = build_event_pools(weighted_train)
        rng = np.random.default_rng(SEED)
        for r in target_players.itertuples(index=False):
            result = simulate_fantavoto(
                r.player_code, r.role, player_pools, role_pools, n_sims=N_SIMS, rng=rng, use_recency_weights=use_weights
            )
            rows.append({"player_code": r.player_code, "half_life_label": label, "sim_mean": result.mean})

    sim_df = pd.DataFrame(rows).astype({"player_code": "int64"})
    merged = sim_df.merge(statistiche[["player_code", "fantamedia"]], on="player_code", how="inner").dropna(subset=["fantamedia"])

    print("\n=== Results ===")
    lines = ["# Time-decay bootstrap validation (walk-forward, honest)", "", "| Setting | Correlation with real Fm |", "|---|---:|"]
    corr_by_label = {}
    for label, _, _ in settings:
        subset = merged[merged["half_life_label"] == label]
        corr = subset["sim_mean"].corr(subset["fantamedia"])
        corr_by_label[label] = corr
        print(f"{label}: correlation={corr:.4f}")
        lines.append(f"| {label} | {corr:.4f} |")

    baseline_corr = corr_by_label["baseline_no_decay"]
    control_corr = corr_by_label["uniform_weighted_control"]
    decay_labels = [str(h) for h in HALF_LIFE_VALUES if h is not None]
    best_label = max(decay_labels, key=lambda label: corr_by_label[label])
    best_corr = corr_by_label[best_label]

    print(f"\nRaw baseline (rng.integers, no decay): {baseline_corr:.4f}")
    print(f"Same-sampler control (rng.choice, uniform weights): {control_corr:.4f}")
    print(f"Best decay setting: half_life={best_label}, correlation={best_corr:.4f}")

    sampler_switch_effect = control_corr - baseline_corr
    decay_effect = best_corr - control_corr
    print(f"Sampler-switch effect alone (control - baseline): {sampler_switch_effect:+.4f}")
    print(f"Decay effect on top of that (best decay - control): {decay_effect:+.4f}")

    verdict = "ADOPT" if decay_effect > 0.005 else "DO NOT ADOPT (improvement is a sampler-switch artifact, not real decay signal)"
    print(f"\nVerdict: {verdict}")
    lines += [
        "",
        f"Raw baseline (rng.integers): {baseline_corr:.4f}. Same-sampler uniform-weight "
        f"control (rng.choice, no real decay): {control_corr:.4f}. Best decay setting "
        f"(half_life={best_label}): {best_corr:.4f}.",
        f"Sampler-switch effect alone: {sampler_switch_effect:+.4f}. Decay effect on top "
        f"of the same sampler: {decay_effect:+.4f}.",
        "",
        f"**Verdict: {verdict}**",
    ]

    from pathlib import Path
    Path("data/staged/fantacalcio_voti_manual/_time_decay_validation.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
