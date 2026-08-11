"""Ingestion for football-data.co.uk Serie A match results (free CSV, no auth).

Registered in docs/SOURCE_REGISTER.md as "produzione" / automation permitted (public
CSV download, no ToS restriction on this kind of use). Fields per
https://www.football-data.co.uk/notes.txt.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .snapshot import DEFAULT_RAW_ROOT, RawSnapshot, fetch_and_snapshot

SOURCE_ID = "football_data_co_uk"
_BASE_URL = "https://www.football-data.co.uk/mmz4281/{season_code}/I1.csv"

# Columns we actually rely on downstream; football-data.co.uk adds/reorders odds
# columns across seasons/bookmakers, so we select rather than assume a fixed schema.
REQUIRED_COLUMNS = [
    "Div",
    "Date",
    "HomeTeam",
    "AwayTeam",
    "FTHG",
    "FTAG",
    "FTR",
]
_OPTIONAL_COLUMNS = [
    "Time",
    "HTHG",
    "HTAG",
    "HTR",
    "HS",
    "AS",
    "HST",
    "AST",
    # Pre-match market-average odds (mean across bookmakers, not a single
    # bookmaker's line) -- recovered for docs/CURRENT_TASK.md block 3, an
    # independent cross-check/input for team strength alongside Dixon-Coles.
    "AvgH",
    "AvgD",
    "AvgA",
]


@dataclass(frozen=True)
class StagedMatchResults:
    season_code: str
    snapshot: RawSnapshot
    frame: "pd.DataFrame"


def fetch_season(season_code: str, raw_root: Path = DEFAULT_RAW_ROOT) -> RawSnapshot:
    """Fetch and snapshot one Serie A season. `season_code` is e.g. '2425' for 2024/25."""
    url = _BASE_URL.format(season_code=season_code)
    return fetch_and_snapshot(
        url=url,
        source_id=SOURCE_ID,
        filename=f"serie_a_{season_code}.csv",
        raw_root=raw_root,
    )


def parse_snapshot(snapshot: RawSnapshot, season_code: str) -> StagedMatchResults:
    """Parse a raw snapshot into a typed staged frame. Raises if required columns
    are missing rather than silently dropping rows/columns."""
    raw_bytes = Path(snapshot.content_path).read_bytes()
    frame = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8-sig")

    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(
            f"football-data.co.uk snapshot {snapshot.content_path} is missing required "
            f"columns {missing}; got columns {list(frame.columns)}"
        )

    keep = REQUIRED_COLUMNS + [c for c in _OPTIONAL_COLUMNS if c in frame.columns]
    frame = frame[keep].copy()
    frame = frame.dropna(subset=["Date", "HomeTeam", "AwayTeam"])
    frame["Date"] = pd.to_datetime(frame["Date"], dayfirst=True, errors="raise")
    frame["source_id"] = SOURCE_ID
    frame["source_file_hash"] = snapshot.sha256
    frame["ingested_time"] = snapshot.retrieved_at

    return StagedMatchResults(season_code=season_code, snapshot=snapshot, frame=frame)


def write_staged_csv(staged: StagedMatchResults, staged_root: Path = Path("data/staged")) -> Path:
    out_dir = staged_root / SOURCE_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"serie_a_{staged.season_code}.csv"
    staged.frame.to_csv(out_path, index=False)
    return out_path
