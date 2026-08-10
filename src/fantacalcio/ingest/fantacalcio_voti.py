"""Parser for Fantacalcio.it "Voti" Excel exports — manual, user-owned import ONLY.

This module deliberately contains no fetch/download/HTTP logic. The exported file
itself states: "QUESTO FILE NON PUO' ESSERE RIPRODOTTO NE' PUBBLICATO... E' DA
CONSIDERARSI AD USO PERSONALE ESCLUSIVO" (cannot be reproduced or published; for
exclusive personal use). Per docs/SOURCE_REGISTER.md and ADR-2026-007, the only
compliant path is a human manually downloading the file from fantacalcio.it in their
browser and handing it to this pipeline — never automated retrieval.

Raw files processed by this module must never be committed to git (data/raw and
data/private are gitignored) and never redistributed outside personal/local use.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

SOURCE_ID = "fantacalcio_voti_manual"

# One sheet per rating panel ("redazione"); Fantacalcio.it reconciles across these,
# per docs/DATA_AND_MODELING.md's "miglior export riconciliato compatibile con la
# redazione". Sheet names are fixed by the export format, not user-editable.
PANELS = ("Fantacalcio", "Statistico", "Italia")

_HEADER_ROW_INDEX = 5  # 0-indexed row containing "Cod.", "Ruolo", "Nome", ...
_EXPECTED_COLUMNS = ["Cod.", "Ruolo", "Nome", "Voto", "Gf", "Gs", "Rp", "Rs", "Rf", "Au", "Amm", "Esp", "Ass"]
_NUMERIC_COLUMNS = ["Gf", "Gs", "Rp", "Rs", "Rf", "Au", "Amm", "Esp", "Ass"]

_FILENAME_RE = re.compile(r"Voti_Fantacalcio_Stagione_(\d{4})_(\d{2})_Giornata_(\d+)\.xlsx$", re.IGNORECASE)


class VotiParseError(ValueError):
    pass


@dataclass(frozen=True)
class VotiFileInfo:
    season_start_year: int
    season_end_year_suffix: int
    matchday: int

    @property
    def season_label(self) -> str:
        return f"{self.season_start_year}_{self.season_end_year_suffix:02d}"


def parse_filename(path: str | Path) -> VotiFileInfo:
    """Extract season/matchday from the standard export filename. Raises rather than
    guessing if the filename doesn't match — season/matchday must be traceable."""
    name = Path(path).name
    m = _FILENAME_RE.search(name)
    if not m:
        raise VotiParseError(
            f"Filename {name!r} does not match the expected "
            "'Voti_Fantacalcio_Stagione_YYYY_YY_Giornata_N.xlsx' pattern; "
            "pass season/matchday explicitly instead of relying on filename parsing."
        )
    return VotiFileInfo(
        season_start_year=int(m.group(1)),
        season_end_year_suffix=int(m.group(2)),
        matchday=int(m.group(3)),
    )


@dataclass(frozen=True)
class StagedVoti:
    file_path: str
    file_sha256: str
    season_label: str
    matchday: int
    frame: "pd.DataFrame"


def parse_voti_file(path: str | Path, season_label: str | None = None, matchday: int | None = None) -> StagedVoti:
    """Parse a manually-downloaded Voti_Fantacalcio_*.xlsx into a typed long frame,
    one row per (panel, player). `season_label`/`matchday` are inferred from the
    filename if not given explicitly; pass them explicitly if the file was renamed.
    """
    path = Path(path)
    if not path.is_file():
        raise VotiParseError(f"File not found: {path}")

    if season_label is None or matchday is None:
        info = parse_filename(path)
        season_label = season_label or info.season_label
        matchday = matchday if matchday is not None else info.matchday

    file_bytes = path.read_bytes()
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()

    frames = []
    for panel in PANELS:
        try:
            raw = pd.read_excel(path, sheet_name=panel, header=_HEADER_ROW_INDEX)
        except ValueError as exc:
            raise VotiParseError(f"Expected sheet {panel!r} not found in {path}: {exc}") from exc

        missing = [c for c in _EXPECTED_COLUMNS if c not in raw.columns]
        if missing:
            raise VotiParseError(
                f"Sheet {panel!r} in {path} is missing expected columns {missing}; "
                f"got {list(raw.columns)}. The export format may have changed."
            )

        # Team-name banner rows (e.g. "Atalanta") repeat through the sheet with every
        # column NaN except the team name in column 0; a real player row always has a
        # numeric player code. Drop banner rows explicitly rather than assuming row
        # positions, since team roster sizes vary.
        players = raw[pd.to_numeric(raw["Cod."], errors="coerce").notna()].copy()

        voto_str = players["Voto"].astype(str).str.strip()
        # '-' means the player was not rated this matchday (didn't play / excluded from
        # the panel), a real domain value distinct from a missing/malformed cell.
        players["voto_no_vote"] = voto_str == "-"
        players["voto_provisional"] = voto_str.str.endswith("*")
        players["voto"] = pd.to_numeric(voto_str.str.rstrip("*").str.strip(), errors="coerce")
        unparsed_voto = players[
            players["Voto"].notna() & players["voto"].isna() & ~players["voto_no_vote"]
        ]
        if len(unparsed_voto) > 0:
            raise VotiParseError(
                f"Sheet {panel!r} in {path} has {len(unparsed_voto)} 'Voto' values that "
                f"are not numeric, numeric+'*', or '-': {unparsed_voto['Voto'].unique().tolist()}"
            )

        for col in _NUMERIC_COLUMNS:
            players[col] = pd.to_numeric(players[col], errors="coerce")

        players = players.rename(
            columns={
                "Cod.": "player_code",
                "Ruolo": "role",
                "Nome": "display_name",
                "Gf": "goals_scored",
                "Gs": "goals_conceded",
                "Rp": "penalties_saved",
                "Rs": "penalties_missed",
                "Rf": "penalties_won",
                "Au": "own_goals",
                "Amm": "yellow_cards",
                "Esp": "red_cards",
                "Ass": "assists",
            }
        )
        players["panel"] = panel
        players["season_label"] = season_label
        players["matchday"] = matchday
        players["source_id"] = SOURCE_ID
        players["source_file_hash"] = file_sha256

        frames.append(
            players[
                [
                    "player_code", "role", "display_name", "voto", "voto_provisional", "voto_no_vote",
                    "goals_scored", "goals_conceded", "penalties_saved", "penalties_missed",
                    "penalties_won", "own_goals", "yellow_cards", "red_cards", "assists",
                    "panel", "season_label", "matchday", "source_id", "source_file_hash",
                ]
            ]
        )

    combined = pd.concat(frames, ignore_index=True)
    return StagedVoti(
        file_path=str(path), file_sha256=file_sha256, season_label=season_label, matchday=matchday, frame=combined
    )


def write_staged_csv(staged: StagedVoti, staged_root: Path = Path("data/staged")) -> Path:
    """Writes to data/staged/, which is gitignored — this data is personal-use-only
    per the source file's own licence text and must never be committed or shared."""
    out_dir = staged_root / SOURCE_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"voti_{staged.season_label}_g{staged.matchday}.csv"
    staged.frame.to_csv(out_path, index=False)
    return out_path
