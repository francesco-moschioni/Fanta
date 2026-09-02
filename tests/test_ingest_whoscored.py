"""Stage 7 (ADR-2026-079). Synthetic fixtures only — never real WhoScored content."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from fantacalcio.ingest.whoscored import (
    StagedWhoScored,
    WhoScoredParseError,
    parse_missing_players,
    parse_probable_lineup,
    write_staged_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _missing_records():
    return [
        {
            "player_name": "Mario Rossi",
            "team": "Synthetic FC",
            "position": "D",
            "status": "Injured",
            "reason": "Hamstring",
            "expected_return": "2026-09-10",
            "report_time": "2026-09-01T09:00:00",
        },
        {
            "player_name": "Luca Bianchi",
            "team": "Other FC",
            "position": "C",
            "status": "Suspended",
            "reason": "Yellow card accumulation",
            "expected_return": None,
            "report_time": "2026-09-02T09:00:00",
        },
        {
            "player_name": "Paolo Verdi",
            "team": "Synthetic FC",
            "position": "A",
            "status": "75% doubt",
            "reason": "Knock",
            "report_time": "2026-09-02T12:00:00",
        },
    ]


def _write_json(tmp_path: Path, obj, name="whoscored_missing_2026.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


class TestParseMissingPlayers:
    def test_parses_json_array_fixture(self, tmp_path):
        staged = parse_missing_players(_write_json(tmp_path, _missing_records()))
        assert isinstance(staged, StagedWhoScored)
        assert staged.kind == "missing_players"
        assert staged.source_name == "whoscored"
        assert staged.file_sha256 and len(staged.file_sha256) == 64
        # available_time = latest report timestamp
        assert staged.available_time == pd.Timestamp("2026-09-02T12:00:00")
        # mixed feed -> tier C overall
        assert staged.quality_tier == "C"

        f = staged.frame
        assert list(f["status"]) == ["out", "suspended", "doubtful"]
        assert list(f["quality_tier"]) == ["C", "B", "C"]
        assert f.loc[0, "expected_return"] == pd.Timestamp("2026-09-10")
        assert f.loc[1, "role"] == "C"

    def test_all_suspensions_is_tier_b(self, tmp_path):
        recs = [
            {"player_name": "A", "status": "Suspended", "report_time": "2026-09-01"},
            {"player_name": "B", "status": "ban", "report_time": "2026-09-01"},
        ]
        staged = parse_missing_players(_write_json(tmp_path, recs))
        assert staged.quality_tier == "B"
        assert (staged.frame["quality_tier"] == "B").all()

    def test_html_with_embedded_json_assignment(self, tmp_path):
        payload = json.dumps({"injuries": _missing_records()})
        html = f"<html><body><script>\nvar preloaded = {payload};\n</script></body></html>"
        p = tmp_path / "whoscored_missing_2026.html"
        p.write_text(html, encoding="utf-8")
        staged = parse_missing_players(p)
        assert len(staged.frame) == 3
        assert staged.frame.iloc[0]["player_name"] == "Mario Rossi"

    def test_html_with_json_parse_blob(self, tmp_path):
        payload = json.dumps(_missing_records()).replace('"', "\\x22")
        html = f"<script>var d = JSON.parse('{payload}');</script>"
        p = tmp_path / "whoscored_missing_2026.html"
        p.write_text(html, encoding="utf-8")
        staged = parse_missing_players(p)
        assert list(staged.frame["status"]) == ["out", "suspended", "doubtful"]

    def test_unknown_status_raises(self, tmp_path):
        recs = [{"player_name": "X", "status": "banana", "report_time": "2026-09-01"}]
        with pytest.raises(WhoScoredParseError, match="status"):
            parse_missing_players(_write_json(tmp_path, recs))

    def test_no_report_time_raises(self, tmp_path):
        recs = [{"player_name": "X", "status": "out"}]
        with pytest.raises(WhoScoredParseError, match="report timestamp"):
            parse_missing_players(_write_json(tmp_path, recs))

    def test_report_time_override(self, tmp_path):
        recs = [{"player_name": "X", "status": "out"}]
        staged = parse_missing_players(
            _write_json(tmp_path, recs), report_time="2026-09-05"
        )
        assert staged.available_time == pd.Timestamp("2026-09-05")

    def test_malformed_file_raises(self, tmp_path):
        p = tmp_path / "whoscored_missing_2026.json"
        p.write_text("{ not json", encoding="utf-8")
        with pytest.raises(WhoScoredParseError):
            parse_missing_players(p)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(WhoScoredParseError, match="not found"):
            parse_missing_players(tmp_path / "nope.json")

    def test_no_rows_raises(self, tmp_path):
        with pytest.raises(WhoScoredParseError):
            parse_missing_players(_write_json(tmp_path, [{"foo": "bar"}]))

    def test_write_staged_csv_roundtrips(self, tmp_path):
        staged = parse_missing_players(_write_json(tmp_path, _missing_records()))
        out = write_staged_csv(staged, staged_root=tmp_path / "staged")
        assert out.is_file()
        assert len(pd.read_csv(out)) == 3


class TestParseProbableLineup:
    def test_parses_probable_lineup(self, tmp_path):
        recs = [
            {"player_name": "Mario Rossi", "team": "Synthetic FC",
             "is_probable_starter": True, "report_time": "2026-09-01"},
            {"player_name": "Luca Bianchi", "team": "Synthetic FC",
             "status": "bench", "report_time": "2026-09-01"},
        ]
        staged = parse_probable_lineup(_write_json(tmp_path, recs, name="whoscored_lineup.json"))
        assert staged.kind == "probable_lineup"
        assert staged.quality_tier == "C"
        assert list(staged.frame["is_probable_starter"]) == [True, False]


def test_whoscored_fetch_is_not_imported_by_pipeline_or_run_scripts():
    """ADR-2026-070/079: the fetch helper must stay standalone."""
    import_markers = (
        "import whoscored_fetch",
        "from whoscored_fetch",
        "fantacalcio.ingest.whoscored_fetch",
        "ingest.whoscored_fetch import",
    )
    offenders = []
    for base in (REPO_ROOT / "src" / "fantacalcio", REPO_ROOT / "scripts"):
        for py in base.rglob("*.py"):
            if py.name == "whoscored_fetch.py":
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            if any(marker in text for marker in import_markers):
                offenders.append(str(py.relative_to(REPO_ROOT)))
    assert offenders == [], f"whoscored_fetch imported by: {offenders}"
