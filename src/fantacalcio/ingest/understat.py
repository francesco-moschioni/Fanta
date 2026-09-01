"""Pure parser for manually-saved Understat exports — no HTTP, ever.

Engine v2 Stage 3 (ADR-2026-075, under the personal-use override ADR-2026-070).

Understat declares ``robots.txt: Disallow: /``. Per docs/SOURCE_REGISTER.md the
only compliant path is a human opening the page (or an already-downloaded JSON)
in their own browser and handing the file to this parser. This module therefore
contains **no fetch / download / urllib logic** — it requires a file that is
already on disk. Any retrieval lives in the standalone
``understat_fetch.py`` script, which nothing in the pipeline imports.

Raw HTML/JSON is never committed (``data/raw`` and ``data/staged`` are
gitignored); test fixtures are synthetic, never real Understat content.

Format assumptions (no real sample was available when this was written — the
parser is defensive and raises :class:`UnderstatParseError` on anything it does
not recognise rather than inventing data):

* Understat embeds page data as ``var <name> = JSON.parse('<payload>')`` where
  ``<payload>`` is a JSON string with ``\\xHH`` hex escapes. Both the raw HTML
  page and a hand-saved ``.json`` (the decoded array/object) are accepted.
* Per-player season aggregates ("playersData" on a league page, or the
  season/group rows on a player page) carry at least:
  ``games, time, goals, xG, assists, xA, shots, key_passes, npg, npxG,
  xGChain, xGBuildup`` (Understat serialises them as strings).
* Shot events ("shotsData" on a player page) carry at least
  ``minute, X, Y, xG, result, situation, shotType`` plus ``player`` and
  ``player_assisted``. Coordinates are 0..1 fractions of the pitch.
"""

from __future__ import annotations

import codecs
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

SOURCE_NAME = "understat"
DEFAULT_SOURCE_VERSION = "understat_manual_v1"
QUALITY_TIER = "C"

_SEASON_AGG_FIELDS = (
    "games", "time", "goals", "xG", "assists", "xA", "shots",
    "key_passes", "npg", "npxG", "xGChain", "xGBuildup",
)
_SEASON_INT_FIELDS = ("games", "time", "goals", "assists", "shots", "key_passes", "npg")
_SEASON_FLOAT_FIELDS = ("xG", "xA", "npxG", "xGChain", "xGBuildup")

_SHOT_FIELDS = ("minute", "xG", "result", "situation", "shotType")

# ``var foo = JSON.parse('....')`` — capture the single-quoted payload.
_JSON_PARSE_RE = re.compile(r"JSON\.parse\(\s*'((?:[^'\\]|\\.)*)'\s*\)")
_SEASON_FROM_NAME_RE = re.compile(r"(20\d{2})(?:[_-](\d{2,4}))?")

# Understat position tokens -> classic fantacalcio role letters. First character
# of the position string ("GK", "D C", "M C", "F S", "Sub") is the signal; the
# resolver is role-constrained so an unmapped position simply fails to resolve
# rather than being force-joined.
_POSITION_TO_ROLE = {"G": "P", "D": "D", "M": "C", "F": "A"}


class UnderstatParseError(ValueError):
    """Raised when an Understat file does not match the expected structure."""


