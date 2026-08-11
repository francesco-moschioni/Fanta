"""Exponential recency weighting shared by the voto/participation bootstrap
(docs/CURRENT_TASK.md block 4), for consistency with the exponential time-decay
already validated for team strength (Dixon-Coles, ADR-2026-011, rate `xi` per
day). The voti panel has no per-row date, only (season_label, matchday), so decay
here is expressed in "matchdays ago" (a dense chronological rank over every
distinct (season, matchday) pair actually present in the data) rather than days
-- robust to a season having fewer than 38 rounds played so far, no fixed-length
assumption baked into the index itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ~1 Serie A season (38 rounds): the same order of magnitude as Dixon-Coles'
# ~385-day (~1 year) half-life, expressed in matchdays instead of days.
DEFAULT_HALF_LIFE_MATCHDAYS = 38.0


def add_global_matchday_index(df: pd.DataFrame) -> pd.DataFrame:
    """Adds `matchday_index`: a dense, chronological rank (0-based) over every
    distinct (season_rank, matchday) pair in `df`, in order. Requires
    `season_rank` and `matchday` columns."""
    order = df[["season_rank", "matchday"]].drop_duplicates().sort_values(["season_rank", "matchday"])
    order = order.reset_index(drop=True)
    order["matchday_index"] = order.index
    return df.merge(order, on=["season_rank", "matchday"], how="left")


def add_recency_weight(
    df: pd.DataFrame,
    half_life_matchdays: float | None,
    index_col: str = "matchday_index",
    weight_col: str = "recency_weight",
) -> pd.DataFrame:
    """Adds `weight_col`: exponential decay weight relative to the most recent
    `index_col` value present in `df` (the "as of" point). `half_life_matchdays
    = None` gives every row weight 1.0 (no decay -- the pre-block-4 baseline)."""
    out = df.copy()
    if half_life_matchdays is None:
        out[weight_col] = 1.0
        return out
    max_index = out[index_col].max()
    decay_rate = np.log(2) / half_life_matchdays
    out[weight_col] = np.exp(-decay_rate * (max_index - out[index_col]))
    return out
