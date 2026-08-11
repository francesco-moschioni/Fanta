import pandas as pd
import pytest

from fantacalcio.modeling.time_decay import add_global_matchday_index, add_recency_weight


class TestAddGlobalMatchdayIndex:
    def test_assigns_dense_chronological_rank(self):
        df = pd.DataFrame(
            {"season_rank": [0, 0, 1, 1], "matchday": [2, 1, 1, 2], "player_code": [1, 2, 3, 4]}
        )
        out = add_global_matchday_index(df)
        # Sorted by (season_rank, matchday): (0,1)->0, (0,2)->1, (1,1)->2, (1,2)->3
        lookup = dict(zip(zip(out["season_rank"], out["matchday"]), out["matchday_index"]))
        assert lookup[(0, 1)] == 0
        assert lookup[(0, 2)] == 1
        assert lookup[(1, 1)] == 2
        assert lookup[(1, 2)] == 3

    def test_preserves_row_count(self):
        df = pd.DataFrame({"season_rank": [0, 0, 0], "matchday": [1, 1, 2], "player_code": [1, 2, 3]})
        out = add_global_matchday_index(df)
        assert len(out) == 3


class TestAddRecencyWeight:
    def test_no_decay_gives_weight_one(self):
        df = pd.DataFrame({"matchday_index": [0, 1, 2]})
        out = add_recency_weight(df, half_life_matchdays=None)
        assert (out["recency_weight"] == 1.0).all()

    def test_most_recent_row_gets_weight_one(self):
        df = pd.DataFrame({"matchday_index": [0, 1, 2]})
        out = add_recency_weight(df, half_life_matchdays=38.0)
        assert out.loc[out["matchday_index"] == 2, "recency_weight"].iloc[0] == 1.0

    def test_half_life_ago_gets_weight_half(self):
        df = pd.DataFrame({"matchday_index": [0, 38]})
        out = add_recency_weight(df, half_life_matchdays=38.0)
        oldest_weight = out.loc[out["matchday_index"] == 0, "recency_weight"].iloc[0]
        assert oldest_weight == pytest.approx(0.5)

    def test_older_rows_have_lower_weight(self):
        df = pd.DataFrame({"matchday_index": [0, 10, 20]})
        out = add_recency_weight(df, half_life_matchdays=38.0)
        weights = out.sort_values("matchday_index")["recency_weight"].tolist()
        assert weights[0] < weights[1] < weights[2]
