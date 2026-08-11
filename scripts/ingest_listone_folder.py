#!/usr/bin/env python3
"""Batch-parse a folder of manually-downloaded Quotazioni_/Statistiche_Fantacalcio_*.xlsx files.

Usage:
    python scripts/ingest_listone_folder.py <folder>

Same policy as ingest_voti_folder.py: reads only files already on disk, no fetch/HTTP
logic. Season is inferred from each filename.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from fantacalcio.ingest.fantacalcio_listone import (
    ListoneParseError,
    parse_quotazioni_file,
    parse_statistiche_file,
    write_staged_csv,
)

_MANIFEST_FIELDS = ["file_name", "kind", "season_label", "rows", "sha256", "status", "error"]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/ingest_listone_folder.py <folder>", file=sys.stderr)
        return 2

    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"Not a directory: {folder}", file=sys.stderr)
        return 2

    quotazioni_files = sorted(folder.glob("Quotazioni_Fantacalcio_*.xlsx"))
    statistiche_files = sorted(folder.glob("Statistiche_Fantacalcio_*.xlsx"))
    files = [(p, "quotazioni", parse_quotazioni_file) for p in quotazioni_files]
    files += [(p, "statistiche", parse_statistiche_file) for p in statistiche_files]

    if not files:
        print(f"No 'Quotazioni_Fantacalcio_*.xlsx' or 'Statistiche_Fantacalcio_*.xlsx' files found in {folder}")
        return 0

    print(f"Found {len(files)} file(s) in {folder}")

    manifest_rows = []
    ok_count, fail_count = 0, 0
    for path, kind, parser in files:
        try:
            staged = parser(path)
            out_path = write_staged_csv(staged)
            print(f"  OK   [{kind}] {path.name} -> {out_path} ({len(staged.frame)} rows, season {staged.season_label})")
            manifest_rows.append(
                {
                    "file_name": path.name,
                    "kind": kind,
                    "season_label": staged.season_label,
                    "rows": len(staged.frame),
                    "sha256": staged.file_sha256,
                    "status": "ok",
                    "error": "",
                }
            )
            ok_count += 1
        except ListoneParseError as exc:
            print(f"  FAIL [{kind}] {path.name}: {exc}")
            manifest_rows.append(
                {
                    "file_name": path.name,
                    "kind": kind,
                    "season_label": "",
                    "rows": "",
                    "sha256": "",
                    "status": "failed",
                    "error": str(exc),
                }
            )
            fail_count += 1

    manifest_dir = Path("data/staged/fantacalcio_listone")
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
