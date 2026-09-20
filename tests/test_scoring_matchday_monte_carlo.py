"""Tests for Matchday Monte Carlo Simulation."""

from fantacalcio.modeling.matchday_event_model import project_player_matchday
from fantacalcio.scoring.matchday_monte_carlo import simulate_player_matchday


def test_simulate_player_matchday_reproducible():
    proj = project_player_matchday(
        player_code=10,
        player_name="Lautaro Martinez",
        role="A",
        team="Inter",
        opponent="Monza",
        is_home=True,
        participation_rate=0.90,
        base_voto=6.8,
    )

    sim1 = simulate_player_matchday(proj, n_sims=1000, seed=123)
    sim2 = simulate_player_matchday(proj, n_sims=1000, seed=123)

    assert sim1.mean_fantavoto == sim2.mean_fantavoto
    assert sim1.p90_fantavoto == sim2.p90_fantavoto
    assert sim1.prob_at_least_1_goal == sim2.prob_at_least_1_goal


def test_simulate_player_matchday_metrics():
    proj = project_player_matchday(
        player_code=20,
        player_name="Barella N.",
        role="C",
        team="Inter",
        opponent="Monza",
        is_home=True,
        participation_rate=0.85,
        base_voto=6.4,
    )

    sim = simulate_player_matchday(proj, n_sims=2000, seed=42)

    assert sim.player_code == 20
    assert sim.simulations_count == 2000
    assert sim.mean_fantavoto > 0.0
    assert sim.p90_fantavoto >= sim.median_fantavoto >= sim.p10_fantavoto
    assert 0.0 <= sim.prob_no_vote <= 0.3
    assert sim.upside_bonus >= 0.0
    assert sim.downside_risk >= 0.0
