"""Rolling-origin validation utilities for the team-strength models.

Per docs/DATA_AND_MODELING.md: splits must be rolling-origin/expanding-window, never
random folds across time, and every feature must be computable strictly before the
match it predicts (`available_at` <= decision time).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Re-exported for backwards compatibility: the implementation now lives in
# `fantacalcio.modeling.metrics`. Existing imports of `log_loss` from this
# module keep working unchanged.
from fantacalcio.modeling.metrics import log_loss  # noqa: F401

SEASON_ORDER = ["2122", "2223", "2324", "2425", "2526"]


def load_seasons(season_codes: list[str], staged_root: Path = Path("data/staged/football_data_co_uk")) -> pd.DataFrame:
    """Load and concatenate staged football-data.co.uk seasons, chronologically sorted.
    Raises if a requested season's staged file is missing rather than silently
    skipping it."""
    frames = []
    for code in season_codes:
        path = staged_root / f"serie_a_{code}.csv"
        if not path.is_file():
            raise FileNotFoundError(
                f"Staged season file not found: {path}. Fetch it first with "
                "fantacalcio.ingest.football_data_co_uk.fetch_season."
            )
        df = pd.read_csv(path, parse_dates=["Date"])
        df["season_code"] = code
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("Date").reset_index(drop=True)
    return combined


@dataclass(frozen=True)
class Fold:
    season_code: str
    train: pd.DataFrame
    test: pd.DataFrame


def rolling_origin_splits(df: pd.DataFrame, season_order: list[str] = SEASON_ORDER) -> list[Fold]:
    """Expanding-window, leave-one-season-out-forward splits: train on every season
    strictly before the test season. The first season in `season_order` present in
    `df` is never a test fold (no prior data to train on)."""
    present_seasons = [s for s in season_order if s in set(df["season_code"])]
    folds = []
    for i in range(1, len(present_seasons)):
        test_season = present_seasons[i]
        train_seasons = present_seasons[:i]
        train = df[df["season_code"].isin(train_seasons)].reset_index(drop=True)
        test = df[df["season_code"] == test_season].reset_index(drop=True)
        folds.append(Fold(season_code=test_season, train=train, test=test))
    return folds


def assert_no_leakage(train: pd.DataFrame, test: pd.DataFrame) -> None:
    """Fail loudly if any training match is dated on/after any test match — the
    concrete, checkable form of the `available_at` <= decision-time invariant."""
    if train.empty or test.empty:
        return
    max_train_date = train["Date"].max()
    min_test_date = test["Date"].min()
    if max_train_date >= min_test_date:
        raise ValueError(
            f"Leakage: latest training match ({max_train_date.date()}) is not strictly "
            f"before the earliest test match ({min_test_date.date()})"
        )


def outcome_index(row: pd.Series) -> int:
    return {"H": 0, "D": 1, "A": 2}[row["FTR"]]
