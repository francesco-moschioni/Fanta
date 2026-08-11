"""Immutable raw snapshots with checksum and retrieval metadata.

Per docs/DATA_AND_MODELING.md: `raw` is immutable source snapshots with checksum and
access metadata. Every snapshot written here is a new file; nothing already written
under data/raw/ is ever edited or overwritten in place.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RAW_ROOT = Path("data/raw")


class SnapshotError(RuntimeError):
    """Raised when a snapshot cannot be fetched, written, or verified."""


@dataclass(frozen=True)
class RawSnapshot:
    source_id: str
    url: str
    retrieved_at: str
    sha256: str
    content_path: str
    manifest_path: str
    byte_size: int


def _utcnow_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetch_and_snapshot(
    url: str,
    source_id: str,
    filename: str,
    raw_root: Path = DEFAULT_RAW_ROOT,
    timeout: int = 30,
) -> RawSnapshot:
    """Download `url` and write it as an immutable, checksummed raw snapshot.

    Never call this against a source without a `docs/SOURCE_REGISTER.md` entry
    confirming automation is permitted for it.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 (vetted, registered sources only)
            content = response.read()
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed, explicit error
        raise SnapshotError(f"Failed to fetch {url!r} for source {source_id!r}: {exc}") from exc

    return write_snapshot(content=content, url=url, source_id=source_id, filename=filename, raw_root=raw_root)


def write_snapshot(
    content: bytes,
    url: str,
    source_id: str,
    filename: str,
    raw_root: Path = DEFAULT_RAW_ROOT,
) -> RawSnapshot:
    """Write already-fetched bytes as an immutable, checksummed raw snapshot.

    Split out from `fetch_and_snapshot` so tests and offline/manual-import flows can
    snapshot content without a network call.
    """
    retrieved_at = _utcnow_compact()
    snapshot_dir = raw_root / source_id / retrieved_at
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    content_path = snapshot_dir / filename
    if content_path.exists():
        raise SnapshotError(f"Refusing to overwrite existing raw snapshot file: {content_path}")
    content_path.write_bytes(content)

    sha256 = hashlib.sha256(content).hexdigest()
    # Scoped to `filename`, not a fixed "manifest.json": two snapshots for the same
    # source landing in the same per-second timestamped directory (e.g. a fast
    # audit loop fetching several seasons back-to-back) would otherwise share one
    # manifest file, and the second write would silently overwrite the first
    # file's provenance record while its checksummed content stayed on disk.
    manifest_path = snapshot_dir / f"{filename}.manifest.json"
    manifest = {
        "source_id": source_id,
        "url": url,
        "retrieved_at": retrieved_at,
        "sha256": sha256,
        "filename": filename,
        "byte_size": len(content),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return RawSnapshot(
        source_id=source_id,
        url=url,
        retrieved_at=retrieved_at,
        sha256=sha256,
        content_path=str(content_path),
        manifest_path=str(manifest_path),
        byte_size=len(content),
    )


def verify_snapshot(snapshot: RawSnapshot) -> bool:
    """Recompute the checksum of a written snapshot and compare to its manifest."""
    content = Path(snapshot.content_path).read_bytes()
    return hashlib.sha256(content).hexdigest() == snapshot.sha256


def snapshot_to_dict(snapshot: RawSnapshot) -> dict:
    return asdict(snapshot)
