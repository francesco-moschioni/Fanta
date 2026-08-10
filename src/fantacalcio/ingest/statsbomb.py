"""Ingestion for StatsBomb Open Data (CC-BY-NC 4.0-style attribution licence, no auth).

Registered in docs/SOURCE_REGISTER.md as "R&D" tier. Covers Serie A 2015/16
(competition_id=12, season_id=27) among other competitions/seasons. Used here as a
free, no-account benchmark for lineup/event data quality, not as the live current-
season provider (StatsBomb's open tranche does not include recent seasons).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .snapshot import DEFAULT_RAW_ROOT, RawSnapshot, fetch_and_snapshot

SOURCE_ID = "statsbomb_open_data"
_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

SERIE_A_2015_16 = {"competition_id": 12, "season_id": 27}

_REQUIRED_MATCH_KEYS = {"match_id", "match_date", "home_team", "away_team", "home_score", "away_score"}


@dataclass(frozen=True)
class StagedMatches:
    competition_id: int
    season_id: int
    snapshot: RawSnapshot
    frame: "pd.DataFrame"


def fetch_matches(competition_id: int, season_id: int, raw_root: Path = DEFAULT_RAW_ROOT) -> RawSnapshot:
    url = f"{_BASE}/matches/{competition_id}/{season_id}.json"
    return fetch_and_snapshot(
        url=url,
        source_id=SOURCE_ID,
        filename=f"matches_{competition_id}_{season_id}.json",
        raw_root=raw_root,
    )


def parse_matches_snapshot(snapshot: RawSnapshot, competition_id: int, season_id: int) -> StagedMatches:
    raw = json.loads(Path(snapshot.content_path).read_bytes())
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"StatsBomb matches snapshot {snapshot.content_path} has no usable match list")

    rows = []
    for i, m in enumerate(raw):
        missing = _REQUIRED_MATCH_KEYS - m.keys()
        if missing:
            raise ValueError(
                f"StatsBomb matches snapshot {snapshot.content_path} match[{i}] missing keys {missing}"
            )
        rows.append(
            {
                "match_id": m["match_id"],
                "date": m["match_date"],
                "home_team": m["home_team"]["home_team_name"],
                "away_team": m["away_team"]["away_team_name"],
                "home_score": m["home_score"],
                "away_score": m["away_score"],
                "match_status": m.get("match_status"),
            }
        )

    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["source_id"] = SOURCE_ID
    frame["source_file_hash"] = snapshot.sha256
    frame["ingested_time"] = snapshot.retrieved_at

    return StagedMatches(competition_id=competition_id, season_id=season_id, snapshot=snapshot, frame=frame)


def write_staged_csv(staged: StagedMatches, staged_root: Path = Path("data/staged")) -> Path:
    out_dir = staged_root / SOURCE_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"matches_{staged.competition_id}_{staged.season_id}.csv"
    staged.frame.to_csv(out_path, index=False)
    return out_path


@dataclass(frozen=True)
class MatchDepthSample:
    match_id: int
    events_snapshot: RawSnapshot
    lineups_snapshot: RawSnapshot
    starting_xi_home: int
    starting_xi_away: int
    substitution_events: int
    card_events: int
    penalty_events: int
    goal_events: int


def sample_match_depth(match_id: int, raw_root: Path = DEFAULT_RAW_ROOT) -> MatchDepthSample:
    """Fetch one match's events+lineups and count key event types, as a field-coverage
    probe (does this provider actually carry subs/cards/penalties, not just the score)."""
    events_snapshot = fetch_and_snapshot(
        url=f"{_BASE}/events/{match_id}.json",
        source_id=SOURCE_ID,
        filename=f"events_{match_id}.json",
        raw_root=raw_root,
    )
    lineups_snapshot = fetch_and_snapshot(
        url=f"{_BASE}/lineups/{match_id}.json",
        source_id=SOURCE_ID,
        filename=f"lineups_{match_id}.json",
        raw_root=raw_root,
    )

    events = json.loads(Path(events_snapshot.content_path).read_bytes())
    lineups = json.loads(Path(lineups_snapshot.content_path).read_bytes())

    return _compute_depth_metrics(match_id, events, lineups, events_snapshot, lineups_snapshot)


def _compute_depth_metrics(
    match_id: int,
    events: list[dict],
    lineups: list[dict],
    events_snapshot: RawSnapshot,
    lineups_snapshot: RawSnapshot,
) -> MatchDepthSample:
    def event_type_count(type_name: str) -> int:
        return sum(1 for e in events if e.get("type", {}).get("name") == type_name)

    starting_counts = []
    for team in lineups:
        starting = sum(
            1
            for p in team.get("lineup", [])
            if any(pos.get("start_reason") == "Starting XI" for pos in p.get("positions", []))
        )
        starting_counts.append(starting)
    while len(starting_counts) < 2:
        starting_counts.append(0)

    penalty_events = sum(
        1
        for e in events
        if e.get("type", {}).get("name") == "Shot" and (e.get("shot") or {}).get("type", {}).get("name") == "Penalty"
    )

    # A card is a `card` sub-field on a "Foul Committed" or "Bad Behaviour" event, not
    # every foul: most fouls carry no card at all (verified against real match data,
    # 2026-08-10 — an earlier version of this counted all fouls, wildly overstating cards).
    card_events = sum(
        1
        for e in events
        if e.get("type", {}).get("name") in ("Foul Committed", "Bad Behaviour")
        and (e.get("foul_committed") or e.get("bad_behaviour") or {}).get("card") is not None
    )

    return MatchDepthSample(
        match_id=match_id,
        events_snapshot=events_snapshot,
        lineups_snapshot=lineups_snapshot,
        starting_xi_home=starting_counts[0],
        starting_xi_away=starting_counts[1],
        substitution_events=event_type_count("Substitution"),
        card_events=card_events,
        penalty_events=penalty_events,
        goal_events=sum(
            1
            for e in events
            if e.get("type", {}).get("name") == "Shot"
            and (e.get("shot") or {}).get("outcome", {}).get("name") == "Goal"
        ),
    )
