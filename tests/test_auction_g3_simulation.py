import pandas as pd
import pytest

from fantacalcio.auction.g3_simulation import simulate_opponent_competition, win_probability_for_bid
from fantacalcio.domain import AssignmentEvent, AssignmentItem, Role, replay
from fantacalcio.persistence.player_table import REQUIRED_COLUMNS, build_player_table, connect


def _row(player_code, display_name="Player", role="A", team_name="Roma", quotazione_asta=10, admin_score=None, **kwargs):
    defaults = {c: None for c in REQUIRED_COLUMNS}
    defaults.update(
        player_code=player_code, display_name=display_name, role=role, team_name=team_name,
        quotazione_asta=quotazione_asta, admin_score=admin_score,
        sim_mean=6.5, sim_median=6.0, sim_p10=5.0, sim_p90=8.0,
        player_games_in_pool=50, used_role_pool_only=False, replacement_level=5.5,
        var_mean=1.0, var_p10=-0.5, var_p90=2.5, data_quality_tier="full_history",
        round_pool="G3", list_pool_name="remaining_players", list_state="provisional",
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


def _assign(event_id, team_id, round_id, pool_id, player_ids, amount, role=Role.FWD) -> AssignmentEvent:
    return AssignmentEvent(
        event_id=event_id, ts="2026-01-01T00:00:00Z", round_id=round_id, team_id=team_id,
        pool_id=pool_id, role=role, item=AssignmentItem(player_ids=player_ids), amount=amount,
        source="test", author="test", corrects=None,
    )


def _through_g2(team_id: str, extra_g2_events: list[AssignmentEvent] | None = None) -> list[AssignmentEvent]:
    """Minimal G1+G2 history so remaining_G2 (and thus G3's budget expr) is
    defined for `team_id` -- mirrors the real ledger, where G1/G2 always
    finish before G3. Any `extra_g2_events` (e.g. forward purchases for the
    opponent-behaviour signal -- forwards are a G2 pool, not G1) are ordered
    after the G1 seed, since the ledger must be round-ordered."""
    return [
        _assign(f"g1seed-{team_id}", team_id, "G1", "defenders_top_1_60", (f"g1seed-player-{team_id}",), 1, role=Role.DEF),
        _assign(f"g2seed-{team_id}", team_id, "G2", "midfielders_top_1_20", (f"g2seed-player-{team_id}",), 1, role=Role.MID),
        *(extra_g2_events or []),
    ]


class TestSimulateOpponentCompetition:
    def test_deterministic_with_same_seed(self, ruleset, tmp_path):
        rows = [_row(i, quotazione_asta=10) for i in range(1, 10)]
        conn = _players_conn(tmp_path, rows)
        fwd_events = [_assign(f"e{i}", "team_02", "G2", "forwards_top_1_20", (str(i),), 15) for i in range(1, 5)]
        events = _through_g2("team_02", fwd_events)
        state = replay(ruleset, events)
        pool = pd.DataFrame({"player_code": range(1, 10), "role": ["A"] * 9})
        target = pd.Series(_row(99, quotazione_asta=10))

        sim1 = simulate_opponent_competition(target, ruleset, state, conn, events, ["team_02"], pool, seed=42)
        sim2 = simulate_opponent_competition(target, ruleset, state, conn, events, ["team_02"], pool, seed=42)
        assert sim1.max_opponent_bid_samples == sim2.max_opponent_bid_samples

    def test_no_eligible_opponents_means_certain_win(self, ruleset, tmp_path):
        rows = [_row(i, quotazione_asta=10) for i in range(1, 5)]
        conn = _players_conn(tmp_path, rows)
        # opponent's forward slots are already full -> not eligible
        target_needs = ruleset.roster.forwards
        fwd_events = [
            _assign(f"e{i}", "team_02", "G2", "forwards_top_1_20", (str(i),), 10)
            for i in range(1, target_needs + 1)
        ]
        events = _through_g2("team_02", fwd_events)
        state = replay(ruleset, events)
        pool = pd.DataFrame({"player_code": [99], "role": ["A"]})
        target = pd.Series(_row(99, quotazione_asta=10))

        sim = simulate_opponent_competition(target, ruleset, state, conn, events, ["team_02"], pool, seed=1)
        assert sim.n_eligible_opponents == 0
        assert sim.prob_no_competition == 1.0
        assert win_probability_for_bid(sim, sim.effective_quotazione) == 1.0

    def test_win_probability_increases_with_bid(self, ruleset, tmp_path):
        rows = [_row(i, quotazione_asta=10) for i in range(1, 30)]
        conn = _players_conn(tmp_path, rows)
        fwd_events = [_assign(f"e{i}", "team_02", "G2", "forwards_top_1_20", (str(i),), 20) for i in range(1, 5)]
        events = _through_g2("team_02", fwd_events)
        state = replay(ruleset, events)
        pool = pd.DataFrame({"player_code": range(1, 30), "role": ["A"] * 29})
        target = pd.Series(_row(99, quotazione_asta=10))

        sim = simulate_opponent_competition(target, ruleset, state, conn, events, ["team_02"], pool, seed=7)
        low_bid_win = win_probability_for_bid(sim, sim.effective_quotazione)
        high_bid_win = win_probability_for_bid(sim, sim.effective_quotazione * 10)
        assert high_bid_win >= low_bid_win

    def test_explanation_names_correction_source(self, ruleset, tmp_path):
        rows = [_row(i, quotazione_asta=10) for i in range(1, 5)]
        conn = _players_conn(tmp_path, rows)
        events = _through_g2("team_02")
        state = replay(ruleset, events)
        pool = pd.DataFrame({"player_code": range(1, 5), "role": ["A"] * 4})
        target = pd.Series(_row(99, quotazione_asta=10))

        sim = simulate_opponent_competition(target, ruleset, state, conn, events, ["team_02"], pool, seed=1)
        assert any("Correzione di inflazione" in line for line in sim.explanation)
        assert not sim.price_correction_reliable  # no historical data at all
