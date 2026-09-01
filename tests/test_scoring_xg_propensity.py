"""Stage 3 (ADR-2026-075): xG/xA blended into MC goal/assist propensity."""

from __future__ import annotations

import numpy as np

from fantacalcio.scoring.monte_carlo import HistoricalRow, SimulationResult
from fantacalcio.scoring.xg_propensity import adjust_event_propensity

N = 2000


def _row(goals: int, assists: int, voto: float) -> HistoricalRow:
    return HistoricalRow(
        voto=voto, role="C", goals_scored=goals, assists=assists, goals_conceded=1,
        own_goals=0, yellow_cards=0, red_cards=0, penalties_missed=0, team_goals_conceded=1.0,
    )


def _ensemble(seed: int = 0, assist_frac: float = 0.2):
    rng = np.random.default_rng(seed)
    has_assist = rng.random(N) < assist_frac
    has_goal = rng.random(N) < 0.15
    # assist rows -> voto >= 9 exactly; goal-only rows -> voto 8 (kept distinct)
    rows = [
        _row(int(g), int(a), 6.0 + 3.0 * a + 2.0 * g)
        for g, a in zip(has_goal, has_assist)
    ]
    samples = np.array([r.voto for r in rows], dtype=float)
    result = SimulationResult(
        player_code=1, role="C", n_sims=N, player_games_in_pool=50,
        used_role_pool_only=False, samples=samples,
    )
    hist_goal = float(np.mean([r.goals_scored for r in rows]))
    hist_assist = float(np.mean([r.assists for r in rows]))
    return result, rows, hist_goal, hist_assist


def test_absent_xg_returns_input_byte_identical():
    result, rows, hg, ha = _ensemble()
    out = adjust_event_propensity(
        result, historical_rows=rows, xg_goal_rate=None, xg_assist_rate=None,
        role="C", hist_goal_rate=hg, hist_assist_rate=ha, rng=np.random.default_rng(1),
    )
    assert out is result
    assert np.array_equal(out.samples, result.samples)


def test_deterministic_under_fixed_seed():
    result, rows, hg, ha = _ensemble()
    kw = dict(
        historical_rows=rows, xg_goal_rate=0.4, xg_assist_rate=0.5,
        role="C", hist_goal_rate=hg, hist_assist_rate=ha,
    )
    a = adjust_event_propensity(result, rng=np.random.default_rng(123), **kw)
    b = adjust_event_propensity(result, rng=np.random.default_rng(123), **kw)
    assert np.array_equal(a.samples, b.samples)


def test_higher_xa_rate_raises_assist_draw_frequency_monotone():
    result, rows, hg, ha = _ensemble(assist_frac=0.1)
    assist_mask = np.array([r.assists > 0 for r in rows])
    base_freq = assist_mask.mean()

    def assist_freq_after(xa_rate: float) -> float:
        out = adjust_event_propensity(
            result, historical_rows=rows, xg_goal_rate=None, xg_assist_rate=xa_rate,
            role="C", hist_goal_rate=hg, hist_assist_rate=ha, rng=np.random.default_rng(7),
        )
        # every assist row has a distinct fantavoto (>= 9) -> count them back
        return float(np.mean(out.samples >= 9.0 - 1e-9))

    low = assist_freq_after(ha)           # ~unchanged (ratio ~1)
    high = assist_freq_after(ha * 10.0)   # strong upweight of assist draws
    assert high > low
    assert high > base_freq


def test_degenerate_ensemble_no_events_returns_input_unchanged():
    # no goal/assist rows in the ensemble -> no differential weight possible
    rng = np.random.default_rng(0)
    rows = [_row(0, 0, 6.0) for _ in range(N)]
    samples = np.array([r.voto for r in rows], dtype=float)
    result = SimulationResult(
        player_code=2, role="C", n_sims=N, player_games_in_pool=10,
        used_role_pool_only=False, samples=samples,
    )
    out = adjust_event_propensity(
        result, historical_rows=rows, xg_goal_rate=0.5, xg_assist_rate=5.0,
        role="C", hist_goal_rate=0.1, hist_assist_rate=0.1, rng=rng,
    )
    assert out is result
    assert np.array_equal(out.samples, result.samples)
