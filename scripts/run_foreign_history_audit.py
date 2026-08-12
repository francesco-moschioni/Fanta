#!/usr/bin/env python3
"""Read-only discovery audit: for players flagged `no_history_transfer`/
`no_history_new_team` in the M3 output (zero Serie A history in this
pipeline, because they arrived from another league), checks whether
API-Football's free plan (100 req/day, seasons 2022-2024 only, verified
2026-08-10, docs/SOURCE_REGISTER.md) can find their prior-league history.

**Real finding from the first run (2026-08-12)**: API-Football's `players`
search endpoint rejects a name-only global search outright -- it requires a
`team` or `league` parameter alongside `search`. So a `team_id` is required
per player, resolved here via `search_team()` first.

`SAMPLE_HINTS` maps a display name (as it appears in
`_m3_replacement_values.csv`) to the prior club name to search for. These
were NOT invented by this script -- they were researched via web search
(Haiku subagents, 2026-08-12) with cited sources, recorded in this file's
git history. Anyone re-running this script should re-verify a hint before
trusting it for a real bid decision; this is discovery, not ground truth.

This is discovery only: nothing here writes to the domain pipeline or joins
anything by name into player_code (CLAUDE.md forbids name-only joins). It
reports raw candidate matches for a human to look at, same spirit as the M1
provider audit (scripts/run_m1_provider_audit.py) -- prove real coverage
before spending money or engineering effort on a new source.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.ingest.api_football import ApiFootballError, RequestBudget, search_player, search_team

M3_CSV = Path("data/staged/fantacalcio_voti_manual/_m3_replacement_values.csv")
REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_foreign_history_audit.md")
SEASON = 2023  # free-plan seasons are 2022-2024 only

# display_name -> (prior club to search for, source note). Researched via web
# search 2026-08-12, cited in the audit report -- re-verify before trusting.
SAMPLE_HINTS: dict[str, str | None] = {
    "Ramos G.": "Paris Saint Germain",
    "Mastantuono": "Real Madrid",
    "Kevin Carlos": "Nice",
    "Alajbegovic": "Bayer Leverkusen",
    "Stones": "Manchester City",
}


def main() -> None:
    df = pd.read_csv(M3_CSV)
    no_history = df[df["data_quality_tier"].isin(["no_history_transfer", "no_history_new_team"])]
    print(f"{len(no_history)} players with zero Serie A history in the current pipeline.")

    budget = RequestBudget()
    lines = [
        "# Foreign-league history discovery audit (API-Football free plan)",
        "",
        f"{len(no_history)} players in `_m3_replacement_values.csv` have zero Serie A "
        "history -- their real playing history exists, just not in a league this "
        f"pipeline ingests today. Season {SEASON} (free plan restricts seasons to "
        "2022-2024). Prior-club hints researched via web search 2026-08-12, cited "
        "sources in commit history -- re-verify before trusting for a real bid.",
        "",
        "**Discovery only** -- raw candidate matches, no identity resolution "
        "performed, nothing written to the domain pipeline.",
        "",
    ]

    for name, club_hint in SAMPLE_HINTS.items():
        lines.append(f"## {name} — prior club hint: {club_hint}")
        lines.append("")
        if club_hint is None:
            lines.append("No hint provided, skipped.")
            lines.append("")
            continue
        try:
            team_result = search_team(club_hint, budget)
        except ApiFootballError as e:
            lines.append(f"Team search failed: `{e}`")
            lines.append("")
            continue
        if not team_result.matches:
            lines.append(f"No team found for {club_hint!r} on the free plan.")
            lines.append("")
            continue
        team = team_result.matches[0].get("team", {})
        team_id = team.get("id")
        lines.append(f"Resolved team: **{team.get('name', '?')}** (id={team_id})")
        lines.append("")

        try:
            player_result = search_player(name.split()[0], SEASON, budget, team_id=team_id)
        except ApiFootballError as e:
            lines.append(f"Player search failed: `{e}`")
            lines.append("")
            continue
        if not player_result.matches:
            lines.append(
                f"No player match for {name!r} at team_id={team_id}, season {SEASON} "
                "-- possibly a name-format mismatch, or the player wasn't at this club "
                f"that season (only 2022-2024 available on free plan)."
            )
        else:
            lines.append("| Name | Team (that season) | Position | Goals | Assists | Games |")
            lines.append("|---|---|---|---:|---:|---:|")
            for m in player_result.matches[:3]:
                player = m.get("player", {})
                stats = m.get("statistics", [{}])
                s0 = stats[0] if stats else {}
                team_name = s0.get("team", {}).get("name", "?")
                games = s0.get("games", {})
                goals = s0.get("goals", {})
                lines.append(
                    f"| {player.get('name', '?')} | {team_name} | {games.get('position', '?')} | "
                    f"{goals.get('total', '?')} | {goals.get('assists', '?')} | {games.get('appearences', '?')} |"
                )
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nRequests used: {budget.used}/{budget.limit}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
