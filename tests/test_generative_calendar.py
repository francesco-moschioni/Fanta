"""Stage 4 follow-up: real per-club season calendar loader (ADR-2026-077 addendum)."""

from __future__ import annotations

import pandas as pd
import pytest

from fantacalcio.scoring.generative.calendar import (
    CLUB_ALIASES,
    load_season_fixtures,
    staged_calendar_path,
)

_STAGED = staged_calendar_path("2026-27")
_HAVE_STAGED = _STAGED.is_file()

pytestmark = pytest.mark.skipif(
    not _HAVE_STAGED, reason="no staged OpenFootball 2026-27 calendar on this checkout"
)


def test_every_club_has_a_full_round_robin():
    fx = load_season_fixtures("2026-27")
    assert set(fx) == set(CLUB_ALIASES.values())
    for team, games in fx.items():
        assert len(games) == 38, team
        assert sum(g.is_home for g in games) == 19, team
        assert [g.matchday for g in games] == sorted(g.matchday for g in games)
        assert {g.matchday for g in games} == set(range(1, 39)), team


def test_home_and_away_are_consistent_between_the_two_clubs():
    raw = pd.read_csv(_STAGED)
    inv = {v: k for k, v in CLUB_ALIASES.items()}
    fx = load_season_fixtures("2026-27")
    row = raw.iloc[0]
    home_short, away_short = CLUB_ALIASES[row["team1"]], CLUB_ALIASES[row["team2"]]
    md = int(str(row["round"]).split()[-1])
    assert next(g for g in fx[home_short] if g.matchday == md).is_home is True
    assert next(g for g in fx[away_short] if g.matchday == md).is_home is False
    assert inv[home_short] == row["team1"]


def test_unknown_club_name_raises(tmp_path):
    csv = tmp_path / "serie_a_9999-00.csv"
    pd.DataFrame(
        {
            "round": ["Matchday 1", "Matchday 1"],
            "date": ["2099-08-20", "2099-08-20"],
            "team1": ["Made Up FC", "AC Milan"],
            "team2": ["AC Milan", "Made Up FC"],
        }
    ).to_csv(csv, index=False)
    with pytest.raises(KeyError, match="alias table"):
        load_season_fixtures("9999-00", staged_root=tmp_path)


def test_missing_calendar_raises():
    with pytest.raises(FileNotFoundError):
        load_season_fixtures("1900-01")
