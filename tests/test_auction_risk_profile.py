import numpy as np
import pytest

from fantacalcio.auction.risk_profile import cvar, risk_adjusted_objective


class TestCvar:
    def test_cvar_le_mean_for_non_degenerate_sample(self):
        rng = np.random.default_rng(0)
        s = rng.normal(loc=50, scale=12, size=5000)
        assert cvar(s, alpha=0.10) < float(np.mean(s))

    def test_cvar_equals_value_for_degenerate_sample(self):
        s = np.full(100, 7.0)
        assert cvar(s, alpha=0.10) == pytest.approx(7.0)

    def test_invalid_alpha_raises(self):
        with pytest.raises(ValueError):
            cvar([1.0, 2.0], alpha=0.0)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            cvar([], alpha=0.1)


class TestRiskAdjustedObjective:
    def test_rho_zero_is_mean(self):
        assert risk_adjusted_objective(10.0, 2.0, 0.0) == 10.0

    def test_rho_one_is_cvar(self):
        assert risk_adjusted_objective(10.0, 2.0, 1.0) == 2.0

    def test_monotone_in_rho_toward_cvar(self):
        vals = [risk_adjusted_objective(10.0, 2.0, r) for r in np.linspace(0, 1, 11)]
        for a, b in zip(vals, vals[1:]):
            assert b <= a  # cvar < mean, so raising rho lowers the blend

    def test_rho_out_of_range_raises(self):
        with pytest.raises(ValueError):
            risk_adjusted_objective(1.0, 0.0, 1.5)
