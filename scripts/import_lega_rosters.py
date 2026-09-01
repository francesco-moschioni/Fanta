"""Reconstruct the G3/G4 (+ post-auction) assignments into the ledger from the
league-platform roster export, so the ledger reflects the real pre-riparazione
state (today it stops at G1+G2).

Source: "20lega-rosters-*.xlsx" (see src/fantacalcio/ingest/lega_rosters.py).
20 teams x 23 players, each (name, cost). A trailing "*" = player left Serie A.

Method
------
1. Parse the grid; resolve each platform team name to a `team_id` via
   `ledger.team_labels` (19/20 exact; `team_05` was renamed "Werder Bremer" ->
   "I Have a N'Drim", confirmed by the owner 2026-09-01).
2. Resolve every player display name to a `player_code` against the refreshed
   end-of-market listone: the `Tutti` sheet first, then the `Ceduti` sheet
   (players who left Serie A but still occupy a roster slot), then a small
   explicit fallback for two goalkeepers only in an older listone.
3. The 4 players carried under synthetic negative codes at G2 time
   (ADR-2026-051/064: Molina N. -1, Obrador -2, Spence -3, Schmid -4) now have
   real Fantacalcio.it codes. Their negative code is aliased to the real one so
   the roster line is recognised as already-owned (no duplicate assignment) --
   the ledger history for those 4 is NOT rewritten here (that needs its own
   decision; the replay() correction mechanism double-counts budget in the audit
   view -- see docs/CURRENT_TASK.md follow-ups).
4. For each team: owned = G1+G2 player_ids from the ledger (negatives aliased).
   new = roster player_codes - owned. Every `new` non-goalkeeper line becomes an
   AssignmentEvent in round G3 (G3 and G4 share the pool `remaining_players` and
   a single carried budget `remaining_G2 + 40`, so the G3/G4 split does not
   change any invariant; labelling everything G3 is budget-equivalent).
   Goalkeeper blocks were all set in G1; no G3/G4 GK lines exist in the export,
   so GK reconciliation is out of scope here (2 known GK swaps are flagged, not
   written -- docs/CURRENT_TASK.md).
5. Validate the whole thing via `replay(existing + new)`. Dry-run by default;
   `--yes` appends.

Usage
-----
    python scripts/import_lega_rosters.py <roster.xlsx> <listone.xlsx> [--yes] [--relabel-team05]
"""

from __future__ import annotations

import argparse
import difflib
import sys
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fantacalcio.config import ConfigError, load_ruleset
from fantacalcio.domain import AssignmentEvent, AssignmentItem, DomainError, Role, replay
from fantacalcio.ingest.lega_rosters import parse_roster_file
from fantacalcio.persistence import ledger_store, team_labels_store

ROUND_ID = "G3"
POOL_ID = "remaining_players"
SOURCE = "lega_roster_export_import"
AUTHOR = "utente"

# Synthetic negative code -> real Fantacalcio.it code (new end-of-market listone).
NEGATIVE_ALIAS = {"-1": "4998", "-2": "7329", "-3": "5982", "-4": "7551"}

# team_05 was labelled "Werder Bremer"; the roster export calls it "I Have a N'Drim".
TEAM05_OLD_LABEL = "Werder Bremer"
TEAM05_NEW_LABEL = "I Have a N'Drim"

# Two goalkeepers that are in the ledger (G1 blocks) but no longer resolvable
# against the current listone and not in Ceduti -- older-listone codes, kept so
# the resolver can still see them by name if they appear.
OLD_GK_FALLBACK = {"lolic": ("7466", "P"), "satalino": ("2127", "P")}

_ROLE_MAP = {"P": Role.GK, "D": Role.DEF, "C": Role.MID, "A": Role.FWD}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.lower().replace(".", "").replace("'", " ").replace("-", " ").split("*")[0].strip()


def _load_listone_index(listone_xlsx: Path) -> dict[str, list[tuple[str, str, str, str]]]:
    """norm(name) -> list of (player_code, role_letter, display_name, team_name)
    across the `Tutti` and `Ceduti` sheets of the end-of-market Quotazioni file."""
    wb = openpyxl.load_workbook(listone_xlsx, read_only=True, data_only=True)
    idx: dict[str, list[tuple[str, str, str, str]]] = {}
    for sheet in ("Tutti", "Ceduti"):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        for r in ws.iter_rows(min_row=3, values_only=True):
            if r[0] is None:
                continue
            try:
                code = str(int(r[0]))
            except (TypeError, ValueError):
                continue
            role, name, team = str(r[1]), str(r[3]), str(r[4])
            idx.setdefault(_norm(name), []).append((code, role, name, team))
    wb.close()
    return idx


def _resolve_player(name: str, idx: dict) -> tuple[tuple[str, str] | None, str]:
    """-> ((player_code, role_letter), how) or (None, reason)."""
    n = _norm(name)
    if n in idx:
        hits = idx[n]
        if len(hits) == 1:
            c, role, *_ = hits[0]
            return (c, role), "exact"
        return None, f"AMBIGUOUS x{len(hits)}: {[h[2] + '/' + h[1] for h in hits]}"
    if n in OLD_GK_FALLBACK:
        c, role = OLD_GK_FALLBACK[n]
        return (c, role), "old-listone-gk"
    close = difflib.get_close_matches(n, list(idx), n=3, cutoff=0.86)
    if len(close) == 1 and len(idx[close[0]]) == 1:
        c, role, *_ = idx[close[0]][0]
        ratio = difflib.SequenceMatcher(None, n, close[0]).ratio()
        return (c, role), f"fuzzy~{ratio:.2f}"
    return None, f"NO-MATCH (close: {close})" if close else "NO-MATCH"


