import pandas as pd
import pytest

from fantacalcio.auction.market_model import (
    MIN_RELIABLE_SAMPLE,
    all_opponent_profiles,
    opponent_profile,
    round_role_inflation,
)
from fantacalcio.domain import AssignmentEvent, AssignmentItem, Role, replay
from fantacalcio.persistence.player_table import REQUIRED_COLUMNS, build_player_table, connect


def _row(player_code, display_name="Player", role="D", team_name="Roma", quotazione_asta=10, admin_score=None, **kwargs):
    defaults = {c: None for c in REQUIRED_COLUMNS}
    defaults.update(
        player_code=player_code, display_name=display_name, role=role, team_name=team_name,
        quotazione_asta=quotazione_asta, admin_score=admin_score,
        sim_mean=6.5, sim_median=6.0, sim_p10=5.0, sim_p90=8.0,
        player_games_in_pool=50, used_role_pool_only=False, replacement_level=5.5,
        var_mean=1.0, var_p10=-0.5, var_p90=2.5, data_quality_tier="full_history",
        round_pool="G1", list_pool_name="defenders_top_1_60", list_state="provisional",
    )
    defaults.update(kwargs)
    return defaults


def _players_conn(tmp_path, rows):
    csv_path = tmp_path / "source.csv"
    df = pd.DataFrame(rows)
    if "admin_score" not in df.columns:
        df["admin_score"] = None
    df.to_csv(csv_path, index=False)
    db_path = tmp_path / "db.duckdb"
    build_player_table(source_csv=csv_path, db_path=db_path)
    return connect(db_path)


def _assign(event_id, team_id, round_id, role, pool_id, player_ids, amount):
    return AssignmentEvent(
        event_id=event_id, ts="t", round_id=round_id, team_id=team_id,
        pool_id=pool_id, role=role, item=AssignmentItem(player_ids=player_ids),
        amount=amount, source="test", author="test",
    )


class TestOpponentProfile:
    def test_slots_and_budget_reflect_state(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1, quotazione_asta=10), _row(2, quotazione_asta=20)])
        events = [_assign("e1", "team-01", "G1", Role.DEF, "defenders_top_1_60", ("1",), 15)]
        state = replay(ruleset, events)
        profile = opponent_profile(state, ruleset, conn, "team-01", "G1")
        assert profile.slots_needed["D"] == ruleset.roster.defenders - 1
        assert profile.budget_remaining == 200 - 15
        assert profile.budget_per_open_slot is not None
        assert profile.players_bought == 1

    def test_full_roster_has_no_budget_per_slot(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1)])
        # team-01 with a full roster: zero slots needed anywhere -> budget_per_open_slot is None
        from fantacalcio.domain import LeagueState, TeamState, TeamRoundBudget

        team = TeamState(team_id="team-01")
        team.budgets["G1"] = TeamRoundBudget(available=200, spent=50)
        team.roster[Role.GK] = ["g1", "g2", "g3"]
        team.roster[Role.DEF] = [f"d{i}" for i in range(ruleset.roster.defenders)]
        team.roster[Role.MID] = [f"m{i}" for i in range(ruleset.roster.midfielders)]
        team.roster[Role.FWD] = [f"f{i}" for i in range(ruleset.roster.forwards)]
        state = LeagueState(ruleset=ruleset, teams={"team-01": team})
        profile = opponent_profile(state, ruleset, conn, "team-01", "G1")
        assert sum(profile.slots_needed.values()) == 0
        assert profile.budget_per_open_slot is None

    def test_quality_signal_reflects_above_average_purchase(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [
            _row(1, quotazione_asta=10),
            _row(2, quotazione_asta=10),
            _row(3, quotazione_asta=50),  # bought by team-01, well above league avg (10)
        ])
        events = [_assign("e1", "team-01", "G1", Role.DEF, "defenders_top_1_60", ("3",), 50)]
        state = replay(ruleset, events)
        profile = opponent_profile(state, ruleset, conn, "team-01", "G1")
        assert profile.quality_signal["D"] > 0

    def test_no_purchase_means_no_quality_entry(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1)])
        state = replay(ruleset, [])
        profile = opponent_profile(state, ruleset, conn, "team-01", "G1")
        assert "D" not in profile.quality_signal

    def test_all_opponent_profiles_covers_every_team(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1)])
        state = replay(ruleset, [])
        profiles = all_opponent_profiles(state, ruleset, conn, "G1", ["team-01", "team-02"])
        assert {p.team_id for p in profiles} == {"team-01", "team-02"}


