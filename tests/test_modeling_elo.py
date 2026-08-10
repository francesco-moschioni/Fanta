import pandas as pd

from fantacalcio.modeling.elo import (
    EloRatings,
    fit_elo_sequential,
    fit_outcome_probability_model,
)


def test_expected_score_is_symmetric_at_equal_rating_no_home_advantage():
    elo = EloRatings(home_advantage=0.0)
    assert elo.expected_score("A", "B") == 0.5


def test_home_advantage_favors_home_team():
    elo = EloRatings(home_advantage=100.0)
    assert elo.expected_score("A", "B") > 0.5


def test_update_moves_winner_rating_up_and_loser_down():
    elo = EloRatings(home_advantage=0.0, k_factor=20.0)
    before_home, before_away = elo.get("A"), elo.get("B")
    elo.update("A", "B", actual_home_score=1.0)
    assert elo.get("A") > before_home
    assert elo.get("B") < before_away


def test_update_leaves_ratings_unchanged_on_expected_outcome():
    # Equal ratings, home win is more likely than 50/50 due to home advantage;
    # a draw (0.5) should pull ratings toward each other only via the expected-vs-home-advantage gap.
    elo = EloRatings(home_advantage=0.0, k_factor=20.0)
    elo.update("A", "B", actual_home_score=0.5)
    assert elo.get("A") == elo.get("B") == 1500.0  # perfectly symmetric case: no rating change


def _synthetic_matches() -> pd.DataFrame:
    # Team "Strong" always beats "Weak" at home and away, over several matches.
    rows = []
    dates = pd.date_range("2022-08-01", periods=6, freq="7D")
    for i, d in enumerate(dates):
        if i % 2 == 0:
            rows.append({"Date": d, "HomeTeam": "Strong", "AwayTeam": "Weak", "FTHG": 3, "FTAG": 0, "FTR": "H"})
        else:
            rows.append({"Date": d, "HomeTeam": "Weak", "AwayTeam": "Strong", "FTHG": 0, "FTAG": 2, "FTR": "A"})
    return pd.DataFrame(rows)


def test_fit_elo_sequential_no_leakage_prefix_stability():
    df = _synthetic_matches()
    _, diffs_full = fit_elo_sequential(df)
    _, diffs_prefix = fit_elo_sequential(df.iloc[:3])
    # The rating_diff computed before match k must be identical whether or not
    # later matches (k+1..N) are present in the input — that's the leakage-safety
    # guarantee of sequential, chronologically-ordered updates.
    assert diffs_full[:3] == diffs_prefix


def test_fit_elo_sequential_strong_team_ends_with_higher_rating():
    df = _synthetic_matches()
    elo, _ = fit_elo_sequential(df)
    assert elo.get("Strong") > elo.get("Weak")


def test_outcome_probability_model_sums_to_one_and_favors_higher_diff():
    diffs = [200.0, -200.0, 0.0, 150.0, -150.0, 50.0] * 5
    results = ["H", "A", "D", "H", "A", "H"] * 5
    model = fit_outcome_probability_model(diffs, results)

    p_home_favored = model.predict(300.0)
    p_away_favored = model.predict(-300.0)
    assert abs(sum(p_home_favored) - 1.0) < 1e-6
    assert p_home_favored[0] > p_away_favored[0]
    assert p_home_favored[0] > p_home_favored[2]