def _resolve_team_id(name: str, labels: dict[str, str]) -> str | None:
    target = _norm(name)
    squash = lambda s: "".join(ch for ch in _norm(s) if ch.isalnum())
    for tid, lab in labels.items():
        if _norm(lab) == target or squash(lab) == squash(name):
            return tid
    if squash(name) == squash(TEAM05_NEW_LABEL):
        for tid, lab in labels.items():
            if _norm(lab) == _norm(TEAM05_OLD_LABEL):
                return tid
    best, best_r = None, 0.0
    for tid, lab in labels.items():
        r = difflib.SequenceMatcher(None, target, _norm(lab)).ratio()
        if r > best_r:
            best, best_r = tid, r
    return best if best_r >= 0.80 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("roster_xlsx", type=Path)
    ap.add_argument("listone_xlsx", type=Path)
    ap.add_argument("--yes", action="store_true", help="append to the ledger (default: dry-run)")
    ap.add_argument("--relabel-team05", action="store_true",
                    help="also update team_labels: team_05 -> 'I Have a N'Drim'")
    args = ap.parse_args()

    ruleset = load_ruleset(Path("config/auction_rules.v1.yaml"))
    staged = parse_roster_file(args.roster_xlsx)
    idx = _load_listone_index(args.listone_xlsx)

    labels_conn = team_labels_store.connect()
    labels = team_labels_store.get_all_labels(labels_conn)
    ledger_conn = ledger_store.connect()
    existing = ledger_store.load_events(ledger_conn)

    # owned player_ids per team from the ledger (G1+G2), negatives aliased
    owned: dict[str, set[str]] = {}
    for ev in existing:
        if isinstance(ev, AssignmentEvent):
            s = owned.setdefault(ev.team_id, set())
            for pid in ev.item.player_ids:
                s.add(NEGATIVE_ALIAS.get(pid, pid))

    new_events: list[AssignmentEvent] = []
    errors: list[str] = []
    flags: list[str] = []
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    for team_name, slots in staged.teams.items():
        tid = _resolve_team_id(team_name, labels)
        if tid is None:
            errors.append(f"team not resolved: {team_name!r}")
            continue
        team_owned = owned.get(tid, set())
        resolved_codes: set[str] = set()
        for slot in slots:
            res, how = _resolve_player(slot.display_name, idx)
            if res is None:
                errors.append(f"[{team_name}] {slot.display_name!r} ({slot.cost}cr): {how}")
                continue
            code, role_letter = res
            code = NEGATIVE_ALIAS.get(code, code)
            resolved_codes.add(code)
            if code in team_owned:
                continue  # already on the ledger (G1/G2, or negative-aliased)
            if _ROLE_MAP[role_letter] is Role.GK:
                flags.append(f"[{team_name}] GK line not in ledger, NOT written: "
                             f"{slot.display_name} {slot.cost}cr (GK swaps out of scope)")
                continue
            new_events.append(AssignmentEvent(
                event_id=uuid.uuid4().hex,
                ts=ts,
                round_id=ROUND_ID,
                team_id=tid,
                pool_id=POOL_ID,
                role=_ROLE_MAP[role_letter],
                item=AssignmentItem(player_ids=(code,)),
                amount=int(slot.cost),
                source=SOURCE,
                author=AUTHOR,
                corrects=None,
            ))
        # ledger players no longer on the roster (info only)
        gone = team_owned - resolved_codes
        if gone:
            flags.append(f"[{team_name}] in ledger but not on current roster: {sorted(gone)}")

    print(f"Parsed {len(staged.teams)} teams. New G3/G4 assignments to write: {len(new_events)}. "
          f"Errors: {len(errors)}. Flags: {len(flags)}.")
    for f in flags:
        print("  FLAG:", f)
    if errors:
        print("\nERRORS (nothing written):")
        for e in errors:
            print("  -", e)
        return 1

    try:
        replay(ruleset, existing + new_events)
    except (DomainError, ConfigError) as exc:
        print(f"\nREPLAY FAILED, nothing written: {exc}")
        return 1
    print("replay(existing + new) OK: invariants hold.")

    # per-team spend summary
    by_team: dict[str, int] = {}
    for ev in new_events:
        by_team[ev.team_id] = by_team.get(ev.team_id, 0) + ev.amount
    for tid in sorted(by_team):
        print(f"  {tid} ({labels.get(tid,'')}): +{by_team[tid]}cr over {sum(1 for e in new_events if e.team_id==tid)} picks")

    if not args.yes:
        print("\nDRY-RUN: nothing written. Re-run with --yes to append.")
        return 0

    if args.relabel_team05:
        for tid, lab in labels.items():
            if _norm(lab) == _norm(TEAM05_OLD_LABEL):
                team_labels_store.set_label(labels_conn, tid, TEAM05_NEW_LABEL)
                print(f"relabelled {tid}: {lab!r} -> {TEAM05_NEW_LABEL!r}")
    for ev in new_events:
        ledger_store.append_event(ledger_conn, ev)
    print(f"Appended {len(new_events)} events. Ledger now has {len(ledger_store.load_events(ledger_conn))}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
