"""Pure parser for manually-saved WhoScored exports — no HTTP, ever.

Engine v2 Stage 7 (ADR-2026-079, under the personal-use override ADR-2026-070).

Per docs/SOURCE_REGISTER.md "Override d'uso personale" the only path adopted here
is a human opening the page (or an already-downloaded JSON) in their own browser
and handing the file to this parser. This module therefore contains **no fetch /
download / urllib logic** — it requires a file already on disk. Any retrieval
lives in the standalone ``whoscored_fetch.py`` script, which nothing in the
pipeline imports (``tests/test_ingest_whoscored.py`` asserts this statically).

Raw HTML/JSON is never committed (``data/raw`` and ``data/staged`` are
gitignored); test fixtures are synthetic, never real WhoScored content.

Format assumptions (no real sample was available when this was written — the
parser is defensive and raises :class:`WhoScoredParseError` on anything it does
not recognise rather than inventing data):

* The saved file is either **decoded JSON** (an array of records, or an object
  whose values hold such arrays) or an **HTML page with an embedded JSON blob**:
  a ``var <name> = {...};`` / ``= [...];`` assignment, or a
  ``JSON.parse('<payload>')`` call with ``\\xHH`` / unicode escapes (the same
  dual-mode as :mod:`fantacalcio.ingest.understat`).
* A **missing-players** record carries at least a player name and a status,
  under any of the aliases in :data:`_ALIASES` (``player_name`` / ``name`` /
  ``playerName``; ``status`` / ``type`` / ``injuryType``). Optional: team,
  reason, expected return date, report timestamp, role/position.
* Status strings are mapped to ``{out, doubtful, suspended, available}`` by
  :func:`_normalise_status`; an unrecognised status raises rather than being
  passed through.
* A **probable-lineup** record carries a player name and either an explicit
  ``is_probable_starter`` / ``probable`` boolean or a ``status`` of the form
  ``"starter"`` / ``"bench"`` / ``"doubt"``.
"""

from __future__ import annotations

import codecs
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

SOURCE_NAME = "whoscored"
DEFAULT_SOURCE_VERSION = "whoscored_manual_v1"

MISSING_STATUSES = ("out", "doubtful", "suspended", "available")

# per-row quality tier: suspensions are factual (B), injury doubt is softer (C)
_TIER_BY_STATUS = {
    "suspended": "B",
    "out": "C",
    "doubtful": "C",
    "available": "C",
}

_ALIASES = {
    "player_name": ("player_name", "name", "playername", "player"),
    "team": ("team", "team_name", "teamname", "club"),
    "status": ("status", "type", "injurytype", "availability"),
    "reason": ("reason", "injury", "comment", "knocktype", "note"),
    "expected_return": (
        "expected_return", "return_date", "expectedreturn", "returndate", "expected",
    ),
    "report_time": (
        "report_time", "reporttime", "timestamp", "updated", "last_updated",
        "lastupdated", "date", "as_of",
    ),
    "role": ("role", "position", "pos"),
    "is_probable_starter": (
        "is_probable_starter", "probable", "probable_starter", "isprobablestarter",
    ),
}

_JSON_PARSE_RE = re.compile(r"JSON\.parse\(\s*'((?:[^'\\]|\\.)*)'\s*\)")
_ASSIGN_RE = re.compile(r"=\s*(\{|\[)")


class WhoScoredParseError(ValueError):
    """Raised when a WhoScored file does not match the expected structure."""


@dataclass(frozen=True)
class StagedWhoScored:
    file_path: str
    file_sha256: str
    kind: str  # "missing_players" | "probable_lineup"
    source_name: str
    source_version: str
    quality_tier: str  # "B" iff every row is a (factual) suspension, else "C"
    available_time: pd.Timestamp
    frame: pd.DataFrame


# --------------------------------------------------------------------------- #
# embedded-JSON loading (dual-mode: decoded JSON file or HTML with a blob)      #
# --------------------------------------------------------------------------- #
def _decode_blob(payload: str) -> object:
    try:
        unescaped = codecs.decode(payload, "unicode_escape")
        try:
            unescaped = unescaped.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        return json.loads(unescaped)
    except (ValueError, json.JSONDecodeError) as exc:
        raise WhoScoredParseError(f"could not decode embedded JSON blob: {exc}") from exc


