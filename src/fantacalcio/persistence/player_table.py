"""DuckDB-backed player forecast table for the UI (docs/CURRENT_TASK.md, M4 slice 1).

Per ADR-2026-008: DuckDB for columnar reads over immutable analytical snapshots
(this table), SQLite reserved for the live auction ledger's transactional writes
(a later M4 slice, not this one). This module only ever reads the already-computed
`_m3_replacement_values.csv` (Monte Carlo + VAR + round pools + data quality tier,
scripts/run_m3_replacement_values.py) -- no modeling logic lives here, per
CLAUDE.md's "all scoring/assignment/... deterministic code" rule: the UI layer
displays what the domain layer already computed, it never recomputes it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

SOURCE_CSV = Path("data/staged/fantacalcio_voti_manual/_m3_replacement_values.csv")
DEFAULT_DB_PATH = Path("data/local/fantacalcio.duckdb")

REQUIRED_COLUMNS = [
    "player_code",
    "display_name",
    "role",
    "team_name",
    "quotazione_asta",
    "sim_mean",
    "sim_median",
    "sim_p10",
    "sim_p90",
    "player_games_in_pool",
    "used_role_pool_only",
    "replacement_level",
    "var_mean",
    "var_p10",
    "var_p90",
    "degenerate_replacement",
    "data_quality_tier",
    "round_pool",
    "list_pool_name",
    "list_state",
    "participation_rate",
    "participation_season",
    "participation_seasons_of_history",
]


@dataclass(frozen=True)
class BuildResult:
    db_path: Path
    n_players: int
    source_path: Path
    source_sha256: str
    source_generated_at: str
    built_at: str


def build_player_table(source_csv: Path = SOURCE_CSV, db_path: Path = DEFAULT_DB_PATH) -> BuildResult:
    """Rebuilds the DuckDB `players` table from the source CSV, plus a `meta`
    table recording provenance (source path/hash, build timestamp) -- per
    CLAUDE.md's "every feature must have an as_of/provenance definition" rule,
    the UI must never show this data without saying when/from-what it was built.

    `source_generated_at` (the CSV's own mtime) is tracked separately from
    `built_at` (when this function ran): a data-quality audit found the UI only
    showed the latter, which can be much later than when the underlying Monte
    Carlo/replacement-value calculation actually ran -- e.g. after an unrelated
    DuckDB rebuild that re-reads an unchanged CSV."""
    if not source_csv.is_file():
        raise FileNotFoundError(
            f"{source_csv} not found. Run scripts/run_monte_carlo_fantavoto.py then "
            "scripts/run_m3_replacement_values.py first."
        )
    df = pd.read_csv(source_csv)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{source_csv} is missing required columns {missing}; got {list(df.columns)}")

    source_sha256 = hashlib.sha256(source_csv.read_bytes()).hexdigest()
    source_generated_at = datetime.fromtimestamp(source_csv.stat().st_mtime, tz=timezone.utc).isoformat()
    built_at = datetime.now(timezone.utc).isoformat()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("CREATE OR REPLACE TABLE players AS SELECT * FROM df")
        conn.execute("CREATE OR REPLACE TABLE meta (key VARCHAR, value VARCHAR)")
        conn.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [
                ("source_path", str(source_csv)),
                ("source_sha256", source_sha256),
                ("source_generated_at", source_generated_at),
                ("built_at", built_at),
                ("n_players", str(len(df))),
            ],
        )
    finally:
        conn.close()

    return BuildResult(
        db_path=db_path,
        n_players=len(df),
        source_path=source_csv,
        source_sha256=source_sha256,
        source_generated_at=source_generated_at,
        built_at=built_at,
    )


def connect(db_path: Path = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    if not db_path.is_file():
        raise FileNotFoundError(f"{db_path} not found. Run scripts/build_player_table.py first.")
    return duckdb.connect(str(db_path), read_only=True)


def get_build_meta(conn: duckdb.DuckDBPyConnection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM meta").fetchall()
    return dict(rows)


def search_players(
    conn: duckdb.DuckDBPyConnection,
    name_query: str | None = None,
    role: str | None = None,
    team_name: str | None = None,
    round_pool: str | None = None,
    data_quality_tier: str | None = None,
) -> pd.DataFrame:
    """All filters are optional and additive (AND). `name_query` is a
    case-insensitive substring match on `display_name`."""
    clauses = []
    params: list = []
    if name_query:
        clauses.append("lower(display_name) LIKE ?")
        params.append(f"%{name_query.lower()}%")
    if role:
        clauses.append("role = ?")
        params.append(role)
    if team_name:
        clauses.append("team_name = ?")
        params.append(team_name)
    if round_pool:
        clauses.append("round_pool = ?")
        params.append(round_pool)
    if data_quality_tier:
        clauses.append("data_quality_tier = ?")
        params.append(data_quality_tier)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT * FROM players {where} ORDER BY var_mean DESC"
    return conn.execute(query, params).df()


def get_player(conn: duckdb.DuckDBPyConnection, player_code: int) -> pd.Series | None:
    result = conn.execute("SELECT * FROM players WHERE player_code = ?", [player_code]).df()
    if result.empty:
        return None
    return result.iloc[0]


def distinct_values(conn: duckdb.DuckDBPyConnection, column: str) -> list[str]:
    if column not in REQUIRED_COLUMNS:
        raise ValueError(f"{column!r} is not a filterable column")
    rows = conn.execute(f"SELECT DISTINCT {column} FROM players ORDER BY {column}").fetchall()
    return [r[0] for r in rows]
