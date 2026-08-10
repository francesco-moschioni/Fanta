#!/usr/bin/env python3
"""M2 backtest: Elo and Dixon-Coles vs naive baselines, rolling-origin, 5 seasons.

Loads all available football-data.co.uk seasons (2021/22-2025/26), builds
leave-one-season-out expanding-window folds, fits each model on the training folds
only, and scores outcome log loss + goals MAE on the held-out season. Verifies the
no-leakage invariant per fold before scoring. Writes a report to
data/outputs/m2_team_strength_backtest.md.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from fantacalcio.modeling.baselines import (
    fit_constant_outcome_baseline,
    fit_previous_season_average_goals,
)
from fantacalcio.modeling.dixon_coles import fit_dixon_coles
from fantacalcio.modeling.elo import fit_elo_sequential, fit_outcome_probability_model
from fantacalcio.modeling.validation import (
    SEASON_ORDER,
    assert_no_leakage,
    load_seasons,
    log_loss,
    outcome_index,
    rolling_origin_splits,
)

SEED = 42


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def main() -> None:
    np.random.seed(SEED)
    df = load_seasons(SEASON_ORDER)
    folds = rolling_origin_splits(df, SEASON_ORDER)

    rows = []
    for fold in folds:
        assert_no_leakage(fold.train, fold.test)

        # --- Baselines ---
        outcome_baseline = fit_constant_outcome_baseline(fold.train)
        goals_baseline = fit_previous_season_average_goals(fold.train)
        baseline_probs = outcome_baseline.predict(len(fold.test))
        baseline_home_pred = np.full(len(fold.test), goals_baseline.avg_home_goals)
        baseline_away_pred = np.full(len(fold.test), goals_baseline.avg_away_goals)

        # --- Elo ---
        # `train_diffs` is the rating_diff computed *before* each training match, as
        # returned by the sequential fit — using the final post-training ratings
        # here instead would leak the training season's own outcomes into the
        # probability-model fit.
        elo, train_diffs = fit_elo_sequential(fold.train)
        outcome_model = fit_outcome_probability_model(train_diffs, list(fold.train.sort_values("Date")["FTR"]))
        elo_probs = [
            outcome_model.predict(elo.rating_diff(r["HomeTeam"], r["AwayTeam"]))
            for _, r in fold.test.iterrows()
        ]

        # --- Dixon-Coles ---
        dc = fit_dixon_coles(fold.train)
        dc_probs = []
        dc_home_pred, dc_away_pred = [], []
        unknown_team_matches = 0
        for _, r in fold.test.iterrows():
            if not (dc.is_known_team(r["HomeTeam"]) and dc.is_known_team(r["AwayTeam"])):
                unknown_team_matches += 1
            dc_probs.append(dc.outcome_probabilities(r["HomeTeam"], r["AwayTeam"]))
            lh, la = dc.expected_goals(r["HomeTeam"], r["AwayTeam"])
            dc_home_pred.append(lh)
            dc_away_pred.append(la)

        y_true_idx = [outcome_index(r) for _, r in fold.test.iterrows()]
        y_home = fold.test["FTHG"].to_numpy()
        y_away = fold.test["FTAG"].to_numpy()

        rows.append(
            {
                "season": fold.season_code,
                "n_test": len(fold.test),
                "unknown_team_matches": unknown_team_matches,
                "baseline_logloss": log_loss(y_true_idx, baseline_probs),
                "elo_logloss": log_loss(y_true_idx, elo_probs),
                "dc_logloss": log_loss(y_true_idx, dc_probs),
                "baseline_goals_mae": (mae(y_home, baseline_home_pred) + mae(y_away, baseline_away_pred)) / 2,
                "dc_goals_mae": (mae(y_home, np.array(dc_home_pred)) + mae(y_away, np.array(dc_away_pred))) / 2,
            }
        )

    report_lines = [
        "# M2 team-strength backtest — Elo and Dixon-Coles vs naive baselines",
        "",
        f"Seed: {SEED}. Rolling-origin, expanding window, leave-one-season-out. "
        f"No-leakage check passed for every fold (train strictly before test).",
        "",
        "| Season | Matches | Unknown-team matches | Baseline log loss | Elo log loss | "
        "Dixon-Coles log loss | Baseline goals MAE | Dixon-Coles goals MAE |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        report_lines.append(
            f"| {r['season']} | {r['n_test']} | {r['unknown_team_matches']} | "
            f"{r['baseline_logloss']:.4f} | {r['elo_logloss']:.4f} | {r['dc_logloss']:.4f} | "
            f"{r['baseline_goals_mae']:.4f} | {r['dc_goals_mae']:.4f} |"
        )

    avg_baseline_ll = np.mean([r["baseline_logloss"] for r in rows])
    avg_elo_ll = np.mean([r["elo_logloss"] for r in rows])
    avg_dc_ll = np.mean([r["dc_logloss"] for r in rows])
    avg_baseline_mae = np.mean([r["baseline_goals_mae"] for r in rows])
    avg_dc_mae = np.mean([r["dc_goals_mae"] for r in rows])

    report_lines += [
        "",
        "## Summary (mean across folds)",
        "",
        f"- Outcome log loss: baseline={avg_baseline_ll:.4f}, Elo={avg_elo_ll:.4f}, "
        f"Dixon-Coles={avg_dc_ll:.4f} (lower is better)",
        f"- Goals MAE: baseline={avg_baseline_mae:.4f}, Dixon-Coles={avg_dc_mae:.4f} (lower is better)",
        "",
        f"Elo beats the constant-outcome baseline on log loss: {avg_elo_ll < avg_baseline_ll}. "
        f"Dixon-Coles beats it too: {avg_dc_ll < avg_baseline_ll}. "
        f"Dixon-Coles beats the average-goals baseline on MAE: {avg_dc_mae < avg_baseline_mae}.",
        "",
        "Unknown-team matches (promoted teams with no training history) fall back to "
        "average strength per `docs/CURRENT_TASK.md` scope note — a real, expected "
        "source of extra error, not a bug; see the per-fold column above for how many "
        "matches this affected.",
    ]

    out_path = Path("data/outputs/m2_team_strength_backtest.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    print("\n".join(report_lines))
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    main()
