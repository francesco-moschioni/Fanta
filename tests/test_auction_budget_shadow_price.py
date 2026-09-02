import importlib.util

import pytest

from fantacalcio.auction.budget_shadow_price import (
    LARGE_SENTINEL_BID,
    ShadowPriceResult,
    _pulp_dual_crosscheck,
    budget_shadow_price,
    max_bid_from_shadow_price,
)
from fantacalcio.auction.roster_optimizer import Candidate

_HAS_PULP = importlib.util.find_spec("pulp") is not None


def _candidates():
    return [
        Candidate(player_code=1, role="D", var_mean=6.0, cost=40),
        Candidate(player_code=2, role="D", var_mean=5.0, cost=30),
        Candidate(player_code=3, role="D", var_mean=3.0, cost=20),
        Candidate(player_code=4, role="D", var_mean=1.0, cost=10),
        Candidate(player_code=5, role="A", var_mean=8.0, cost=60),
        Candidate(player_code=6, role="A", var_mean=4.0, cost=25),
        Candidate(player_code=7, role="A", var_mean=2.0, cost=12),
    ]


SLOTS = {"D": 2, "A": 1}


class TestBudgetShadowPrice:
    def test_returns_frozen_result(self):
        res = budget_shadow_price(_candidates(), SLOTS, budget=80)
        assert isinstance(res, ShadowPriceResult)
        with pytest.raises(Exception):
            res.lambda_star = 1.0  # frozen

    def test_shadow_price_non_negative(self):
        for b in (40, 60, 80, 100, 140):
            res = budget_shadow_price(_candidates(), SLOTS, budget=b)
            assert res.lambda_star >= 0.0

    def test_non_increasing_in_budget(self):
        lams = [budget_shadow_price(_candidates(), SLOTS, budget=b).lambda_star for b in range(40, 160, 10)]
        for a, c in zip(lams, lams[1:]):
            assert c <= a + 1e-6

    def test_non_binding_when_budget_large(self):
        res = budget_shadow_price(_candidates(), SLOTS, budget=100_000)
        assert res.binding is False
        assert res.lambda_star == 0.0

    def test_binding_when_budget_tight(self):
        res = budget_shadow_price(_candidates(), SLOTS, budget=70)
        assert res.binding is True
        assert res.lambda_star > 0.0
        assert sum(res.implied_roster) == sum(SLOTS.values())
        assert res.duality_gap_estimate >= 0.0

    def test_accepts_dict_rows(self):
        rows = [
            {"player_code": c.player_code, "role": c.role, "cost": c.cost, "var_mean": c.var_mean}
            for c in _candidates()
        ]
        res = budget_shadow_price(rows, SLOTS, budget=70)
        assert res.lambda_star > 0.0

    def test_negative_budget_raises(self):
        with pytest.raises(ValueError):
            budget_shadow_price(_candidates(), SLOTS, budget=-1)


class TestMaxBidFromShadowPrice:
    def test_ratio_ceiling(self):
        assert max_bid_from_shadow_price(10.0, 0.5) == 20
        assert max_bid_from_shadow_price(10.1, 0.5) == 21  # ceiling

    def test_floor_enforced(self):
        assert max_bid_from_shadow_price(0.0, 5.0, floor=1) == 1
        assert max_bid_from_shadow_price(-3.0, 5.0, floor=2) == 2

    def test_lambda_zero_returns_finite_large_sentinel(self):
        out = max_bid_from_shadow_price(10.0, 0.0)
        assert out == LARGE_SENTINEL_BID
        assert out >= 1
        assert out != float("inf")


@pytest.mark.skipif(not _HAS_PULP, reason="pulp (optional 'solver' extra) not installed")
class TestPulpCrosscheck:
    def test_lp_dual_matches_bisection(self):
        cands, slots, budget = _candidates(), SLOTS, 70
        lam_bisect = budget_shadow_price(cands, slots, budget=budget).lambda_star
        lam_lp = _pulp_dual_crosscheck(cands, slots, budget=budget)
        assert lam_lp == pytest.approx(lam_bisect, abs=0.05)
