"""Overlay the curated official admin list onto the player pool's `list_state`.

Per CLAUDE.md: the admin's official list and the model's own ranking are separate
objects, with `unknown`/`provisional`/`official` states. `round_pools.py` produces
a `provisional` G1/G2/G3_G4 assignment from the model's own VAR ranking because,
at the time it was written, the real admin list hadn't arrived yet. It has now
(`data/curated/admin_list_2026_27/`, ADR-2026-044/045): for any player the admin
list actually resolves to a `player_code`, this module flips `list_state` from
`provisional` to `official` and records the admin's own `rank`/`score` alongside
the model's, so the UI can show both without ever silently overwriting one with
the other. Players the admin list doesn't cover (or resolves to a `player_code`
we don't have, e.g. the 9 new signings) are left exactly as `round_pools.py` left
them -- still `provisional`, never force-labeled.

Goalkeepers are a separate case: the admin list's Lista 1 is a per-club block
quotation, not a per-player one (confirmed by the user), so it's merged onto
`team_name` instead of `player_code`, into its own `admin_gk_block_score` column,
never into the per-goalkeeper `admin_rank`/`admin_score` fields used by outfield
players.
"""

from __future__ import annotations

import pandas as pd


def apply_official_admin_list(
    player_pool: pd.DataFrame,
    resolved_players: pd.DataFrame,
    goalkeeper_blocks: pd.DataFrame,
) -> pd.DataFrame:
    """`player_pool` needs `player_code`, `role`, `team_name`, `list_state`.
    `resolved_players` and `goalkeeper_blocks` are the curated admin-list frames
    from `fantacalcio.identity.admin_official_list`. Returns a copy; never
    mutates the input in place."""
    out = player_pool.copy()
    out["admin_rank"] = pd.NA
    out["admin_score"] = pd.NA
    out["admin_gk_block_score"] = pd.NA

    admin_by_code = resolved_players.set_index("player_code")[["rank", "score"]]
    matched_codes = out["player_code"].isin(admin_by_code.index)
    out.loc[matched_codes, "admin_rank"] = out.loc[matched_codes, "player_code"].map(admin_by_code["rank"])
    out.loc[matched_codes, "admin_score"] = out.loc[matched_codes, "player_code"].map(admin_by_code["score"])
    out.loc[matched_codes, "list_state"] = "official"

    if not goalkeeper_blocks.empty:
        gk_score_by_team = goalkeeper_blocks.set_index("team_name_canonical")["score"]
        is_gk = out["role"] == "P"
        gk_team_matched = is_gk & out["team_name"].isin(gk_score_by_team.index)
        out.loc[gk_team_matched, "admin_gk_block_score"] = out.loc[gk_team_matched, "team_name"].map(
            gk_score_by_team
        )
        out.loc[gk_team_matched, "list_state"] = "official"

    return out
