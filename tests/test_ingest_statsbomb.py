import json

import pytest

from fantacalcio.ingest import statsbomb as sb
from fantacalcio.ingest.snapshot import write_snapshot

_SAMPLE_EVENTS = [
    {"type": {"name": "Foul Committed"}, "foul_committed": {}},  # foul, no card
    {"type": {"name": "Foul Committed"}, "foul_committed": {"card": {"name": "Yellow Card"}}},
    {"type": {"name": "Bad Behaviour"}, "bad_behaviour": {"card": {"name": "Yellow Card"}}},
    {"type": {"name": "Substitution"}},
    {"type": {"name": "Substitution"}},
    {"type": {"name": "Shot"}, "shot": {"type": {"name": "Penalty"}, "outcome": {"name": "Goal"}}},
    {"type": {"name": "Shot"}, "shot": {"type": {"name": "Open Play"}, "outcome": {"name": "Goal"}}},
    {"type": {"name": "Shot"}, "shot": {"type": {"name": "Open Play"}, "outcome": {"name": "Saved"}}},
]

_SAMPLE_LINEUPS = [
    {
        "lineup": [
            {"positions": [{"start_reason": "Starting XI"}]},
            {"positions": [{"start_reason": "Starting XI"}]},
            {"positions": [{"start_reason": "Substitution - On (Tactical)"}]},
        ]
    },
    {"lineup": [{"positions": [{"start_reason": "Starting XI"}]}]},
]


def test_compute_depth_metrics_counts_cards_not_fouls():
    metrics = sb._compute_depth_metrics(
        match_id=1,
        events=_SAMPLE_EVENTS,
        lineups=_SAMPLE_LINEUPS,
        events_snapshot=None,
        lineups_snapshot=None,
    )
    # 3 fouls total, only 2 carry a card -> card_events must be 2, not 3.
    assert metrics.card_events == 2
    assert metrics.substitution_events == 2
    assert metrics.penalty_events == 1
    assert metrics.goal_events == 2
    assert metrics.starting_xi_home == 2
    assert metrics.starting_xi_away == 1

_MATCHES_JSON = json.dumps(
    [
        {
            "match_id": 111,
            "match_date": "2015-08-22",
            "home_team": {"home_team_name": "Hellas Verona"},
            "away_team": {"away_team_name": "Bologna"},
            "home_score": 0,
            "away_score": 2,
            "match_status": "available",
        }
    ]
)


def test_parse_matches_snapshot(tmp_path):
    snap = write_snapshot(
        content=_MATCHES_JSON.encode("utf-8"), url="u", source_id=sb.SOURCE_ID, filename="m.json", raw_root=tmp_path
    )
    staged = sb.parse_matches_snapshot(snap, competition_id=12, season_id=27)
    assert len(staged.frame) == 1
    row = staged.frame.iloc[0]
    assert row["home_team"] == "Hellas Verona"
    assert row["home_score"] == 0
    assert row["away_score"] == 2


def test_parse_matches_snapshot_missing_key_raises(tmp_path):
    bad = json.dumps([{"match_id": 1, "match_date": "2015-08-22"}])
    snap = write_snapshot(content=bad.encode("utf-8"), url="u", source_id=sb.SOURCE_ID, filename="m.json", raw_root=tmp_path)
    with pytest.raises(ValueError, match="missing keys"):
        sb.parse_matches_snapshot(snap, competition_id=12, season_id=27)


def test_parse_matches_snapshot_empty_list_raises(tmp_path):
    snap = write_snapshot(content=b"[]", url="u", source_id=sb.SOURCE_ID, filename="m.json", raw_root=tmp_path)
    with pytest.raises(ValueError, match="no usable match list"):
        sb.parse_matches_snapshot(snap, competition_id=12, season_id=27)
