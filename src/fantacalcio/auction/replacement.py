"""Value above replacement (VAR): the first layer of forecast-to-bid.

Per docs/DATA_AND_MODELING.md: "Prediction is not bid" -- a raw expected fantavoto
(from the Monte Carlo model, ADR-2026-018) doesn't say anything about a player's
*auction* value without a reference point. Replacement level is that reference: the
value of the best player at that role who would NOT be rostered if every team filled
its roster from the same ranked pool. A player's VAR is what makes them worth
bidding above the pool's baseline, not their raw expected score.

Role slot counts come from config/auction_rules.v1.yaml, never hardcoded, per
CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import Ruleset

# Voti/listone role codes -> the Ruleset.roster field holding that role's per-team slot count.
_ROLE_TO_ROSTER_FIELD = {
    "P": "goalkeeper_block_size",
    "D": "defenders",
    "C": "midfielders",
    "A": "forwards",
}


class ReplacementLevelError(ValueError):
    pass


def league_slots_per_role(ruleset: Ruleset) -> dict[str, int]:
    """Total draftable slots for each role across the whole league (per-team slot
    count from config x number of teams)."""
    return {
        role: getattr(ruleset.roster, field) * ruleset.teams
        for role, field in _ROLE_TO_ROSTER_FIELD.items()
    }


@dataclass(frozen=True)
class ReplacementLevels:
    by_role: dict[str, float]  # role -> replacement-level fantavoto (mean)
    by_role_p10: dict[str, float]
    by_role_p90: dict[str, float]
    n_players_by_role: dict[str, int]
    shortfall_by_role: dict[str, int]  # slots - available, 0 if fully supplied


def compute_replacement_levels(player_pool: pd.DataFrame, ruleset: Ruleset) -> ReplacementLevels:
    """`player_pool` must have columns: role, sim_mean, sim_p10, sim_p90 (the Monte
    Carlo output, see scripts/run_monte_carlo_fantavoto.py). Replacement level for a
    role is the value of the player ranked exactly at that role's total league slot
    count -- the best player who would be left over once every team has filled that
    role. If fewer players are available than slots, the lowest-ranked available
    player stands in (with the shortfall flagged, not silently ignored)."""
    slots = league_slots_per_role(ruleset)
    unknown_roles = set(player_pool["role"].unique()) - set(slots)
    if unknown_roles:
        raise ReplacementLevelError(
            f"player_pool has role(s) with no configured roster slot count: {unknown_roles}"
        )

    by_role, by_role_p10, by_role_p90, n_players, shortfall = {}, {}, {}, {}, {}
    for role, n_slots in slots.items():
        role_players = player_pool[player_pool["role"] == role].sort_values("sim_mean", ascending=False)
        n_players[role] = len(role_players)
        shortfall[role] = max(0, n_slots - len(role_players))
        if role_players.empty:
            raise ReplacementLevelError(f"No players available for role {role!r}; cannot compute replacement level.")
        rank_idx = min(n_slots, len(role_players)) - 1  # 0-indexed rank of the replacement player
        replacement_row = role_players.iloc[rank_idx]
        by_role[role] = float(replacement_row["sim_mean"])
        by_role_p10[role] = float(replacement_row["sim_p10"])
        by_role_p90[role] = float(replacement_row["sim_p90"])

    return ReplacementLevels(
        by_role=by_role,
        by_role_p10=by_role_p10,
        by_role_p90=by_role_p90,
        n_players_by_role=n_players,
        shortfall_by_role=shortfall,
    )


def add_value_above_replacement(player_pool: pd.DataFrame, levels: ReplacementLevels) -> pd.DataFrame:
    """Adds var_mean, var_p10, var_p90 columns. Uncertainty is propagated, not
    collapsed to a point number: a player's P10 VAR uses their own P10 against the
    role's mean replacement level (a simple, transparent choice -- not a full
    distributional convolution, which would need the two distributions' shapes,
    not just their quantiles).

    Also adds `degenerate_replacement`: True for every player whose role has a
    supply shortfall (fewer players available than league-wide slots, see
    `shortfall_by_role`). When that happens, replacement level silently becomes
    "the worst available player" instead of "the best excluded player", which
    mechanically pushes every player in that role toward VAR >= 0 -- a real
    change in what the number means, not just noisier data. This flag lets the
    UI say so on the affected rows instead of only in an aggregate warning
    (statistical audit finding B2, docs/DECISIONS.md ADR-2026-038)."""
    out = player_pool.copy()
    out["replacement_level"] = out["role"].map(levels.by_role)
    out["var_mean"] = out["sim_mean"] - out["replacement_level"]
    out["var_p10"] = out["sim_p10"] - out["replacement_level"]
    out["var_p90"] = out["sim_p90"] - out["replacement_level"]
    out["degenerate_replacement"] = out["role"].map(levels.shortfall_by_role).fillna(0) > 0
    return out
