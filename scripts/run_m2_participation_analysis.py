#!/usr/bin/env python3
"""M2: season-level participation rate analysis, real data.

Computes participation rate (matchdays rated / 38) per player per season from the
voti panel (5 seasons), checks whether last season's rate predicts next season's
(season-to-season persistence), and cross-validates against the independently
sourced `statistiche` export's own participation field (Pv) for 2025/26.

Report stays local under data/staged/ (gitignored) — derived from personal-use-
licensed data, same policy as the other voti-derived reports.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.modeling.participation import (
    compute_season_participation,
    cross_check_against_statistiche,
    season_to_season_persistence,
)
from fantacalcio.modeling.player_voto import load_player_matchday_panel

REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_m2_participation_report.md")
STATISTICHE_PATH = Path("data/staged/fantacalcio_statistiche_manual/latest.csv")


def main() -> None:
    print("Loading voti panel...")
    voti = load_player_matchday_panel()
    participation = compute_season_participation(voti)
    print(f"Computed participation for {len(participation.frame)} player-season rows.")

    persistence = season_to_season_persistence(participation)
    print(f"Persistence: n={persistence.n_pairs}, corr={persistence.correlation:.3f}, "
          f"MAE carry-forward={persistence.mae_vs_carry_forward:.4f}, "
          f"MAE global-mean baseline={persistence.mae_vs_global_mean_baseline:.4f}")

    lines = [
        "# M2 participation rate — season-to-season persistence and cross-check",
        "",
        f"{len(participation.frame)} player-season rows across "
        f"{participation.frame['season_label'].nunique()} seasons.",
        "",
        "## Season-to-season persistence",
        "",
        f"- Player-seasons compared (consecutive-season pairs only): {persistence.n_pairs}",
        f"- Correlation (last season's rate vs. this season's rate): {persistence.correlation:.4f}",
        f"- MAE, naive carry-forward (predict this season's rate = last season's rate): {persistence.mae_vs_carry_forward:.4f}",
        f"- MAE, global-mean baseline (predict this season's rate = overall average): {persistence.mae_vs_global_mean_baseline:.4f}",
        f"- Carry-forward beats global-mean baseline: {persistence.mae_vs_carry_forward < persistence.mae_vs_global_mean_baseline}",
        "",
    ]

    if STATISTICHE_PATH.is_file():
        statistiche = pd.read_csv(STATISTICHE_PATH)
        check = cross_check_against_statistiche(participation, statistiche, season_label="2025_26")
        print(f"Cross-check vs statistiche Pv: n={check.n_matched}, corr={check.correlation:.3f}, MAE={check.mae:.3f}")
        lines += [
            "## Cross-check against independently sourced `Pv` (statistiche export)",
            "",
            f"- Matched players: {check.n_matched}",
            f"- Correlation (our voti-derived matchdays-rated vs. their Pv): {check.correlation:.4f}",
            f"- MAE: {check.mae:.4f} matchdays",
            "",
            "A high correlation and low MAE here means our two independently ingested "
            "sources (voti export, statistiche export) agree on how often each player "
            "played — a real cross-source consistency check, not just an internal one.",
        ]
    else:
        lines.append("statistiche file not found — cross-check skipped.")
        print("statistiche file not found, skipping cross-check.")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
