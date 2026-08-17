import pandas as pd
import pytest

from fantacalcio.auction.bid_recommendation import (
    BidRecommendationError,
    budget_available_for_round,
    budget_remaining_for_round,
    recommend_max_bid,
    remaining_roster_slots,
)
from fantacalcio.domain import AssignmentEvent, AssignmentItem, Role, replay


def _pool(rows):
    return pd.DataFrame(rows, columns=["player_code", "var_mean"])


class TestBudgetHelpers:
    def test_budget_available_for_started_round(self, ruleset):
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-01",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("def-01",)), amount=10,
                source="test", author="test",
            )
        ]
        state = replay(ruleset, events)
        team = state.team("team-01")
        assert budget_available_for_round(team, "G1", ruleset) == 200
        assert budget_remaining_for_round(team, "G1", ruleset) == 190

    def test_budget_for_not_yet_started_round_evaluates_expression(self, ruleset):
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-01",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("def-01",)), amount=50,
                source="test", author="test",
            )
        ]
        state = replay(ruleset, events)
        team = state.team("team-01")
        # G2 hasn't started for this team: available = remaining_G1 (150) + 100 = 250
        assert budget_available_for_round(team, "G2", ruleset) == 250
        assert budget_remaining_for_round(team, "G2", ruleset) == 250  # nothing spent yet

    def test_remaining_roster_slots_reads_from_config(self, ruleset):
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-01",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("def-01",)), amount=10,
                source="test", author="test",
            )
        ]
        state = replay(ruleset, events)
        team = state.team("team-01")
        slots = remaining_roster_slots(team, ruleset)
        assert slots["D"] == ruleset.roster.defenders - 1
        assert slots["P"] == ruleset.roster.goalkeeper_block_size
        assert slots["C"] == ruleset.roster.midfielders
        assert slots["A"] == ruleset.roster.forwards


class TestRecommendMaxBid:
    def test_higher_var_gets_higher_max_bid(self, ruleset):
        events: list = []
        state = replay(ruleset, events)
        pool = _pool([(1, 5.0), (2, 1.0), (3, 0.5)])
        rec_high = recommend_max_bid(state, ruleset, "team-01", "G1", 1, 5.0, pool)
        rec_low = recommend_max_bid(state, ruleset, "team-01", "G1", 2, 1.0, pool)
        assert rec_high.max_bid > rec_low.max_bid

    def test_max_bid_never_exceeds_remaining_budget(self, ruleset):
        state = replay(ruleset, [])
        pool = _pool([(1, 100.0)])  # absurdly high VAR
        rec = recommend_max_bid(state, ruleset, "team-01", "G1", 1, 100.0, pool)
        assert rec.max_bid <= rec.remaining_budget

    def test_reserve_scales_with_remaining_slots(self, ruleset):
        state = replay(ruleset, [])
        pool = _pool([(1, 5.0), (2, 5.0)])
        rec = recommend_max_bid(state, ruleset, "team-01", "G1", 1, 5.0, pool)
        slots = remaining_roster_slots(state.team("team-01"), ruleset)
        assert rec.reserve_for_other_slots == sum(slots.values()) - 1

    def test_player_not_in_pool_raises(self, ruleset):
        state = replay(ruleset, [])
        pool = _pool([(2, 5.0)])
        with pytest.raises(BidRecommendationError, match="not in the undrafted pool"):
            recommend_max_bid(state, ruleset, "team-01", "G1", 999, 5.0, pool)

    def test_assigned_players_excluded_from_pool(self, ruleset):
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-02",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("1",)), amount=10,
                source="test", author="test",
            )
        ]
        state = replay(ruleset, events)
        pool = _pool([(1, 5.0), (2, 3.0)])
        with pytest.raises(BidRecommendationError, match="not in the undrafted pool"):
            recommend_max_bid(state, ruleset, "team-01", "G1", 1, 5.0, pool)

    def test_zero_pool_var_splits_evenly(self, ruleset):
        state = replay(ruleset, [])
        pool = _pool([(1, -1.0), (2, -2.0)])  # both below replacement
        rec = recommend_max_bid(state, ruleset, "team-01", "G1", 1, -1.0, pool)
        assert rec.var_share == 0.5

    def test_full_roster_raises(self, ruleset, monkeypatch):
        import fantacalcio.auction.bid_recommendation as mod

        monkeypatch.setattr(mod, "remaining_roster_slots", lambda team, rs: {"P": 0, "D": 0, "C": 0, "A": 0})
        state = replay(ruleset, [])
        pool = _pool([(1, 5.0)])
        with pytest.raises(BidRecommendationError, match="already full"):
            recommend_max_bid(state, ruleset, "team-01", "G1", 1, 5.0, pool)


