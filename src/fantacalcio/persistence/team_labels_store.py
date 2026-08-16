"""Friendly per-team display labels (docs/CURRENT_TASK.md, M4 slice 7).

Purely cosmetic: `team_id` (team_01..team_NN) remains the only key the domain
layer/ledger ever uses -- CLAUDE.md's entity-resolution rule ("never join
players or teams only by display name") applies here too, so a label is never
used as a key, only as a label attached to the real id for the UI. No real
participant names are in this repo yet (private_participants/ is empty); this
lets the user set their own memorable label locally without waiting for that.

`config/team_labels.v1.yaml` (versioned, unlike `data/local/ledger.sqlite3`
which is gitignored) holds the real team names so they survive a redeploy on
ephemeral storage, e.g. Streamlit Community Cloud (ADR-2026-049): the
container starts with an empty database every time, so `seed_missing_labels`
re-populates it from the config file on each app start. It only ever fills in
a label that's still empty -- a manual rename already saved in this session's
database always wins, never silently overwritten by the config file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

DEFAULT_DB_PATH = Path("data/local/ledger.sqlite3")
DEFAULT_CONFIG_PATH = Path("config/team_labels.v1.yaml")

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


def load_labels_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping of team_id -> label, got {type(data).__name__}")
    return {str(k): str(v) for k, v in data.items()}


def seed_missing_labels(conn: sqlite3.Connection, mapping: dict[str, str]) -> list[str]:
    """Fills in a label only for a `team_id` that has none yet. Never overwrites
    an existing label (manual or previously seeded). Returns the list of
    `team_id`s actually seeded, for callers that want to report what changed."""
    existing = get_all_labels(conn)
    seeded = []
    for team_id, label in mapping.items():
        if not existing.get(team_id):
            set_label(conn, team_id, label)
            seeded.append(team_id)
    return seeded


def display_name(team_id: str, labels: dict[str, str]) -> str:
    """`team_01` -> `team_01` if unlabeled, `"Nome scelto" (team_01)` if labeled --
    the real id stays visible so it's never ambiguous which underlying team a
    label refers to."""
    label = labels.get(team_id)
    return f"{label} ({team_id})" if label else team_id
