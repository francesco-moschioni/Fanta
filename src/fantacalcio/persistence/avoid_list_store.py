"""Players flagged to avoid: pre-auction warnings, symmetric to
`locks_store.py`'s targets (docs/CURRENT_TASK.md, M4 slice 7).

Same nature as a lock -- pure planning intent, never a ledger/domain event, no
effect on replay(). A separate table (not reusing `locks`) because "avoid"
and "target" are semantically opposite and should never be confusable in a
query; keeping them apart also means a player can't accidentally end up in
both.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path("data/local/ledger.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS avoid_list (
    team_id TEXT NOT NULL,
    player_code INTEGER NOT NULL,
    role TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL,
    PRIMARY KEY (team_id, player_code)
);
"""


@dataclass(frozen=True)
class AvoidedPlayer:
    team_id: str
    player_code: int
    role: str
    reason: str
    added_at: str


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def add_avoid(conn: sqlite3.Connection, team_id: str, player_code: int, role: str, reason: str = "") -> None:
    added_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    conn.execute(
        "INSERT OR REPLACE INTO avoid_list (team_id, player_code, role, reason, added_at) VALUES (?, ?, ?, ?, ?)",
        (team_id, player_code, role, reason, added_at),
    )
    conn.commit()


def remove_avoid(conn: sqlite3.Connection, team_id: str, player_code: int) -> None:
    conn.execute("DELETE FROM avoid_list WHERE team_id = ? AND player_code = ?", (team_id, player_code))
    conn.commit()


def list_avoided(conn: sqlite3.Connection, team_id: str | None = None) -> list[AvoidedPlayer]:
    if team_id is not None:
        rows = conn.execute(
            "SELECT team_id, player_code, role, reason, added_at FROM avoid_list WHERE team_id = ? ORDER BY added_at",
            (team_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT team_id, player_code, role, reason, added_at FROM avoid_list ORDER BY added_at"
        ).fetchall()
    return [AvoidedPlayer(*row) for row in rows]


def is_avoided(conn: sqlite3.Connection, team_id: str, player_code: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM avoid_list WHERE team_id = ? AND player_code = ?", (team_id, player_code)
    ).fetchone()
    return row is not None
