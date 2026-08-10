import pandas as pd
import pytest

from fantacalcio.modeling.player_voto import (
    RunningStats,
    load_player_matchday_panel,
    shrunk_estimate,
    walk_forward,
)


class TestRunningStats:
    def test_mean_none_when_empty(self):
        stats = RunningStats()
        assert stats.mean("x") is None

    def test_update_and_mean(self):
        stats = RunningStats()
        stats.update("x", 6.0)
        stats.update("x", 8.0)
        assert stats.mean("x") == 7.0


class TestShrunkEstimate:
    def test_no_history_falls_back_to_role_mean(self):
        player_stats, role_stats, global_stats = RunningStats(), RunningStats(), RunningStats()
        role_stats.update("D", 6.5)
        pred, used_role_fallback, used_global_fallback = shrunk_estimate(
            player_stats, role_stats, global_stats, player_code=1, role="D"
        )
        assert pred == 6.5
        assert used_role_fallback is True
        assert used_global_fallback is False

    def test_no_role_history_falls_back_to_global_mean(self):
        player_stats, role_stats, global_stats = RunningStats(), RunningStats(), RunningStats()
        global_stats.update("_global", 6.0)
        pred, _, used_global_fallback = shrunk_estimate(
            player_stats, role_stats, global_stats, player_code=1, role="D"
        )
        assert pred == 6.0
        assert used_global_fallback is True

    def test_shrinks_toward_role_mean_with_few_games(self):
        player_stats, role_stats, global_stats = RunningStats(), RunningStats(), RunningStats()
        role_stats.update("D", 6.0)
        player_stats.update(1, 8.0)  # one great game
        pred, used_role_fallback, _ = shrunk_estimate(
            player_stats, role_stats, global_stats, player_code=1, role="D", prior_games=8.0
        )
        assert not used_role_fallback
        # weight = 1/(1+8) = 1/9, so prediction should be close to the role mean, not 8.0
        assert 6.0 < pred < 6.3

    def test_converges_to_player_mean_with_many_games(self):
        player_stats, role_stats, global_stats = RunningStats(), RunningStats(), RunningStats()
        role_stats.update("D", 6.0)
        for _ in range(200):
            player_stats.update(1, 8.0)
        pred, _, _ = shrunk_estimate(player_stats, role_stats, global_stats, player_code=1, role="D", prior_games=8.0)
        assert pred > 7.9


def _synthetic_panel() -> pd.DataFrame:
    rows = []
    for md in range(1, 6):
        for season_label in ["2021_22"]:
            rows.append(
                {"season_label": season_label, "matchday": md, "player_code": 1, "role": "D",
                 "voto": 6.0 + 0.1 * md, "voto_no_vote": False}
            )
            rows.append(
                {"season_label": season_label, "matchday": md, "player_code": 2, "role": "A",
                 "voto": 7.0, "voto_no_vote": False}
            )
    df = pd.DataFrame(rows)
    df["season_rank"] = 0
    return df


class TestWalkForward:
    def test_no_leakage_prefix_stability(self):
        df = _synthetic_panel()
        full = walk_forward(df)
        prefix_df = df[df["matchday"] <= 3]
        prefix = walk_forward(prefix_df)

        full_first_three = full[full["matchday"] <= 3].sort_values(["matchday", "player_code"]).reset_index(drop=True)
        prefix_sorted = prefix.sort_values(["matchday", "player_code"]).reset_index(drop=True)
        pd.testing.assert_series_equal(
            full_first_three["shrinkage_pred"], prefix_sorted["shrinkage_pred"], check_names=False
        )

    def test_first_matchday_has_no_player_history(self):
        df = _synthetic_panel()
        result = walk_forward(df)
        first_md = result[result["matchday"] == 1]
        assert (first_md["player_games_seen"] == 0).all()
        assert first_md["baseline_last_value"].isna().all()

    def test_baseline_last_value_tracks_previous_actual(self):
        df = _synthetic_panel()
        result = walk_forward(df).sort_values(["player_code", "matchday"]).reset_index(drop=True)
        p1 = result[result["player_code"] == 1].reset_index(drop=True)
        for i in range(1, len(p1)):
            assert p1.loc[i, "baseline_last_value"] == p1.loc[i - 1, "actual_voto"]

    def test_no_vote_rows_are_excluded_from_scoring(self):
        df = _synthetic_panel()
        df.loc[(df["player_code"] == 1) & (df["matchday"] == 3), "voto_no_vote"] = True
        result = walk_forward(df)
        assert len(result[(result["player_code"] == 1) & (result["matchday"] == 3)]) == 0


class TestLoadPlayerMatchdayPanel:
    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_player_matchday_panel(staged_dir=tmp_path / "does_not_exist")

    def test_filters_panel_and_all_role(self, tmp_path):
        df = pd.DataFrame(
            {
                "player_code": [1, 1, 2],
                "role": ["D", "D", "ALL"],
                "voto": [6.0, 6.5, 6.0],
                "voto_no_vote": [False, False, False],
                "voto_provisional": [False, False, False],
                "panel": ["Fantacalcio", "Statistico", "Fantacalcio"],
                "season_label": ["2021_22", "2021_22", "2021_22"],
                "matchday": [1, 1, 1],
            }
        )
        df.to_csv(tmp_path / "voti_2021_22_g1.csv", index=False)
        result = load_player_matchday_panel(staged_dir=tmp_path)
        assert len(result) == 1
        assert result.iloc[0]["panel"] == "Fantacalcio"
        assert result.iloc[0]["role"] == "D"

    def test_unknown_season_label_raises(self, tmp_path):
        df = pd.DataFrame(
            {
                "player_code": [1], "role": ["D"], "voto": [6.0], "voto_no_vote": [False],
                "voto_provisional": [False], "panel": ["Fantacalcio"], "season_label": ["1999_00"],
                "matchday": [1],
            }
        )
        df.to_csv(tmp_path / "voti_1999_00_g1.csv", index=False)
        with pytest.raises(ValueError, match="not in SEASON_ORDER"):
            load_player_matchday_panel(staged_dir=tmp_path)
