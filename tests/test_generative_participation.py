import numpy as np
import pytest

from fantacalcio.scoring.generative import (
    KEEPER_BACKUP,
    KEEPER_NAILED,
    PlayerSeasonParticipation,
    sample_appearance,
    sample_minutes,
    simulate_appearance_counts,
)


def test_deterministic_under_seed():
    feat = PlayerSeasonParticipation(0.65)
    a = sample_appearance(feat, "C", 38, np.random.default_rng(1))
    b = sample_appearance(feat, "C", 38, np.random.default_rng(1))
    np.testing.assert_array_equal(a, b)


def test_appearance_marginal_matches_participation_rate():
    feat = PlayerSeasonParticipation(0.6, start_share=0.8)
    rng = np.random.default_rng(0)
    status = np.concatenate([sample_appearance(feat, "C", 38, rng) for _ in range(400)])
    appear_rate = (status > 0).mean()
    start_rate = (status == 2).mean()
    assert abs(appear_rate - 0.6) < 0.02
    assert abs(start_rate - 0.6 * 0.8) < 0.02


def test_minutes_zero_when_unused_and_bounded():
    status = np.array([0, 1, 2, 0, 2])
    m = sample_minutes(status, "C", np.random.default_rng(2))
    assert m[0] == 0.0 and m[3] == 0.0
    assert 0.0 < m[1] <= 44.0
    assert 15.0 <= m[2] <= 90.0


def test_keeper_nailed_designation_is_a_floor_on_the_rate():
    # A "nailed" keeper whose observed rate is only 0.5 still gets the 0.90 floor
    # (the designation bounds the data, it does not override it) -> plays most of
    # the season with low variance, but a misclassification is no longer 0.97.
    feat = PlayerSeasonParticipation(0.5, keeper_status=KEEPER_NAILED)
    counts = simulate_appearance_counts(feat, "P", 38, 600, np.random.default_rng(5))
    assert 32.0 <= counts.mean() <= 37.0
    assert counts.std() < 2.5
    # a keeper whose rate is already high keeps that higher rate
    hi = PlayerSeasonParticipation(0.97, keeper_status=KEEPER_NAILED)
    assert simulate_appearance_counts(hi, "P", 38, 400, np.random.default_rng(5)).mean() >= 35.0
    # minutes for a keeper's starts are a flat 90 (near-zero variance).
    status = sample_appearance(feat, "P", 38, np.random.default_rng(9))
    m = sample_minutes(status, "P", np.random.default_rng(9))
    assert set(np.unique(m[status == 2])) == {90.0}


def test_keeper_backup_barely_plays():
    feat = PlayerSeasonParticipation(0.05, keeper_status=KEEPER_BACKUP)
    counts = simulate_appearance_counts(feat, "P", 38, 600, np.random.default_rng(6))
    assert counts.mean() < 3.0
    assert np.percentile(counts, 90) <= 4.0


def test_keeper_rate_follows_the_participation_rate():
    from fantacalcio.scoring.generative.participation import KEEPER_RATE

    feat = PlayerSeasonParticipation(0.70, keeper_status=KEEPER_RATE)
    counts = simulate_appearance_counts(feat, "P", 38, 800, np.random.default_rng(11))
    assert abs(counts.mean() - 0.70 * 38) < 2.0  # tracks the rate, no hard classification
    status = sample_appearance(feat, "P", 38, np.random.default_rng(3))
    assert set(np.unique(status)).issubset({0, 2})  # keepers never cameo


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        PlayerSeasonParticipation(1.4)
    with pytest.raises(ValueError):
        PlayerSeasonParticipation(0.5, keeper_status="bench")
