"""Real per-team season calendar -> ``list[Fixture]`` (Engine v2 Stage 4 follow-up,
ADR-2026-077 addendum 2026-09-02).

``season.simulate_season`` needs an ordered fixture list per club so the
``Var[N]`` count term reflects the club's actual number of games and home/away
pattern instead of the neutral ``default_season_fixtures`` stand-in. This module
turns a staged OpenFootball calendar CSV (``data/staged/openfootball/serie_a_<season>.csv``,
produced by ``ingest.openfootball``) into ``{canonical_team_name: [Fixture, ...]}``.

Pure and offline: it only reads an already-staged CSV. Team names are mapped
through an explicit alias table (no fuzzy matching) so an unrecognised club name
fails loudly rather than silently dropping fixtures. ``opponent_strength`` /
``team_prior`` stay neutral here -- odds/Dixon-Coles priors are layered on
separately (Stage 2).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .season import Fixture

STAGED_OPENFOOTBALL_DIR = Path("data/staged/openfootball")

# OpenFootball long-form club name -> the short ``team_name`` used by the staged
# listone (``data/staged/fantacalcio_quotazioni_manual/<season>.csv``) and the
# rest of the pipeline. Serie A is a fixed 20-club round robin; keep this
# explicit so a renamed/promoted club is a visible KeyError, not a silent gap.
CLUB_ALIASES: dict[str, str] = {
    "AC Milan": "Milan",
    "AC Monza": "Monza",
    "ACF Fiorentina": "Fiorentina",
    "AS Roma": "Roma",
    "Atalanta BC": "Atalanta",
    "Bologna FC 1909": "Bologna",
    "Cagliari Calcio": "Cagliari",
    "Como 1907": "Como",
    "FC Internazionale Milano": "Inter",
    "Frosinone Calcio": "Frosinone",
    "Genoa CFC": "Genoa",
    "Juventus FC": "Juventus",
    "Parma Calcio 1913": "Parma",
    "SS Lazio": "Lazio",
    "SSC Napoli": "Napoli",
    "Torino FC": "Torino",
    "US Lecce": "Lecce",
    "US Sassuolo Calcio": "Sassuolo",
    "Udinese Calcio": "Udinese",
    "Venezia FC": "Venezia",
}


def _matchday_number(round_label: object) -> int:
    """``"Matchday 12"`` -> ``12``. Fails loudly on any other shape."""
    text = str(round_label).strip()
    parts = text.split()
    if len(parts) != 2 or parts[0].lower() != "matchday" or not parts[1].isdigit():
        raise ValueError(f"Unrecognised OpenFootball round label: {round_label!r}")
    return int(parts[1])


def staged_calendar_path(season: str, staged_root: Path = STAGED_OPENFOOTBALL_DIR) -> Path:
    return staged_root / f"serie_a_{season}.csv"


def load_season_fixtures(
    season: str,
    *,
    staged_root: Path = STAGED_OPENFOOTBALL_DIR,
    aliases: dict[str, str] | None = None,
) -> dict[str, list[Fixture]]:
    """``{canonical_team_name: [Fixture(matchday, is_home), ...]}`` for one season.

    Each club's list is ordered by matchday. ``matchday`` is the OpenFootball
    round number; ``is_home`` is true for the club's home games. Raises if the
    CSV is missing, a club name is not in ``aliases``, or a club does not have
    exactly ``2 * (n_clubs - 1)`` games.
    """
    path = staged_calendar_path(season, staged_root)
    if not path.is_file():
        raise FileNotFoundError(
            f"No staged OpenFootball calendar for {season} at {path}. "
            "Run ingest.openfootball.fetch_season / parse_snapshot / write_staged_csv first."
        )
    alias_map = CLUB_ALIASES if aliases is None else aliases
    frame = pd.read_csv(path)

    unknown = (set(frame["team1"]) | set(frame["team2"])) - alias_map.keys()
    if unknown:
        raise KeyError(
            f"OpenFootball calendar {path} has clubs not in the alias table: "
            f"{sorted(unknown)}. Update CLUB_ALIASES."
        )

    frame = frame.assign(_md=frame["round"].map(_matchday_number))
    frame = frame.sort_values(["_md", "date"], kind="stable")

    n_clubs = len(set(frame["team1"]) | set(frame["team2"]))
    expected_games = 2 * (n_clubs - 1)

    out: dict[str, list[Fixture]] = {}
    for long_name, short_name in alias_map.items():
        home = frame[frame["team1"] == long_name][["_md"]].assign(is_home=True)
        away = frame[frame["team2"] == long_name][["_md"]].assign(is_home=False)
        games = pd.concat([home, away]).sort_values("_md", kind="stable")
        if len(games) != expected_games:
            raise ValueError(
                f"{short_name}: found {len(games)} games in {path}, expected {expected_games}"
            )
        out[short_name] = [
            Fixture(matchday=int(md), is_home=bool(is_home))
            for md, is_home in games.itertuples(index=False)
        ]
    return out


__all__ = ["CLUB_ALIASES", "STAGED_OPENFOOTBALL_DIR", "load_season_fixtures", "staged_calendar_path"]
