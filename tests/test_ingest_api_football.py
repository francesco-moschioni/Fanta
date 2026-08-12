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


def test_search_player_returns_raw_matches_without_filtering(tmp_path, monkeypatch):
    fake_matches = [{"player": {"name": "Someone Else"}}, {"player": {"name": "Test Player"}}]

    def fake_call(endpoint, params, budget):
        assert endpoint == "players"
        assert params == {"search": "Test Player", "season": 2023}
        budget.consume(1)
        return b'{"response": []}', {"response": fake_matches}

    monkeypatch.setattr(af, "_call", fake_call)
    budget = af.RequestBudget()
    result = af.search_player("Test Player", 2023, budget, raw_root=tmp_path)
    assert result.query_name == "Test Player"
    assert result.matches == fake_matches  # unfiltered, no name-only join performed here
    assert budget.used == 1


def test_search_player_includes_team_id_when_given(tmp_path, monkeypatch):
    seen_params = {}

    def fake_call(endpoint, params, budget):
        seen_params.update(params)
        budget.consume(1)
        return b'{"response": []}', {"response": []}

    monkeypatch.setattr(af, "_call", fake_call)
    budget = af.RequestBudget()
    af.search_player("Test Player", 2023, budget, team_id=505, raw_root=tmp_path)
    assert seen_params == {"search": "Test Player", "season": 2023, "team": 505}
