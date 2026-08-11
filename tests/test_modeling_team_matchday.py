import pandas as pd
import pytest

from fantacalcio.modeling.team_matchday import (
    TeamMatchdayError,
    build_team_matchday_results,
)


def _fd_frame(rows):
    return pd.DataFrame(rows, columns=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])


def test_derives_matchday_by_chronological_rank():
    fd = _fd_frame(
        [
            ["2025-08-24", "Atalanta", "Pisa", 2, 0],
            ["2025-08-30", "Parma", "Atalanta", 1, 1],
            ["2025-09-14", "Atalanta", "Lecce", 0, 0],
        ]
    )
    fd["Date"] = pd.to_datetime(fd["Date"])
    result = build_team_matchday_results(fd, "2526")
    atalanta = result.frame[result.frame["team_name"] == "Atalanta"].sort_values("matchday")
    assert list(atalanta["matchday"]) == [1, 2, 3]
    assert list(atalanta["goals_scored"]) == [2, 1, 0]
    assert list(atalanta["goals_conceded"]) == [0, 1, 0]


def test_season_label_mapping():
    fd = _fd_frame([["2025-08-24", "A", "B", 1, 0]])
    fd["Date"] = pd.to_datetime(fd["Date"])
    result = build_team_matchday_results(fd, "2526")
    assert (result.frame["season_label"] == "2025_26").all()


def test_unknown_season_code_raises():
    fd = _fd_frame([["2025-08-24", "A", "B", 1, 0]])
    fd["Date"] = pd.to_datetime(fd["Date"])
    with pytest.raises(TeamMatchdayError, match="Unknown"):
        build_team_matchday_results(fd, "9999")


def test_more_than_38_matches_raises():
    rows = [[f"2025-08-{24 + (i % 5)}", "Atalanta", "Pisa", 1, 0] for i in range(39)]
    fd = _fd_frame(rows)
    fd["Date"] = pd.to_datetime(fd["Date"])
    with pytest.raises(TeamMatchdayError, match="more than 38 matches"):
        build_team_matchday_results(fd, "2526")


def test_home_and_away_goals_swapped_correctly():
    fd = _fd_frame([["2025-08-24", "Home", "Away", 3, 1]])
    fd["Date"] = pd.to_datetime(fd["Date"])
    result = build_team_matchday_results(fd, "2526")
    home_row = result.frame[result.frame["team_name"] == "Home"].iloc[0]
    away_row = result.frame[result.frame["team_name"] == "Away"].iloc[0]
    assert home_row["goals_scored"] == 3 and home_row["goals_conceded"] == 1
    assert away_row["goals_scored"] == 1 and away_row["goals_conceded"] == 3
