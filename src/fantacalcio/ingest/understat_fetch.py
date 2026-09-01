"""STANDALONE personal-use fetch helper for Understat — NOT part of the pipeline.

Engine v2 Stage 3, personal-use override ADR-2026-070 / ADR-2026-075.

Understat's ``robots.txt`` is ``Disallow: /``. That is acknowledged here and NOT
worked around at scale: the project owner authorised, for their own private
local fantacalcio only, occasional manual retrieval of xG/xA/shots/minutes data.
To keep the risk contained and the source replaceable, this script:

* is **standalone** — run as ``python -m fantacalcio.ingest.understat_fetch ...``
  or ``python src/fantacalcio/ingest/understat_fetch.py ...``. It does its work
  only under ``if __name__ == "__main__"``; importing the module has no side
  effect and starts no network activity;
* is **never imported** by any pipeline module, by ``scripts/run_*.py`` or by CI
  (``tests/test_ingest_understat.py`` statically asserts this);
* rate-limits to at least ``MIN_INTERVAL_SECONDS`` (>= 5s) between requests and
  keeps an on-disk cache so a page is fetched at most once;
* writes results through ``ingest.snapshot.write_snapshot`` so every raw file is
  immutable and checksummed. Raw files are gitignored and never redistributed.

If a licensed provider is bought later, only ``ingest/understat.py`` changes;
this script can simply be deleted.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from pathlib import Path

from fantacalcio.ingest.snapshot import write_snapshot

BASE_URL = "https://understat.com"
MIN_INTERVAL_SECONDS = 5.0
DEFAULT_CACHE_DIR = Path("data/raw/_understat_fetch_cache")
SOURCE_ID = "understat"
_USER_AGENT = "personal-local-fantacalcio/1.0 (manual, rate-limited, non-crawling)"


class _RateLimiter:
    def __init__(self, min_interval: float = MIN_INTERVAL_SECONDS) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


def _cache_path(cache_dir: Path, url: str) -> Path:
    safe = url.replace("https://", "").replace("http://", "").replace("/", "_")
    return cache_dir / f"{safe}.html"


def fetch_page(url: str, *, cache_dir: Path, limiter: _RateLimiter) -> bytes:
    """Return the bytes for ``url``, from the on-disk cache when present."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = _cache_path(cache_dir, url)
    if cached.is_file():
        print(f"cache hit: {url}")
        return cached.read_bytes()

    limiter.wait()
    print(f"fetching (rate-limited >= {MIN_INTERVAL_SECONDS}s): {url}")
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - manual personal use
        content = resp.read()
    cached.write_bytes(content)
    return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual, rate-limited Understat fetch (personal use).")
    parser.add_argument("paths", nargs="+", help="Understat paths, e.g. 'league/Serie_A/2023' or 'player/1234'.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--filename-prefix", default="understat")
    args = parser.parse_args(argv)

    limiter = _RateLimiter()
    for rel in args.paths:
        url = f"{BASE_URL}/{rel.lstrip('/')}"
        content = fetch_page(url, cache_dir=args.cache_dir, limiter=limiter)
        fname = f"{args.filename_prefix}_{rel.strip('/').replace('/', '_')}.html"
        snap = write_snapshot(content=content, url=url, source_id=SOURCE_ID, filename=fname)
        print(f"snapshot: {snap.content_path} ({snap.byte_size} bytes, sha256={snap.sha256[:12]}...)")
    print("done. Parse the snapshots with fantacalcio.ingest.understat (pure, offline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
