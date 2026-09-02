"""Best starting XI for one matchday, per formation (ADR-2026-080).

The roster is small (24 players), so picking the XI is an exact per-role
top-k by ``score`` -- no solver needed. Infeasibility (not enough players of
some role for the chosen shape) is reported on the result object, never raised.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from .bench import order_bench
from .formations import Formation
from .modifier import historical_defence_modifier
from .risk_profile import RiskProfile

_ROLE_CODES = ("P", "D", "C", "A")
_ROLE_LABELS = {"P": "portieri", "D": "difensori", "C": "centrocampisti", "A": "attaccanti"}


@dataclass(frozen=True)
class PlayerSlot:
    """One roster player as seen by the lineup optimizer."""

    player_code: int
    role: str  # "P" | "D" | "C" | "A"
    score: float
    sim_mean: float
    p10: float
    p90: float
    p_vote: float
    display_name: str
    data_quality_tier: str

    def __post_init__(self) -> None:
        if self.role not in _ROLE_CODES:
            raise ValueError(f"PlayerSlot.role must be one of {_ROLE_CODES}, got {self.role!r}")


@dataclass(frozen=True)
class LineupResult:
    formation: Formation
    starters: tuple[PlayerSlot, ...] = ()
    bench: tuple[PlayerSlot, ...] = ()
    total_score: float = 0.0
    expected_points: float = 0.0
    defence_modifier_estimate: float | None = None
    feasible: bool = True
    infeasible_reason: str = ""


def _by_role(players: Sequence[PlayerSlot]) -> dict[str, list[PlayerSlot]]:
    buckets: dict[str, list[PlayerSlot]] = {r: [] for r in _ROLE_CODES}
    for p in players:
        buckets[p.role].append(p)
    for r in _ROLE_CODES:
        # Deterministic: score desc, then player_code asc as a stable tie-break.
        buckets[r].sort(key=lambda p: (-p.score, p.player_code))
    return buckets


def best_xi(
    players: list[PlayerSlot],
    formation: Formation,
    *,
    defence_modifier: bool = False,
) -> LineupResult:
    """Pick the top-scored players per role to fill ``formation``'s slots.

    When ``defence_modifier`` is True, the (unratified, historical) defence
    modifier estimate is computed from the starting goalkeeper + defenders'
    ``sim_mean`` and ADDED to ``total_score`` so :func:`compare_formations` can
    prefer solid-defence shapes. ``expected_points`` (sum of starters'
    ``sim_mean``) never includes it. When False, ``defence_modifier_estimate``
    is None and the objective is individual ``score`` only.
    """
    buckets = _by_role(players)
    starters: list[PlayerSlot] = []
    for role_code in _ROLE_CODES:
        need = formation.slots_for(role_code)
        have = buckets[role_code]
        if len(have) < need:
            return LineupResult(
                formation=formation,
                feasible=False,
                infeasible_reason=(
                    f"servono {need} {_ROLE_LABELS[role_code]} per il modulo "
                    f"{formation.name}, in rosa disponibili {len(have)}"
                ),
            )
        starters.extend(have[:need])

    starter_codes = {p.player_code for p in starters}
    bench = order_bench([p for p in players if p.player_code not in starter_codes], formation)

    total_score = sum(p.score for p in starters)
    expected_points = sum(p.sim_mean for p in starters)

    estimate: float | None = None
    if defence_modifier:
        gk_def = [p.sim_mean for p in starters if p.role in ("P", "D")]
        estimate = historical_defence_modifier(
            gk_def, n_defenders=formation.slots_for("D")
        )
        total_score += estimate

    return LineupResult(
        formation=formation,
        starters=tuple(starters),
        bench=tuple(bench),
        total_score=total_score,
        expected_points=expected_points,
        defence_modifier_estimate=estimate,
        feasible=True,
    )


def compare_formations(
    players: list[PlayerSlot],
    formations: Sequence[Formation],
    *,
    profile: RiskProfile | None = None,
    defence_modifier: bool = False,
) -> list[LineupResult]:
    """One :func:`best_xi` per formation, feasible ones first, sorted by
    ``total_score`` descending. Infeasible formations are kept in the list with
    ``feasible=False`` (flagged, not dropped).

    ``profile`` is accepted for call-site symmetry with the rest of the package;
    player scores are expected to have been computed with it already (the page
    builds :class:`PlayerSlot` with ``score`` set). It is not re-applied here.
    """
    results = [best_xi(players, f, defence_modifier=defence_modifier) for f in formations]
    results.sort(key=lambda r: (0 if r.feasible else 1, -r.total_score))
    return results
