"""G3 sealed-bid free-choice envelope drafts: pre-auction planning for the
final "busta chiusa senza liste" phase (config `sealed_bid_free`, ADR
docs/CURRENT_TASK.md 2026-08-18) -- distinct from the real ledger exactly like
`g2_envelopes_store.py`/`locks_store.py` (CLAUDE.md: "Distingui sempre
acquistato da ipotetico"). Saving a draft pick here never touches
`domain.replay()` or budget/roster state; it is a UI-facing worksheet,
validated by `src/fantacalcio/auction/g3_envelope_feasibility.py` before being
written here (this module itself does not validate).

Unlike G2's banded lists (preference rank, win at most 1 per band), G3 has no
lists or preference ranking at all: up to `max_players_this_phase` (config)
free player picks, each its own independent sealed bid against the same
player's other bidders -- a team could win all of them. One row = one
candidate player with its bid amount.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path("data/local/ledger.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS g3_envelope_picks (
    team_id TEXT NOT NULL,
    player_code INTEGER NOT NULL,
    role TEXT NOT NULL,
    bid_amount INTEGER NOT NULL,
    saved_at TEXT NOT NULL,
    PRIMARY KEY (team_id, player_code)
);
"""


@dataclass(frozen=True)
class G3EnvelopePick:
    team_id: str
    player_code: int
    role: str
    bid_amount: int
    saved_at: str


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def save_pick(conn: sqlite3.Connection, team_id: str, player_code: int, role: str, bid_amount: int) -> None:
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    conn.execute(
        "INSERT OR REPLACE INTO g3_envelope_picks (team_id, player_code, role, bid_amount, saved_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (team_id, player_code, role, bid_amount, saved_at),
    )
    conn.commit()


def remove_pick(conn: sqlite3.Connection, team_id: str, player_code: int) -> None:
    conn.execute(
        "DELETE FROM g3_envelope_picks WHERE team_id = ? AND player_code = ?",
        (team_id, player_code),
    )
    conn.commit()


def list_picks(conn: sqlite3.Connection, team_id: str) -> list[G3EnvelopePick]:
    rows = conn.execute(
        "SELECT team_id, player_code, role, bid_amount, saved_at FROM g3_envelope_picks "
        "WHERE team_id = ? ORDER BY saved_at",
        (team_id,),
    ).fetchall()
    return [G3EnvelopePick(*row) for row in rows]
