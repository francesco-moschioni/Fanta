#!/usr/bin/env python3
"""Batch-parse a folder of manually-saved Understat files -> data/staged/understat/.

Usage:
    python scripts/ingest_understat_folder.py <folder>

Same policy as ingest_listone_folder.py / ingest_voti_folder.py: reads only files
already on disk, no fetch/HTTP logic (retrieval is a separate standalone script
that nothing in the pipeline imports). Season is inferred from each filename
(e.g. ``..._2023.json`` / ``..._2023_24.html``).

Files whose name contains "shot" are parsed as shot events; everything else is
parsed as per-player season aggregates.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from fantacalcio.ingest.understat import (
    UnderstatParseError,
    parse_player_season,
    parse_shot_events,
    write_staged_csv,
)

_MANIFEST_FIELDS = ["file_name", "kind", "season_label", "rows", "sha256", "available_time", "status", "error"]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/ingest_understat_folder.py <folder>", file=sys.stderr)
        return 2

    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"Not a directory: {folder}", file=sys.stderr)
        return 2

    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".json", ".html", ".htm"}
    )
    if not files:
        print(f"No .json / .html Understat files found in {folder}")
        return 0

    print(f"Found {len(files)} file(s) in {folder}")

    manifest_rows = []
    ok_count, fail_count = 0, 0
    for path in files:
        kind = "shot_events" if "shot" in path.name.lower() else "player_season"
        parser = parse_shot_events if kind == "shot_events" else parse_player_season
        try:
            staged = parser(path)
            out_path = write_staged_csv(staged)
            print(f"  OK   [{staged.kind}] {path.name} -> {out_path} "
                  f"({len(staged.frame)} rows, season {staged.season_label})")
            manifest_rows.append(
                {
                    "file_name": path.name,
                    "kind": staged.kind,
                    "season_label": staged.season_label or "",
                    "rows": len(staged.frame),
                    "sha256": staged.file_sha256,
                    "available_time": staged.available_time.isoformat(),
                    "status": "ok",
                    "error": "",
                }
            )
            ok_count += 1
        except UnderstatParseError as exc:
            print(f"  FAIL [{kind}] {path.name}: {exc}")
            manifest_rows.append(
                {
                    "file_name": path.name, "kind": kind, "season_label": "", "rows": "",
                    "sha256": "", "available_time": "", "status": "failed", "error": str(exc),
                }
            )
            fail_count += 1

    manifest_dir = Path("data/staged/understat")
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
