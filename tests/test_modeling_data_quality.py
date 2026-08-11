import pandas as pd

from fantacalcio.modeling.data_quality import (
    TIER_FULL_HISTORY,
    TIER_NO_HISTORY_NEW_TEAM,
    TIER_NO_HISTORY_TRANSFER,
    TIER_PARTIAL_HISTORY,
    add_data_quality_tier,
    classify_data_quality,
)


class TestClassifyDataQuality:
    def test_full_history_at_threshold(self):
        assert classify_data_quality(60, "Inter", {"Inter"}, full_history_threshold=60) == TIER_FULL_HISTORY

    def test_full_history_above_threshold(self):
        assert classify_data_quality(150, "Inter", {"Inter"}) == TIER_FULL_HISTORY

    def test_partial_history_below_threshold(self):
        assert classify_data_quality(5, "Inter", {"Inter"}, full_history_threshold=60) == TIER_PARTIAL_HISTORY

    def test_zero_history_known_team_is_transfer(self):
        assert classify_data_quality(0, "Inter", {"Inter", "Milan"}) == TIER_NO_HISTORY_TRANSFER

    def test_zero_history_unknown_team_is_new_team(self):
        assert classify_data_quality(0, "Frosinone", {"Inter", "Milan"}) == TIER_NO_HISTORY_NEW_TEAM


class TestAddDataQualityTier:
    def test_adds_tier_column(self):
        pool = pd.DataFrame(
            {
                "player_games_in_pool": [100, 5, 0, 0],
                "team_name": ["Inter", "Inter", "Inter", "Frosinone"],
            }
        )
        result = add_data_quality_tier(pool, known_teams={"Inter", "Milan"})
        assert list(result["data_quality_tier"]) == [
            TIER_FULL_HISTORY,
            TIER_PARTIAL_HISTORY,
            TIER_NO_HISTORY_TRANSFER,
            TIER_NO_HISTORY_NEW_TEAM,
        ]
