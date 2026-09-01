"""Stage 3 (ADR-2026-075). Synthetic fixtures only — never real Understat content."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from fantacalcio.ingest.understat import (
    UnderstatParseError,
    parse_player_season,
    parse_shot_events,
    write_staged_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _season_record(name="Synthetic Player", pid="1", position="F S", **overrides):
    rec = {
        "id": pid,
        "player_name": name,
        "position": position,
        "team_title": "Synthetic FC",
        "games": "30",
        "time": "2500",
        "goals": "12",
        "xG": "10.5",
        "assists": "5",
        "xA": "4.2",
        "shots": "60",
        "key_passes": "35",
        "npg": "9",
        "npxG": "8.1",
        "xGChain": "12.3",
        "xGBuildup": "4.5",
    }
    rec.update({k: str(v) for k, v in overrides.items()})
    return rec


def _write_json(tmp_path: Path, obj, name="understat_2023.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


class TestParsePlayerSeason:
    def test_parses_json_array_fixture(self, tmp_path):
        path = _write_json(tmp_path, [_season_record(), _season_record(name="Other", pid="2", position="M C")])
        staged = parse_player_season(path)

        assert staged.kind == "player_season"
        assert staged.source_name == "understat"
        assert staged.quality_tier == "C"
        assert staged.file_sha256 and len(staged.file_sha256) == 64
        assert staged.season_label == "2023_24"
        # end of season = 30 June of the following year
        assert staged.available_time == pd.Timestamp("2024-06-30")

        frame = staged.frame
        assert len(frame) == 2
        for col in ("games", "goals", "shots", "npg"):
            assert pd.api.types.is_integer_dtype(frame[col])
        for col in ("xG", "xA", "npxG", "xGChain", "xGBuildup"):
            assert pd.api.types.is_float_dtype(frame[col])
        assert set(frame["understat_role"]) == {"A", "C"}
        assert (frame["minutes"] == frame["time"]).all()

    def test_season_from_explicit_arg_overrides_filename(self, tmp_path):
        path = _write_json(tmp_path, [_season_record()], name="whatever.json")
        staged = parse_player_season(path, season="2021_22")
        assert staged.season_label == "2021_22"
        assert staged.available_time == pd.Timestamp("2022-06-30")

    def test_html_json_parse_blob_with_hex_escapes(self, tmp_path):
        payload = json.dumps([_season_record(name="HTML Guy", position="D C")])
        # Understat hex-escapes the payload inside a single-quoted JSON.parse arg.
        escaped = payload.replace('"', "\\x22")
        html = (
            "<html><body><script>\n"
            f"var playersData = JSON.parse('{escaped}');\n"
            "</script></body></html>"
        )
        path = tmp_path / "understat_2022_23.html"
        path.write_text(html, encoding="utf-8")
        staged = parse_player_season(path)
        assert staged.season_label == "2022_23"
        assert staged.frame.iloc[0]["understat_player_name"] == "HTML Guy"
        assert staged.frame.iloc[0]["understat_role"] == "D"

    def test_unknown_season_raises(self, tmp_path):
        path = _write_json(tmp_path, [_season_record()], name="noseason.json")
        with pytest.raises(UnderstatParseError, match="season"):
            parse_player_season(path)

    def test_missing_field_raises(self, tmp_path):
        bad = _season_record()
        del bad["npxG"]
        path = _write_json(tmp_path, [bad])
        with pytest.raises(UnderstatParseError, match="missing expected fields"):
            parse_player_season(path)

    def test_malformed_file_raises(self, tmp_path):
        path = tmp_path / "understat_2023.json"
        path.write_text("{ this is not json", encoding="utf-8")
        with pytest.raises(UnderstatParseError):
            parse_player_season(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(UnderstatParseError, match="not found"):
            parse_player_season(tmp_path / "missing.json")

    def test_write_staged_csv_roundtrips(self, tmp_path):
        path = _write_json(tmp_path, [_season_record()])
        staged = parse_player_season(path)
        out = write_staged_csv(staged, staged_root=tmp_path / "staged")
        assert out.is_file()
        back = pd.read_csv(out)
        assert len(back) == 1


class TestParseShotEvents:
    def test_parses_shot_fixture(self, tmp_path):
        shots = [
            {
                "minute": "23", "X": "0.91", "Y": "0.52", "xG": "0.27",
                "result": "Goal", "situation": "OpenPlay", "shotType": "RightFoot",
                "player": "Synthetic Player", "player_assisted": "Team Mate",
                "match_id": "555", "date": "2023-09-01",
            },
            {
                "minute": "77", "X": "0.80", "Y": "0.40", "xG": "0.05",
                "result": "MissedShots", "situation": "FromCorner", "shotType": "Head",
                "player": "Synthetic Player", "player_assisted": "",
                "match_id": "556", "date": "2023-09-15",
            },
        ]
        path = _write_json(tmp_path, shots, name="understat_shots_2023.json")
        staged = parse_shot_events(path)
        assert staged.kind == "shot_events"
        assert staged.quality_tier == "C"
        assert list(staged.frame["result"]) == ["Goal", "MissedShots"]
        assert staged.frame.iloc[0]["a_player"] == "Team Mate"
        # available_time falls on the latest shot date
        assert staged.available_time == pd.Timestamp("2023-09-15")

    def test_no_shot_rows_raises(self, tmp_path):
        path = _write_json(tmp_path, [{"foo": "bar"}], name="understat_shots_2023.json")
        with pytest.raises(UnderstatParseError):
            parse_shot_events(path)


def test_understat_fetch_is_not_imported_by_pipeline_or_run_scripts():
    """ADR-2026-070/075: the fetch helper must stay standalone."""
    import_markers = (
        "import understat_fetch",
        "from understat_fetch",
        "fantacalcio.ingest.understat_fetch",
        "ingest.understat_fetch import",
    )
    offenders = []
    for base in (REPO_ROOT / "src" / "fantacalcio", REPO_ROOT / "scripts"):
        for py in base.rglob("*.py"):
            if py.name == "understat_fetch.py":
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            if any(marker in text for marker in import_markers):
                offenders.append(str(py.relative_to(REPO_ROOT)))
    assert offenders == [], f"understat_fetch imported by: {offenders}"
