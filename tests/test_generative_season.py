import numpy as np
import pandas as pd
import pytest

from fantacalcio.modeling.metrics import crps_ensemble, pit_values
from fantacalcio.scoring.monte_carlo import build_event_pools, simulate_fantavoto
from fantacalcio.scoring.generative import (
    DisciplineRates,
    GenerativeConfig,
    PlayerRates,
    PlayerSeasonParticipation,
    TeamMatchPrior,
    default_season_fixtures,
    simulate_season,
)
from fantacalcio.scoring.generative.participation import KEEPER_NAILED


def _pools(seed_events=True):
    rows = []
    rng = np.random.default_rng(0)
    for i in range(220):
        rows.append(dict(
            player_code=1, role="C", voto=6.0 + rng.integers(0, 5) * 0.2,
            goals_scored=int(seed_events and i % 8 == 0), assists=int(seed_events and i % 11 == 0),
            goals_conceded=0, own_goals=0, yellow_cards=int(i % 6 == 0), red_cards=0,
            penalties_missed=0, team_goals_conceded=float(i % 3), recency_weight=1.0,
        ))
    for i in range(400):
        rows.append(dict(
            player_code=2, role="C", voto=6.0 + (i % 3) * 0.1, goals_scored=0, assists=0,
            goals_conceded=0, own_goals=0, yellow_cards=0, red_cards=0, penalties_missed=0,
            team_goals_conceded=1.0, recency_weight=1.0,
        ))
    # a defender pool for the dependency test
    for i in range(400):
        rows.append(dict(
            player_code=10, role="D", voto=6.0, goals_scored=0, assists=0, goals_conceded=0,
            own_goals=0, yellow_cards=0, red_cards=0, penalties_missed=0,
            team_goals_conceded=1.0, recency_weight=1.0,
        ))
    return build_event_pools(pd.DataFrame(rows))


def _cfg(role="C", rate=0.6, keeper="none"):
    pp, rp = _pools()
    return pp, rp, GenerativeConfig(
        role=role,
        participation=PlayerSeasonParticipation(rate, keeper_status=keeper),
        player_pools=pp, role_pools=rp,
        rates=PlayerRates(goal_per90=0.15, assist_per90=0.12, n_goal_events=20, n_assist_events=15),
        discipline=DisciplineRates(),
    )


def test_deterministic_under_seed():
    _, _, cfg = _cfg()
    a = simulate_season(1, cfg, n_sims=200, base_seed=42)
    b = simulate_season(1, cfg, n_sims=200, base_seed=42)
    np.testing.assert_array_equal(a.season_totals, b.season_totals)


def test_season_is_not_38x_matchday():
    pp, rp, cfg = _cfg(rate=0.6)
    boot = simulate_fantavoto(1, "C", pp, rp, n_sims=20000, rng=np.random.default_rng(7))
    res = simulate_season(1, cfg, n_sims=4000, base_seed=42)

    expected_mean = boot.mean * 0.6 * 38
    assert abs(res.mean - expected_mean) / expected_mean < 0.05

    naive = res.naive_38x_variance(float(np.var(boot.samples)))
    # Var[S] = E[N] sigma^2 + Var[N] mu^2  >  38 * sigma^2 : the count-variance term.
    assert res.variance > naive
    assert res.variance > 3.0 * naive  # and by a wide margin here


def test_degradation_regression_matches_bootstrap_scaled_by_participation():
    pp, rp, _ = _cfg()
    cfg = GenerativeConfig(
        role="C", participation=PlayerSeasonParticipation(0.55),
        player_pools=pp, role_pools=rp,
    )
    boot = simulate_fantavoto(1, "C", pp, rp, n_sims=20000, rng=np.random.default_rng(11))
    res = simulate_season(1, cfg, n_sims=4000, base_seed=42, active_modules=())
    expected = boot.mean * 0.55 * 38
    # Tolerance achieved in practice ~0.2%; contract band is 5%.
    assert abs(res.mean - expected) / expected < 0.05


def test_keeper_appearance_count_via_season():
    pp, rp = _pools()
    cfg = GenerativeConfig(
        role="P", participation=PlayerSeasonParticipation(0.5, keeper_status=KEEPER_NAILED),
        player_pools=pp, role_pools={"P": rp["D"]},  # reuse D pool shape as a stand-in
    )
    res = simulate_season(999, cfg, n_sims=400, base_seed=42)
    assert 36.0 <= res.expected_appearances <= 38.0
    assert res.appearance_counts.std() < 2.0


def test_shared_scoreline_couples_teammates():
    pp, rp = _pools()
    prior = [TeamMatchPrior(lam_for=1.3, lam_against=1.1) for _ in range(38)]
    base = dict(player_pools=pp, role_pools=rp, participation=PlayerSeasonParticipation(0.95))
    cfg_d = GenerativeConfig(role="D", **base)

    a = simulate_season(10, cfg_d, n_sims=600, base_seed=42, club_id=500, team_priors=prior)
    b = simulate_season(11, cfg_d, n_sims=600, base_seed=42, club_id=500, team_priors=prior)
    c = simulate_season(12, cfg_d, n_sims=600, base_seed=42, club_id=999, team_priors=prior)

    # clean-sheet indicator per season path (matchday 0, always played at rate .95)
    cs_a = (a.team_goals_against[:, 0] == 0).astype(float)
    cs_b = (b.team_goals_against[:, 0] == 0).astype(float)
    cs_c = (c.team_goals_against[:, 0] == 0).astype(float)
    same_club = np.corrcoef(cs_a, cs_b)[0, 1]
    diff_club = np.corrcoef(cs_a, cs_c)[0, 1]
    assert same_club > 0.9          # identical shared draw
    assert abs(diff_club) < 0.15    # independent


def test_counter_based_seeding_module_isolation():
    _, _, cfg = _cfg()
    none = simulate_season(1, cfg, n_sims=300, base_seed=42, active_modules=())
    disc = simulate_season(1, cfg, n_sims=300, base_seed=42, active_modules=("discipline",))
    # Adding the discipline module must not shift the participation / minutes /
    # scoreline streams.
    np.testing.assert_array_equal(none.minutes, disc.minutes)
    np.testing.assert_array_equal(none.appearance_counts, disc.appearance_counts)
    np.testing.assert_array_equal(none.team_goals_against, disc.team_goals_against)


def test_crps_pit_sanity_on_synthetic_completed_season():
    pp, rp, cfg = _cfg(rate=0.7)
    # "realised" seasons drawn from the same generative process with a disjoint seed
    truth = simulate_season(1, cfg, n_sims=60, base_seed=999).season_totals
    forecast = simulate_season(1, cfg, n_sims=2000, base_seed=42).season_totals

    score = crps_ensemble(forecast, float(np.mean(truth)))
    assert np.isfinite(score) and score >= 0.0

    pit = pit_values(np.tile(forecast, (truth.size, 1)), truth)
    assert pit.min() >= 0.0 and pit.max() <= 1.0
    assert 0.25 < pit.mean() < 0.75  # not systematically mis-calibrated
