"""Bench ordering and warnings for the "max 5 substitutions, no switch" rule
(docs/SCORING_RULES.md; ADR-2026-080).

With no in-play position switch allowed, a substitute can only replace a
starter of the same role. So the useful bench order is: a backup goalkeeper
first, then the roles that are thinnest in the starting XI (fewest starters =
least slack if one goes to SV), and within a role by ``score`` descending.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .formations import Formation

if TYPE_CHECKING:  # pragma: no cover
    from .optimizer import PlayerSlot

_ROLE_LABELS_PLURAL = {"P": "portieri", "D": "difensori", "C": "centrocampisti", "A": "attaccanti"}
_ROLE_LABELS_SING = {"P": "portiere", "D": "difensore", "C": "centrocampista", "A": "attaccante"}


def order_bench(
    bench_players: Sequence["PlayerSlot"], formation: Formation
) -> tuple["PlayerSlot", ...]:
    """Order substitutes by usefulness under no-switch subs.

    Priority key per player: goalkeepers first; then ascending number of
    starters the formation gives that role (thinner role = higher priority);
    then ``score`` descending; then ``player_code`` ascending for determinism.
    """

    def role_priority(role_code: str) -> tuple[int, int]:
        if role_code == "P":
            return (0, 0)
        return (1, formation.slots_for(role_code))

    return tuple(
        sorted(
            bench_players,
            key=lambda p: (*role_priority(p.role), -p.score, p.player_code),
        )
    )


def bench_notes(
    bench_players: Sequence["PlayerSlot"], formation: Formation
) -> list[str]:
    """Plain-Italian warnings about how thin the bench cover is per role."""
    counts: dict[str, int] = {"P": 0, "D": 0, "C": 0, "A": 0}
    for p in bench_players:
        counts[p.role] = counts.get(p.role, 0) + 1

    notes: list[str] = []

    if counts["P"] == 0:
        notes.append("Nessun portiere di riserva in panchina.")
    elif counts["P"] == 1:
        notes.append("Solo 1 portiere di riserva.")

    for role_code in ("D", "C", "A"):
        n = counts[role_code]
        if n == 0:
            notes.append(
                f"Nessun {_ROLE_LABELS_SING[role_code]} in panchina: "
                f"{_ROLE_LABELS_PLURAL[role_code]} scoperti se un titolare non prende voto."
            )
        elif n == 1:
            notes.append(
                f"Solo 1 {_ROLE_LABELS_SING[role_code]} di riserva: "
                f"{_ROLE_LABELS_PLURAL[role_code]} scoperti se ne saltano 2."
            )

    return notes