class TestMarketContext:
    def _players_conn(self, tmp_path, rows):
        from fantacalcio.persistence.player_table import REQUIRED_COLUMNS, build_player_table, connect

        def _row(player_code, role="D", quotazione_asta=10):
            defaults = {c: None for c in REQUIRED_COLUMNS}
            defaults.update(
                player_code=player_code, display_name=f"P{player_code}", role=role, team_name="Roma",
                quotazione_asta=quotazione_asta, admin_score=None,
                sim_mean=6.5, sim_median=6.0, sim_p10=5.0, sim_p90=8.0,
                player_games_in_pool=50, used_role_pool_only=False, replacement_level=5.5,
                var_mean=1.0, var_p10=-0.5, var_p90=2.5, data_quality_tier="full_history",
                round_pool="G1", list_pool_name="defenders_top_1_60", list_state="provisional",
            )
            return defaults

        csv_path = tmp_path / "source.csv"
        df = pd.DataFrame([_row(*r) for r in rows])
        if "admin_score" not in df.columns:
            df["admin_score"] = None
        df.to_csv(csv_path, index=False)
        db_path = tmp_path / "db.duckdb"
        build_player_table(source_csv=csv_path, db_path=db_path)
        return connect(db_path)

    def test_no_market_context_leaves_max_bid_equal_to_base_bid(self, ruleset):
        state = replay(ruleset, [])
        pool = _pool([(1, 5.0), (2, 1.0)])
        rec = recommend_max_bid(state, ruleset, "team-01", "G1", 1, 5.0, pool)
        assert rec.max_bid == rec.base_bid
        assert rec.inflation_ratio is None
        assert "Correzione di mercato non disponibile" in rec.explanation[-2]

    def test_inflation_scales_up_max_bid(self, ruleset, tmp_path):
        # historical data: defenders paid 2x quotazione in a different round
        history = [
            AssignmentEvent(
                event_id=f"h{i}", ts="t", round_id="G3", team_id="team-99",
                pool_id="remaining_players", role=Role.DEF,
                item=AssignmentItem(player_ids=(str(100 + i),)), amount=20,
                source="test", author="test",
            )
            for i in range(3)
        ]
        # need those historical players priced too
        conn2 = self._players_conn(tmp_path, [(10, "D", 10)] + [(100 + i, "D", 10) for i in range(3)])
        state = replay(ruleset, [])
        pool = _pool([(10, 5.0)])
        rec = recommend_max_bid(
            state, ruleset, "team-01", "G1", 10, 5.0, pool,
            voti_role="D", player_conn=conn2, all_events=history,
        )
        assert rec.inflation_ratio == pytest.approx(2.0)
        assert rec.inflation_n == 3
        assert rec.max_bid == min(int(round(rec.base_bid * 2.0)), rec.remaining_budget)
        assert any("Correzione di mercato" in line for line in rec.explanation)

    def test_current_round_excluded_from_inflation_baseline(self, ruleset, tmp_path):
        conn = self._players_conn(tmp_path, [(10, "D", 10), (11, "D", 10)])
        # a purchase in the SAME round being bid on must not count as history
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-02",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("11",)), amount=50,
                source="test", author="test",
            )
        ]
        state = replay(ruleset, events)
        pool = _pool([(10, 5.0)])
        rec = recommend_max_bid(
            state, ruleset, "team-01", "G1", 10, 5.0, pool,
            voti_role="D", player_conn=conn, all_events=events,
        )
        assert rec.inflation_ratio is None
        assert rec.max_bid == rec.base_bid

    def test_competition_signal_reported_not_multiplied(self, ruleset, tmp_path):
        conn = self._players_conn(tmp_path, [(10, "D", 10)])
        state = replay(ruleset, [])
        pool = _pool([(10, 5.0)])
        rec = recommend_max_bid(
            state, ruleset, "team-01", "G1", 10, 5.0, pool,
            voti_role="D", opponent_ids=["team-02", "team-03"],
        )
        assert rec.competition_teams_total == 2
        assert rec.competition_teams_needing == 2  # neither has bought anything yet
        assert rec.max_bid == rec.base_bid  # competition never changes the price
        assert any("Concorrenza stimata" in line for line in rec.explanation)
