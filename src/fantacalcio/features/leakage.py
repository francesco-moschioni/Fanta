"""Automatic leakage checks for the feature layer.

Generalises ``fantacalcio.modeling.validation.assert_no_leakage`` (which compares
two match frames by ``Date``) to the long-format feature frame: no feature row
may have become available *after* the decision it is allowed to inform.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd


class LeakageError(Exception):
    """Raised when a feature row is available only after the decision time."""


def assert_available_before_decision(
    df: pd.DataFrame,
    decision_time: datetime | pd.Timestamp,
    *,
    time_col: str = "available_time",
) -> None:
    """Fail loudly if any ``df[time_col]`` is strictly after ``decision_time``.

    The error lists the offending rows (entity + feature + timestamp) so a
    failing check points straight at the leaking feature.
    """
    if time_col not in df.columns:
        raise LeakageError(f"leakage check: column {time_col!r} not in frame")
    cutoff = pd.Timestamp(decision_time)
    times = pd.to_datetime(df[time_col])
    offending = df[times > cutoff]
    if not offending.empty:
        cols = [c for c in ("entity_type", "entity_id", "feature_name", time_col) if c in offending.columns]
        preview = offending[cols].head(20).to_dict("records")
        raise LeakageError(
            f"{len(offending)} feature row(s) available after decision_time {cutoff}: {preview}"
        )


def assert_no_leakage_across_folds(
    df: pd.DataFrame,
    folds: list[tuple[datetime | pd.Timestamp, ...]],
    *,
    time_col: str = "available_time",
) -> None:
    """Batch form: run :func:`assert_available_before_decision` for every fold.

    Each entry in ``folds`` is a tuple whose first element is the fold's decision
    time (any further elements are ignored, so ``rolling_origin`` style tuples
    can be passed straight through).
    """
    for fold in folds:
        decision_time = fold[0] if isinstance(fold, (tuple, list)) else fold
        assert_available_before_decision(df, decision_time, time_col=time_col)


__all__ = [
    "LeakageError",
    "assert_available_before_decision",
    "assert_no_leakage_across_folds",
]
