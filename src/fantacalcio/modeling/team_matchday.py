"""Team-level per-matchday goals scored/conceded, derived from football-data.co.uk
match results — used to give defenders a real clean-sheet signal (unlike the voti
export's `goals_conceded` field, which is only reliable for goalkeepers; see
ADR-2026-016 and src/fantacalcio/scoring/engine.py).

Matchday number is not a column in the football-data.co.uk export. It is derived by
ranking each team's matches chronologically within a season (matchday = 1-indexed
rank by date) rather than joining a separate source for round numbers. Verified
2026-08-11 against OpenFootball's explicit `round` field for season 2025/26: the
date sequence for a sample team (Atalanta) matched "Matchday 1, 2, 3..." exactly,
confirming this league has no byes/irregular scheduling that would break the
assumption of one match per team per matchday.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# football-data.co.uk season code -> voti/listone season_label
FD_TO_VOTI_SEASON = {
    "2122": "2021_22",
    "2223": "2022_23",
    "2324": "2023_24",
    "2425": "2024_25",
    "2526": "2025_26",
}


class TeamMatchdayError(ValueError):
    pass


@dataclass(frozen=True)
class TeamMatchdayResults:
    frame: pd.DataFrame  # columns: team_name, season_label, matchday, goals_scored, goals_conceded, date


def build_team_matchday_results(fd_matches: pd.DataFrame, season_code: str) -> TeamMatchdayResults:
    """`fd_matches` is one season's staged football-data.co.uk frame (columns Date,
    HomeTeam, AwayTeam, FTHG, FTAG). Returns one row per team per matchday."""
    if season_code not in FD_TO_VOTI_SEASON:
        raise TeamMatchdayError(
            f"Unknown football-data.co.uk season code {season_code!r}; "
            f"add it to FD_TO_VOTI_SEASON if this is a real season."
        )
    season_label = FD_TO_VOTI_SEASON[season_code]

    home = fd_matches[["Date", "HomeTeam", "FTHG", "FTAG"]].rename(
        columns={"HomeTeam": "team_name", "FTHG": "goals_scored", "FTAG": "goals_conceded"}
    )
    away = fd_matches[["Date", "AwayTeam", "FTAG", "FTHG"]].rename(
        columns={"AwayTeam": "team_name", "FTAG": "goals_scored", "FTHG": "goals_conceded"}
    )
    combined = pd.concat([home, away], ignore_index=True)
    combined = combined.sort_values(["team_name", "Date"]).reset_index(drop=True)
    combined["matchday"] = combined.groupby("team_name").cumcount() + 1
    combined["season_label"] = season_label
    combined = combined.rename(columns={"Date": "date"})

    counts = combined.groupby("team_name").size()
    irregular = counts[counts > 38]
    if len(irregular) > 0:
        raise TeamMatchdayError(
            f"Team(s) with more than 38 matches in season {season_code!r}, "
            f"chronological-rank matchday derivation is unsafe: {irregular.to_dict()}"
        )

    return TeamMatchdayResults(frame=combined[["team_name", "season_label", "matchday", "goals_scored", "goals_conceded", "date"]])


def build_all_seasons(staged_root: str = "data/staged/football_data_co_uk") -> TeamMatchdayResults:
    from pathlib import Path

    frames = []
    for code in FD_TO_VOTI_SEASON:
        path = Path(staged_root) / f"serie_a_{code}.csv"
        if not path.is_file():
            raise TeamMatchdayError(f"Staged season file not found: {path}")
        fd = pd.read_csv(path, parse_dates=["Date"])
        frames.append(build_team_matchday_results(fd, code).frame)
    return TeamMatchdayResults(frame=pd.concat(frames, ignore_index=True))
