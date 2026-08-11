import numpy as np
import pandas as pd
import pytest

from fantacalcio.scoring.monte_carlo import (
    build_event_pools,
    simulate_fantavoto,
)


def _row(player_code, role, voto, goals_scored=0, team_goals_conceded=None, recency_weight=1.0, **kwargs):
    defaults = dict(
        player_code=player_code, role=role, voto=voto, goals_scored=goals_scored,
        assists=0, goals_conceded=0, own_goals=0, yellow_cards=0, red_cards=0,
        penalties_missed=0, team_goals_conceded=team_goals_conceded, recency_weight=recency_weight,
    )
    defaults.update(kwargs)
    return defaults


def _pools_from_rows(rows):
    df = pd.DataFrame(rows)
    return build_event_pools(df)


class TestBuildEventPools:
    def test_groups_by_player_and_role(self):
        rows = [_row(1, "D", 6.0), _row(1, "D", 6.5), _row(2, "A", 6.0)]
        player_pools, role_pools = _pools_from_rows(rows)
        assert len(player_pools[1]) == 2
        assert len(player_pools[2]) == 1
        assert len(role_pools["D"]) == 2
        assert len(role_pools["A"]) == 1

    def test_team_goals_conceded_nan_becomes_none(self):
        rows = [_row(1, "P", 6.0, team_goals_conceded=float("nan"))]
        player_pools, _ = _pools_from_rows(rows)
        assert player_pools[1][0].team_goals_conceded is None


class TestSimulateFantavoto:
    def test_reproducible_with_same_seed(self):
        rows = [_row(1, "D", 6.0 + i * 0.1) for i in range(20)]
        player_pools, role_pools = _pools_from_rows(rows)
        result_a = simulate_fantavoto(1, "D", player_pools, role_pools, n_sims=200, rng=np.random.default_rng(42))
        result_b = simulate_fantavoto(1, "D", player_pools, role_pools, n_sims=200, rng=np.random.default_rng(42))
        np.testing.assert_array_equal(result_a.samples, result_b.samples)

    def test_different_seed_gives_different_samples(self):
        rows = [_row(1, "D", 6.0 + i * 0.1) for i in range(20)]
        player_pools, role_pools = _pools_from_rows(rows)
        result_a = simulate_fantavoto(1, "D", player_pools, role_pools, n_sims=200, rng=np.random.default_rng(1))
        result_b = simulate_fantavoto(1, "D", player_pools, role_pools, n_sims=200, rng=np.random.default_rng(2))
        assert not np.array_equal(result_a.samples, result_b.samples)

    def test_no_history_uses_role_pool_only(self):
        rows = [_row(2, "A", 6.5) for _ in range(30)]
        player_pools, role_pools = _pools_from_rows(rows)
        result = simulate_fantavoto(999, "A", player_pools, role_pools, n_sims=100, rng=np.random.default_rng(42))
        assert result.used_role_pool_only
        assert result.player_games_in_pool == 0

    def test_extensive_history_dominates_own_pool(self):
        # Player has 300 games all at voto=9 (very distinctive); role pool is all 6.0.
        own_rows = [_row(1, "A", 9.0) for _ in range(300)]
        role_rows = [_row(2, "A", 6.0) for _ in range(50)]
        player_pools, role_pools = _pools_from_rows(own_rows + role_rows)
        result = simulate_fantavoto(1, "A", player_pools, role_pools, n_sims=2000, prior_games=60.0, rng=np.random.default_rng(42))
        # weight_own = 300/(300+60) = 0.833, so mean should be much closer to 9 than 6.
        assert result.mean > 8.0

    def test_summary_statistics_available(self):
        rows = [_row(1, "D", 6.0), _row(1, "D", 7.0), _row(1, "D", 5.0)] * 20
        player_pools, role_pools = _pools_from_rows(rows)
        result = simulate_fantavoto(1, "D", player_pools, role_pools, n_sims=500, rng=np.random.default_rng(42))
        assert result.p10 <= result.median <= result.p90
        assert isinstance(result.mean, float)

    def test_missing_role_pool_raises(self):
        player_pools, role_pools = _pools_from_rows([_row(1, "D", 6.0)])
        with pytest.raises(ValueError, match="No role pool"):
            simulate_fantavoto(1, "A", player_pools, role_pools, rng=np.random.default_rng(42))

    def test_goal_events_reflected_in_samples(self):
        # All historical rows for this player scored a goal -> every sample should
        # include the +3 goal bonus on top of voto.
        rows = [_row(1, "A", 6.0, goals_scored=1) for _ in range(50)]
        player_pools, role_pools = _pools_from_rows(rows)
        result = simulate_fantavoto(1, "A", player_pools, role_pools, n_sims=100, prior_games=1.0, rng=np.random.default_rng(42))
        assert result.mean > 8.0  # 6.0 voto + 3.0 goal, minus small role-pool mixing

    def test_recency_weights_ignored_by_default(self):
        # Half the rows (voto=4) have zero weight; if weights aren't consulted
        # by default, both halves are drawn from equally.
        rows = [_row(1, "D", 8.0, recency_weight=1.0) for _ in range(20)] + [
            _row(1, "D", 4.0, recency_weight=0.0) for _ in range(20)
        ]
        player_pools, role_pools = _pools_from_rows(rows)
        result = simulate_fantavoto(1, "D", player_pools, role_pools, n_sims=2000, prior_games=1.0, rng=np.random.default_rng(42))
        assert 5.5 < result.mean < 6.5  # roughly midway between 4.0 and 8.0

    def test_recency_weights_used_when_enabled(self):
        rows = [_row(1, "D", 8.0, recency_weight=1.0) for _ in range(20)] + [
            _row(1, "D", 4.0, recency_weight=0.0) for _ in range(20)
        ]
        player_pools, role_pools = _pools_from_rows(rows)
        result = simulate_fantavoto(
            1, "D", player_pools, role_pools, n_sims=2000, prior_games=1.0,
            rng=np.random.default_rng(42), use_recency_weights=True,
        )
        assert result.mean > 7.5  # zero-weight rows should never be drawn
