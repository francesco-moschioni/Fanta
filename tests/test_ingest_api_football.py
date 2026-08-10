import json

import pytest

from fantacalcio.ingest import api_football as af
from fantacalcio.ingest.snapshot import write_snapshot

_FIXTURES_JSON = json.dumps(
    {
        "response": [
            {
                "fixture": {"id": 1, "date": "2023-08-19T18:30:00+00:00", "status": {"short": "FT"}},
                "teams": {"home": {"name": "Genoa"}, "away": {"name": "Inter"}},
                "goals": {"home": 0, "away": 2},
            }
        ]
    }
)


class TestRequestBudget:
    def test_consume_within_limit(self):
        budget = af.RequestBudget(limit=5)
        budget.consume(3)
        assert budget.used == 3

    def test_consume_over_limit_raises(self):
        budget = af.RequestBudget(limit=5)
        budget.consume(4)
        with pytest.raises(af.ApiFootballError, match="Refusing to make"):
            budget.consume(2)
        assert budget.used == 4  # rejected call does not count as consumed


def test_parse_fixtures_snapshot(tmp_path):
    snap = write_snapshot(
        content=_FIXTURES_JSON.encode("utf-8"), url="u", source_id=af.SOURCE_ID, filename="f.json", raw_root=tmp_path
    )
    staged = af.parse_fixtures_snapshot(snap, league_id=135, season=2023)
    assert len(staged.frame) == 1
    row = staged.frame.iloc[0]
    assert row["home_team"] == "Genoa"
    assert row["home_goals"] == 0
    assert row["away_goals"] == 2


def test_parse_fixtures_snapshot_empty_response_raises(tmp_path):
    snap = write_snapshot(
        content=b'{"response": []}', url="u", source_id=af.SOURCE_ID, filename="f.json", raw_root=tmp_path
    )
    with pytest.raises(ValueError, match="empty response"):
        af.parse_fixtures_snapshot(snap, league_id=135, season=2023)


def test_get_key_missing_raises(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    with pytest.raises(af.ApiFootballError, match="not set"):
        af._get_key()
