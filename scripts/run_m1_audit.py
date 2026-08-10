#!/usr/bin/env python3
"""Run the M1 free-source ingestion + entity-resolution + data-quality audit.

Fetches one Serie A season from football-data.co.uk and OpenFootball, resolves team
identities against football-data.co.uk as the canonical anchor, computes coverage/
missingness/cross-source match-rate, and writes:

- data/raw/<source>/<timestamp>/... (immutable snapshots)
- data/staged/<source>/...          (typed parsed frames)
- data/identity/team_crosswalk.json (confirmed team_id mappings, both sources)
- data/identity/team_review_queue.json (ambiguous matches needing human review)
- data/outputs/m1_data_quality_report.md (this audit's findings)

Both sources are free, no-auth, and already registered in docs/SOURCE_REGISTER.md
with automation permitted. Sportmonks/API-Football/StatsBomb/Wyscout are NOT
attempted here: they require account creation and/or a licensing review that must
happen outside an automated agent session.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fantacalcio.ingest import football_data_co_uk as fd
from fantacalcio.ingest import openfootball as of
from fantacalcio.ingest.quality import cross_source_match_rate, missingness_report
from fantacalcio.identity.teams import resolve_against_anchor

FD_SEASON = "2526"  # football-data.co.uk code for 2025/26
OF_SEASON = "2025-26"


def main() -> None:
    print(f"Fetching football-data.co.uk season {FD_SEASON} ...")
    fd_snapshot = fd.fetch_season(FD_SEASON)
    fd_staged = fd.parse_snapshot(fd_snapshot, FD_SEASON)
    fd_path = fd.write_staged_csv(fd_staged)
    print(f"  snapshot: {fd_snapshot.content_path} sha256={fd_snapshot.sha256[:12]}...")
    print(f"  staged:   {fd_path} ({len(fd_staged.frame)} rows)")

    print(f"Fetching OpenFootball season {OF_SEASON} ...")
    of_snapshot = of.fetch_season(OF_SEASON)
    of_staged = of.parse_snapshot(of_snapshot, OF_SEASON)
    of_path = of.write_staged_csv(of_staged)
    print(f"  snapshot: {of_snapshot.content_path} sha256={of_snapshot.sha256[:12]}...")
    print(f"  staged:   {of_path} ({len(of_staged.frame)} rows)")

    print("Resolving team identities (OpenFootball -> football-data.co.uk anchor) ...")
    fd_teams = list(fd_staged.frame["HomeTeam"]) + list(fd_staged.frame["AwayTeam"])
    of_teams = list(of_staged.frame["team1"]) + list(of_staged.frame["team2"])
    resolution = resolve_against_anchor(
        anchor_names=fd_teams,
        anchor_source_id=fd.SOURCE_ID,
        other_names=of_teams,
        other_source_id=of.SOURCE_ID,
    )
    print(f"  confirmed: {len(resolution.crosswalk)}, review queue: {len(resolution.review_queue)}")

    identity_dir = Path("data/identity")
    identity_dir.mkdir(parents=True, exist_ok=True)
    (identity_dir / "team_crosswalk.json").write_text(
        json.dumps([asdict(e) for e in resolution.crosswalk], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (identity_dir / "team_review_queue.json").write_text(
        json.dumps([asdict(e) for e in resolution.review_queue], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Map by both the anchor (football-data.co.uk) name and the matched (OpenFootball)
    # name to the same team_id, since each staged frame uses its own source's spelling.
    name_to_team_id: dict[str, str] = {}
    for e in resolution.crosswalk:
        name_to_team_id[e.canonical_name] = e.team_id
        name_to_team_id[e.matched_name] = e.team_id
    fd_staged.frame["home_team_id"] = fd_staged.frame["HomeTeam"].map(name_to_team_id)
    fd_staged.frame["away_team_id"] = fd_staged.frame["AwayTeam"].map(name_to_team_id)
    of_staged.frame["home_team_id"] = of_staged.frame["team1"].map(name_to_team_id)
    of_staged.frame["away_team_id"] = of_staged.frame["team2"].map(name_to_team_id)

    fd_missing = missingness_report(fd_staged.frame, fd.REQUIRED_COLUMNS)
    of_missing = missingness_report(of_staged.frame, ["round", "date", "team1", "team2"])

    match_result = cross_source_match_rate(
        results_frame=fd_staged.frame,
        fixtures_frame=of_staged.frame,
        results_team_id_cols=("home_team_id", "away_team_id"),
        fixtures_team_id_cols=("home_team_id", "away_team_id"),
    )
    print(f"  cross-source match rate: {match_result.match_rate:.2%} ({match_result.matched}/{match_result.total_candidates})")

    report = _render_report(
        fd_snapshot=fd_snapshot,
        of_snapshot=of_snapshot,
        fd_staged=fd_staged,
        of_staged=of_staged,
        fd_missing=fd_missing,
        of_missing=of_missing,
        resolution=resolution,
        match_result=match_result,
    )
    out_dir = Path("data/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "m1_data_quality_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Report written to {report_path}")


def _render_report(*, fd_snapshot, of_snapshot, fd_staged, of_staged, fd_missing, of_missing, resolution, match_result) -> str:
    lines = [
        "# M1 data-quality report — free-source sample",
        "",
        f"Generated by `scripts/run_m1_audit.py`. Season: football-data.co.uk `{FD_SEASON}`, "
        f"OpenFootball `{OF_SEASON}`.",
        "",
        "## Sources audited",
        "",
        f"- **football-data.co.uk**: {fd_snapshot.url}, sha256 `{fd_snapshot.sha256}`, "
        f"retrieved `{fd_snapshot.retrieved_at}`, {fd_missing.row_count} rows.",
        f"- **OpenFootball**: {of_snapshot.url}, sha256 `{of_snapshot.sha256}`, "
        f"retrieved `{of_snapshot.retrieved_at}`, {of_missing.row_count} rows.",
        "",
        "Sportmonks, API-Football, StatsBomb, and Wyscout are **not** included in this "
        "audit: the first two require account/trial creation, which is out of scope for "
        "an automated agent session; the latter two need a separate licensing review "
        "before ingestion. See the open item at the end of this report.",
        "",
        "## Missingness — football-data.co.uk",
        "",
        "| Column | Missing | Missing % |",
        "|---|---:|---:|",
    ]
    for col, count in fd_missing.missing_by_column.items():
        lines.append(f"| {col} | {count} | {fd_missing.missing_pct_by_column[col]:.2%} |")

    lines += [
        "",
        "## Missingness — OpenFootball",
        "",
        "| Column | Missing | Missing % |",
        "|---|---:|---:|",
    ]
    for col, count in of_missing.missing_by_column.items():
        lines.append(f"| {col} | {count} | {of_missing.missing_pct_by_column[col]:.2%} |")

    lines += [
        "",
        "## Entity resolution (team identity)",
        "",
        f"Anchor: football-data.co.uk team names ({len(set(fd_staged.frame['HomeTeam']) | set(fd_staged.frame['AwayTeam']))} unique). "
        f"Resolved against: OpenFootball team names.",
        "",
        f"- Confirmed mappings: {len(resolution.crosswalk)}",
        f"- Sent to manual review queue (confidence below {0.90:.0%}): {len(resolution.review_queue)}",
        "",
        "No name-only join was performed downstream: matches below the auto-accept "
        "confidence threshold are held in `data/identity/team_review_queue.json` and "
        "excluded from the cross-source comparison until a human confirms them.",
        "",
        "### Confirmed crosswalk",
        "",
        "| team_id | canonical name (football-data.co.uk) | OpenFootball name | confidence | method |",
        "|---|---|---|---:|---|",
    ]
    for e in resolution.crosswalk:
        lines.append(
            f"| {e.team_id} | {e.canonical_name} | {e.matched_name} | {e.confidence:.4f} | {e.match_method} |"
        )

    lines += ["", "### Review queue", ""]
    if resolution.review_queue:
        lines.append("| OpenFootball name | best candidate | confidence | reason |")
        lines.append("|---|---|---:|---|")
        for r in resolution.review_queue:
            lines.append(
                f"| {r.matched_name} | {r.best_candidate_name or '(none)'} | {r.confidence:.4f} | {r.reason} |"
            )
    else:
        lines.append("(empty — every OpenFootball team name matched the anchor with high confidence)")

    lines += [
        "",
        "## Cross-source consistency (drift check)",
        "",
        f"Matched {match_result.matched}/{match_result.total_candidates} football-data.co.uk "
        f"results against an OpenFootball fixture with the same resolved team_id pair within "
        f"a 1-day date window: **{match_result.match_rate:.2%}** match rate.",
        "",
    ]
    if match_result.unmatched_sample:
        lines.append("Sample of unmatched results (candidates for drift/coverage investigation):")
        lines.append("")
        lines.append("| date | home_team_id | away_team_id |")
        lines.append("|---|---|---|")
        for u in match_result.unmatched_sample:
            lines.append(f"| {u['date']} | {u['home_team_id']} | {u['away_team_id']} |")
        lines.append("")

    lines += [
        "## Open item — providers requiring account creation",
        "",
        "Per docs/ROADMAP.md M1, the full audit also requires a Sportmonks vs. "
        "API-Football trial on the same ≥100-match sample plus a ≥50-match independent "
        "comparison. Both require signing up for a trial/account, which this session "
        "cannot do on the user's behalf. To continue:",
        "",
        "1. Create a Sportmonks trial account and an API-Football account (free tier is enough to audit).",
        "2. Provide the two API keys as environment variables (never commit them):"
        " `SPORTMONKS_API_KEY`, `API_FOOTBALL_KEY`.",
        "3. Re-open `docs/CURRENT_TASK.md` for the remainder of M1 once the keys are available.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
