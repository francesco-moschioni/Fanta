"""Ingestion for API-Football (api-sports.io), free tier.

Registered in docs/SOURCE_REGISTER.md as "candidato challenger". Requires
API_FOOTBALL_KEY in the environment; never read from a committed file. The free plan
is capped at 100 requests/day and restricted to seasons 2022-2024 (verified
2026-08-10) — current-season data requires a paid plan. `RequestBudget` makes that
cap explicit in code so a caller cannot silently blow through it.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .snapshot import DEFAULT_RAW_ROOT, RawSnapshot, write_snapshot

SOURCE_ID = "api_football"
_BASE = "https://v3.football.api-sports.io"
SERIE_A_LEAGUE_ID = 135
FREE_PLAN_DAILY_LIMIT = 100
# The free plan also enforces a per-minute rate limit tighter than the daily cap
# (empirically hit a 429 at 10 calls with no spacing; verified 2026-08-10). Space
# calls out rather than guessing the exact limit or retrying blindly on 429.
_MIN_SECONDS_BETWEEN_CALLS = 7.0
_last_call_monotonic: float | None = None


class ApiFootballError(RuntimeError):
    pass


class RequestBudget:
    """Tracks calls made in-process against a hard cap; refuses the call that would
    exceed it rather than making it and finding out from a 429."""

    def __init__(self, limit: int = FREE_PLAN_DAILY_LIMIT):
        self.limit = limit
        self.used = 0

    def consume(self, n: int = 1) -> None:
        if self.used + n > self.limit:
            raise ApiFootballError(
                f"Refusing to make {n} more API-Football call(s): would exceed the "
                f"budget of {self.limit} (already used {self.used}). Free plan is "
                f"capped at {FREE_PLAN_DAILY_LIMIT}/day; run again after reset or on a paid plan."
            )
        self.used += n


def _get_key() -> str:
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        raise ApiFootballError("API_FOOTBALL_KEY is not set in the environment")
    return key


def _throttle() -> None:
    global _last_call_monotonic
    if _last_call_monotonic is not None:
        elapsed = time.monotonic() - _last_call_monotonic
        wait = _MIN_SECONDS_BETWEEN_CALLS - elapsed
        if wait > 0:
            time.sleep(wait)
    _last_call_monotonic = time.monotonic()


def _call(endpoint: str, params: dict, budget: RequestBudget) -> tuple[bytes, dict]:
    budget.consume(1)
    _throttle()
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{_BASE}/{endpoint}?{qs}"
    req = urllib.request.Request(url, headers={"x-apisports-key": _get_key()})
    with urllib.request.urlopen(req, timeout=30) as response:
        content = response.read()
    payload = json.loads(content)
    if payload.get("errors"):
        raise ApiFootballError(f"API-Football error for {endpoint} {params}: {payload['errors']}")
    return content, payload


@dataclass(frozen=True)
class StagedFixtures:
    league_id: int
    season: int
    snapshot: RawSnapshot
    frame: "pd.DataFrame"


def fetch_fixtures(league_id: int, season: int, budget: RequestBudget, raw_root: Path = DEFAULT_RAW_ROOT) -> RawSnapshot:
    """One call returns every fixture for the league+season."""
    content, _ = _call("fixtures", {"league": league_id, "season": season}, budget)
    return write_snapshot(
        content=content,
        url=f"{_BASE}/fixtures?league={league_id}&season={season}",
        source_id=SOURCE_ID,
        filename=f"fixtures_{league_id}_{season}.json",
        raw_root=raw_root,
    )


def parse_fixtures_snapshot(snapshot: RawSnapshot, league_id: int, season: int) -> StagedFixtures:
    payload = json.loads(Path(snapshot.content_path).read_bytes())
    response = payload.get("response")
    if not response:
        raise ValueError(f"API-Football fixtures snapshot {snapshot.content_path} has an empty response")

    rows = []
    for f in response:
        rows.append(
            {
                "fixture_id": f["fixture"]["id"],
                "date": f["fixture"]["date"],
                "status": f["fixture"]["status"]["short"],
                "home_team": f["teams"]["home"]["name"],
                "away_team": f["teams"]["away"]["name"],
                "home_goals": f["goals"]["home"],
                "away_goals": f["goals"]["away"],
            }
        )
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise", utc=True)
    frame["source_id"] = SOURCE_ID
    frame["source_file_hash"] = snapshot.sha256
    frame["ingested_time"] = snapshot.retrieved_at
    return StagedFixtures(league_id=league_id, season=season, snapshot=snapshot, frame=frame)


def write_staged_csv(staged: StagedFixtures, staged_root: Path = Path("data/staged")) -> Path:
    out_dir = staged_root / SOURCE_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"fixtures_{staged.league_id}_{staged.season}.csv"
    staged.frame.to_csv(out_path, index=False)
    return out_path


@dataclass(frozen=True)
class PlayerSearchResult:
    query_name: str
    season: int
    snapshot: RawSnapshot
    matches: list[dict]  # raw API-Football player summaries, unfiltered -- caller decides identity match


def search_player(
    name: str, season: int, budget: RequestBudget, team_id: int | None = None, raw_root: Path = DEFAULT_RAW_ROOT
) -> PlayerSearchResult:
    """Searches API-Football's player index by name for a given season.

    `team_id` is required in practice, not optional: confirmed by a real call
    (2026-08-12, data/staged/fantacalcio_voti_manual/_foreign_history_audit.md)
    that the free plan rejects a name-only global search with "The League or
    Team field is required with the Search field." A `team_id` must come from
    something the caller already has reason to believe (a human-supplied
    hint), never guessed here -- this function does not resolve identity, it
    only queries a scope the caller already chose.

    Read-only discovery only -- this never joins results into the domain
    pipeline by name (CLAUDE.md forbids name-only joins); it's for a human to
    look at candidate matches and their league/team/stats before deciding
    anything is usable. Free-plan seasons are restricted to 2022-2024
    (verified 2026-08-10, docs/SOURCE_REGISTER.md)."""
    params = {"search": name, "season": season}
    if team_id is not None:
        params["team"] = team_id
    content, payload = _call("players", params, budget)
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    snapshot = write_snapshot(
        content=content,
        url=f"{_BASE}/players?{qs}",
        source_id=SOURCE_ID,
        filename=f"player_search_{name.replace(' ', '_')}_{season}_{team_id}.json",
        raw_root=raw_root,
    )
    return PlayerSearchResult(query_name=name, season=season, snapshot=snapshot, matches=payload.get("response", []))


@dataclass(frozen=True)
class FixtureDepthSample:
    fixture_id: int
    lineups_snapshot: RawSnapshot
    events_snapshot: RawSnapshot
    starting_xi_home: int
    starting_xi_away: int
    substitution_events: int
    card_events: int
    penalty_events: int
    goal_events: int


def sample_fixture_depth(fixture_id: int, budget: RequestBudget, raw_root: Path = DEFAULT_RAW_ROOT) -> FixtureDepthSample:
    """Two calls (lineups + events) per fixture. Caller is responsible for keeping the
    sample size within the remaining daily budget."""
    lineups_content, lineups_payload = _call("fixtures/lineups", {"fixture": fixture_id}, budget)
    lineups_snapshot = write_snapshot(
        content=lineups_content,
        url=f"{_BASE}/fixtures/lineups?fixture={fixture_id}",
        source_id=SOURCE_ID,
        filename=f"lineups_{fixture_id}.json",
        raw_root=raw_root,
    )
    events_content, events_payload = _call("fixtures/events", {"fixture": fixture_id}, budget)
    events_snapshot = write_snapshot(
        content=events_content,
        url=f"{_BASE}/fixtures/events?fixture={fixture_id}",
        source_id=SOURCE_ID,
        filename=f"events_{fixture_id}.json",
        raw_root=raw_root,
    )

    lineups_response = lineups_payload.get("response", [])
    starting_counts = [len(team.get("startXI", [])) for team in lineups_response]
    while len(starting_counts) < 2:
        starting_counts.append(0)

    events_response = events_payload.get("response", [])

    def event_type_count(type_name: str) -> int:
        return sum(1 for e in events_response if e.get("type") == type_name)

    penalty_events = sum(
        1 for e in events_response if e.get("type") == "Goal" and e.get("detail") == "Penalty"
    )

    return FixtureDepthSample(
        fixture_id=fixture_id,
        lineups_snapshot=lineups_snapshot,
        events_snapshot=events_snapshot,
        starting_xi_home=starting_counts[0],
        starting_xi_away=starting_counts[1],
        substitution_events=event_type_count("subst"),
        card_events=event_type_count("Card"),
        penalty_events=penalty_events,
        goal_events=sum(1 for e in events_response if e.get("type") == "Goal"),
    )
