"""G2 sealed-bid envelope drafts: pre-auction planning for the 5 banded lists of
G2 (3 midfielder bands + 2 forward bands, ADR-2026-060), distinct from the real
ledger exactly like `locks_store.py` -- CLAUDE.md: "Distingui sempre acquistato
da ipotetico." Saving a draft pick here never touches `domain.replay()` or
budget/roster state; it is a UI-facing worksheet, validated by
`src/fantacalcio/auction/g2_envelope_feasibility.py` before being written here
(this module itself does not validate).

One row = one player picked as a preference within one team's envelope for one
band (`list_pool_name`, e.g. "midfielders_top_1_20"). `preference_rank` (1-6)
encodes the G2 resolution order (preference rank first, then bid amount, per
`config/auction_rules.v1.yaml`).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path("data/local/ledger.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS g2_envelope_picks (
    team_id TEXT NOT NULL,
    list_pool_name TEXT NOT NULL,
    player_code INTEGER NOT NULL,
    role TEXT NOT NULL,
    preference_rank INTEGER NOT NULL,
    bid_amount INTEGER NOT NULL,
    saved_at TEXT NOT NULL,
    PRIMARY KEY (team_id, list_pool_name, player_code)
);
"""


@dataclass(frozen=True)
class EnvelopePick:
    team_id: str
    list_pool_name: str
    player_code: int
    role: str
    preference_rank: int
    bid_amount: int
    saved_at: str


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def save_pick(
    conn: sqlite3.Connection,
    team_id: str,
    list_pool_name: str,
    player_code: int,
    role: str,
    preference_rank: int,
    bid_amount: int,
) -> None:
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    conn.execute(
        "INSERT OR REPLACE INTO g2_envelope_picks "
        "(team_id, list_pool_name, player_code, role, preference_rank, bid_amount, saved_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (team_id, list_pool_name, player_code, role, preference_rank, bid_amount, saved_at),
    )
    conn.commit()


def remove_pick(conn: sqlite3.Connection, team_id: str, list_pool_name: str, player_code: int) -> None:
    conn.execute(
        "DELETE FROM g2_envelope_picks WHERE team_id = ? AND list_pool_name = ? AND player_code = ?",
        (team_id, list_pool_name, player_code),
    )
    conn.commit()


def list_picks(
    conn: sqlite3.Connection, team_id: str, list_pool_name: str | None = None
) -> list[EnvelopePick]:
    if list_pool_name is not None:
        rows = conn.execute(
            "SELECT team_id, list_pool_name, player_code, role, preference_rank, bid_amount, saved_at "
            "FROM g2_envelope_picks WHERE team_id = ? AND list_pool_name = ? ORDER BY preference_rank",
            (team_id, list_pool_name),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT team_id, list_pool_name, player_code, role, preference_rank, bid_amount, saved_at "
            "FROM g2_envelope_picks WHERE team_id = ? ORDER BY list_pool_name, preference_rank",
            (team_id,),
        ).fetchall()
    return [EnvelopePick(*row) for row in rows]
