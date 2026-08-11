#!/usr/bin/env python3
"""Validates a recency-weighted multi-season participation estimate against the
existing single-most-recent-season baseline (`latest_known_participation`),
honestly (docs/CURRENT_TASK.md block 4).

Walk-forward at the season level: for each season transition (predict season N
from seasons < N), compare (a) baseline: last known season's participation rate,
(b) decayed multi-season weighted average, at several half-life values. If decay
doesn't beat the baseline, it is NOT adopted, same standard as ADR-2026-017.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.modeling.participation import (
    compute_season_participation,
    decayed_participation_estimate,
    latest_known_participation,
)
from fantacalcio.modeling.player_voto import SEASON_ORDER, load_player_matchday_panel

HALF_LIFE_VALUES = [0.5, 1.0, 2.0, None]


def main() -> None:
    print("Loading voti panel and computing season participation...")
    voti = load_player_matchday_panel()
    participation = compute_season_participation(voti)
    frame = participation.frame

    lines = [
        "# Participation decay validation (walk-forward, season-level, honest)",
        "",
        "| Method | Correlation with actual next-season rate | Mean abs error |",
        "|---|---:|---:|",
    ]
    results = {}

    for target_rank in range(1, len(SEASON_ORDER)):
        actual = frame[frame["season_rank"] == target_rank][["player_code", "participation_rate"]].rename(
            columns={"participation_rate": "actual_rate"}
        )

        # Baseline: latest known season strictly before target_rank.
        prior = participation.frame[frame["season_rank"] < target_rank]
        from fantacalcio.modeling.participation import SeasonParticipation

        baseline_pred = latest_known_participation(SeasonParticipation(frame=prior))[["player_code", "participation_rate"]].rename(
            columns={"participation_rate": "baseline_pred"}
        )
        merged = actual.merge(baseline_pred, on="player_code", how="inner")
        results.setdefault("baseline_latest_season", []).append(merged)

        for half_life in HALF_LIFE_VALUES:
            decayed = decayed_participation_estimate(participation, half_life, as_of_season_rank=target_rank)
            decayed = decayed.rename(columns={"decayed_participation_rate": "decayed_pred"})
            m = actual.merge(decayed[["player_code", "decayed_pred"]], on="player_code", how="inner")
            label = f"decay_half_life_{half_life}" if half_life is not None else "plain_multi_season_average"
            results.setdefault(label, []).append(m)

    print("\n=== Results (aggregated across all season transitions) ===")
    baseline_corr = None
    for label, frames in results.items():
        all_rows = pd.concat(frames, ignore_index=True)
        pred_col = "baseline_pred" if label == "baseline_latest_season" else "decayed_pred"
        corr = all_rows[pred_col].corr(all_rows["actual_rate"])
        mae = (all_rows[pred_col] - all_rows["actual_rate"]).abs().mean()
        print(f"{label}: correlation={corr:.4f}, MAE={mae:.4f} ({len(all_rows)} player-transitions)")
        lines.append(f"| {label} | {corr:.4f} | {mae:.4f} |")
        if label == "baseline_latest_season":
            baseline_corr = corr

    best_label = max(
        (label for label in results if label != "baseline_latest_season"),
        key=lambda label: pd.concat(results[label], ignore_index=True)["decayed_pred"].corr(
            pd.concat(results[label], ignore_index=True)["actual_rate"]
        ),
    )
    best_frames = pd.concat(results[best_label], ignore_index=True)
    best_corr = best_frames["decayed_pred"].corr(best_frames["actual_rate"])
    verdict = "ADOPT" if best_corr > baseline_corr + 0.005 else "DO NOT ADOPT (no meaningful improvement)"
    print(f"\nBaseline (latest known season): {baseline_corr:.4f}. Best: {best_label} = {best_corr:.4f}. Verdict: {verdict}")
    lines += ["", f"**Verdict: {verdict}** (baseline={baseline_corr:.4f}, best={best_label}={best_corr:.4f})"]

    Path("data/staged/fantacalcio_voti_manual/_participation_decay_validation.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
