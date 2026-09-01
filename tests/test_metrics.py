import numpy as np
import pytest

from fantacalcio.modeling.metrics import (
    coverage,
    crps_ensemble,
    log_loss,
    mae,
    multiclass_log_loss,
    ndcg_at_k,
    pit_values,
    rmse,
    spearman_rank_corr,
)
from fantacalcio.modeling.validation import log_loss as validation_log_loss


def test_crps_point_mass_is_zero():
    samples = np.full(200, 3.7)
    assert crps_ensemble(samples, 3.7) == 0.0


def test_crps_positive_for_spread_ensemble():
    rng = np.random.default_rng(0)
    samples = rng.normal(0.0, 1.0, size=5000)
    assert crps_ensemble(samples, 0.0) > 0.0


def test_coverage_near_nominal_for_calibrated_normal():
    rng = np.random.default_rng(42)
    n_rows = 400
    samples = rng.normal(0.0, 1.0, size=(n_rows, 3000))
    observed = rng.normal(0.0, 1.0, size=n_rows)
    cov = coverage(samples, observed, lo=0.1, hi=0.9)
    assert abs(cov - 0.8) < 0.05


def test_pit_values_uniform_ish_for_calibrated_normal():
    rng = np.random.default_rng(1)
    samples = rng.normal(0.0, 1.0, size=(500, 2000))
    observed = rng.normal(0.0, 1.0, size=500)
    pit = pit_values(samples, observed)
    assert pit.shape == (500,)
    assert 0.4 < pit.mean() < 0.6


def test_spearman_monotonic():
    assert spearman_rank_corr([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == pytest.approx(1.0)
    assert spearman_rank_corr([1, 2, 3, 4, 5], [50, 40, 30, 20, 10]) == pytest.approx(-1.0)


def test_ndcg_in_unit_interval_and_perfect_is_one():
    rng = np.random.default_rng(7)
    pred = rng.normal(size=20)
    true = rng.uniform(0, 10, size=20)
    v = ndcg_at_k(pred, true, k=10)
    assert 0.0 <= v <= 1.0
    assert ndcg_at_k(true, true, k=10) == 1.0


def test_mae_rmse_basic():
    assert mae([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 0.0
    assert rmse([0.0, 0.0], [3.0, 4.0]) == np.sqrt(12.5)


def test_moved_log_loss_matches_validation_import():
    y_true = [0, 1, 2, 1]
    probs = [(0.7, 0.2, 0.1), (0.2, 0.6, 0.2), (0.1, 0.2, 0.7), (0.3, 0.4, 0.3)]
    assert log_loss(y_true, probs) == validation_log_loss(y_true, probs)


def test_multiclass_log_loss_matches_tuple_form():
    y_true = [0, 1, 2]
    probs = [(0.7, 0.2, 0.1), (0.2, 0.6, 0.2), (0.1, 0.2, 0.7)]
    assert abs(multiclass_log_loss(np.array(probs), np.array(y_true)) - log_loss(y_true, probs)) < 1e-12
