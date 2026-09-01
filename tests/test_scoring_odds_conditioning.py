import logging

import numpy as np
import pytest

from fantacalcio.scoring.monte_carlo import HistoricalRow, SimulationResult
from fantacalcio.scoring.odds_conditioning import condition_samples, scale_scoring_propensity

N = 2000
PMF_LEN = 8


def _row(conceded: int) -> HistoricalRow:
    return HistoricalRow(
        voto=6.0,
        role="D",
        goals_scored=0,
        assists=0,
        goals_conceded=conceded,
        own_goals=0,
        yellow_cards=0,
        red_cards=0,
        penalties_missed=0,
        team_goals_conceded=float(conceded),
    )


def _ensemble(seed: int = 0):
    rng = np.random.default_rng(seed)
    # realised conceded per draw, skewed toward 1-2
    conceded = rng.choice([0, 1, 2, 3, 4], size=N, p=[0.25, 0.35, 0.22, 0.13, 0.05])
    rows = [_row(int(c)) for c in conceded]
    # fantavoto: higher when the team conceded fewer (clean-sheet bonus baked in)
    samples = 6.0 - 0.4 * conceded + np.where(conceded == 0, 1.0, 0.0) + rng.normal(0, 0.3, N)
    result = SimulationResult(
        player_code=1, role="D", n_sims=N, player_games_in_pool=50,
        used_role_pool_only=False, samples=samples,
    )
    return result, rows, conceded


def _empirical_pmf(conceded) -> np.ndarray:
    return np.bincount(conceded, minlength=PMF_LEN).astype(float) / len(conceded)


def test_deterministic_under_fixed_seed():
    result, rows, conceded = _ensemble()
    target = np.array([0.55, 0.30, 0.10, 0.05, 0, 0, 0, 0], dtype=float)
    a = condition_samples(result, target_conceded_pmf=target, historical_rows=rows,
                          role="D", rng=np.random.default_rng(123))
    b = condition_samples(result, target_conceded_pmf=target, historical_rows=rows,
                          role="D", rng=np.random.default_rng(123))
    assert np.array_equal(a.samples, b.samples)


def test_conditioning_on_own_empirical_pmf_is_near_identity():
    result, rows, conceded = _ensemble()
    target = _empirical_pmf(conceded)
    out = condition_samples(result, target_conceded_pmf=target, historical_rows=rows,
                            role="D", rng=np.random.default_rng(7))
    assert out.mean == pytest.approx(result.mean, abs=0.05)


def test_strong_defence_target_raises_mean_and_clean_sheet_freq():
    result, rows, conceded = _ensemble()
    cs_before = np.mean(conceded == 0)
    mild = np.array([0.35, 0.35, 0.18, 0.12, 0, 0, 0, 0], dtype=float)
    strong = np.array([0.65, 0.25, 0.07, 0.03, 0, 0, 0, 0], dtype=float)
    out_mild = condition_samples(result, target_conceded_pmf=mild, historical_rows=rows,
                                 role="D", rng=np.random.default_rng(1))
    out_strong = condition_samples(result, target_conceded_pmf=strong, historical_rows=rows,
                                   role="D", rng=np.random.default_rng(1))
    assert out_strong.mean > out_mild.mean > result.mean - 0.2
    # clean-sheet frequency: fraction of resampled draws sitting at the CS bump
    cs_strong = np.mean(out_strong.samples > result.mean + 0.5)
    assert cs_strong > cs_before


def test_ess_degeneracy_returns_input_unchanged_with_warning(caplog):
    result, rows, conceded = _ensemble()
    impossible = np.zeros(PMF_LEN)
    impossible[7] = 1.0  # all mass where no draw ever lands
    with caplog.at_level(logging.WARNING, logger="fantacalcio.scoring.odds_conditioning"):
        out = condition_samples(result, target_conceded_pmf=impossible, historical_rows=rows,
                                role="D", rng=np.random.default_rng(0))
    assert out is result
    assert any("unchanged" in r.message for r in caplog.records)


def test_length_mismatch_raises():
    result, rows, _ = _ensemble()
    with pytest.raises(ValueError):
        condition_samples(result, target_conceded_pmf=np.ones(PMF_LEN) / PMF_LEN,
                          historical_rows=rows[:-1], role="D")


def test_scale_scoring_propensity_monotone_in_ratio():
    rng = np.random.default_rng(0)
    scored = rng.random(N) < 0.3
    samples = np.where(scored, 9.0, 6.0) + rng.normal(0, 0.2, N)
    rows = [
        HistoricalRow(6.0, "A", int(s), 0, 0, 0, 0, 0, 0, None) for s in scored
    ]
    result = SimulationResult(player_code=2, role="A", n_sims=N, player_games_in_pool=40,
                              used_role_pool_only=False, samples=samples)
    up = scale_scoring_propensity(result, team_goals_ratio=1.6, role="A",
                                  historical_rows=rows, rng=np.random.default_rng(3))
    down = scale_scoring_propensity(result, team_goals_ratio=0.6, role="A",
                                    historical_rows=rows, rng=np.random.default_rng(3))
    assert up.mean > result.mean > down.mean


def test_scale_scoring_propensity_noop_for_defender():
    result = SimulationResult(player_code=3, role="D", n_sims=10, player_games_in_pool=1,
                              used_role_pool_only=False, samples=np.full(10, 6.0))
    out = scale_scoring_propensity(result, team_goals_ratio=2.0, role="D")
    assert out is result
