"""Friendly per-team display labels (docs/CURRENT_TASK.md, M4 slice 7).

Purely cosmetic: `team_id` (team_01..team_NN) remains the only key the domain
layer/ledger ever uses -- CLAUDE.md's entity-resolution rule ("never join
players or teams only by display name") applies here too, so a label is never
used as a key, only as a label attached to the real id for the UI. No real
participant names are in this repo yet (private_participants/ is empty); this
lets the user set their own memorable label locally without waiting for that.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("data/local/ledger.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS team_labels (
    team_id TEXT PRIMARY KEY,
    label TEXT NOT NULL
);
"""


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def set_label(conn: sqlite3.Connection, team_id: str, label: str) -> None:
    conn.execute("INSERT OR REPLACE INTO team_labels (team_id, label) VALUES (?, ?)", (team_id, label))
    conn.commit()


def get_label(conn: sqlite3.Connection, team_id: str) -> str | None:
    row = conn.execute("SELECT label FROM team_labels WHERE team_id = ?", (team_id,)).fetchone()
    return row[0] if row else None


def get_all_labels(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT team_id, label FROM team_labels").fetchall()
    return dict(rows)


def display_name(team_id: str, labels: dict[str, str]) -> str:
    """`team_01` -> `team_01` if unlabeled, `"Nome scelto" (team_01)` if labeled --
    the real id stays visible so it's never ambiguous which underlying team a
    label refers to."""
    label = labels.get(team_id)
    return f"{label} ({team_id})" if label else team_id
