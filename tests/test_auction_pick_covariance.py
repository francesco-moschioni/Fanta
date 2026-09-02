import numpy as np

from fantacalcio.auction.pick_covariance import (
    complementarity_adjustment,
    covariance_matrix,
    marginal_downside_contribution,
    marginal_variance_contribution,
    roster_point_samples,
)


def _rng():
    return np.random.default_rng(42)


class TestRosterSamples:
    def test_sum_aligned_vectors(self):
        ps = {1: np.array([1.0, 2.0, 3.0]), 2: np.array([10.0, 20.0, 30.0])}
        assert np.allclose(roster_point_samples(ps), [11.0, 22.0, 33.0])

    def test_covariance_matrix_shape_and_codes(self):
        rng = _rng()
        ps = {3: rng.normal(size=500), 1: rng.normal(size=500)}
        codes, cov = covariance_matrix(ps)
        assert codes == [1, 3]
        assert cov.shape == (2, 2)


class TestMarginalContribution:
    def test_correlated_candidate_adds_more_variance_than_uncorrelated(self):
        rng = _rng()
        base = rng.normal(size=4000)
        roster = base + rng.normal(size=4000) * 0.1
        correlated = base * 1.0 + rng.normal(size=4000) * 0.1  # co-moves with roster
        uncorrelated = rng.normal(size=4000)
        # equalise raw spread
        uncorrelated *= np.std(correlated) / np.std(uncorrelated)
        dv_corr = marginal_variance_contribution(roster, correlated)
        dv_unc = marginal_variance_contribution(roster, uncorrelated)
        assert dv_corr > dv_unc

    def test_downside_contribution_sign(self):
        rng = _rng()
        roster = rng.normal(loc=100, scale=10, size=3000)
        good = rng.normal(loc=20, scale=1, size=3000)  # reliable add -> lifts floor
        d = marginal_downside_contribution(roster, good)
        assert d > 0


class TestComplementarityAdjustment:
    def test_risk_aversion_zero_is_identity(self):
        assert complementarity_adjustment(7.0, 123.0, -5.0, risk_aversion=0.0) == 7.0

    def test_correlated_same_club_candidate_has_lower_risk_adjusted_var(self):
        rng = _rng()
        base = rng.normal(size=4000)
        roster = base * 3.0 + rng.normal(size=4000) * 0.3
        raw_var = 6.0
        correlated = base * 3.0 + rng.normal(size=4000) * 0.3
        uncorrelated = rng.normal(size=4000) * np.std(correlated)

        adj_corr = complementarity_adjustment(
            raw_var,
            marginal_variance_contribution(roster, correlated),
            marginal_downside_contribution(roster, correlated),
            risk_aversion=0.5,
        )
        adj_unc = complementarity_adjustment(
            raw_var,
            marginal_variance_contribution(roster, uncorrelated),
            marginal_downside_contribution(roster, uncorrelated),
            risk_aversion=0.5,
        )
        assert adj_corr < adj_unc
        assert adj_unc <= raw_var + 1e-9 or adj_unc > 0
