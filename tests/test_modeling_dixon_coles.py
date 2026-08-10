import numpy as np
import pandas as pd

from fantacalcio.modeling.dixon_coles import fit_dixon_coles


def _synthetic_matches() -> pd.DataFrame:
    rng = np.random.RandomState(42)
    teams_strong = ["Strong1", "Strong2"]
    teams_weak = ["Weak1", "Weak2"]
    rows = []
    dates = pd.date_range("2022-08-01", periods=40, freq="3D")
    all_teams = teams_strong + teams_weak
    for i, d in enumerate(dates):
        home, away = rng.choice(all_teams, size=2, replace=False)
        home_strength = 2.0 if home in teams_strong else 0.5
        away_strength = 2.0 if away in teams_strong else 0.5
        fthg = rng.poisson(home_strength)
        ftag = rng.poisson(away_strength * 0.7)
        rows.append({"Date": d, "HomeTeam": home, "AwayTeam": away, "FTHG": fthg, "FTAG": ftag})
    return pd.DataFrame(rows)


def test_fit_dixon_coles_strong_teams_have_higher_attack():
    df = _synthetic_matches()
    model = fit_dixon_coles(df, xi=0.0)  # no decay, keep it simple for this check
    avg_strong_attack = (model.attack["Strong1"] + model.attack["Strong2"]) / 2
    avg_weak_attack = (model.attack["Weak1"] + model.attack["Weak2"]) / 2
    assert avg_strong_attack > avg_weak_attack


def test_attack_parameters_sum_to_approximately_zero():
    df = _synthetic_matches()
    model = fit_dixon_coles(df, xi=0.0)
    assert abs(sum(model.attack.values())) < 1e-3


def test_expected_goals_are_positive_and_finite():
    df = _synthetic_matches()
    model = fit_dixon_coles(df)
    lh, la = model.expected_goals("Strong1", "Weak1")
    assert lh > 0 and la > 0
    assert np.isfinite(lh) and np.isfinite(la)


def test_outcome_probabilities_sum_to_one():
    df = _synthetic_matches()
    model = fit_dixon_coles(df)
    p_home, p_draw, p_away = model.outcome_probabilities("Strong1", "Weak1")
    assert abs((p_home + p_draw + p_away) - 1.0) < 1e-6
    assert p_home > 0 and p_draw > 0 and p_away > 0


def test_unknown_team_falls_back_to_average_strength_without_crashing():
    df = _synthetic_matches()
    model = fit_dixon_coles(df)
    assert not model.is_known_team("Promoted FC")
    lh, la = model.expected_goals("Promoted FC", "Strong1")
    assert np.isfinite(lh) and np.isfinite(la)
