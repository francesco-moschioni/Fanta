import pandas as pd

from fantacalcio.modeling.participation import (
    compute_season_participation,
    cross_check_against_statistiche,
    latest_known_participation,
    season_to_season_persistence,
)


def _voti_panel_row(player_code, season_label, season_rank, matchday, role="D", no_vote=False):
    return {
        "player_code": player_code,
        "season_label": season_label,
        "season_rank": season_rank,
        "matchday": matchday,
        "role": role,
        "voto_no_vote": no_vote,
        "voto": 6.0,
    }


def test_compute_season_participation_counts_distinct_matchdays():
    rows = [
        _voti_panel_row(1, "2021_22", 0, md) for md in [1, 2, 3, 5, 8]
    ]
    df = pd.DataFrame(rows)
    result = compute_season_participation(df)
    row = result.frame.iloc[0]
    assert row["player_code"] == 1
    assert row["matchdays_rated"] == 5
    assert row["participation_rate"] == 5 / 38


def test_compute_season_participation_excludes_no_vote_rows():
    rows = [
        _voti_panel_row(1, "2021_22", 0, 1),
        _voti_panel_row(1, "2021_22", 0, 2, no_vote=True),
    ]
    df = pd.DataFrame(rows)
    result = compute_season_participation(df)
    assert result.frame.iloc[0]["matchdays_rated"] == 1


def test_season_to_season_persistence_high_correlation_for_consistent_players():
    rows = []
    # Player 1: always plays a lot. Player 2: always plays little. Both consistent
    # across 3 consecutive seasons -> should show strong season-to-season correlation.
    for season_rank, mds in enumerate([range(1, 35), range(1, 33), range(1, 36)]):
        for md in mds:
            rows.append(_voti_panel_row(1, f"s{season_rank}", season_rank, md))
    for season_rank, mds in enumerate([range(1, 6), range(1, 4), range(1, 8)]):
        for md in mds:
            rows.append(_voti_panel_row(2, f"s{season_rank}", season_rank, md))
    df = pd.DataFrame(rows)
    participation = compute_season_participation(df)
    result = season_to_season_persistence(participation)
    assert result.n_pairs == 4  # 2 players * 2 consecutive-season transitions each
    assert result.correlation > 0.9
    assert result.mae_vs_carry_forward < result.mae_vs_global_mean_baseline


def test_season_to_season_persistence_skips_non_consecutive_seasons():
    rows = [_voti_panel_row(1, "s0", 0, 1), _voti_panel_row(1, "s2", 2, 1)]  # gap: no s1
    df = pd.DataFrame(rows)
    participation = compute_season_participation(df)
    result = season_to_season_persistence(participation)
    assert result.n_pairs == 0


def test_season_to_season_persistence_empty_returns_nan():
    df = pd.DataFrame(columns=["player_code", "season_label", "season_rank", "matchday", "role", "voto_no_vote", "voto"])
    participation = compute_season_participation(df)
    result = season_to_season_persistence(participation)
    assert result.n_pairs == 0
    assert result.correlation != result.correlation  # NaN check


def test_cross_check_against_statistiche_matches_consistent_data():
    rows = [_voti_panel_row(1, "2025_26", 0, md) for md in range(1, 21)]
    df = pd.DataFrame(rows)
    participation = compute_season_participation(df)
    statistiche = pd.DataFrame({"player_code": [1], "matches_with_vote": [20]})
    result = cross_check_against_statistiche(participation, statistiche, "2025_26")
    assert result.n_matched == 1
    assert result.mae == 0.0


def test_cross_check_against_statistiche_no_overlap():
    rows = [_voti_panel_row(1, "2025_26", 0, 1)]
    df = pd.DataFrame(rows)
    participation = compute_season_participation(df)
    statistiche = pd.DataFrame({"player_code": [999], "matches_with_vote": [10]})
    result = cross_check_against_statistiche(participation, statistiche, "2025_26")
    assert result.n_matched == 0


def test_latest_known_participation_picks_most_recent_season():
    rows = (
        [_voti_panel_row(1, "s0", 0, md) for md in range(1, 6)]  # 5 matchdays, season_rank 0
        + [_voti_panel_row(1, "s1", 1, md) for md in range(1, 31)]  # 30 matchdays, season_rank 1 (latest)
    )
    df = pd.DataFrame(rows)
    participation = compute_season_participation(df)
    latest = latest_known_participation(participation)
    row = latest[latest["player_code"] == 1].iloc[0]
    assert row["season_label"] == "s1"
    assert row["matchdays_rated"] == 30
    assert row["seasons_of_history"] == 2
