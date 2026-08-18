"""Backfill the missing custom-logo BudgetAdjustmentEvents.

Discovered while importing G2 results (2026-08-18): cross-checking the G2
recap's own totals against each team's known G1 spend shows every one of the
20 teams' implied G1 budget was 203 (200 + 3), not just team_01's -- but the
ledger only ever recorded the +3 `custom_logo_bonus` adjustment for team_01
(ADR-2026-013's postilla admin). This backfills the other 19.

Usage:
    python scripts/backfill_logo_bonus_all_teams.py [--yes]
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fantacalcio.config import ConfigError, load_ruleset
from fantacalcio.domain import BudgetAdjustmentEvent, DomainError, replay
from fantacalcio.persistence import ledger_store

REASON = "custom_logo_bonus"
AUTHOR = "utente"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    ruleset = load_ruleset(Path("config/auction_rules.v1.yaml"))
    ledger_conn = ledger_store.connect()
    existing_events = ledger_store.load_events(ledger_conn)

    already_bonused = {
        e.team_id for e in existing_events
        if isinstance(e, BudgetAdjustmentEvent) and e.reason == REASON
    }
    missing = [f"team_{i:02d}" for i in range(1, 21) if f"team_{i:02d}" not in already_bonused]
    print(f"{len(already_bonused)} squadre già con bonus logo: {sorted(already_bonused)}")
    print(f"{len(missing)} squadre da correggere: {missing}")

    candidates = [
        BudgetAdjustmentEvent(
            event_id=uuid.uuid4().hex,
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            round_id="G1",
            team_id=team_id,
            amount=3,
            reason=REASON,
            author=AUTHOR,
        )
        for team_id in missing
    ]

    try:
        replay(ruleset, existing_events + candidates)
    except (DomainError, ConfigError) as exc:
        print(f"REPLAY FALLITO, nessuna scrittura effettuata: {exc}")
        return 1
    print("Replay OK.")

    if not args.yes:
        print("DRY-RUN: rilancia con --yes per scrivere.")
        return 0

    for c in candidates:
        ledger_store.append_event(ledger_conn, c)
    print(f"Scritti {len(candidates)} eventi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
