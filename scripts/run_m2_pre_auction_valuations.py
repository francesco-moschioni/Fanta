#!/usr/bin/env python3
"""M2: first pre-auction player valuations for the 2026/27 roster.

Combines the two validated M2 models against the real 2026/27 quotazioni listone
(498 players, the actual pool for the upcoming auction):

- expected base voto: shrinkage estimator (ADR-2026-012), fitted on ALL available
  history (2021/22-2025/26) since 2026/27 hasn't been played yet — not a backtest,
  a genuine forecast;
- participation prior: last known season's participation rate (ADR-2026-014).

This is explicitly a first pass, not a finished auction-value model: it has no
replacement-level, scarcity, budget, or opponent-demand logic yet (those are
M3/auction-engine concerns per docs/DATA_AND_MODELING.md's forecast-to-bid layer).
It answers "what should I roughly expect from this player", not "what should I bid".

Report stays local under data/staged/ (gitignored, personal-use-licensed sources).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.ingest.fantacalcio_listone import parse_quotazioni_file
from fantacalcio.modeling.participation import (
    compute_season_participation,
    latest_known_participation,
)
from fantacalcio.modeling.player_voto import (
    fit_final_stats,
    load_player_matchday_panel,
    shrunk_estimate,
)

REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_m2_pre_auction_valuations.md")
CSV_PATH = Path("data/staged/fantacalcio_voti_manual/_m2_pre_auction_valuations.csv")
QUOTAZIONI_2026_27 = Path("data/staged/fantacalcio_quotazioni_manual/2026_27.csv")


def main() -> None:
    print("Loading 2026/27 quotazioni (the actual auction pool)...")
    listone = pd.read_csv(QUOTAZIONI_2026_27)
    print(f"{len(listone)} players in the 2026/27 pool.")

    print("Fitting voto model on all historical seasons (2021/22-2025/26)...")
    voti = load_player_matchday_panel()
    fitted = fit_final_stats(voti)
    print(f"Fitted on seasons: {fitted.seasons_used}")

    print("Computing participation history...")
    participation = compute_season_participation(voti)
    latest_participation = latest_known_participation(participation).set_index("player_code")

    rows = []
    for r in listone.itertuples(index=False):
        code = int(r.player_code)
        pred_voto, used_role_fallback, used_global_fallback = shrunk_estimate(
            fitted.player_stats, fitted.role_stats, fitted.global_stats, code, r.role
        )
        player_games = fitted.player_stats.counts.get(code, 0)

        if code in latest_participation.index:
            p = latest_participation.loc[code]
            participation_rate = float(p["participation_rate"])
            participation_season = p["season_label"]
            seasons_of_history = int(p["seasons_of_history"])
        else:
            role_rows = participation.frame[participation.frame["role"] == r.role]
            participation_rate = float(role_rows["participation_rate"].mean()) if len(role_rows) else float("nan")
            participation_season = "role_average_fallback"
            seasons_of_history = 0

        rows.append(
            {
                "player_code": code,
                "display_name": r.display_name,
                "role": r.role,
                "team_name": r.team_name,
                "quotazione_asta": r.quotazione_asta_classic,
                "fvm": r.fvm_classic,
                "expected_voto": round(pred_voto, 3),
                "player_matchdays_in_history": player_games,
                "used_role_fallback_for_voto": used_role_fallback,
                "participation_rate": round(participation_rate, 3) if participation_rate == participation_rate else None,
                "participation_source": participation_season,
                "seasons_of_history": seasons_of_history,
            }
        )

    result = pd.DataFrame(rows).sort_values(["expected_voto"], ascending=False)
    result.to_csv(CSV_PATH, index=False)

    n_new_to_dataset = (result["player_matchdays_in_history"] == 0).sum()
    n_no_participation_history = (result["participation_source"] == "role_average_fallback").sum()

    lines = [
        "# M2 pre-auction valuations — 2026/27 roster (first pass)",
        "",
        f"{len(result)} players in the 2026/27 quotazioni pool. Voto model fitted on "
        f"{fitted.seasons_used}. **Not an auction-value model yet** — no replacement "
        "level, scarcity, budget, or opponent-demand logic; that's M3 scope.",
        "",
        f"- Players with zero historical voto (new to our 5-season dataset — promoted/new signings/etc.): "
        f"{n_new_to_dataset} ({n_new_to_dataset / len(result):.1%}) — get role-average expected voto.",
        f"- Players with no participation history at all: {n_no_participation_history} "
        f"({n_no_participation_history / len(result):.1%}) — get role-average participation rate.",
        "",
        "## Top 15 by expected voto",
        "",
        "| Player | Role | Team | Quotazione | Expected voto | Participation rate | Seasons of history |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in result.head(15).itertuples(index=False):
        lines.append(
            f"| {row.display_name} | {row.role} | {row.team_name} | {row.quotazione_asta} | "
            f"{row.expected_voto} | {row.participation_rate} | {row.seasons_of_history} |"
        )

    lines += ["", "## Bottom 10 by expected voto (excluding role fallback with no history)", ""]
    with_history = result[result["player_matchdays_in_history"] > 0]
    lines += ["| Player | Role | Team | Expected voto | Player matchdays in history |", "|---|---|---|---:|---:|"]
    for row in with_history.tail(10).itertuples(index=False):
        lines.append(f"| {row.display_name} | {row.role} | {row.team_name} | {row.expected_voto} | {row.player_matchdays_in_history} |")

    lines += ["", "## By role: average expected voto and participation rate", "", "| Role | Avg expected voto | Avg participation rate | Players |", "|---|---:|---:|---:|"]
    for role, g in result.groupby("role"):
        lines.append(f"| {role} | {g['expected_voto'].mean():.3f} | {g['participation_rate'].mean():.3f} | {len(g)} |")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nFull CSV: {CSV_PATH}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