@dataclass(frozen=True)
class StagedUnderstat:
    file_path: str
    file_sha256: str
    kind: str  # "player_season" | "shot_events"
    season_label: str | None
    source_name: str
    source_version: str
    quality_tier: str
    available_time: pd.Timestamp
    frame: pd.DataFrame


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _normalise_season_label(raw: str | int | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    m = _SEASON_FROM_NAME_RE.search(s)
    if not m:
        return None
    start = int(m.group(1))
    return f"{start}_{(start + 1) % 100:02d}"


def _season_from_filename(path: Path) -> str | None:
    return _normalise_season_label(path.name)


def _season_end_time(season_label: str | None) -> pd.Timestamp:
    """End of a season: 30 June of the year after its start year.

    Raises if the season is unknown — ``available_time`` must be traceable and a
    silent far-future/near-past guess would defeat the leakage check.
    """
    if season_label is None:
        raise UnderstatParseError(
            "Cannot determine the Understat season (not in the filename and not "
            "passed explicitly); pass season=... so available_time is traceable."
        )
    start = int(season_label.split("_")[0])
    return pd.Timestamp(year=start + 1, month=6, day=30)


def _decode_blob(payload: str) -> object:
    """Decode one Understat ``JSON.parse('...')`` payload into Python objects."""
    try:
        unescaped = codecs.decode(payload, "unicode_escape")
        # Understat hex-escapes multibyte UTF-8 byte-by-byte; recover it.
        try:
            unescaped = unescaped.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        return json.loads(unescaped)
    except (ValueError, json.JSONDecodeError) as exc:
        raise UnderstatParseError(f"could not decode embedded JSON blob: {exc}") from exc


def _iter_embedded_blobs(text: str):
    for m in _JSON_PARSE_RE.finditer(text):
        try:
            yield _decode_blob(m.group(1))
        except UnderstatParseError:
            continue


def _load_objects(path: Path) -> tuple[list, str]:
    """Return (list-of-candidate-JSON-objects, sha256) for a file on disk.

    A ``.json`` file yields exactly one object; an HTML page yields every
    ``JSON.parse('...')`` payload it contains.
    """
    if not path.is_file():
        raise UnderstatParseError(f"File not found: {path}")
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", errors="replace")
    stripped = text.lstrip()
    if stripped[:1] in ("[", "{"):
        try:
            return [json.loads(text)], sha
        except (ValueError, json.JSONDecodeError) as exc:
            raise UnderstatParseError(f"file looks like JSON but did not parse: {exc}") from exc
    blobs = list(_iter_embedded_blobs(text))
    if not blobs:
        raise UnderstatParseError(
            "no JSON payload found: expected a .json array/object or an HTML page "
            "with a `var ... = JSON.parse('...')` block."
        )
    return blobs, sha


def _records_with_keys(obj: object, keys: tuple[str, ...]) -> list[dict]:
    """Best-effort flatten of an Understat blob to a list of dicts holding ``keys``."""
    def _ok(d: object) -> bool:
        return isinstance(d, dict) and all(k in d for k in keys)

    if isinstance(obj, list):
        return [d for d in obj if _ok(d)]
    if isinstance(obj, dict):
        if _ok(obj):
            return [obj]
        out: list[dict] = []
        for v in obj.values():
            if isinstance(v, list):
                out.extend(d for d in v if _ok(d))
            elif _ok(v):
                out.append(v)
        return out
    return []


# --------------------------------------------------------------------------- #
# per-player season aggregates                                                 #
# --------------------------------------------------------------------------- #
def parse_player_season(
    path: str | Path,
    *,
    season: str | int | None = None,
    source_version: str = DEFAULT_SOURCE_VERSION,
) -> StagedUnderstat:
    """Parse per-player season aggregates from a saved Understat file.

    ``season`` is inferred from the filename (e.g. ``understat_2023.json`` or
    ``..._2023_24.html``) if not passed. ``available_time`` is the end of that
    season (30 June of the following year).
    """
    path = Path(path)
    objects, sha = _load_objects(path)
    season_label = _normalise_season_label(season) or _season_from_filename(path)

    records: list[dict] = []
    for obj in objects:
        records = _records_with_keys(obj, ("xG", "time"))
        if records:
            break
    if not records:
        raise UnderstatParseError(
            f"no per-player season rows found in {path}; expected dicts with at "
            f"least {_SEASON_AGG_FIELDS!r}."
        )

    missing = sorted({f for f in _SEASON_AGG_FIELDS for r in records if f not in r})
    if missing:
        raise UnderstatParseError(
            f"season rows in {path} are missing expected fields {missing}; "
            "the Understat export format may have changed."
        )

    rows = []
    for r in records:
        position = str(r.get("position", "") or "")
        role = _POSITION_TO_ROLE.get(position[:1].upper()) if position else None
        row = {
            "understat_player_id": str(r.get("id", "") or ""),
            "understat_player_name": str(r.get("player_name", r.get("player", "")) or ""),
            "position": position,
            "understat_role": role,
            "team_title": str(r.get("team_title", "") or ""),
            "season_label": season_label,
        }
        for f in _SEASON_INT_FIELDS:
            row[f] = pd.to_numeric(pd.Series([r[f]]), errors="coerce").iloc[0]
        for f in _SEASON_FLOAT_FIELDS:
            row[f] = float(pd.to_numeric(pd.Series([r[f]]), errors="coerce").iloc[0])
        rows.append(row)

    frame = pd.DataFrame(rows)
    frame[list(_SEASON_INT_FIELDS)] = frame[list(_SEASON_INT_FIELDS)].astype("Int64")
    frame["minutes"] = frame["time"].astype("Int64")
    frame["source_name"] = SOURCE_NAME
    frame["source_file_hash"] = sha

    return StagedUnderstat(
        file_path=str(path),
        file_sha256=sha,
        kind="player_season",
        season_label=season_label,
        source_name=SOURCE_NAME,
        source_version=source_version,
        quality_tier=QUALITY_TIER,
        available_time=_season_end_time(season_label),
        frame=frame,
    )


# --------------------------------------------------------------------------- #
# shot events (best-effort)                                                    #
# --------------------------------------------------------------------------- #
def parse_shot_events(
    path: str | Path,
    *,
    season: str | int | None = None,
    source_version: str = DEFAULT_SOURCE_VERSION,
) -> StagedUnderstat:
    """Parse shot-level events from a saved Understat player page / JSON.

    Best-effort: Understat's ``shotsData`` var name and field spelling are not
    documented here, so anything without ``minute``/``xG``/``result`` raises.
    ``x``/``y`` come from ``X``/``Y`` (0..1 pitch fractions); ``a_player`` from
    ``player_assisted``. ``available_time`` is the latest shot ``date`` when
    present, else the season end.
    """
    path = Path(path)
    objects, sha = _load_objects(path)
    season_label = _normalise_season_label(season) or _season_from_filename(path)

    records: list[dict] = []
    for obj in objects:
        records = _records_with_keys(obj, ("minute", "xG", "result"))
        if records:
            break
    if not records:
        raise UnderstatParseError(
            f"no shot rows found in {path}; expected dicts with {_SHOT_FIELDS!r}."
        )

    rows = []
    for r in records:
        rows.append(
            {
                "minute": pd.to_numeric(pd.Series([r.get("minute")]), errors="coerce").iloc[0],
                "x": float(pd.to_numeric(pd.Series([r.get("X", r.get("x"))]), errors="coerce").iloc[0]),
                "y": float(pd.to_numeric(pd.Series([r.get("Y", r.get("y"))]), errors="coerce").iloc[0]),
                "xG": float(pd.to_numeric(pd.Series([r.get("xG")]), errors="coerce").iloc[0]),
                "result": str(r.get("result", "") or ""),
                "situation": str(r.get("situation", "") or ""),
                "shotType": str(r.get("shotType", "") or ""),
                "player": str(r.get("player", "") or ""),
                "a_player": str(r.get("player_assisted", r.get("a_player", "")) or ""),
                "match_id": str(r.get("match_id", "") or ""),
                "date": r.get("date", None),
                "season_label": season_label,
            }
        )

    frame = pd.DataFrame(rows)
    frame["minute"] = frame["minute"].astype("Int64")
    parsed_dates = pd.to_datetime(frame["date"], errors="coerce")
    frame["date"] = parsed_dates
    frame["source_name"] = SOURCE_NAME
    frame["source_file_hash"] = sha

    if parsed_dates.notna().any():
        available_time = pd.Timestamp(parsed_dates.max()).normalize()
    else:
        available_time = _season_end_time(season_label)

    return StagedUnderstat(
        file_path=str(path),
        file_sha256=sha,
        kind="shot_events",
        season_label=season_label,
        source_name=SOURCE_NAME,
        source_version=source_version,
        quality_tier=QUALITY_TIER,
        available_time=available_time,
        frame=frame,
    )


def write_staged_csv(staged: StagedUnderstat, staged_root: Path = Path("data/staged")) -> Path:
    """Write to data/staged/understat/ (gitignored — personal-use-only source)."""
    out_dir = staged_root / "understat"
    out_dir.mkdir(parents=True, exist_ok=True)
    label = staged.season_label or "unknown"
    out_path = out_dir / f"understat_{staged.kind}_{label}.csv"
    staged.frame.to_csv(out_path, index=False)
    return out_path


__all__ = [
    "UnderstatParseError",
    "StagedUnderstat",
    "parse_player_season",
    "parse_shot_events",
    "write_staged_csv",
    "SOURCE_NAME",
]
