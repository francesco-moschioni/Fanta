import pandas as pd
import pytest

from fantacalcio.features.leakage import (
    LeakageError,
    assert_available_before_decision,
    assert_no_leakage_across_folds,
)


def _frame(times: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entity_type": ["player"] * len(times),
            "entity_id": [str(i) for i in range(len(times))],
            "feature_name": ["recency_weight"] * len(times),
            "available_time": pd.to_datetime(times),
        }
    )


def test_clean_frame_passes():
    df = _frame(["2026-07-01", "2026-07-15", "2026-08-01"])
    assert_available_before_decision(df, pd.Timestamp("2026-08-01"))


def test_one_poisoned_row_raises():
    df = _frame(["2026-07-01", "2026-08-02"])
    with pytest.raises(LeakageError, match="available after decision_time"):
        assert_available_before_decision(df, pd.Timestamp("2026-08-01"))


def test_batch_form_raises_on_any_fold():
    df = _frame(["2026-07-01", "2026-08-15"])
    folds = [
        (pd.Timestamp("2026-09-01"),),
        (pd.Timestamp("2026-08-01"), "extra-ignored"),
    ]
    with pytest.raises(LeakageError):
        assert_no_leakage_across_folds(df, folds)


def test_batch_form_passes_when_all_folds_clean():
    df = _frame(["2026-01-01", "2026-02-01"])
    folds = [(pd.Timestamp("2026-03-01"),), (pd.Timestamp("2026-06-01"),)]
    assert_no_leakage_across_folds(df, folds)