def _iter_balanced(text: str):
    """Yield every top-level ``= {...}`` / ``= [...]`` JSON value found in ``text``."""
    for m in _ASSIGN_RE.finditer(text):
        start = m.start(1)
        open_ch = text[start]
        close_ch = "}" if open_ch == "{" else "]"
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        yield json.loads(text[start : i + 1])
                    except (ValueError, json.JSONDecodeError):
                        pass
                    break


def _load_objects(path: Path) -> tuple[list, str]:
    if not path.is_file():
        raise WhoScoredParseError(f"File not found: {path}")
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", errors="replace")
    stripped = text.lstrip()
    if stripped[:1] in ("[", "{"):
        try:
            return [json.loads(text)], sha
        except (ValueError, json.JSONDecodeError) as exc:
            raise WhoScoredParseError(
                f"file looks like JSON but did not parse: {exc}"
            ) from exc

    objects: list = []
    for m in _JSON_PARSE_RE.finditer(text):
        try:
            objects.append(_decode_blob(m.group(1)))
        except WhoScoredParseError:
            continue
    objects.extend(_iter_balanced(text))
    if not objects:
        raise WhoScoredParseError(
            "no JSON payload found: expected a .json array/object or an HTML page "
            "with a `var ... = {...};` / `JSON.parse('...')` block."
        )
    return objects, sha


def _normalise_record(rec: dict) -> dict:
    low = {str(k).lower(): v for k, v in rec.items()}
    out: dict = {}
    for canonical, aliases in _ALIASES.items():
        for a in aliases:
            if a in low and low[a] not in (None, ""):
                out[canonical] = low[a]
                break
    return out


def _records_with(objects: list, need: tuple[str, ...]) -> list[dict]:
    def _ok(d: object) -> bool:
        if not isinstance(d, dict):
            return False
        norm = _normalise_record(d)
        return all(k in norm for k in need)

    found: list[dict] = []
    for obj in objects:
        if isinstance(obj, list):
            found.extend(_normalise_record(d) for d in obj if _ok(d))
        elif isinstance(obj, dict):
            if _ok(obj):
                found.append(_normalise_record(obj))
            for v in obj.values():
                if isinstance(v, list):
                    found.extend(_normalise_record(d) for d in v if _ok(d))
        if found:
            break
    return found


def _normalise_status(raw: object) -> str:
    s = str(raw).strip().lower()
    if not s:
        raise WhoScoredParseError("empty status")
    if "susp" in s or "squalif" in s or "banned" in s or s == "ban":
        return "suspended"
    if any(t in s for t in ("doubt", "question", "%", "knock", "test", "50", "75")):
        return "doubtful"
    if any(t in s for t in ("out", "injur", "ruled", "unavail")):
        return "out"
    if any(t in s for t in ("available", "fit", "ok", "starter", "bench")):
        return "available"
    raise WhoScoredParseError(f"unrecognised WhoScored status {raw!r}; refusing to guess")


def _report_time(records: list[dict], override) -> pd.Timestamp:
    if override is not None:
        return pd.Timestamp(override)
    times = pd.to_datetime(
        pd.Series([r.get("report_time") for r in records]), errors="coerce"
    )
    if times.notna().any():
        return pd.Timestamp(times.max())
    raise WhoScoredParseError(
        "cannot determine the report timestamp (no report_time/updated/date field "
        "and none passed as report_time=...); available_time must be traceable."
    )