class TestRoundRoleInflation:
    def test_ratio_computed_from_amount_over_quotazione(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1, quotazione_asta=10)])
        events = [_assign("e1", "team-01", "G1", Role.DEF, "defenders_top_1_60", ("1",), 20)]
        results = round_role_inflation(events, conn, "G1")
        assert len(results) == 1
        assert results[0].role == "D"
        assert results[0].n == 1
        assert results[0].mean_ratio == 2.0
        assert results[0].reliable is False  # n=1 < MIN_RELIABLE_SAMPLE

    def test_reliable_flag_true_at_threshold(self, ruleset, tmp_path):
        rows = [_row(i, quotazione_asta=10) for i in range(1, MIN_RELIABLE_SAMPLE + 1)]
        conn = _players_conn(tmp_path, rows)
        events = [
            _assign(f"e{i}", "team-01", "G1", Role.DEF, "defenders_top_1_60", (str(i),), 10)
            for i in range(1, MIN_RELIABLE_SAMPLE + 1)
        ]
        results = round_role_inflation(events, conn, "G1")
        assert results[0].n == MIN_RELIABLE_SAMPLE
        assert results[0].reliable is True

    def test_goalkeeper_blocks_excluded(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [
            _row(1, role="P", quotazione_asta=5, list_pool_name="goalkeeper_blocks"),
            _row(2, role="P", quotazione_asta=5, list_pool_name="goalkeeper_blocks"),
            _row(3, role="P", quotazione_asta=5, list_pool_name="goalkeeper_blocks"),
        ])
        events = [_assign("e1", "team-01", "G1", Role.GK, "goalkeeper_blocks", ("1", "2", "3"), 60)]
        results = round_role_inflation(events, conn, "G1")
        assert results == []

    def test_other_round_excluded(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1, quotazione_asta=10)])
        events = [_assign("e1", "team-01", "G2", Role.DEF, "defenders_top_1_60", ("1",), 20)]
        results = round_role_inflation(events, conn, "G1")
        assert results == []

    def test_voided_purchase_excluded(self, ruleset, tmp_path):
        from fantacalcio.domain import VoidEvent

        conn = _players_conn(tmp_path, [_row(1, quotazione_asta=10)])
        events = [
            _assign("e1", "team-01", "G1", Role.DEF, "defenders_top_1_60", ("1",), 20),
            VoidEvent(event_id="v1", ts="t", voids="e1", author="test", reason="mistake"),
        ]
        results = round_role_inflation(events, conn, "G1")
        assert results == []


class TestPriceTierInflation:
    def test_splits_into_tiers_and_ratios_differ(self, ruleset, tmp_path):
        # cheap defenders overpaid a lot, expensive ones paid close to quotazione
        rows = [_row(i, quotazione_asta=5) for i in range(1, 5)] + [_row(i, quotazione_asta=50) for i in range(5, 9)]
        conn = _players_conn(tmp_path, rows)
        events = (
            [_assign(f"c{i}", "team-01", "G1", Role.DEF, "defenders_top_1_60", (str(i),), 15) for i in range(1, 5)]
            + [_assign(f"e{i}", "team-01", "G1", Role.DEF, "defenders_top_1_60", (str(i),), 52) for i in range(5, 9)]
        )
        from fantacalcio.auction.market_model import price_tier_inflation

        tiers = price_tier_inflation(events, conn, voti_role="D", n_tiers=2)
        assert len(tiers) == 2
        low, high = sorted(tiers, key=lambda t: t.quotazione_min)
        assert low.mean_ratio > high.mean_ratio  # cheap tier overpaid more

    def test_too_few_observations_returns_empty(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1, quotazione_asta=10)])
        events = [_assign("e1", "team-01", "G1", Role.DEF, "defenders_top_1_60", ("1",), 10)]
        from fantacalcio.auction.market_model import price_tier_inflation

        assert price_tier_inflation(events, conn, voti_role="D") == []


class TestMarketRegimeAndAggressiveness:
    def test_market_regime_ratio_pools_all_roles_and_gk_blocks(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [
            _row(1, role="D", quotazione_asta=10),
            _row(2, role="P", quotazione_asta=5, list_pool_name="goalkeeper_blocks"),
            _row(3, role="P", quotazione_asta=5, list_pool_name="goalkeeper_blocks"),
        ])
        events = [
            _assign("e1", "team-01", "G1", Role.DEF, "defenders_top_1_60", ("1",), 20),  # ratio 2.0
            _assign("e2", "team-01", "G1", Role.GK, "goalkeeper_blocks", ("2", "3"), 20),  # ratio 2.0 (20/10)
        ]
        from fantacalcio.auction.market_model import market_regime_ratio

        regime = market_regime_ratio(events, conn)
        assert regime.n == 2
        assert regime.mean_ratio == pytest.approx(2.0)

    def test_no_purchases_returns_none(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1)])
        from fantacalcio.auction.market_model import market_regime_ratio

        assert market_regime_ratio([], conn) is None

    def test_team_aggressiveness_positive_for_overpaying_team(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1, quotazione_asta=10), _row(2, quotazione_asta=10)])
        events = [
            _assign("e1", "team-01", "G1", Role.DEF, "defenders_top_1_60", ("1",), 30),  # ratio 3.0, aggressive
            _assign("e2", "team-02", "G1", Role.DEF, "defenders_top_1_60", ("2",), 10),  # ratio 1.0, cautious
        ]
        from fantacalcio.auction.market_model import team_aggressiveness_index

        idx = team_aggressiveness_index(events, conn, ["team-01", "team-02"])
        assert idx["team-01"].delta_vs_market > 0
        assert idx["team-02"].delta_vs_market < 0

    def test_team_with_no_purchases_omitted(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1)])
        events = [_assign("e1", "team-01", "G1", Role.DEF, "defenders_top_1_60", ("1",), 10)]
        from fantacalcio.auction.market_model import team_aggressiveness_index

        idx = team_aggressiveness_index(events, conn, ["team-01", "team-02"])
        assert "team-02" not in idx


