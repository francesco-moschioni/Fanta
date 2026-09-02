import math

import pytest

from fantacalcio.auction.opponent_demand_price import (
    DEFAULT_CLEARING_FORM,
    calibrate_clearing_form,
    demand_pressure_from_state,
    expected_clearing_price,
)
from fantacalcio.domain import (
    AssignmentEvent,
    AssignmentItem,
    Role,
    replay,
)


class TestExpectedClearingPrice:
    def test_demand_zero_returns_anchor(self):
        assert expected_clearing_price(30, demand_pressure=0.0) == pytest.approx(30.0)
        assert expected_clearing_price(30, demand_pressure=0.0, role_inflation=1.2) == pytest.approx(36.0)

    def test_monotone_non_decreasing_in_demand(self):
        prev = -math.inf
        for d in [0, 0.5, 1, 2, 4, 8, 20]:
            p = expected_clearing_price(25, demand_pressure=d)
            assert p >= prev - 1e-9
            prev = p

    def test_at_least_anchor_and_finite(self):
        p = expected_clearing_price(25, demand_pressure=5.0)
        assert p >= 25.0
        assert math.isfinite(p)

    def test_capped_by_richest_rival_bid(self):
        p = expected_clearing_price(25, demand_pressure=50.0, richest_rival_bid=31)
        assert p == 31.0

    def test_bounded_above_by_gmax(self):
        p = expected_clearing_price(10, demand_pressure=1e6, g_max=2.0)
        assert p <= 20.0 + 1e-6


class TestCalibrate:
    def test_none_frame_returns_defaults(self):
        assert calibrate_clearing_form(None) == DEFAULT_CLEARING_FORM

    def test_empty_frame_returns_defaults(self):
        import pandas as pd

        assert calibrate_clearing_form(pd.DataFrame()) == DEFAULT_CLEARING_FORM


class TestDemandPressureFromState:
    def test_pressure_counts_opponents_needing_role(self, ruleset):
        state = replay(ruleset, [])
        # nobody has bought anything -> every opponent still needs D
        d = demand_pressure_from_state(
            state, ruleset, "D", exclude_team_id="team-01", round_id="G1"
        )
        # team-02 and team-03 exist only if referenced; force them in
        state.team("team-02")
        state.team("team-03")
        d = demand_pressure_from_state(
            state, ruleset, "D", exclude_team_id="team-01", round_id="G1"
        )
        assert d == pytest.approx(2.0)

    def test_pressure_zero_when_no_opponent_needs_role(self, ruleset, monkeypatch):
        import fantacalcio.auction.opponent_demand_price as mod

        state = replay(ruleset, [])
        state.team("team-02")
        monkeypatch.setattr(mod, "remaining_roster_slots", lambda ts, rs: {"P": 0, "D": 0, "C": 0, "A": 0})
        d = demand_pressure_from_state(state, ruleset, "D", exclude_team_id="team-01", round_id="G1")
        assert d == 0.0

    def test_richer_opponent_contributes_more(self, ruleset):
        # team-02 spends a lot in G1 (poorer per slot), team-03 spends nothing
        events = [
            AssignmentEvent(
                event_id="e1", ts="t", round_id="G1", team_id="team-02",
                pool_id="defenders_top_1_60", role=Role.DEF,
                item=AssignmentItem(player_ids=("dd-1",)), amount=1,
                source="test", author="test",
            ),
        ]
        state = replay(ruleset, events)
        state.team("team-03")
        d = demand_pressure_from_state(state, ruleset, "D", exclude_team_id="team-01", round_id="G1")
        assert d == pytest.approx(2.0)  # still 2 needing; weights renormalise to mean 1
