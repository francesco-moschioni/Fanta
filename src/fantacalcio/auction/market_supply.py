"""Per-role and per-club market supply vs demand (docs/CURRENT_TASK.md).

Pure counting over data already in the player table -- no new statistics, no
prediction. Surfaces real scarcity the league-wide roster requirements
(config/auction_rules.v1.yaml, never hardcoded) imply against the actual
2026/27 listone size: e.g. ADR-2026-019's forward shortage (88 available vs
100 required) and ADR-2026-036's goalkeeper shortage (59 vs 60, plus specific
clubs too thin to supply a same-club block) were both found this way.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import Ruleset
from .replacement import league_slots_per_role


@dataclass(frozen=True)
class RoleSupply:
    role: str
    available: int
    required: int

    @property
    def shortfall(self) -> int:
        return max(0, self.required - self.available)


def compute_role_supply(player_pool: pd.DataFrame, ruleset: Ruleset) -> list[RoleSupply]:
    """`player_pool` must have a `role` column (P/D/C/A). Returns one entry per
    role in a fixed, predictable order (P, D, C, A)."""
    slots = league_slots_per_role(ruleset)
    role_order = ["P", "D", "C", "A"]
    return [
        RoleSupply(role=role, available=int((player_pool["role"] == role).sum()), required=slots[role])
        for role in role_order
        if role in slots
    ]


@dataclass(frozen=True)
class ClubGoalkeeperSupply:
    team_name: str
    goalkeeper_count: int
    can_form_same_club_block: bool


def compute_goalkeeper_club_supply(player_pool: pd.DataFrame, ruleset: Ruleset) -> list[ClubGoalkeeperSupply]:
    """Real clubs with fewer goalkeepers than `goalkeeper_block_size`: a
    same-club goalkeeper block (config: `goalkeeper_same_club`) is
    structurally impossible for anyone targeting them, not just unlucky."""
    block_size = ruleset.roster.goalkeeper_block_size
    gk = player_pool[player_pool["role"] == "P"]
    counts = gk.groupby("team_name").size()
    return sorted(
        (
            ClubGoalkeeperSupply(team_name=club, goalkeeper_count=int(n), can_form_same_club_block=n >= block_size)
            for club, n in counts.items()
        ),
        key=lambda c: (c.goalkeeper_count, c.team_name),
    )
