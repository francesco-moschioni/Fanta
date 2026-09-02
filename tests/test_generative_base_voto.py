import numpy as np
import pandas as pd
import pytest

from fantacalcio.scoring.monte_carlo import build_event_pools
from fantacalcio.scoring.generative import sample_appearance_scores, sample_base_voto


def _pools():
    rows = []
    for i in range(120):
        rows.append(dict(player_code=1, role="C", voto=7.0, goals_scored=0, assists=0,
                         goals_conceded=0, own_goals=0, yellow_cards=0, red_cards=0,
                         penalties_missed=0, team_goals_conceded=1.0, recency_weight=1.0))
    for i in range(200):
        rows.append(dict(player_code=2, role="C", voto=6.0, goals_scored=0, assists=0,
                         goals_conceded=0, own_goals=0, yellow_cards=0, red_cards=0,
                         penalties_missed=0, team_goals_conceded=1.0, recency_weight=1.0))
    return build_event_pools(pd.DataFrame(rows))


def test_deterministic_under_seed():
    pp, rp = _pools()
    a = sample_base_voto(pp[1], rp["C"], 500, np.random.default_rng(1))
    b = sample_base_voto(pp[1], rp["C"], 500, np.random.default_rng(1))
    np.testing.assert_array_equal(a, b)


def test_shrinkage_mixes_own_and_role_pool():
    pp, rp = _pools()
    # 120 own games, prior 60 -> weight_own = 0.667 -> mean between 6.0 and 7.0, closer to 7.
    out = sample_base_voto(pp[1], rp["C"], 20000, np.random.default_rng(2), prior_games=60.0)
    assert 6.5 < out.mean() < 7.0


def test_no_own_history_uses_role_pool():
    pp, rp = _pools()
    out = sample_base_voto([], rp["C"], 5000, np.random.default_rng(3))
    assert abs(out.mean() - np.mean([r.voto for r in rp["C"]])) < 0.05


def test_appearance_scores_return_rows_aligned():
    pp, rp = _pools()
    scores, rows = sample_appearance_scores(pp, rp, 1, "C", 50, np.random.default_rng(4))
    assert scores.shape == (50,)
    assert len(rows) == 50 and all(r is not None for r in rows)


def test_ordinal_seam_not_implemented():
    pp, rp = _pools()
    with pytest.raises(NotImplementedError):
        sample_base_voto(pp[1], rp["C"], 10, np.random.default_rng(5), model="ordinal")


def test_empty_role_pool_raises():
    with pytest.raises(ValueError):
        sample_base_voto([6.0], [], 10, np.random.default_rng(6))
