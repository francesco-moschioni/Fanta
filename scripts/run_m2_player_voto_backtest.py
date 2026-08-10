#!/usr/bin/env python3
"""M2 backtest: shrinkage player-voto estimator vs naive baselines, walk-forward.

Loads the real 5-season voti panel (primary "Fantacalcio" rating panel), scores
every rated matchday with the shrinkage estimator and three baselines using only
strictly-earlier matchdays, and reports MAE overall and by role.

Note: this is derived from data whose own licence restricts it to personal use
(see docs/SOURCE_REGISTER.md), so the report is written under data/staged/
(gitignored), not data/outputs/ — consistent with the M1 voti quality-audit report.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from fantacalcio.modeling.player_voto import load_player_matchday_panel, walk_forward

REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_m2_player_voto_backtest.md")


def mae(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = ~np.isnan(pred)
    return float(np.mean(np.abs(actual[mask] - pred[mask])))


def coverage(actual: np.ndarray, pred: np.ndarray) -> float:
    """Fraction of rows where a baseline could even be computed (had history)."""
    return float(np.mean(~np.isnan(pred)))


def main() -> None:
    print("Loading player-matchday panel...")
    df = load_player_matchday_panel()
    print(f"Loaded {len(df)} rated rows.")

    print("Running walk-forward scoring...")
    scored = walk_forward(df)
    print(f"Scored {len(scored)} rows.")

    lines = [
        "# M2 player-voto backtest — shrinkage estimator vs naive baselines",
        "",
        f"Walk-forward over {scored['season_label'].nunique()} seasons, "
        f"{scored['player_code'].nunique()} distinct players, {len(scored)} rated rows. "
        "Primary panel only (\"Fantacalcio\"); coach rows excluded.",
        "",
        "## Overall",
        "",
        "| Model | MAE | Coverage (had history) |",
        "|---|---:|---:|",
    ]

    actual = scored["actual_voto"].to_numpy()
    models = {
        "Shrinkage (Empirical Bayes)": scored["shrinkage_pred"].to_numpy(),
        "Baseline: last known voto": scored["baseline_last_value"].to_numpy(),
        "Baseline: role mean-to-date": scored["baseline_role_mean"].to_numpy(),
        "Baseline: season mean-to-date": scored["baseline_season_mean"].to_numpy(),
    }
    for name, pred in models.items():
        lines.append(f"| {name} | {mae(actual, pred):.4f} | {coverage(actual, pred):.2%} |")

    lines += ["", "## By role", "", "| Role | Model | MAE |", "|---|---|---:|"]
    for role, group in scored.groupby("role"):
        role_actual = group["actual_voto"].to_numpy()
        for name, col in [
            ("Shrinkage", "shrinkage_pred"),
            ("Last known voto", "baseline_last_value"),
            ("Role mean-to-date", "baseline_role_mean"),
            ("Season mean-to-date", "baseline_season_mean"),
        ]:
            lines.append(f"| {role} | {name} | {mae(role_actual, group[col].to_numpy()):.4f} |")

    fallback_rate = scored["used_role_fallback"].mean()
    lines += [
        "",
        f"Shrinkage estimator used the role/global-mean fallback (no player history yet) "
        f"for {fallback_rate:.2%} of predictions — expected to be highest early in each "
        f"player's career/dataset presence, not a defect.",
        "",
        "## Participation model: explicitly out of scope",
        "",
        "This backtest scores only rows the source already rated. It says nothing about "
        "whether a player will be fielded at all next matchday — that requires a full-roster "
        "reference this project does not yet have (see docs/CURRENT_TASK.md).",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
