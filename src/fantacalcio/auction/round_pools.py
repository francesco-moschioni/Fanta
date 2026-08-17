"""Assign players to the real G1-G4 round pools (docs/AUCTION_RULES.md, ADR-2026-013).

Per config/auction_rules.v1.yaml and docs/AUCTION_RULES.md:
  G1 = goalkeeper_blocks + defenders ranked 1-60
  G2 = midfielders ranked 1-60 + forwards ranked 1-40
  G3/G4 = everyone else (remaining_players), no role constraint

Pool cutoffs (60/60/40) are parsed from the config's own pool-name strings
(`defenders_top_1_60`, etc.) rather than hardcoded as separate Python literals --
per CLAUDE.md, "do not hardcode ... pool sizes". The pool *names* are still an
approximation of the real admin lists (docs/OPEN_QUESTIONS.md: exact thresholds
aren't independently confirmed yet, only implied by these names) -- this module
doesn't invent new numbers, it reads the ones already recorded in config.

The admin's official list and our model's ranking are different objects (per
CLAUDE.md's "non-negotiable rules" and docs/AUCTION_RULES.md's list_states table).
We don't have the real admin list yet (arrives via Google Form, per the recap in
docs/archive/Recap_regole_asta_admin_20260811.txt). This module produces a
`provisional` ranking from our own VAR (ADR-2026-019) -- explicitly labeled as
such, never silently presented as the real cutoff.
"""

from __future__ import annotations

import re

import pandas as pd

from ..config import ConfigError, Ruleset

POOL_GOALKEEPER_BLOCKS = "goalkeeper_blocks"
POOL_REMAINING = "remaining_players"
LIST_STATE_PROVISIONAL = "provisional"

_TOP_N_RE = re.compile(r"_top_1_(\d+)$")
_BAND_RE = re.compile(r"_top_(\d+)_(\d+)$")


def _pool_cutoff(ruleset: Ruleset, round_id: str, pool_name: str) -> int:
    """Read the "top N" cutoff embedded in a config pool name, e.g.
    'defenders_top_1_60' -> 60. Raises rather than guessing if the config doesn't
    actually define that pool for that round, or the name doesn't carry a number."""
    round_ = ruleset.round_by_id(round_id)
    if pool_name not in round_.pools:
        raise ConfigError(f"Round {round_id!r} does not list pool {pool_name!r} in config/auction_rules.v1.yaml")
    match = _TOP_N_RE.search(pool_name)
    if not match:
        raise ConfigError(f"Pool name {pool_name!r} doesn't carry a parseable 'top N' cutoff")
    return int(match.group(1))


def _pool_band(ruleset: Ruleset, round_id: str, pool_name: str) -> tuple[int, int]:
    """Read the (start, end) band embedded in a banded config pool name, e.g.
    'midfielders_top_21_40' -> (21, 40). Per ADR-2026-060, G2 midfielders/forwards
    are split into per-admin-list bands of 20, each its own 6-preference sealed
    bid list -- distinct from the single top-N pools used elsewhere (G1)."""
    round_ = ruleset.round_by_id(round_id)
    if pool_name not in round_.pools:
        raise ConfigError(f"Round {round_id!r} does not list pool {pool_name!r} in config/auction_rules.v1.yaml")
    match = _BAND_RE.search(pool_name)
    if not match:
        raise ConfigError(f"Pool name {pool_name!r} doesn't carry a parseable band 'top A_B'")
    return int(match.group(1)), int(match.group(2))


def _banded_pool_names(ruleset: Ruleset, round_id: str, prefix: str) -> list[str]:
    """All config pool names for `round_id` starting with `prefix`, ordered by
    their band's start position, e.g. prefix 'midfielders_' -> the 3 bands of 20
    for G2 midfielders in ascending order."""
    round_ = ruleset.round_by_id(round_id)
    names = [name for name in round_.pools if name.startswith(prefix)]
    return sorted(names, key=lambda name: _pool_band(ruleset, round_id, name)[0])


def _top_n_cutoff(role_players: pd.DataFrame, n: int, rank_col: str) -> pd.DataFrame:
    """Top `n` by `rank_col` descending; ties at the cutoff are ALL included rather
    than arbitrarily broken, since we have no tie-break rule to invent (see
    docs/OPEN_QUESTIONS.md: sealed_bid_tie_breaker is still unconfirmed)."""
    ranked = role_players.sort_values(rank_col, ascending=False)
    if len(ranked) <= n:
        return ranked
    threshold = ranked.iloc[n - 1][rank_col]
    return ranked[ranked[rank_col] >= threshold]


