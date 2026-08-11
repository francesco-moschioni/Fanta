"""Uses Fantacalcio's own market valuation (FVM, already ingested from quotazioni
exports -- `docs/CURRENT_TASK.md` block 2) as a secondary prior for players whose
own-history pool is thin or empty (ADR-2026-020's `no_history_transfer`/
`no_history_new_team` tiers, and more generally any `partial_history` player).

Problem: `simulate_fantavoto`'s fallback for missing own history is the flat
role-level pool (every midfielder ever, averaged) -- which treats a squad
player and a star equally once neither has Serie A history. FVM is Fantacalcio's
own assessment of a player's market quality, known *before* the season starts
(it's part of the pre-season quotazioni release), so it's a legitimate `as_of`
prior, not a leak from the season being predicted.

This buckets each role's historical rows by the FVM their player carried in that
same historical season (quantile edges fit on training data only), so a
low/no-history player can draw from historical rows of similarly-valued players
instead of the role average.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .monte_carlo import HistoricalRow

QUOTAZIONI_DIR = Path("data/staged/fantacalcio_quotazioni_manual")
DEFAULT_N_BUCKETS = 4


def load_fvm_lookup(seasons: list[str], quotazioni_dir: Path = QUOTAZIONI_DIR) -> pd.DataFrame:
    """Returns columns [player_code, season_label, fvm_classic] across the given
    seasons. Each season's FVM is the value published for that season (pre-season,
    no leakage from future seasons)."""
    frames = []
    for season in seasons:
        path = quotazioni_dir / f"{season}.csv"
        if path.is_file():
            df = pd.read_csv(path)[["player_code", "fvm_classic"]].copy()
            df["season_label"] = season
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["player_code", "season_label", "fvm_classic"])


def fit_fvm_bucket_edges(train_fvm_by_role: pd.DataFrame, n_buckets: int = DEFAULT_N_BUCKETS) -> dict[str, np.ndarray]:
    """`train_fvm_by_role` needs columns [role, fvm_classic]. Returns role -> quantile
    edge array (from training data only), for consistent bucket assignment on
    unseen (test/target) players."""
    edges = {}
    for role, g in train_fvm_by_role.groupby("role"):
        quantiles = np.linspace(0, 1, n_buckets + 1)
        role_edges = np.unique(g["fvm_classic"].quantile(quantiles).to_numpy())
        if len(role_edges) < 2:
            role_edges = np.array([g["fvm_classic"].min(), g["fvm_classic"].max()])
        edges[role] = role_edges
    return edges


def assign_bucket(fvm: float, role: str, edges: dict[str, np.ndarray]) -> int:
    role_edges = edges.get(role)
    if role_edges is None or len(role_edges) < 2:
        return 0
    # np.digitize with the outer edges as bin boundaries; clip so values at/above
    # the max land in the last bucket instead of an out-of-range bucket.
    bucket = int(np.digitize([fvm], role_edges[1:-1], right=True)[0])
    return min(bucket, len(role_edges) - 2)


def build_fvm_bucketed_role_pools(
    rated_with_team_and_fvm: pd.DataFrame,
    edges: dict[str, np.ndarray],
) -> dict[tuple[str, int], list[HistoricalRow]]:
    """`rated_with_team_and_fvm` must have the same columns as
    `monte_carlo.build_event_pools`'s input plus `fvm_classic`. Rows with unknown
    FVM are excluded (can't bucket them)."""
    pools: dict[tuple[str, int], list[HistoricalRow]] = {}
    known = rated_with_team_and_fvm.dropna(subset=["fvm_classic"])
    for row in known.itertuples(index=False):
        bucket = assign_bucket(row.fvm_classic, row.role, edges)
        historical_row = HistoricalRow(
            voto=float(row.voto),
            role=row.role,
            goals_scored=int(row.goals_scored),
            assists=int(row.assists),
            goals_conceded=int(row.goals_conceded),
            own_goals=int(row.own_goals),
            yellow_cards=int(row.yellow_cards),
            red_cards=int(row.red_cards),
            penalties_missed=int(row.penalties_missed),
            team_goals_conceded=float(row.team_goals_conceded) if pd.notna(row.team_goals_conceded) else None,
        )
        pools.setdefault((row.role, bucket), []).append(historical_row)
    return pools
