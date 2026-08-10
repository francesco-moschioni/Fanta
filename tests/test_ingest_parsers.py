import json

import pytest

from fantacalcio.ingest import football_data_co_uk as fd
from fantacalcio.ingest import openfootball as of
from fantacalcio.ingest.snapshot import write_snapshot

_FD_CSV = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
    "I1,17/08/2025,Genoa,Inter,0,2,A\n"
    "I1,18/08/2025,Milan,Napoli,1,1,D\n"
)

_OF_JSON = json.dumps(
    {
        "name": "Test Serie A",
        "matches": [
            {
                "round": "Matchday 1",
                "date": "2025-08-17",
                "team1": "Genoa CFC",
                "team2": "FC Internazionale Milano",
                "score": {"ht": [0, 1], "ft": [0, 2]},
            },
            {
                "round": "Matchday 1",
                "date": "2025-08-18",
                "team1": "AC Milan",
                "team2": "SSC Napoli",
                "score": [1, 1],
            },
            {
                "round": "Matchday 2",
                "date": "2025-08-25",
                "team1": "AS Roma",
                "team2": "Genoa CFC",
                "score": None,
            },
        ],
    }
)


def test_parse_football_data_co_uk_snapshot(tmp_path):
    snap = write_snapshot(
        content=_FD_CSV.encode("utf-8"), url="u", source_id=fd.SOURCE_ID, filename="f.csv", raw_root=tmp_path
    )
    staged = fd.parse_snapshot(snap, season_code="2526")
    assert len(staged.frame) == 2
    assert set(staged.frame["HomeTeam"]) == {"Genoa", "Milan"}
    assert (staged.frame["source_id"] == fd.SOURCE_ID).all()


def test_parse_football_data_co_uk_missing_column_raises(tmp_path):
    bad_csv = "Div,Date,HomeTeam,AwayTeam\nI1,17/08/2025,Genoa,Inter\n"
    snap = write_snapshot(
        content=bad_csv.encode("utf-8"), url="u", source_id=fd.SOURCE_ID, filename="f.csv", raw_root=tmp_path
    )
    with pytest.raises(ValueError, match="missing required columns"):
        fd.parse_snapshot(snap, season_code="2526")


def test_parse_openfootball_snapshot_handles_all_score_shapes(tmp_path):
    snap = write_snapshot(
        content=_OF_JSON.encode("utf-8"), url="u", source_id=of.SOURCE_ID, filename="f.json", raw_root=tmp_path
    )
    staged = of.parse_snapshot(snap, season="2025-26")
    assert len(staged.frame) == 3

    by_team = staged.frame.set_index("team2")
    assert by_team.loc["FC Internazionale Milano", "ft_home"] == 0
    assert by_team.loc["FC Internazionale Milano", "ft_away"] == 2
    assert by_team.loc["SSC Napoli", "ft_home"] == 1  # bare-list score shape
    assert bool(by_team.loc["Genoa CFC", "played"]) is False  # null score shape


def test_parse_openfootball_missing_matches_key_raises(tmp_path):
    snap = write_snapshot(
        content=b'{"name": "x"}', url="u", source_id=of.SOURCE_ID, filename="f.json", raw_root=tmp_path
    )
    with pytest.raises(ValueError, match="matches"):
        of.parse_snapshot(snap, season="2025-26")


def test_parse_openfootball_unrecognized_score_shape_raises(tmp_path):
    bad = json.dumps(
        {"matches": [{"round": "MD1", "date": "2025-08-17", "team1": "A", "team2": "B", "score": "2-0"}]}
    )
    snap = write_snapshot(content=bad.encode("utf-8"), url="u", source_id=of.SOURCE_ID, filename="f.json", raw_root=tmp_path)
    with pytest.raises(ValueError, match="Unrecognized OpenFootball"):
        of.parse_snapshot(snap, season="2025-26")
