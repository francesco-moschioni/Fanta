"""Formation-strength comparison across the league's configured moduli
(docs/CURRENT_TASK.md, "confronto moduli").

Distinct from "undici ideale" (docs/UX_PRODUCT.md): that needs per-matchday
risk data (probable lineup, injuries, opponent of the week) that doesn't exist
yet (docs/OPEN_QUESTIONS.md), so nothing here can say who to start THIS week.
This answers a narrower, honestly-scoped question instead: "given the players
I actually own (real roster + locks) and their season-average VAR, which of
the league's 8 valid formations would my strongest starting XI be built
around, on average across a season?"

The auction-time roster composition (3P/8D/8C/5A, config/auction_rules.v1.yaml)
already provisions enough depth to field every configured formation at once --
the best-fitting formation doesn't change what you need to buy, only which of
the players you already own you'd start each week. That's exactly why this is
a reporting tool over an already-built roster, not a new target for
roster_optimizer.py's auction-time role slots.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Ruleset

_OUTFIELD_ROLES = ("D", "C", "A")


class FormationStrengthError(ValueError):
    pass


@dataclass(frozen=True)
class RosterPlayer:
    player_code: int
    role: str  # "P" | "D" | "C" | "A"
    var_mean: float


@dataclass(frozen=True)
class FormationStrength:
    formation: str  # e.g. "4-3-3"
    starters: tuple[RosterPlayer, ...]  # best XI found for this formation (may be short)
    total_var: float
    fully_coverable: bool  # False if fewer owned players than the formation needs in some role
    missing_by_role: dict[str, int]  # role -> how many short; empty if none


def parse_formation(formation: str) -> dict[str, int]:
    """"4-3-3" -> {"D": 4, "C": 3, "A": 3}. The goalkeeper (always 1 starter) is
    implicit, not part of the string, matching config/auction_rules.v1.yaml's
    `league.formations` format."""
    parts = formation.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise FormationStrengthError(f"Malformed formation string {formation!r}; expected 'D-C-A', e.g. '4-3-3'")
    d, c, a = (int(p) for p in parts)
    return {"D": d, "C": c, "A": a}


def compute_formation_strength(owned: list[RosterPlayer], ruleset: Ruleset) -> list[FormationStrength]:
    """For every formation in `ruleset.formations`, picks the best-VAR
    goalkeeper plus the best-VAR owned players in each outfield role up to
    that formation's count, and sums their VAR. Results are sorted by
    total_var descending, best first. A formation the roster can't fully fill
    (fewer owned players in a role than needed) is still returned, flagged via
    `fully_coverable=False` and `missing_by_role` -- never silently hidden."""
    by_role: dict[str, list[RosterPlayer]] = {"P": [], "D": [], "C": [], "A": []}
    for p in owned:
        if p.role not in by_role:
            raise FormationStrengthError(f"Unknown role {p.role!r} for player {p.player_code}")
        by_role[p.role].append(p)
    for role in by_role:
        by_role[role].sort(key=lambda p: p.var_mean, reverse=True)

    results = []
    for formation in ruleset.formations:
        needs = parse_formation(formation)
        needs["P"] = 1
        starters: list[RosterPlayer] = []
        missing: dict[str, int] = {}
        for role in ("P", *_OUTFIELD_ROLES):
            n_needed = needs[role]
            chosen = by_role[role][:n_needed]
            starters.extend(chosen)
            shortfall = n_needed - len(chosen)
            if shortfall > 0:
                missing[role] = shortfall
        results.append(
            FormationStrength(
                formation=formation,
                starters=tuple(starters),
                total_var=sum(p.var_mean for p in starters),
                fully_coverable=not missing,
                missing_by_role=missing,
            )
        )
    return sorted(results, key=lambda r: r.total_var, reverse=True)
