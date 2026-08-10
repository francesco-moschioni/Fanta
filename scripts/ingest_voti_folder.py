#!/usr/bin/env python3
"""Batch-parse a folder of manually-downloaded Voti_Fantacalcio_*.xlsx files.

Usage:
    python scripts/ingest_voti_folder.py <folder>

Only reads files already on disk — no download/HTTP logic, per ADR-2026-007 and the
source file's own "ad uso personale esclusivo" licence text. Point this at a folder
containing files you (or your league admin) downloaded by hand from fantacalcio.it.

Writes one staged CSV per file to data/staged/fantacalcio_voti_manual/ (gitignored)
plus a run manifest (data/staged/fantacalcio_voti_manual/_manifest.csv, also
gitignored) recording exactly what was processed, with file hashes for traceability.
Continues past a bad file rather than aborting the whole batch; every failure is
reported at the end, never silently skipped.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from fantacalcio.ingest.fantacalcio_voti import VotiParseError, parse_voti_file, write_staged_csv

_MANIFEST_FIELDS = ["file_name", "season_label", "matchday", "rows", "sha256", "status", "error"]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/ingest_voti_folder.py <folder>", file=sys.stderr)
        return 2

    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"Not a directory: {folder}", file=sys.stderr)
        return 2

    files = sorted(folder.glob("Voti_Fantacalcio_*.xlsx"))
    if not files:
        print(f"No 'Voti_Fantacalcio_*.xlsx' files found in {folder}")
        return 0

    print(f"Found {len(files)} file(s) in {folder}")

    manifest_rows = []
    ok_count, fail_count = 0, 0
    for path in files:
        try:
            staged = parse_voti_file(path)
            out_path = write_staged_csv(staged)
            print(f"  OK   {path.name} -> {out_path} ({len(staged.frame)} rows)")
            manifest_rows.append(
                {
                    "file_name": path.name,
                    "season_label": staged.season_label,
                    "matchday": staged.matchday,
                    "rows": len(staged.frame),
                    "sha256": staged.file_sha256,
                    "status": "ok",
                    "error": "",
                }
            )
            ok_count += 1
        except VotiParseError as exc:
            print(f"  FAIL {path.name}: {exc}")
            manifest_rows.append(
                {
                    "file_name": path.name,
                    "season_label": "",
                    "matchday": "",
                    "rows": "",
                    "sha256": "",
                    "status": "failed",
                    "error": str(exc),
                }
            )
            fail_count += 1

    manifest_dir = Path("data/staged/fantacalcio_voti_manual")
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"\n{ok_count} parsed, {fail_count} failed. Manifest: {manifest_path}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
