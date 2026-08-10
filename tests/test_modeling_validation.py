import pandas as pd
import pytest

from fantacalcio.modeling.validation import (
    assert_no_leakage,
    load_seasons,
    log_loss,
    outcome_index,
    rolling_origin_splits,
)


def _matches(season_code: str, dates: list[str], teams=("A", "B")) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "HomeTeam": [teams[0]] * len(dates),
            "AwayTeam": [teams[1]] * len(dates),
            "FTHG": [1] * len(dates),
            "FTAG": [0] * len(dates),
            "FTR": ["H"] * len(dates),
            "season_code": [season_code] * len(dates),
        }
    )


def test_rolling_origin_splits_expanding_window():
    df = pd.concat(
        [
            _matches("2122", ["2021-08-01"]),
            _matches("2223", ["2022-08-01"]),
            _matches("2324", ["2023-08-01"]),
        ]
    )
    folds = rolling_origin_splits(df, season_order=["2122", "2223", "2324"])
    assert [f.season_code for f in folds] == ["2223", "2324"]
    assert list(folds[0].train["season_code"].unique()) == ["2122"]
    assert list(folds[1].train["season_code"].unique()) == ["2122", "2223"]


def test_assert_no_leakage_passes_for_valid_split():
    train = _matches("2122", ["2021-08-01", "2021-09-01"])
    test = _matches("2223", ["2022-08-01"])
    assert_no_leakage(train, test)  # should not raise


def test_assert_no_leakage_raises_when_train_overlaps_test():
    train = _matches("2122", ["2021-08-01", "2022-09-01"])
    test = _matches("2223", ["2022-08-01"])
    with pytest.raises(ValueError, match="Leakage"):
        assert_no_leakage(train, test)


def test_log_loss_perfect_prediction_near_zero():
    y_true = [0, 1, 2]
    probs = [(0.999, 0.0005, 0.0005), (0.0005, 0.999, 0.0005), (0.0005, 0.0005, 0.999)]
    assert log_loss(y_true, probs) < 0.01


def test_outcome_index_mapping():
    assert outcome_index(pd.Series({"FTR": "H"})) == 0
    assert outcome_index(pd.Series({"FTR": "D"})) == 1
    assert outcome_index(pd.Series({"FTR": "A"})) == 2


def test_load_seasons_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        load_seasons(["9999"], staged_root=tmp_path)


def test_load_seasons_sorts_chronologically(tmp_path):
    for code, date in [("2223", "2022-08-01"), ("2122", "2021-08-01")]:
        _matches(code, [date]).drop(columns=["season_code"]).to_csv(tmp_path / f"serie_a_{code}.csv", index=False)
    combined = load_seasons(["2223", "2122"], staged_root=tmp_path)
    assert list(combined["season_code"]) == ["2122", "2223"]
