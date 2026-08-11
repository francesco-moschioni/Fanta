"""Player locks: pre-auction planning targets, distinct from the real ledger
(docs/CURRENT_TASK.md, M4 slice 5).

A lock is *intent*, not an auction outcome -- CLAUDE.md: "Distingui sempre
acquistato da ipotetico." It lives in its own SQLite table (same database file
as the ledger, ADR-2026-008, but a separate table) and never enters
`domain.replay()`: locking/unlocking a player has zero effect on budget,
roster, or any deterministic auction state. It is purely a UI-facing wishlist,
gated by `src/fantacalcio/auction/lock_feasibility.py`'s checks before being
written here (CLAUDE.md: "Locked players remain locked. If infeasible, explain
the conflicting constraint...") -- this module itself does not validate,
it only persists what the caller already decided is feasible.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path("data/local/ledger.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS locks (
    team_id TEXT NOT NULL,
    player_code INTEGER NOT NULL,
    role TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    locked_at TEXT NOT NULL,
    PRIMARY KEY (team_id, player_code)
);
"""


@dataclass(frozen=True)
class LockedPlayer:
    team_id: str
    player_code: int
    role: str
    note: str
    locked_at: str


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def add_lock(conn: sqlite3.Connection, team_id: str, player_code: int, role: str, note: str = "") -> None:
    locked_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    conn.execute(
        "INSERT OR REPLACE INTO locks (team_id, player_code, role, note, locked_at) VALUES (?, ?, ?, ?, ?)",
        (team_id, player_code, role, note, locked_at),
    )
    conn.commit()


def remove_lock(conn: sqlite3.Connection, team_id: str, player_code: int) -> None:
    conn.execute("DELETE FROM locks WHERE team_id = ? AND player_code = ?", (team_id, player_code))
    conn.commit()


def list_locks(conn: sqlite3.Connection, team_id: str | None = None) -> list[LockedPlayer]:
    if team_id is not None:
        rows = conn.execute(
            "SELECT team_id, player_code, role, note, locked_at FROM locks WHERE team_id = ? ORDER BY locked_at",
            (team_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT team_id, player_code, role, note, locked_at FROM locks ORDER BY locked_at"
        ).fetchall()
    return [LockedPlayer(*row) for row in rows]


def is_locked(conn: sqlite3.Connection, team_id: str, player_code: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM locks WHERE team_id = ? AND player_code = ?", (team_id, player_code)
    ).fetchone()
    return row is not None
