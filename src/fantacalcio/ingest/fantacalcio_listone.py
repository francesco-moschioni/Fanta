"""Parsers for Fantacalcio.it "Quotazioni" and "Statistiche" Excel exports.

Same policy as fantacalcio_voti.py: manual-import only, no fetch/HTTP logic. These
exports don't carry an explicit licence banner like the voti file, but come from the
same source via the same manual-download path, so are treated with the same
personal-use-only caution by default: never committed, never redistributed.

`Id` is the same stable player identifier used in the voti exports (verified:
Carnesecchi = 4431 in both), so these three sources join cleanly without ever
touching display names.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

QUOTAZIONI_SOURCE_ID = "fantacalcio_quotazioni_manual"
STATISTICHE_SOURCE_ID = "fantacalcio_statistiche_manual"

_QUOTAZIONI_COLUMNS = {
    "Id": "player_code",
    "R": "role",
    "RM": "role_mantra",
    "Nome": "display_name",
    "Squadra": "team_name",
    "Qt.A": "quotazione_asta_classic",
    "Qt.I": "quotazione_iniziale_classic",
    "Qt.A M": "quotazione_asta_mantra",
    "Qt.I M": "quotazione_iniziale_mantra",
    "FVM": "fvm_classic",
    "FVM M": "fvm_mantra",
}

_STATISTICHE_COLUMNS = {
    "Id": "player_code",
    "R": "role",
    "Rm": "role_mantra",
    "Nome": "display_name",
    "Squadra": "team_name",
    "Pv": "matches_with_vote",
    "Mv": "voto_medio",
    "Fm": "fantamedia",
    "Gf": "goals_scored",
    "Gs": "goals_conceded",
    "Rp": "penalties_saved",
    "Rc": "penalties_taken",
    "R+": "penalties_scored",
    "R-": "penalties_missed",
    "Ass": "assists",
    "Amm": "yellow_cards",
    "Esp": "red_cards",
    "Au": "own_goals",
}


class ListoneParseError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class StagedListone:
    file_path: str
    file_sha256: str
    source_id: str
    frame: "pd.DataFrame"


def _parse(path: str | Path, column_map: dict[str, str], source_id: str, sheet: str = "Tutti") -> StagedListone:
    path = Path(path)
    if not path.is_file():
        raise ListoneParseError(f"File not found: {path}")

    try:
        raw = pd.read_excel(path, sheet_name=sheet, header=1)
    except ValueError as exc:
        raise ListoneParseError(f"Expected sheet {sheet!r} not found in {path}: {exc}") from exc

    missing = [c for c in column_map if c not in raw.columns]
    if missing:
        raise ListoneParseError(
            f"{path} sheet {sheet!r} is missing expected columns {missing}; "
            f"got {list(raw.columns)}. The export format may have changed."
        )

    frame = raw[list(column_map)].rename(columns=column_map).copy()
    frame = frame[pd.to_numeric(frame["player_code"], errors="coerce").notna()]
    frame["source_id"] = source_id
    frame["source_file_hash"] = _sha256(path)

    return StagedListone(file_path=str(path), file_sha256=_sha256(path), source_id=source_id, frame=frame)


def parse_quotazioni_file(path: str | Path) -> StagedListone:
    return _parse(path, _QUOTAZIONI_COLUMNS, QUOTAZIONI_SOURCE_ID)


def parse_statistiche_file(path: str | Path) -> StagedListone:
    return _parse(path, _STATISTICHE_COLUMNS, STATISTICHE_SOURCE_ID)


def write_staged_csv(staged: StagedListone, staged_root: Path = Path("data/staged")) -> Path:
    out_dir = staged_root / staged.source_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "latest.csv"
    staged.frame.to_csv(out_path, index=False)
    return out_path
