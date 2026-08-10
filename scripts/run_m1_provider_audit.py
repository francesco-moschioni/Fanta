#!/usr/bin/env python3
"""M1 provider audit: StatsBomb Open Data and API-Football against football-data.co.uk.

Sportmonks is excluded: its free plan does not include Serie A at all (verified
2026-08-10), so no same-sample comparison is possible without a paid upgrade.

Part A — StatsBomb Open Data (Serie A 2015/16, full 380-match season, free/no-auth):
cross-validated against football-data.co.uk season 1516 on date/team/score, plus a
small event-depth sample to confirm lineup/sub/card/penalty coverage.

Part B — API-Football (Serie A 2023 season, free tier, 100 calls/day hard cap):
cross-validated against football-data.co.uk season 2324, plus a lineup/event depth
sample sized to stay well within the daily call budget.

Both parts write immutable raw snapshots, a staged CSV, and append to
data/outputs/m1_provider_audit_report.md.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fantacalcio.ingest import api_football as af
from fantacalcio.ingest import football_data_co_uk as fd
from fantacalcio.ingest import statsbomb as sb
from fantacalcio.ingest.quality import cross_source_match_rate, missingness_report
from fantacalcio.identity.teams import resolve_against_anchor

STATSBOMB_DEPTH_SAMPLE_SIZE = 15
API_FOOTBALL_DEPTH_SAMPLE_SIZE = 30  # + 1 fixtures call = 61 calls, well under the 100/day cap


def audit_statsbomb() -> str:
    print("=== Part A: StatsBomb Open Data (Serie A 2015/16) ===")
    fd_snapshot = fd.fetch_season("1516")
    fd_staged = fd.parse_snapshot(fd_snapshot, "1516")
    fd.write_staged_csv(fd_staged)
    print(f"football-data.co.uk 1516: {len(fd_staged.frame)} rows")

    sb_snapshot = sb.fetch_matches(**sb.SERIE_A_2015_16)
    sb_staged = sb.parse_matches_snapshot(sb_snapshot, **sb.SERIE_A_2015_16)
    sb.write_staged_csv(sb_staged)
    print(f"StatsBomb 2015/16: {len(sb_staged.frame)} rows")

    fd_teams = list(fd_staged.frame["HomeTeam"]) + list(fd_staged.frame["AwayTeam"])
    sb_teams = list(sb_staged.frame["home_team"]) + list(sb_staged.frame["away_team"])
    resolution = resolve_against_anchor(
        anchor_names=fd_teams, anchor_source_id=fd.SOURCE_ID,
        other_names=sb_teams, other_source_id=sb.SOURCE_ID,
    )
    print(f"Team resolution: {len(resolution.crosswalk)} confirmed, {len(resolution.review_queue)} review queue")

    name_to_id: dict[str, str] = {}
    for e in resolution.crosswalk:
        name_to_id[e.canonical_name] = e.team_id
        name_to_id[e.matched_name] = e.team_id
    fd_staged.frame["home_team_id"] = fd_staged.frame["HomeTeam"].map(name_to_id)
    fd_staged.frame["away_team_id"] = fd_staged.frame["AwayTeam"].map(name_to_id)
    sb_staged.frame["home_team_id"] = sb_staged.frame["home_team"].map(name_to_id)
    sb_staged.frame["away_team_id"] = sb_staged.frame["away_team"].map(name_to_id)

    match_result = cross_source_match_rate(
        results_frame=fd_staged.frame,
        fixtures_frame=sb_staged.frame.rename(columns={"date": "date"}),
        results_team_id_cols=("home_team_id", "away_team_id"),
        fixtures_team_id_cols=("home_team_id", "away_team_id"),
    )
    print(f"Match rate vs football-data.co.uk: {match_result.match_rate:.2%} ({match_result.matched}/{match_result.total_candidates})")

    # Score agreement, not just fixture presence: for matched games, do the scores agree?
    fd_lookup = {
        (row["home_team_id"], row["away_team_id"], row["Date"].date()): (row["FTHG"], row["FTAG"])
        for _, row in fd_staged.frame.dropna(subset=["home_team_id", "away_team_id"]).iterrows()
    }
    score_agree, score_total = 0, 0
    for _, row in sb_staged.frame.dropna(subset=["home_team_id", "away_team_id"]).iterrows():
        for delta in (-1, 0, 1):
            key = (row["home_team_id"], row["away_team_id"], (row["date"] + pd_timedelta(delta)).date())
            if key in fd_lookup:
                score_total += 1
                if fd_lookup[key] == (row["home_score"], row["away_score"]):
                    score_agree += 1
                break
    score_agreement_rate = round(score_agree / score_total, 4) if score_total else 0.0
    print(f"Score agreement on matched fixtures: {score_agreement_rate:.2%} ({score_agree}/{score_total})")

    depth_samples = []
    sample_ids = list(sb_staged.frame["match_id"])[:STATSBOMB_DEPTH_SAMPLE_SIZE]
    for i, match_id in enumerate(sample_ids, start=1):
        print(f"  depth sample {i}/{len(sample_ids)}: match {match_id}")
        depth_samples.append(sb.sample_match_depth(int(match_id)))

    return _render_section(
        title="Part A — StatsBomb Open Data (Serie A 2015/16)",
        anchor_label="football-data.co.uk (season 1516)",
        other_label="StatsBomb Open Data",
        match_result=match_result,
        score_agreement_rate=score_agreement_rate,
        score_total=score_total,
        resolution=resolution,
        depth_rows=[
            (
                d.match_id,
                d.starting_xi_home,
                d.starting_xi_away,
                d.substitution_events,
                d.card_events,
                d.penalty_events,
                d.goal_events,
            )
            for d in depth_samples
        ],
        license_note="CC-BY-NC-style attribution licence; free, no account. Historical season only "
        "(no current-season coverage) — usable as a quality benchmark / R&D source, not as the live provider.",
    )


def audit_api_football() -> str:
    print("=== Part B: API-Football (Serie A 2023) ===")
    budget = af.RequestBudget()

    fd_snapshot = fd.fetch_season("2324")
    fd_staged = fd.parse_snapshot(fd_snapshot, "2324")
    fd.write_staged_csv(fd_staged)
    print(f"football-data.co.uk 2324: {len(fd_staged.frame)} rows")

    af_snapshot = af.fetch_fixtures(af.SERIE_A_LEAGUE_ID, 2023, budget)
    af_staged = af.parse_fixtures_snapshot(af_snapshot, af.SERIE_A_LEAGUE_ID, 2023)
    af.write_staged_csv(af_staged)
    print(f"API-Football 2023: {len(af_staged.frame)} rows (budget used: {budget.used}/{budget.limit})")

    fd_teams = list(fd_staged.frame["HomeTeam"]) + list(fd_staged.frame["AwayTeam"])
    af_teams = list(af_staged.frame["home_team"]) + list(af_staged.frame["away_team"])
    resolution = resolve_against_anchor(
        anchor_names=fd_teams, anchor_source_id=fd.SOURCE_ID,
        other_names=af_teams, other_source_id=af.SOURCE_ID,
    )
    print(f"Team resolution: {len(resolution.crosswalk)} confirmed, {len(resolution.review_queue)} review queue")

    name_to_id: dict[str, str] = {}
    for e in resolution.crosswalk:
        name_to_id[e.canonical_name] = e.team_id
        name_to_id[e.matched_name] = e.team_id
    fd_staged.frame["home_team_id"] = fd_staged.frame["HomeTeam"].map(name_to_id)
    fd_staged.frame["away_team_id"] = fd_staged.frame["AwayTeam"].map(name_to_id)
    af_staged.frame["home_team_id"] = af_staged.frame["home_team"].map(name_to_id)
    af_staged.frame["away_team_id"] = af_staged.frame["away_team"].map(name_to_id)
    af_staged.frame["date"] = af_staged.frame["date"].dt.tz_localize(None)

    match_result = cross_source_match_rate(
        results_frame=fd_staged.frame,
        fixtures_frame=af_staged.frame,
        results_team_id_cols=("home_team_id", "away_team_id"),
        fixtures_team_id_cols=("home_team_id", "away_team_id"),
    )
    print(f"Match rate vs football-data.co.uk: {match_result.match_rate:.2%} ({match_result.matched}/{match_result.total_candidates})")

    finished = af_staged.frame[af_staged.frame["status"] == "FT"]
    sample_ids = list(finished["fixture_id"])[:API_FOOTBALL_DEPTH_SAMPLE_SIZE]
    depth_samples = []
    for i, fixture_id in enumerate(sample_ids, start=1):
        remaining = budget.limit - budget.used
        if remaining < 2:
            print(f"  stopping depth sample early: budget exhausted ({budget.used}/{budget.limit})")
            break
        print(f"  depth sample {i}/{len(sample_ids)}: fixture {fixture_id} (budget {budget.used}/{budget.limit})")
        depth_samples.append(af.sample_fixture_depth(int(fixture_id), budget))

    print(f"Final budget used: {budget.used}/{budget.limit}")

    return _render_section(
        title="Part B — API-Football (Serie A 2023)",
        anchor_label="football-data.co.uk (season 2324)",
        other_label="API-Football",
        match_result=match_result,
        score_agreement_rate=None,
        score_total=None,
        resolution=resolution,
        depth_rows=[
            (
                d.fixture_id,
                d.starting_xi_home,
                d.starting_xi_away,
                d.substitution_events,
                d.card_events,
                d.penalty_events,
                d.goal_events,
            )
            for d in depth_samples
        ],
        license_note=f"Free plan: {af.FREE_PLAN_DAILY_LIMIT} requests/day, restricted to seasons 2022-2024 "
        f"(verified 2026-08-10; current season requires a paid plan). This audit used {budget.used} calls.",
    )


def pd_timedelta(days: int):
    import pandas as pd

    return pd.Timedelta(days=days)


def _render_section(*, title, anchor_label, other_label, match_result, score_agreement_rate, score_total, resolution, depth_rows, license_note) -> str:
    lines = [f"## {title}", "", f"Licence/access: {license_note}", ""]
    lines += [
        f"**Fixture match rate** ({other_label} vs {anchor_label}, same team_id pair within 1 day): "
        f"{match_result.match_rate:.2%} ({match_result.matched}/{match_result.total_candidates})",
        "",
    ]
    if score_total is not None:
        lines += [
            f"**Score agreement** on matched fixtures: {score_agreement_rate:.2%} ({score_total} compared)",
            "",
        ]
    lines += [
        f"**Team identity resolution**: {len(resolution.crosswalk)} confirmed, "
        f"{len(resolution.review_queue)} sent to review queue (never force-matched).",
        "",
        "**Depth sample** (starting XI size, substitution/card/penalty/goal event counts per match):",
        "",
        "| id | XI home | XI away | subs | cards | penalties | goals |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in depth_rows:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} |")
    if not depth_rows:
        lines.append("| (no depth sample collected) | | | | | | |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    sections = []
    sections.append(audit_statsbomb())
    sections.append(audit_api_football())

    report = "\n".join(
        [
            "# M1 provider audit — StatsBomb Open Data and API-Football",
            "",
            "Generated by `scripts/run_m1_provider_audit.py`. Sportmonks is excluded: its "
            "free plan does not include Serie A at all (verified 2026-08-10) — see "
            "`docs/SOURCE_REGISTER.md` for the upgrade path if a paid plan is approved.",
            "",
            *sections,
        ]
    )
    out_path = Path("data/outputs/m1_provider_audit_report.md")
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    main()
