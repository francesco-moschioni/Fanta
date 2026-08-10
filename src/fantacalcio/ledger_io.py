"""Local import/export for the auction event ledger.

The JSON event log is the single source of truth and the only format that supports
replay. CSV export is a derived, human-readable snapshot for manual inspection only.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .domain import AssignmentEvent, AssignmentItem, Event, Role, VoidEvent


class LedgerIOError(ValueError):
    """Raised when ledger JSON/CSV content is missing, malformed, or unparseable."""


def event_to_dict(event: Event) -> dict[str, Any]:
    if isinstance(event, AssignmentEvent):
        return {
            "type": "assignment",
            "event_id": event.event_id,
            "ts": event.ts,
            "round_id": event.round_id,
            "team_id": event.team_id,
            "pool_id": event.pool_id,
            "role": event.role.value,
            "player_ids": list(event.item.player_ids),
            "amount": event.amount,
            "source": event.source,
            "author": event.author,
            "corrects": event.corrects,
        }
    if isinstance(event, VoidEvent):
        return {
            "type": "void",
            "event_id": event.event_id,
            "ts": event.ts,
            "voids": event.voids,
            "author": event.author,
            "reason": event.reason,
        }
    raise LedgerIOError(f"Unknown event type: {type(event)!r}")


def event_from_dict(d: dict[str, Any]) -> Event:
    if not isinstance(d, dict):
        raise LedgerIOError(f"Ledger event must be a mapping, got {type(d).__name__}")
    kind = d.get("type")
    try:
        if kind == "assignment":
            return AssignmentEvent(
                event_id=d["event_id"],
                ts=d["ts"],
                round_id=d["round_id"],
                team_id=d["team_id"],
                pool_id=d["pool_id"],
                role=Role(d["role"]),
                item=AssignmentItem(player_ids=tuple(d["player_ids"])),
                amount=d["amount"],
                source=d["source"],
                author=d["author"],
                corrects=d.get("corrects"),
            )
        if kind == "void":
            return VoidEvent(
                event_id=d["event_id"],
                ts=d["ts"],
                voids=d["voids"],
                author=d["author"],
                reason=d["reason"],
            )
    except KeyError as exc:
        raise LedgerIOError(f"Ledger event of type {kind!r} is missing field {exc}") from exc
    raise LedgerIOError(f"Unknown ledger event type: {kind!r}")


def export_ledger_json(events: list[Event], path: str | Path) -> None:
    path = Path(path)
    payload = [event_to_dict(e) for e in events]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def import_ledger_json(path: str | Path) -> list[Event]:
    path = Path(path)
    if not path.is_file():
        raise LedgerIOError(f"Ledger file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LedgerIOError(f"Ledger file {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise LedgerIOError(f"Ledger JSON root must be a list of events, got {type(raw).__name__}")
    return [event_from_dict(d) for d in raw]


_CSV_FIELDS = ["team_id", "round_id", "pool_id", "role", "player_ids", "amount", "event_id", "status"]


def export_assignments_csv(events: list[Event], path: str | Path) -> None:
    """Export a flat snapshot of assignments with derived status (valid/corrected/voided).

    Read-only derived view; re-importing this CSV is not supported because it cannot
    reconstruct correction/void relationships or replay order.
    """
    path = Path(path)
    voided: set[str] = set()
    corrected: set[str] = set()
    assignments: list[AssignmentEvent] = []
    for e in events:
        if isinstance(e, VoidEvent):
            voided.add(e.voids)
        elif isinstance(e, AssignmentEvent):
            if e.corrects:
                corrected.add(e.corrects)
            assignments.append(e)
        else:
            raise LedgerIOError(f"Unknown event type: {type(e)!r}")

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for e in assignments:
            status = "valid"
            if e.event_id in voided:
                status = "voided"
            elif e.event_id in corrected:
                status = "corrected"
            writer.writerow(
                {
                    "team_id": e.team_id,
                    "round_id": e.round_id,
                    "pool_id": e.pool_id,
                    "role": e.role.value,
                    "player_ids": "|".join(e.item.player_ids),
                    "amount": e.amount,
                    "event_id": e.event_id,
                    "status": status,
                }
            )
