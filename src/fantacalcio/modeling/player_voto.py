"""Hierarchical (Empirical-Bayes shrinkage) baseline for player base-voto.

Scope note (see docs/CURRENT_TASK.md): this predicts the base voto for a player who
*is* rated; it does not model participation/call-up probability, because the voti
export only lists players who received a rating, not the full squad. That is a
separate, currently-blocked modeling task pending a full-roster data source.

Walk-forward by construction: matchdays are processed in chronological order: a
player/role's running statistics only ever reflect matchdays strictly before the one
being predicted, then get updated with that matchday's actual results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

STAGED_VOTI_DIR = Path("data/staged/fantacalcio_voti_manual")
PRIMARY_PANEL = "Fantacalcio"
SEASON_ORDER = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]


def load_player_matchday_panel(
    staged_dir: Path = STAGED_VOTI_DIR, season_order: list[str] = SEASON_ORDER
) -> pd.DataFrame:
    """Load every staged voti CSV, keep only the primary panel and real players
    (drop the 'ALL'/coach rows), sorted chronologically by (season, matchday)."""
    files = sorted(staged_dir.glob("voti_*.csv"))
    if not files:
        raise FileNotFoundError(f"No staged voti CSVs found in {staged_dir}")
    frames = [pd.read_csv(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df = df[(df["panel"] == PRIMARY_PANEL) & (df["role"] != "ALL")].copy()

    season_rank = {s: i for i, s in enumerate(season_order)}
    unknown = set(df["season_label"]) - set(season_rank)
    if unknown:
        raise ValueError(f"season_label(s) not in SEASON_ORDER: {unknown}")
    df["season_rank"] = df["season_label"].map(season_rank)
    df = df.sort_values(["season_rank", "matchday"]).reset_index(drop=True)
    return df


@dataclass
class RunningStats:
    sums: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)

    def mean(self, key):
        n = self.counts.get(key, 0)
        return (self.sums.get(key, 0.0) / n) if n > 0 else None

    def update(self, key, value: float) -> None:
        self.sums[key] = self.sums.get(key, 0.0) + value
        self.counts[key] = self.counts.get(key, 0) + 1


@dataclass(frozen=True)
class ShrinkagePrediction:
    player_code: int
    role: str
    predicted_voto: float
    player_games_seen: int
    used_role_fallback: bool
    used_global_fallback: bool


def shrunk_estimate(
    player_stats: RunningStats,
    role_stats: RunningStats,
    global_stats: RunningStats,
    player_code,
    role: str,
    prior_games: float = 60.0,
) -> tuple[float, bool, bool]:
    """weight = n / (n + prior_games); predicted = weight*player_mean + (1-weight)*role_mean.
    Falls back to the global mean if the role itself has no history yet (early matchdays)."""
    n = player_stats.counts.get(player_code, 0)
    player_mean = player_stats.mean(player_code)
    role_mean = role_stats.mean(role)
    global_mean = global_stats.mean("_global")

    used_global_fallback = role_mean is None
    prior_mean = role_mean if role_mean is not None else global_mean
    if prior_mean is None:
        # No history at all yet (very first matchday of the whole dataset): fall
        # back to a fixed, documented neutral prior rather than crashing.
        prior_mean = 6.0

    if n == 0 or player_mean is None:
        return prior_mean, True, used_global_fallback

    weight = n / (n + prior_games)
    predicted = weight * player_mean + (1 - weight) * prior_mean
    return predicted, False, used_global_fallback


@dataclass(frozen=True)
class BaselinePrediction:
    last_value: float | None
    role_mean: float | None
    season_to_date_mean: float | None


def walk_forward(
    df: pd.DataFrame, prior_games: float = 60.0
) -> pd.DataFrame:
    """Score every rated row with the shrinkage estimate and three baselines, all
    computed strictly from matchdays before the row's own (season, matchday)."""
    player_stats = RunningStats()
    role_stats = RunningStats()
    global_stats = RunningStats()
    last_value: dict = {}
    season_stats: dict[str, RunningStats] = {}

    records = []
    group_cols = ["season_rank", "season_label", "matchday"]
    for (_, season_label, matchday), batch in df.groupby(group_cols, sort=True):
        rated = batch[~batch["voto_no_vote"]]
        season_stat = season_stats.setdefault(season_label, RunningStats())

        for row in rated.itertuples(index=False):
            pred, used_role_fallback, used_global_fallback = shrunk_estimate(
                player_stats, role_stats, global_stats, row.player_code, row.role, prior_games
            )
            baseline = BaselinePrediction(
                last_value=last_value.get(row.player_code),
                role_mean=role_stats.mean(row.role),
                season_to_date_mean=season_stat.mean(row.player_code),
            )
            records.append(
                {
                    "season_label": season_label,
                    "matchday": matchday,
                    "player_code": row.player_code,
                    "role": row.role,
                    "actual_voto": row.voto,
                    "shrinkage_pred": pred,
                    "used_role_fallback": used_role_fallback,
                    "used_global_fallback": used_global_fallback,
                    "player_games_seen": player_stats.counts.get(row.player_code, 0),
                    "baseline_last_value": baseline.last_value,
                    "baseline_role_mean": baseline.role_mean,
                    "baseline_season_mean": baseline.season_to_date_mean,
                }
            )

        # Update running stats AFTER scoring the whole batch, so every prediction
        # in this matchday only ever saw strictly earlier matchdays.
        for row in rated.itertuples(index=False):
            player_stats.update(row.player_code, row.voto)
            role_stats.update(row.role, row.voto)
            global_stats.update("_global", row.voto)
            season_stat.update(row.player_code, row.voto)
            last_value[row.player_code] = row.voto

    return pd.DataFrame.from_records(records)


@dataclass(frozen=True)
class FittedStats:
    player_stats: RunningStats
    role_stats: RunningStats
    global_stats: RunningStats
    seasons_used: list[str]


def fit_final_stats(df: pd.DataFrame) -> FittedStats:
    """Accumulate running stats over the *entire* available history (all seasons),
    for predicting a genuinely future, unplayed season — not a backtest. Distinct
    from walk_forward: this returns final state only, no per-row scoring, since
    there's nothing to score yet for a season that hasn't happened."""
    player_stats = RunningStats()
    role_stats = RunningStats()
    global_stats = RunningStats()

    rated = df[~df["voto_no_vote"]]
    for row in rated.itertuples(index=False):
        player_stats.update(row.player_code, row.voto)
        role_stats.update(row.role, row.voto)
        global_stats.update("_global", row.voto)

    return FittedStats(
        player_stats=player_stats,
        role_stats=role_stats,
        global_stats=global_stats,
        seasons_used=sorted(df["season_label"].unique().tolist()),
    )