# --------------------------------------------------------------------------- #
# public parsers                                                               #
# --------------------------------------------------------------------------- #
def parse_missing_players(
    path: str | Path,
    *,
    report_time=None,
    source_version: str = DEFAULT_SOURCE_VERSION,
) -> StagedWhoScored:
    """Parse an injuries / suspensions / doubtful list from a saved WhoScored file.

    Rows: ``player_name, team, status, reason, expected_return, report_time,
    role, quality_tier``. ``available_time`` is the report timestamp.
    """
    path = Path(path)
    objects, sha = _load_objects(path)
    records = _records_with(objects, ("player_name", "status"))
    if not records:
        raise WhoScoredParseError(
            f"no missing-player rows found in {path}; expected dicts with a player "
            "name and a status."
        )

    avail = _report_time(records, report_time)
    rows = []
    for r in records:
        status = _normalise_status(r["status"])
        exp = pd.to_datetime(r.get("expected_return"), errors="coerce")
        rows.append(
            {
                "player_name": str(r["player_name"]),
                "team": str(r.get("team", "") or ""),
                "role": (str(r["role"]) if r.get("role") not in (None, "") else None),
                "status": status,
                "reason": str(r.get("reason", "") or ""),
                "expected_return": (None if pd.isna(exp) else pd.Timestamp(exp)),
                "report_time": pd.Timestamp(
                    pd.to_datetime(r.get("report_time"), errors="coerce")
                )
                if pd.notna(pd.to_datetime(r.get("report_time"), errors="coerce"))
                else avail,
                "quality_tier": _TIER_BY_STATUS[status],
            }
        )

    frame = pd.DataFrame(rows)
    frame["source_name"] = SOURCE_NAME
    frame["source_file_hash"] = sha
    tier = "B" if (frame["quality_tier"] == "B").all() else "C"
    return StagedWhoScored(
        file_path=str(path),
        file_sha256=sha,
        kind="missing_players",
        source_name=SOURCE_NAME,
        source_version=source_version,
        quality_tier=tier,
        available_time=avail,
        frame=frame,
    )


def parse_probable_lineup(
    path: str | Path,
    *,
    report_time=None,
    source_version: str = DEFAULT_SOURCE_VERSION,
) -> StagedWhoScored:
    """Best-effort parse of a probable-lineup file: ``player_name, team,
    is_probable_starter``. ``available_time`` is the report timestamp,
    ``quality_tier`` is C (a projection, not a fact)."""
    path = Path(path)
    objects, sha = _load_objects(path)
    records = _records_with(objects, ("player_name",))
    if not records:
        raise WhoScoredParseError(
            f"no probable-lineup rows found in {path}; expected dicts with a player name."
        )
    avail = _report_time(records, report_time)

    rows = []
    for r in records:
        if "is_probable_starter" in r:
            is_starter = bool(r["is_probable_starter"])
        elif "status" in r:
            s = str(r["status"]).strip().lower()
            if s in ("starter", "start", "xi", "probable"):
                is_starter = True
            elif s in ("bench", "sub", "doubt", "out"):
                is_starter = False
            else:
                raise WhoScoredParseError(
                    f"cannot read probable-starter flag from status {r['status']!r}"
                )
        else:
            raise WhoScoredParseError(
                "probable-lineup row has neither is_probable_starter nor a status field"
            )
        rows.append(
            {
                "player_name": str(r["player_name"]),
                "team": str(r.get("team", "") or ""),
                "role": (str(r["role"]) if r.get("role") not in (None, "") else None),
                "is_probable_starter": is_starter,
            }
        )

    frame = pd.DataFrame(rows)
    frame["source_name"] = SOURCE_NAME
    frame["source_file_hash"] = sha
    return StagedWhoScored(
        file_path=str(path),
        file_sha256=sha,
        kind="probable_lineup",
        source_name=SOURCE_NAME,
        source_version=source_version,
        quality_tier="C",
        available_time=avail,
        frame=frame,
    )


def write_staged_csv(
    staged: StagedWhoScored, staged_root: Path = Path("data/staged")
) -> Path:
    """Write to data/staged/whoscored/ (gitignored — personal-use-only source)."""
    out_dir = staged_root / "whoscored"
    out_dir.mkdir(parents=True, exist_ok=True)
    label = pd.Timestamp(staged.available_time).strftime("%Y%m%d")
    out_path = out_dir / f"whoscored_{staged.kind}_{label}.csv"
    staged.frame.to_csv(out_path, index=False)
    return out_path


__all__ = [
    "WhoScoredParseError",
    "StagedWhoScored",
    "parse_missing_players",
    "parse_probable_lineup",
    "write_staged_csv",
    "SOURCE_NAME",
    "MISSING_STATUSES",
]
