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

Round assignment (`round_pool`/`list_pool_name`): `round_pools.assign_round_pools`
computes a `provisional` G1/G2/G3_G4 split from the model's own VAR ranking, used
only until the real admin list arrives (module docstring there). Per
`config/auction_rules.v1.yaml` (`official_pool_authority: admin_import`,
`model_ranking_is_official_pool: false`) and the user's explicit instruction
(2026-08-16, this file's ADR trail): once a player is resolved against the admin
list, the admin list's own bucket -- not the model's VAR cutoff -- decides
`round_pool`. This is a hard override: for every `official` player this function
OVERWRITES whatever `round_pool`/`list_pool_name` `assign_round_pools` had already
set, it never merely fills gaps. The admin list is treated as "closed": every
player it resolves has a definitive round; every player outside it stays exactly
as `assign_round_pools` left it (provisional G3_G4 in practice, i.e. "turno
libero").
"""

from __future__ import annotations

import pandas as pd

from ..config import Ruleset
from .round_pools import POOL_GOALKEEPER_BLOCKS, hard_override_round_pool_from_admin_rank


def apply_official_admin_list(
    player_pool: pd.DataFrame,
    resolved_players: pd.DataFrame,
    goalkeeper_blocks: pd.DataFrame,
    ruleset: Ruleset,
) -> pd.DataFrame:
    """`player_pool` needs `player_code`, `role`, `team_name`, `list_state`,
    `round_pool`, `list_pool_name` (i.e. it must already have gone through
    `round_pools.assign_round_pools`). `resolved_players` and `goalkeeper_blocks`
    are the curated admin-list frames from `fantacalcio.identity.admin_official_list`
    (`resolved_players` carries `list_number`/`rank` from the original Markdown
    blocks). `ruleset` supplies the G1/G2 pool cutoffs (60/60/40) so this module
    doesn't hardcode them, per CLAUDE.md. Returns a copy; never mutates the input
    in place.

    Synthetic new-signing rows (negative `player_code`, `scripts/add_new_signings.py`,
    ADR-2026-051) are outside this function's authority: they can never appear in
    `resolved_players` (that CSV only carries identities resolved against the
    model's own anchor roster, which these players have no `player_code` in by
    definition), so the blanket reset below used to silently wipe the
    `admin_rank`/`admin_score` those rows already carry from the admin list's own
    numbering -- a real bug found 2026-08-18: it made them fail
    `g2_envelope_feasibility.check_pick_feasibility`'s "admin_rank known" gate in
    the app, even though they ARE genuinely on the admin's official list. Their
    values are preserved across the reset instead of being recomputed here."""
    out = player_pool.copy()
    has_prior_admin_data = "admin_rank" in out.columns and "admin_score" in out.columns
    negative_code_admin_data = (
        out.loc[out["player_code"] < 0, ["player_code", "admin_rank", "admin_score"]]
        if has_prior_admin_data else pd.DataFrame(columns=["player_code", "admin_rank", "admin_score"])
    )
    out["admin_rank"] = pd.NA
    out["admin_score"] = pd.NA
    out["admin_gk_block_score"] = pd.NA
    if not negative_code_admin_data.empty:
        out = out.set_index("player_code")
        out.loc[negative_code_admin_data["player_code"], "admin_rank"] = negative_code_admin_data.set_index("player_code")["admin_rank"]
        out.loc[negative_code_admin_data["player_code"], "admin_score"] = negative_code_admin_data.set_index("player_code")["admin_score"]
        out = out.reset_index()

    admin_by_code = resolved_players.set_index("player_code")[["rank", "score", "role"]]
    matched_codes = out["player_code"].isin(admin_by_code.index)
    out.loc[matched_codes, "admin_rank"] = out.loc[matched_codes, "player_code"].map(admin_by_code["rank"])
    out.loc[matched_codes, "admin_score"] = out.loc[matched_codes, "player_code"].map(admin_by_code["score"])
    out.loc[matched_codes, "list_state"] = "official"

    # Hard override: the admin list's own rank decides the round for every
    # player it resolves, replacing the model-VAR-derived provisional round
    # rather than only filling in what's missing.
    out = hard_override_round_pool_from_admin_rank(out, ruleset)

    if not goalkeeper_blocks.empty:
        gk_score_by_team = goalkeeper_blocks.set_index("team_name_canonical")["score"]
        is_gk = out["role"] == "P"
        gk_team_matched = is_gk & out["team_name"].isin(gk_score_by_team.index)
        out.loc[gk_team_matched, "admin_gk_block_score"] = out.loc[gk_team_matched, "team_name"].map(
            gk_score_by_team
        )
        out.loc[gk_team_matched, "list_state"] = "official"
        out.loc[gk_team_matched, "round_pool"] = "G1"
        out.loc[gk_team_matched, "list_pool_name"] = POOL_GOALKEEPER_BLOCKS

    return out
