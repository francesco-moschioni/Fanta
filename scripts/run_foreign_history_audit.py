#!/usr/bin/env python3
"""Read-only discovery audit: for players flagged `no_history_transfer`/
`no_history_new_team` in the M3 output (zero Serie A history in this
pipeline, because they arrived from another league), checks whether
API-Football's free plan (100 req/day, seasons 2022-2024 only, verified
2026-08-10, docs/SOURCE_REGISTER.md) can find their prior-league history.

**Real finding from the first run (2026-08-12)**: API-Football's `players`
search endpoint rejects a name-only global search outright -- it requires a
`team` or `league` parameter alongside `search`. Confirmed with a real call:

    API-Football error for players {'search': 'Ramos', 'season': 2023}:
    {'team': 'The League or Team field is required with the Search field.',
     'league': 'The League or Team field is required with the Search field.'}

So "search everywhere for this player" is not actually possible without
already knowing which club/league to scope the search to -- and our own
listone (`data/staged/fantacalcio_quotazioni_manual/2026_27.csv`) has no
"prior club" field to resolve that from automatically. Full writeup:
`data/staged/fantacalcio_voti_manual/_foreign_history_audit.md`.

This script is therefore built around a human-supplied hint: `SAMPLE_HINTS`
maps a display name to a `(team_name, league_name)` guess the user already
has some reason to believe (news, admin transfer list, personal knowledge)
-- never invented here. Leave the hint as `None` to see the same rejection
documented above; fill one in to actually query that specific club/league.

This is discovery only: nothing here writes to the domain pipeline or joins
anything by name into player_code (CLAUDE.md forbids name-only joins). It
reports raw candidate matches for a human to look at, same spirit as the M1
provider audit (scripts/run_m1_provider_audit.py) -- prove real coverage
before spending money or engineering effort on a new source.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.ingest.api_football import ApiFootballError, RequestBudget, search_player

M3_CSV = Path("data/staged/fantacalcio_voti_manual/_m3_replacement_values.csv")
REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_foreign_history_audit.md")
SEASON = 2023  # free-plan seasons are 2022-2024 only

# display_name (as it appears in _m3_replacement_values.csv) -> API-Football
# team_id of their PRIOR club, or None to reproduce the documented rejection.
# Fill in real values only from something the user actually knows/trusts
# (news, admin transfer list) -- never a guess made up by this script or an
# LLM. Team IDs can be looked up via the /teams?search= endpoint separately.
SAMPLE_HINTS: dict[str, int | None] = {
    "Ramos G.": None,
    "Mastantuono": None,
    "Kevin Carlos": None,
    "Chalobah T.": None,
    "Stones": None,
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
        "2022-2024).",
        "",
        "**Discovery only** -- raw candidate matches, no identity resolution "
        "performed, nothing written to the domain pipeline.",
        "",
    ]

    for name, team_id in SAMPLE_HINTS.items():
        if team_id is None:
            lines.append(f"## \"{name}\" — no team_id hint provided, skipped")
            lines.append("")
            lines.append(
                "API-Football's free-plan `players` search requires a `team` or "
                "`league` alongside `search` (confirmed 2026-08-12, see module "
                "docstring) -- provide a real `team_id` in `SAMPLE_HINTS` to query this player."
            )
            lines.append("")
            continue
        try:
            result = search_player(name, SEASON, budget, team_id=team_id)
        except ApiFootballError as e:
            lines.append(f"## \"{name}\" — search rejected by the API")
            lines.append("")
            lines.append(f"```\n{e}\n```")
            lines.append("")
            continue
        lines.append(f"## \"{name}\" — {len(result.matches)} match(es)")
        lines.append("")
        if not result.matches:
            lines.append("No match found on the free plan for this season.")
        else:
            lines.append("| Name | Team (that season) | Position | Age |")
            lines.append("|---|---|---|---|")
            for m in result.matches[:5]:
                player = m.get("player", {})
                stats = m.get("statistics", [{}])
                team = stats[0].get("team", {}).get("name", "?") if stats else "?"
                games = stats[0].get("games", {}) if stats else {}
                lines.append(
                    f"| {player.get('name', '?')} | {team} | {games.get('position', '?')} | {player.get('age', '?')} |"
                )
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nRequests used: {budget.used}/{budget.limit}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