class TestEstimatePriceCorrection:
    def test_no_data_returns_none(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(1)])
        from fantacalcio.auction.market_model import estimate_price_correction

        assert estimate_price_correction([], conn, "D", 10) is None

    def test_falls_back_to_role_flat_when_tier_data_too_thin(self, ruleset, tmp_path):
        conn = _players_conn(tmp_path, [_row(i, quotazione_asta=10) for i in range(1, 4)])
        events = [
            _assign(f"e{i}", "team-01", "G1", Role.DEF, "defenders_top_1_60", (str(i),), 20)
            for i in range(1, 4)
        ]
        from fantacalcio.auction.market_model import estimate_price_correction

        correction = estimate_price_correction(events, conn, "D", 10, exclude_round_id="G2")
        assert correction is not None
        assert correction.ratio == pytest.approx(2.0)
        assert "tutte le fasce" in correction.source

    def test_falls_back_to_market_regime_for_unseen_role(self, ruleset, tmp_path):
        # only defenders were ever priced; forecasting a midfielder must fall back
        # to the role-agnostic market-wide signal, not silently return nothing.
        conn = _players_conn(tmp_path, [_row(i, role="D", quotazione_asta=10) for i in range(1, 9)])
        events = [
            _assign(f"e{i}", "team-01", "G1", Role.DEF, "defenders_top_1_60", (str(i),), 15)
            for i in range(1, 9)
        ]
        from fantacalcio.auction.market_model import estimate_price_correction

        correction = estimate_price_correction(events, conn, "C", 10, exclude_round_id="G2")
        assert correction is not None
        assert correction.ratio == pytest.approx(1.5)
        assert "mercato generale" in correction.source or "regime di mercato" in correction.source


class TestTeamPreferenceProfiles:
    def test_computes_per_team_won_lost_not_reached_and_ratios(self, tmp_path):
        conn = _players_conn(tmp_path, [_row(1, quotazione_asta=10), _row(2, quotazione_asta=20)])
        history = pd.DataFrame([
            {"team_id": "team-01", "player_code": 1, "preference_rank": 1, "bid_amount": 15, "outcome": "lost"},
            {"team_id": "team-01", "player_code": 2, "preference_rank": 2, "bid_amount": 30, "outcome": "won"},
            {"team_id": "team-01", "player_code": 2, "preference_rank": 3, "bid_amount": 5, "outcome": "not_reached"},
        ])
        from fantacalcio.auction.market_model import team_preference_profiles

        profiles = team_preference_profiles(history, conn)
        assert len(profiles) == 1
        p = profiles[0]
        assert p.team_id == "team-01"
        assert p.n_won == 1 and p.n_lost == 1 and p.n_not_reached == 1
        assert p.avg_overbid_ratio_lost == pytest.approx(1.5)  # 15/10
        assert p.avg_overbid_ratio_won == pytest.approx(1.5)  # 30/20
        assert p.avg_preference_rank_won == pytest.approx(2.0)

    def test_team_absent_from_history_has_no_profile(self, tmp_path):
        conn = _players_conn(tmp_path, [_row(1)])
        history = pd.DataFrame([
            {"team_id": "team-01", "player_code": 1, "preference_rank": 1, "bid_amount": 15, "outcome": "won"},
        ])
        from fantacalcio.auction.market_model import team_preference_profiles

        profiles = team_preference_profiles(history, conn)
        assert all(p.team_id != "team-02" for p in profiles)

    def test_unknown_player_code_excluded_from_ratio_not_crash(self, tmp_path):
        conn = _players_conn(tmp_path, [_row(1, quotazione_asta=10)])
        history = pd.DataFrame([
            {"team_id": "team-01", "player_code": 999, "preference_rank": 1, "bid_amount": 15, "outcome": "lost"},
        ])
        from fantacalcio.auction.market_model import team_preference_profiles

        profiles = team_preference_profiles(history, conn)
        assert profiles[0].n_lost == 1
        assert profiles[0].avg_overbid_ratio_lost is None
