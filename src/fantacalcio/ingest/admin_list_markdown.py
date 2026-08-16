"""Parser for the official admin ranking list, delivered as a Markdown file.

Manual-import only, same policy as fantacalcio_listone.py: no fetch/HTTP logic,
requires a file already on disk. This format is a *different* object from the
Fantacalcio.it Quotazioni/Statistiche exports: it carries no stable `Id`, only a
display name and a score per role-ranked block. Per docs/DATA_AND_MODELING.md,
this file is staged as-is (immutable raw record); identity resolution against
`player_code` happens as a separate, explicit step (see
fantacalcio.identity.player_name_resolver), never a silent join on name.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_HEADER_RE = re.compile(r"\*\*Lista\s+(\d+)\s*\(([^)]*)\)\*\*", re.IGNORECASE)
_ROW_RE = re.compile(r"^(\d+)\.\s+(.+?)\s+(-?\d+(?:\.\d+)?)\s*$")
_SEPARATOR_RE = re.compile(r"^\\?-\s*$")

# Role tokens as they appear in the "(...)" header portion, e.g. "1-20 Portieri".
_ROLE_KEYWORDS = {
    "portieri": "P",
    "difensori": "D",
    "centrocampisti": "C",
    "attaccanti": "A",
}


class AdminListParseError(ValueError):
    pass


@dataclass(frozen=True)
class StagedAdminList:
    file_path: str
    file_sha256: str
    source_id: str
    frame: "pd.DataFrame"
    unparsed_lines: list[str]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _role_from_header_label(label: str) -> str | None:
    label_lower = label.lower()
    for keyword, role in _ROLE_KEYWORDS.items():
        if keyword in label_lower:
            return role
    return None


SOURCE_ID = "admin_list_markdown"


def parse_admin_list_markdown(path: str | Path) -> StagedAdminList:
    """Parse a Markdown admin list into (list_number, role, rank, display_name, score).

    Blocks with a header role we cannot recognize (e.g. a "Portieri" block whose rows
    are actually team names, not player names) are still parsed structurally but the
    resulting rows carry `role=None`, so downstream identity resolution can flag and
    exclude them rather than silently mis-tagging role.

    List 1 ("Portieri") is a known special case in this format: its rows are team
    names, not individual goalkeeper names — it represents a per-team goalkeeper-slot
    quotation, not a per-player ranking (confirmed by the user for the 2026/27 file).
    Those rows get `entity_type="team"` so downstream resolution matches them against
    team identity (fantacalcio.identity.teams), never against player `player_code`.
    """
    path = Path(path)
    if not path.is_file():
        raise AdminListParseError(f"File not found: {path}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    records: list[dict] = []
    unparsed: list[str] = []
    current_list_number: int | None = None
    current_role: str | None = None
    current_header_label: str | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        header_match = _HEADER_RE.search(line)
        if header_match:
            current_list_number = int(header_match.group(1))
            current_header_label = header_match.group(2).strip()
            current_role = _role_from_header_label(current_header_label)
            continue

        if _SEPARATOR_RE.match(line):
            continue

        row_match = _ROW_RE.match(line)
        if row_match:
            if current_list_number is None:
                unparsed.append(raw_line)
                continue
            rank = int(row_match.group(1))
            display_name = row_match.group(2).strip()
            score = float(row_match.group(3))
            records.append(
                {
                    "list_number": current_list_number,
                    "list_header_label": current_header_label,
                    "role": current_role,
                    "rank": rank,
                    "display_name": display_name,
                    "score": score,
                    "entity_type": "team" if current_list_number == 1 else "player",
                }
            )
            continue

        unparsed.append(raw_line)

    if not records:
        raise AdminListParseError(f"No parseable rows found in {path}")

    frame = pd.DataFrame.from_records(records)
    frame["source_id"] = SOURCE_ID
    frame["source_file_hash"] = _sha256(path)

    return StagedAdminList(
        file_path=str(path),
        file_sha256=_sha256(path),
        source_id=SOURCE_ID,
        frame=frame,
        unparsed_lines=unparsed,
    )


def write_staged_csv(staged: StagedAdminList, staged_root: Path = Path("data/staged")) -> Path:
    out_dir = staged_root / staged.source_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{staged.file_sha256[:12]}.csv"
    staged.frame.to_csv(out_path, index=False)
    return out_path
