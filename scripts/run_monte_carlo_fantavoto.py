#!/usr/bin/env python3
"""Monte Carlo fantavoto distributions: validate against real Fm, then apply to the
real 2026/27 auction roster.

Part A: for every player rated in the 2025/26 season, simulate their fantavoto
distribution using only history from *before* that season (2021/22-2024/25) --
walk-forward at the season level, no leakage -- and compare the simulated mean to
their real 2025/26 Fm. This is the same honesty check used throughout M2: report
the gap, don't chase it to zero artificially.

Part B: apply the same simulation, fitted on all 5 seasons, to the real 2026/27
quotazioni roster (498 players) to produce a distribution (not a point estimate)
per player -- mean, median, P10-P90.

Report stays local under data/staged/ (gitignored, personal-use-licensed sources).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from fantacalcio.modeling.dixon_coles import fit_dixon_coles
from fantacalcio.modeling.player_voto import load_player_matchday_panel
from fantacalcio.modeling.team_matchday import build_all_seasons
from fantacalcio.scoring.monte_carlo import DEFAULT_PRIOR_GAMES, build_event_pools, simulate_fantavoto
from fantacalcio.scoring.team_strength_adjustment import (
    apply_adjustment,
    compute_adjustments,
    historical_avg_team_rating,
    team_ratings_from_model,
)

VALIDATION_REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_validation.md")
APPLICATION_CSV_PATH = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_2026_27.csv")
APPLICATION_REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_2026_27.md")
QUOTAZIONI_DIR = Path("data/staged/fantacalcio_quotazioni_manual")
STATISTICHE_DIR = Path("data/staged/fantacalcio_statistiche_manual")
FOOTBALL_DATA_DIR = Path("data/staged/football_data_co_uk")
FD_SEASON_CODES = {"2021_22": "2122", "2022_23": "2223", "2023_24": "2324", "2024_25": "2425", "2025_26": "2526"}
SEASONS = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]
N_SIMS = 1000
SEED = 42
# Validated via scripts/run_team_strength_adjustment_validation.py walk-forward sweep
# (2026-08-11): k=0.5 improved correlation with real Fm from 0.3472 to 0.3522 vs. k=0
# baseline, with a monotonic 0->0.25->0.5 rise then a fall at k=1.0 -- a real, if
# modest, signal rather than noise. See ADR-2026-023.
TEAM_STRENGTH_K = 0.5


def _join_team_data(voti: pd.DataFrame) -> pd.DataFrame:
    rated = voti[~voti["voto_no_vote"]].copy()
    frames = []
    for season in SEASONS:
        path = QUOTAZIONI_DIR / f"{season}.csv"
        if path.is_file():
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
    return rated


def part_a_validation(rated: pd.DataFrame) -> None:
    print("=== Part A: validation (train on pre-2025/26, predict 2025/26) ===")
    train = rated[rated["season_label"] != "2025_26"]
    player_pools, role_pools = build_event_pools(train)

    statistiche = pd.read_csv(STATISTICHE_DIR / "2025_26.csv")
    target_players = rated[rated["season_label"] == "2025_26"][["player_code", "role"]].drop_duplicates()

    rng = np.random.default_rng(SEED)
    rows = []
    for r in target_players.itertuples(index=False):
        result = simulate_fantavoto(r.player_code, r.role, player_pools, role_pools, n_sims=N_SIMS, rng=rng)
        rows.append({"player_code": r.player_code, "role": r.role, "sim_mean": result.mean, "used_role_pool_only": result.used_role_pool_only})

    sim_df = pd.DataFrame(rows).astype({"player_code": "int64"})
    statistiche = statistiche.astype({"player_code": "int64"})
    merged = sim_df.merge(statistiche[["player_code", "fantamedia"]], on="player_code", how="inner").dropna(subset=["fantamedia"])

    corr = merged["sim_mean"].corr(merged["fantamedia"])
    gap = (merged["fantamedia"] - merged["sim_mean"]).mean()
    print(f"Matched {len(merged)} players. Correlation={corr:.4f}, mean gap (theirs-ours)={gap:.4f}")

    lines = [
        "# Monte Carlo fantavoto — validation (walk-forward, season-level)",
        "",
        f"Trained on 2021/22-2024/25, predicted 2025/26. {len(merged)} players matched "
        f"against real Fm.",
        "",
        f"- Correlation (simulated mean vs. real Fm): {corr:.4f}",
        f"- Mean gap (real Fm - simulated mean): {gap:.4f}",
        f"- Players with no pre-2025/26 history (role-pool-only fallback): "
        f"{sim_df['used_role_pool_only'].sum()} ({sim_df['used_role_pool_only'].mean():.1%})",
        "",
        "This is typically meaningfully lower than the same-season engine validation "
        "(ADR-2026-017: 0.51-0.60 correlation), not just slightly -- report the actual "
        "gap honestly, don't round it toward the in-sample figure. Two plausible, non-"
        "exclusive drivers: (1) predicting an unseen future season is strictly harder "
        "than explaining a season with its own data, and (2) a meaningful fraction of "
        "target players may have zero prior history (transfers/promotions), scored "
        "purely from the role-average pool, which drags correlation down by "
        "construction for that subset. This report doesn't have enough evidence to "
        "say which dominates.",
    ]
    VALIDATION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {VALIDATION_REPORT_PATH}")


def part_b_application(rated: pd.DataFrame) -> None:
    print("\n=== Part B: apply to real 2026/27 roster ===")
    player_pools, role_pools = build_event_pools(rated)  # all 5 seasons

    listone = pd.read_csv(QUOTAZIONI_DIR / "2026_27.csv")
    rng = np.random.default_rng(SEED)

    print("Fitting Dixon-Coles on all seasons for team-strength adjustment (ADR-2026-023)...")
    fd_all = pd.concat(
        [pd.read_csv(FOOTBALL_DATA_DIR / f"serie_a_{FD_SEASON_CODES[s]}.csv", parse_dates=["Date"]) for s in SEASONS],
        ignore_index=True,
    )
    dc_model = fit_dixon_coles(fd_all)
    ratings = team_ratings_from_model(dc_model)
    hist_attack = historical_avg_team_rating(rated, ratings, "attack")
    hist_defense = historical_avg_team_rating(rated, ratings, "defense")

    current_team = listone.set_index("player_code")["team_name"]
    current_role = listone.set_index("player_code")["role"]
    adjustments = compute_adjustments(current_team, current_role, hist_attack, hist_defense, ratings, TEAM_STRENGTH_K)

    rows = []
    for r in listone.itertuples(index=False):
        result = simulate_fantavoto(int(r.player_code), r.role, player_pools, role_pools, n_sims=N_SIMS, rng=rng)
        adj = adjustments.get(r.player_code, 0.0)
        if adj != 0.0:
            result = apply_adjustment(result, adj)
        rows.append(
            {
                "player_code": r.player_code,
                "display_name": r.display_name,
                "role": r.role,
                "team_name": r.team_name,
                "quotazione_asta": r.quotazione_asta_classic,
                "sim_mean": round(result.mean, 3),
                "sim_median": round(result.median, 3),
                "sim_p10": round(result.p10, 3),
                "sim_p90": round(result.p90, 3),
                "team_strength_adjustment": round(adj, 3),
                "player_games_in_pool": result.player_games_in_pool,
                "used_role_pool_only": result.used_role_pool_only,
            }
        )

    out = pd.DataFrame(rows).sort_values("sim_mean", ascending=False)
    out.to_csv(APPLICATION_CSV_PATH, index=False)

    lines = [
        "# Monte Carlo fantavoto — 2026/27 roster (first distributional pass)",
        "",
        f"{len(out)} players, {N_SIMS} simulations each, seed={SEED}. Mixture bootstrap "
        f"(own history vs. role pool, weight n/(n+{DEFAULT_PRIOR_GAMES:.0f})) over real "
        "historical (voto, events) rows -- no assumed distribution shape. Includes a "
        f"Dixon-Coles team-strength adjustment (k={TEAM_STRENGTH_K}, validated via "
        "walk-forward, ADR-2026-023) for A/C/D roles whose 2026/27 team differs in "
        "strength from their historical average team context.",
        "",
        "## Top 15 by simulated mean, with uncertainty range",
        "",
        "| Player | Role | Team | Mean | Median | P10 | P90 | Games in pool |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in out.head(15).itertuples(index=False):
        lines.append(
            f"| {row.display_name} | {row.role} | {row.team_name} | {row.sim_mean} | "
            f"{row.sim_median} | {row.sim_p10} | {row.sim_p90} | {row.player_games_in_pool} |"
        )

    lines += ["", "## By role: average P10-P90 spread (uncertainty width)", "", "| Role | Avg mean | Avg P90-P10 spread |", "|---|---:|---:|"]
    out["spread"] = out["sim_p90"] - out["sim_p10"]
    for role, g in out.groupby("role"):
        lines.append(f"| {role} | {g['sim_mean'].mean():.3f} | {g['spread'].mean():.3f} |")

    APPLICATION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nCSV: {APPLICATION_CSV_PATH}")
    print(f"Report: {APPLICATION_REPORT_PATH}")


def main() -> None:
    print("Loading voti panel and joining team data...")
    voti = load_player_matchday_panel()
    rated = _join_team_data(voti)

    part_a_validation(rated)
    part_b_application(rated)


if __name__ == "__main__":
    main()
