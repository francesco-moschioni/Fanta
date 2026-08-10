import pytest

from fantacalcio.ingest.snapshot import SnapshotError, verify_snapshot, write_snapshot


def test_write_snapshot_creates_content_and_manifest(tmp_path):
    snap = write_snapshot(
        content=b"hello world",
        url="https://example.invalid/data.csv",
        source_id="test_source",
        filename="data.csv",
        raw_root=tmp_path,
    )
    assert (tmp_path / "test_source" / snap.retrieved_at / "data.csv").read_bytes() == b"hello world"
    assert verify_snapshot(snap)
    assert snap.byte_size == 11


def test_write_snapshot_refuses_to_overwrite(tmp_path, monkeypatch):
    import fantacalcio.ingest.snapshot as snapshot_mod

    # Freeze the timestamp so the second call collides with the first, to
    # deterministically exercise the immutability guard.
    monkeypatch.setattr(snapshot_mod, "_utcnow_compact", lambda: "20260101T000000Z")

    write_snapshot(content=b"a", url="u", source_id="s", filename="f.csv", raw_root=tmp_path)
    with pytest.raises(SnapshotError, match="Refusing to overwrite"):
        write_snapshot(content=b"b", url="u", source_id="s", filename="f.csv", raw_root=tmp_path)


def test_verify_snapshot_detects_tampering(tmp_path):
    snap = write_snapshot(
        content=b"original", url="u", source_id="s", filename="f.csv", raw_root=tmp_path
    )
    from pathlib import Path

    Path(snap.content_path).write_bytes(b"tampered")
    assert not verify_snapshot(snap)
