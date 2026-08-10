import pandas as pd

from fantacalcio.modeling.baselines import (
    fit_constant_outcome_baseline,
    fit_previous_season_average_goals,
)


def test_fit_constant_outcome_baseline_matches_empirical_rates():
    train = pd.DataFrame({"FTR": ["H", "H", "D", "A"]})
    baseline = fit_constant_outcome_baseline(train)
    assert baseline.p_home == 0.5
    assert baseline.p_draw == 0.25
    assert baseline.p_away == 0.25
    preds = baseline.predict(3)
    assert preds == [(0.5, 0.25, 0.25)] * 3


def test_fit_previous_season_average_goals():
    train = pd.DataFrame({"FTHG": [2, 0, 1], "FTAG": [1, 1, 0]})
    baseline = fit_previous_season_average_goals(train)
    assert baseline.avg_home_goals == 1.0
    assert round(baseline.avg_away_goals, 4) == round(2 / 3, 4)
