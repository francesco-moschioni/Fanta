"""SQLite-backed append-only auction event ledger (docs/CURRENT_TASK.md, M4 slice 2).

Per ADR-2026-008: SQLite for the live ledger's transactional writes (DuckDB is
reserved for read-heavy analytical tables like `player_table.py`). This module
never UPDATEs or DELETEs an event row -- undo/correction happen the same way
they do in `src/fantacalcio/domain.py`: by appending a new `VoidEvent`, never by
mutating history. Row serialization reuses `src/fantacalcio/ledger_io.py`'s
`event_to_dict`/`event_from_dict` so the on-disk event schema has exactly one
definition, not one per storage backend.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..config import ConfigError, Ruleset
from ..domain import DomainError, Event, LeagueState, effective_events, replay
from ..ledger_io import LedgerIOError, event_from_dict, event_to_dict, import_ledger_json_text

DEFAULT_DB_PATH = Path("data/local/ledger.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_json TEXT NOT NULL,
    appended_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """`check_same_thread=False`: callers (the Streamlit UI) cache this connection
    across script reruns via `st.cache_resource`, and Streamlit's rerun model can
    execute different reruns on different worker threads. This is a local,
    single-user app with no concurrent writers, so relaxing sqlite3's default
    same-thread restriction is safe here."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def append_event(conn: sqlite3.Connection, event: Event) -> None:
    """Appends one event row. Never updates or deletes existing rows -- an
    event_id collision is a real error (duplicate append), not something to
    silently overwrite, matching `domain.replay()`'s own duplicate-id check."""
    payload = json.dumps(event_to_dict(event), ensure_ascii=False)
    try:
        conn.execute("INSERT INTO events (event_id, event_json) VALUES (?, ?)", (event.event_id, payload))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"event_id {event.event_id!r} already exists in the ledger") from exc


def load_events(conn: sqlite3.Connection) -> list[Event]:
    """Returns every event in append (seq) order -- the order `domain.replay()`
    requires for deterministic reconstruction."""
    rows = conn.execute("SELECT event_json FROM events ORDER BY seq ASC").fetchall()
    return [event_from_dict(json.loads(row[0])) for row in rows]


def load_league_state(conn: sqlite3.Connection, ruleset: Ruleset) -> LeagueState:
    """Full audit-trail replay: voided/corrected events' effects remain applied
    (see domain.py's replay() docstring and effective_events()). Use this for a
    complete history view, not for "what's true right now" UI display."""
    return replay(ruleset, load_events(conn))


def load_current_league_state(conn: sqlite3.Connection, ruleset: Ruleset) -> LeagueState:
    """The "current" view a UI should display: voided/corrected assignments are
    excluded before replay, so budget/roster reflect what's actually still true."""
    return replay(ruleset, effective_events(load_events(conn)))


class SeedFromSecretsError(ValueError):
    """Raised when a `ledger_seed_json` secret exists but cannot be applied
    (malformed JSON, or would violate a domain invariant if appended)."""


def seed_missing_events_from_secrets(conn: sqlite3.Connection, ruleset: Ruleset, seed_json_text: str | None) -> int:
    """Idempotent, additive seeding for Streamlit Community Cloud's ephemeral
    storage (ADR-2026-048/049/059): reads a ledger export from `st.secrets`
    (set once, by hand, in the Cloud dashboard -- never committed to git,
    never something this assistant can do on the user's behalf) and appends
    only the events not already present (by event_id), so calling this on
    every page load/container restart is always safe and never re-inserts
    duplicates. `seed_json_text=None`/empty is a no-op (local runs with no
    secret configured). Raises `SeedFromSecretsError` if the secret exists
    but is malformed or would break a domain invariant -- never silently
    drops a bad seed, since that would look like "everything's fine" when
    the auction data is actually missing."""
    if not seed_json_text:
        return 0
    try:
        incoming = import_ledger_json_text(seed_json_text)
    except LedgerIOError as exc:
        raise SeedFromSecretsError(f"Secret ledger_seed_json non è un ledger JSON valido: {exc}") from exc

    existing = load_events(conn)
    existing_ids = {e.event_id for e in existing}
    new_events = [e for e in incoming if e.event_id not in existing_ids]
    if not new_events:
        return 0

    try:
        replay(ruleset, existing + new_events)
    except (DomainError, ConfigError) as exc:
        raise SeedFromSecretsError(f"Il seed da secrets violerebbe un invariante del ledger: {exc}") from exc

    for event in new_events:
        append_event(conn, event)
    return len(new_events)


def seed_missing_events_from_streamlit_secrets(conn: sqlite3.Connection, ruleset: Ruleset) -> int:
    """Same as `seed_missing_events_from_secrets`, reading the `ledger_seed_json`
    key from `st.secrets` (import kept local: this module has no other
    Streamlit dependency, and stays importable/testable without it installed).
    Returns 0 silently if secrets aren't configured at all (local runs) --
    that's the expected, non-error case, not a malformed seed."""
    try:
        import streamlit as st

        seed_json_text = st.secrets.get("ledger_seed_json")
    except Exception:
        seed_json_text = None
    return seed_missing_events_from_secrets(conn, ruleset, seed_json_text)
