import pandas as pd

from fantacalcio.ingest.quality import cross_source_match_rate, missingness_report


def test_missingness_report_counts_and_percentages():
    frame = pd.DataFrame({"a": [1, None, 3, None], "b": [1, 2, 3, 4]})
    report = missingness_report(frame, ["a", "b"])
    assert report.row_count == 4
    assert report.missing_by_column == {"a": 2, "b": 0}
    assert report.missing_pct_by_column == {"a": 0.5, "b": 0.0}


def test_missingness_report_empty_frame_does_not_divide_by_zero():
    frame = pd.DataFrame({"a": []})
    report = missingness_report(frame, ["a"])
    assert report.missing_pct_by_column["a"] == 1.0


def test_cross_source_match_rate_matches_within_tolerance():
    results = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2025-08-17", "2025-08-18"]),
            "home_id": ["genoa", "milan"],
            "away_id": ["inter", "napoli"],
        }
    )
    fixtures = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-08-17", "2025-08-19"]),  # second is 1 day off
            "home_id": ["genoa", "milan"],
            "away_id": ["inter", "napoli"],
        }
    )
    result = cross_source_match_rate(
        results_frame=results,
        fixtures_frame=fixtures,
        results_team_id_cols=("home_id", "away_id"),
        fixtures_team_id_cols=("home_id", "away_id"),
        date_tolerance_days=1,
    )
    assert result.matched == 2
    assert result.total_candidates == 2
    assert result.match_rate == 1.0


def test_cross_source_match_rate_reports_unmatched_sample():
    results = pd.DataFrame({"Date": pd.to_datetime(["2025-08-17"]), "home_id": ["genoa"], "away_id": ["inter"]})
    fixtures = pd.DataFrame({"date": pd.to_datetime(["2025-08-17"]), "home_id": ["milan"], "away_id": ["napoli"]})
    result = cross_source_match_rate(
        results_frame=results,
        fixtures_frame=fixtures,
        results_team_id_cols=("home_id", "away_id"),
        fixtures_team_id_cols=("home_id", "away_id"),
    )
    assert result.matched == 0
    assert result.match_rate == 0.0
    assert result.unmatched_sample == [{"date": "2025-08-17", "home_team_id": "genoa", "away_team_id": "inter"}]
