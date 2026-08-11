#!/usr/bin/env python3
"""Cross-checks Dixon-Coles team-strength ratings (fit from goals alone,
ADR-2026-011) against the market-implied team rating (from betting odds
recovered in docs/CURRENT_TASK.md block 3), honestly.

This is a same-season, in-sample sanity check, not a walk-forward forecast
validation: both are fit on the same season's matches. The question isn't
"does this improve forecasts" (odds for next season don't exist yet, so there's
nothing to feed into the 2026/27 pipeline) -- it's "does our goals-only model
broadly agree with a market that sees far more information than goals alone".
Strong agreement is reassuring; a big gap would flag something wrong with
Dixon-Coles that goals alone didn't surface.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.modeling.dixon_coles import fit_dixon_coles
from fantacalcio.modeling.market_odds import team_market_rating

FOOTBALL_DATA_DIR = Path("data/staged/football_data_co_uk")
SEASON_CODES = ["2122", "2223", "2324", "2425", "2526"]


def main() -> None:
    lines = [
        "# Market-odds cross-check of Dixon-Coles team strength (same-season, honest)",
        "",
        "| Season | Correlation (DC combined strength vs. market expected points) |",
        "|---|---:|",
    ]
    all_corrs = []
    for season_code in SEASON_CODES:
        df = pd.read_csv(FOOTBALL_DATA_DIR / f"serie_a_{season_code}.csv", parse_dates=["Date"])
        dc_model = fit_dixon_coles(df)
        dc_combined = pd.Series({team: dc_model.attack[team] - dc_model.defense[team] for team in dc_model.teams})

        odds_df = df.dropna(subset=["AvgH", "AvgD", "AvgA"])
        market = team_market_rating(odds_df)

        merged = pd.DataFrame({"dc": dc_combined, "market": market}).dropna()
        corr = merged["dc"].corr(merged["market"])
        all_corrs.append(corr)
        print(f"{season_code}: correlation={corr:.4f} ({len(merged)} teams)")
        lines.append(f"| {season_code} | {corr:.4f} |")

    avg_corr = sum(all_corrs) / len(all_corrs)
    print(f"\nAverage correlation across seasons: {avg_corr:.4f}")
    lines += [
        "",
        f"**Average correlation across {len(SEASON_CODES)} seasons: {avg_corr:.4f}**",
        "",
        "Same-season fit for both (not a forecast validation -- see module docstring). "
        "Used as a sanity check on Dixon-Coles, not wired into the 2026/27 forecast "
        "pipeline: odds for a season that hasn't started don't exist yet.",
    ]
    Path("data/staged/fantacalcio_voti_manual/_market_odds_crosscheck.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
