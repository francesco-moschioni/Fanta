"""Formation parsing and loading (ADR-2026-080).

A formation is written like ``"3-4-3"`` = defenders-midfielders-forwards, with
one goalkeeper always implied. The list of allowed formations is never
hardcoded: it comes from ``ruleset.formations`` (config/auction_rules.v1.yaml,
``league.formations``), per CLAUDE.md's "do not hardcode ... formations" rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Role codes as used by the DuckDB player table (`role` column) and the rest of
# the app: P/D/C/A. `ROLE_SLOTS` maps each code to the `Formation` attribute
# holding how many of that role start.
ROLE_SLOTS: dict[str, str] = {
    "P": "goalkeepers",
    "D": "defenders",
    "C": "midfielders",
    "A": "forwards",
}

_OUTFIELD_TOTAL = 10  # 11 starters minus the single goalkeeper
_DEF_RANGE = range(3, 6)  # 3..5
_MID_RANGE = range(2, 6)  # 2..5
_FWD_RANGE = range(1, 4)  # 1..3

_FORMATION_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*$")


class FormationError(ValueError):
    """Raised when a formation string is malformed or not a legal shape."""


@dataclass(frozen=True)
class Formation:
    """An immutable outfield shape. ``goalkeepers`` is always 1."""

    name: str
    defenders: int
    midfielders: int
    forwards: int
    goalkeepers: int = 1

    def __post_init__(self) -> None:
        if self.goalkeepers != 1:
            raise FormationError("a formation always has exactly one goalkeeper")
        total = self.defenders + self.midfielders + self.forwards
        if total != _OUTFIELD_TOTAL:
            raise FormationError(
                f"{self.name!r}: outfield players must sum to {_OUTFIELD_TOTAL}, got "
                f"{self.defenders}+{self.midfielders}+{self.forwards}={total}"
            )
        if self.defenders not in _DEF_RANGE:
            raise FormationError(f"{self.name!r}: defenders {self.defenders} outside 3..5")
        if self.midfielders not in _MID_RANGE:
            raise FormationError(f"{self.name!r}: midfielders {self.midfielders} outside 2..5")
        if self.forwards not in _FWD_RANGE:
            raise FormationError(f"{self.name!r}: forwards {self.forwards} outside 1..3")

    def slots_for(self, role_code: str) -> int:
        """How many players of ``role_code`` (P/D/C/A) start in this formation."""
        try:
            return getattr(self, ROLE_SLOTS[role_code])
        except KeyError:
            raise FormationError(f"unknown role code {role_code!r}") from None


def parse_formation(text: str) -> Formation:
    """``"3-4-3"`` -> ``Formation(name="3-4-3", defenders=3, midfielders=4, forwards=3)``.

    Raises :class:`FormationError` for anything that is not three
    dash-separated positive integers describing a legal shape.
    """
    if not isinstance(text, str):
        raise FormationError(f"formation must be a string, got {type(text).__name__}")
    m = _FORMATION_RE.match(text)
    if not m:
        raise FormationError(f"malformed formation string {text!r}; expected e.g. '3-4-3'")
    d, c, a = (int(g) for g in m.groups())
    canonical = f"{d}-{c}-{a}"
    return Formation(name=canonical, defenders=d, midfielders=c, forwards=a)


def load_formations(ruleset) -> list[Formation]:
    """Every allowed formation from ``ruleset.formations``, parsed and validated.

    Order is preserved from config. Raises :class:`FormationError` if config
    holds a shape this module considers illegal (fail loud, never skip).
    """
    return [parse_formation(s) for s in ruleset.formations]
