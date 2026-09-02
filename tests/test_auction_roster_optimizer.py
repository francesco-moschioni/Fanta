import pytest

from fantacalcio.auction.roster_optimizer import (
    Candidate,
    RosterOptimizerError,
    candidate_price_floor,
    optimize_roster_completion,
)


class TestCandidatePriceFloor:
    def test_no_admin_quotation_uses_fantacalcio_quotation(self):
        assert candidate_price_floor(quotazione_asta=15, admin_quotazione=None) == 15

    def test_admin_quotation_above_fantacalcio_wins(self):
        assert candidate_price_floor(quotazione_asta=15, admin_quotazione=20) == 20

    def test_admin_quotation_below_fantacalcio_never_lowers_floor(self):
        assert candidate_price_floor(quotazione_asta=15, admin_quotazione=5) == 15


class TestOptimizeRosterCompletion:
    def test_picks_highest_var_within_budget_single_role(self):
        candidates = [
            Candidate(player_code=1, role="D", var_mean=5.0, cost=10),
            Candidate(player_code=2, role="D", var_mean=3.0, cost=5),
            Candidate(player_code=3, role="D", var_mean=1.0, cost=1),
        ]
        result = optimize_roster_completion(candidates, {"D": 1}, budget=10)
        assert [c.player_code for c in result.selected] == [1]
        assert result.total_var == 5.0
        assert result.total_cost == 10

    def test_respects_role_slot_cap(self):
        candidates = [Candidate(player_code=i, role="D", var_mean=float(i), cost=1) for i in range(1, 6)]
        result = optimize_roster_completion(candidates, {"D": 2}, budget=100)
        assert len(result.selected) == 2
        assert {c.player_code for c in result.selected} == {5, 4}  # two highest VAR

    def test_respects_budget_cap_prefers_better_total_var_combo(self):
        # One expensive high-VAR player (cost 10, var 6) vs two cheaper ones
        # (cost 4 each, var 3.5 each = 7 total) that fit two slots within budget 9.
        candidates = [
            Candidate(player_code=1, role="D", var_mean=6.0, cost=10),
            Candidate(player_code=2, role="D", var_mean=3.5, cost=4),
            Candidate(player_code=3, role="D", var_mean=3.5, cost=4),
        ]
        result = optimize_roster_completion(candidates, {"D": 2}, budget=9)
        assert result.total_cost <= 9
        assert {c.player_code for c in result.selected} == {2, 3}
        assert result.total_var == 7.0

    def test_multi_role_respects_both_caps_and_shared_budget(self):
        candidates = [
            Candidate(player_code=1, role="C", var_mean=5.0, cost=10),
            Candidate(player_code=2, role="C", var_mean=4.0, cost=5),
            Candidate(player_code=3, role="A", var_mean=6.0, cost=10),
            Candidate(player_code=4, role="A", var_mean=2.0, cost=1),
        ]
        result = optimize_roster_completion(candidates, {"C": 1, "A": 1}, budget=15)
        selected_ids = {c.player_code for c in result.selected}
        # Best combo within budget 15: player 2 (C, cost5, var4) + player 3 (A, cost10, var6) = 15 cost, 10 var
        assert selected_ids == {2, 3}
        assert result.total_var == 10.0
        assert result.total_cost == 15

    def test_no_roles_needed_returns_empty(self):
        candidates = [Candidate(player_code=1, role="D", var_mean=5.0, cost=10)]
        result = optimize_roster_completion(candidates, {"D": 0}, budget=100)
        assert result.selected == ()
        assert result.total_var == 0.0

    def test_infeasible_budget_returns_empty_selection(self):
        candidates = [Candidate(player_code=1, role="D", var_mean=5.0, cost=100)]
        result = optimize_roster_completion(candidates, {"D": 1}, budget=1)
        assert result.selected == ()
        assert result.total_var == 0.0

    def test_negative_budget_raises(self):
        with pytest.raises(RosterOptimizerError, match="budget"):
            optimize_roster_completion([], {"D": 1}, budget=-1)

    def test_negative_role_slots_raises(self):
        with pytest.raises(RosterOptimizerError, match="role_slots_needed"):
            optimize_roster_completion([], {"D": -1}, budget=10)

    def test_reports_when_candidate_pool_was_capped(self):
        candidates = [
            Candidate(player_code=i, role="D", var_mean=float(i), cost=1) for i in range(1, 30)
        ]  # 29 candidates, TOP_N_PER_ROLE=25
        result = optimize_roster_completion(candidates, {"D": 1}, budget=100)
        assert result.candidate_pool_capped

    def test_reports_when_candidate_pool_was_not_capped(self):
        candidates = [Candidate(player_code=1, role="D", var_mean=5.0, cost=10)]
        result = optimize_roster_completion(candidates, {"D": 1}, budget=100)
        assert not result.candidate_pool_capped

    def test_value_col_default_reproduces_var_mean(self):
        candidates = [
            Candidate(player_code=1, role="D", var_mean=5.0, cost=10),
            Candidate(player_code=2, role="D", var_mean=3.0, cost=5),
            Candidate(player_code=3, role="A", var_mean=4.0, cost=6),
        ]
        base = optimize_roster_completion(candidates, {"D": 1, "A": 1}, budget=20)
        explicit = optimize_roster_completion(
            candidates, {"D": 1, "A": 1}, budget=20, value_col="var_mean"
        )
        assert base == explicit

    def test_value_fn_hook_changes_objective(self):
        # value_fn ranks by cost instead of var_mean -> picks the pricier D
        candidates = [
            Candidate(player_code=1, role="D", var_mean=9.0, cost=1),
            Candidate(player_code=2, role="D", var_mean=1.0, cost=8),
        ]
        res = optimize_roster_completion(
            candidates, {"D": 1}, budget=100, value_fn=lambda c: float(c.cost)
        )
        assert [c.player_code for c in res.selected] == [2]

    def test_negative_var_slot_is_left_unfilled_rather_than_hurt_total_var(self):
        # The objective is "maximize total VAR", not "always fill every slot
        # regardless of quality" -- leaving a needed slot unfilled (total VAR
        # 0.0) correctly beats spending a credit on a -2.0 VAR player. Callers
        # that need mandatory completion must treat an unfilled needed slot as
        # a separate concern (this module doesn't claim to solve that).
        candidates = [Candidate(player_code=1, role="D", var_mean=-2.0, cost=1)]
        result = optimize_roster_completion(candidates, {"D": 1}, budget=5)
        assert result.selected == ()
        assert result.total_var == 0.0