def _assign_banded_role(
    out: pd.DataFrame, ruleset: Ruleset, round_id: str, role_code: str, prefix: str, rank_col: str
) -> None:
    """Assign `round_pool`/`list_pool_name` in place for one role split into
    20-player bands (G2 midfielders/forwards, ADR-2026-060). Ties at the overall
    cutoff spill into the last band rather than being dropped or arbitrarily
    broken (same policy as `_top_n_cutoff`, no invented tie-break)."""
    band_names = _banded_pool_names(ruleset, round_id, prefix)
    total_n = max(_pool_band(ruleset, round_id, name)[1] for name in band_names)

    role_players = out[out["role"] == role_code]
    top = _top_n_cutoff(role_players, total_n, rank_col)
    ranked_index = list(top.sort_values(rank_col, ascending=False).index)
    out.loc[ranked_index, "round_pool"] = round_id

    for i, name in enumerate(band_names):
        start, _end = _pool_band(ruleset, round_id, name)
        if start > len(ranked_index):
            continue
        is_last_band = i == len(band_names) - 1
        band_idx = ranked_index[start - 1:] if is_last_band else ranked_index[start - 1 : _end]
        out.loc[band_idx, "list_pool_name"] = name


def assign_round_pools(player_pool: pd.DataFrame, ruleset: Ruleset, rank_col: str = "var_mean") -> pd.DataFrame:
    """`player_pool` needs `role` and `rank_col` (default: var_mean from
    src/fantacalcio/auction/replacement.py). Adds `round_pool` (G1/G2/G3_G4),
    `list_pool_name` (the config's pool identifier), and `list_state` (always
    'provisional' here -- see module docstring)."""
    defenders_cutoff = _pool_cutoff(ruleset, "G1", "defenders_top_1_60")

    out = player_pool.copy()
    out["round_pool"] = None
    out["list_pool_name"] = None

    defenders = out[out["role"] == "D"]
    top_defenders = _top_n_cutoff(defenders, defenders_cutoff, rank_col)
    out.loc[top_defenders.index, "round_pool"] = "G1"
    out.loc[top_defenders.index, "list_pool_name"] = "defenders_top_1_60"

    # All goalkeepers are notionally in the goalkeeper_blocks pool for G1 -- block
    # composition (which 3 keepers form a club's block) is a roster-construction
    # question, not a ranking one; every keeper is eligible, not just a "top N".
    goalkeepers = out[out["role"] == "P"]
    out.loc[goalkeepers.index, "round_pool"] = "G1"
    out.loc[goalkeepers.index, "list_pool_name"] = POOL_GOALKEEPER_BLOCKS

    # G2 midfielders/forwards: bands of 20, each its own list (ADR-2026-060).
    _assign_banded_role(out, ruleset, "G2", "C", "midfielders_", rank_col)
    _assign_banded_role(out, ruleset, "G2", "A", "forwards_", rank_col)

    remaining_mask = out["round_pool"].isna()
    out.loc[remaining_mask, "round_pool"] = "G3_G4"
    out.loc[remaining_mask, "list_pool_name"] = POOL_REMAINING

    out["list_state"] = LIST_STATE_PROVISIONAL
    return out


def hard_override_round_pool_from_admin_rank(
    player_pool: pd.DataFrame, ruleset: Ruleset, admin_rank_col: str = "admin_rank"
) -> pd.DataFrame:
    """For every D/C/A row with a non-null `admin_rank_col` within its role's own
    admin-list cutoff (60/60/40, read from config, never hardcoded), overwrites
    `round_pool`/`list_pool_name` with the admin list's own bucket -- replacing
    whatever `assign_round_pools`' model-VAR ranking had set there.

    Hard override, per the user's explicit instruction (2026-08-16) and
    `config/auction_rules.v1.yaml` (`official_pool_authority: admin_import`,
    `model_ranking_is_official_pool: false`): admin data always wins for any
    player it actually ranks, full stop -- not just a gap-filler. Rows without an
    `admin_rank` (not covered by the admin list) are left exactly as they were.
    Goalkeepers are out of scope here -- they're ranked as per-club blocks, not
    individual `admin_rank`, handled separately wherever `admin_gk_block_score`
    is set.

    Shared by both `apply_official_admin_list` (existing players resolved via
    `player_code`) and `scripts/add_new_signings.py` (brand-new signings that
    carry their own `admin_rank` straight from the admin list but no
    model-anchor `player_code` match) so the two paths can't silently disagree.
    """
    out = player_pool.copy()
    admin_rank = pd.to_numeric(out[admin_rank_col], errors="coerce")

    defenders_cutoff = _pool_cutoff(ruleset, "G1", "defenders_top_1_60")
    mask = (out["role"] == "D") & admin_rank.notna() & (admin_rank <= defenders_cutoff)
    out.loc[mask, "round_pool"] = "G1"
    out.loc[mask, "list_pool_name"] = "defenders_top_1_60"

    # G2 midfielders/forwards: admin_rank falls into whichever 20-player band
    # covers it (ADR-2026-060) -- the admin's own numbered list is the band
    # boundary, not a rank we compute ourselves.
    for role, prefix in (("C", "midfielders_"), ("A", "forwards_")):
        for pool_name in _banded_pool_names(ruleset, "G2", prefix):
            start, end = _pool_band(ruleset, "G2", pool_name)
            band_mask = (out["role"] == role) & admin_rank.notna() & (admin_rank >= start) & (admin_rank <= end)
            out.loc[band_mask, "round_pool"] = "G2"
            out.loc[band_mask, "list_pool_name"] = pool_name
    return out
