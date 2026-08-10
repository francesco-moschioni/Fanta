"""Ingestion for OpenFootball Serie A fixtures/results (CC0, no auth).

Registered in docs/SOURCE_REGISTER.md as "produzione". Source repo:
https://github.com/openfootball/football.json (CC0-licensed).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .snapshot import DEFAULT_RAW_ROOT, RawSnapshot, fetch_and_snapshot

SOURCE_ID = "openfootball"
_BASE_URL = "https://raw.githubusercontent.com/openfootball/football.json/master/{season}/it.1.json"

_REQUIRED_KEYS = {"round", "date", "team1", "team2"}


def _extract_full_time(score: object) -> list | None:
    """OpenFootball's `score` field is inconsistent across records: it is either
    absent/None (unplayed match), a {"ht": [...], "ft": [...]} mapping, or a bare
    [home, away] list when only the full-time score is known. Handle all three
    explicitly; anything else fails loudly rather than being silently coerced."""
    if score is None:
        return None
    if isinstance(score, dict):
        return score.get("ft")
    if isinstance(score, list) and len(score) == 2:
        return score
    raise ValueError(f"Unrecognized OpenFootball 'score' shape: {score!r}")


@dataclass(frozen=True)
class StagedFixtures:
    season: str
    snapshot: RawSnapshot
    frame: "pd.DataFrame"


def fetch_season(season: str, raw_root: Path = DEFAULT_RAW_ROOT) -> RawSnapshot:
    """Fetch and snapshot one Serie A season. `season` is e.g. '2024-25'."""
    url = _BASE_URL.format(season=season)
    return fetch_and_snapshot(
        url=url,
        source_id=SOURCE_ID,
        filename=f"serie_a_{season}.json",
        raw_root=raw_root,
    )


def parse_snapshot(snapshot: RawSnapshot, season: str) -> StagedFixtures:
    raw_bytes = Path(snapshot.content_path).read_bytes()
    payload = json.loads(raw_bytes)

    matches = payload.get("matches")
    if not isinstance(matches, list) or not matches:
        raise ValueError(
            f"OpenFootball snapshot {snapshot.content_path} has no usable 'matches' list"
        )

    rows = []
    for i, m in enumerate(matches):
        missing = _REQUIRED_KEYS - m.keys()
        if missing:
            raise ValueError(
                f"OpenFootball snapshot {snapshot.content_path} match[{i}] missing keys "
                f"{missing}: {m}"
            )
        ft = _extract_full_time(m.get("score"))
        rows.append(
            {
                "round": m["round"],
                "date": m["date"],
                "team1": m["team1"],
                "team2": m["team2"],
                "ft_home": ft[0] if ft else None,
                "ft_away": ft[1] if ft else None,
                "played": ft is not None,
            }
        )

    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["source_id"] = SOURCE_ID
    frame["source_file_hash"] = snapshot.sha256
    frame["ingested_time"] = snapshot.retrieved_at

    return StagedFixtures(season=season, snapshot=snapshot, frame=frame)


def write_staged_csv(staged: StagedFixtures, staged_root: Path = Path("data/staged")) -> Path:
    out_dir = staged_root / SOURCE_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"serie_a_{staged.season}.csv"
    staged.frame.to_csv(out_path, index=False)
    return out_path
