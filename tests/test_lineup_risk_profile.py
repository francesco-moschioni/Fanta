from fantacalcio.lineup.risk_profile import (
    AGGRESSIVO,
    BILANCIATO,
    PRESETS,
    PRUDENTE,
    player_score,
)


def test_presets_registered():
    assert set(PRESETS) == {"prudente", "bilanciato", "aggressivo"}


def test_bilanciato_equals_sim_mean():
    row = {"sim_mean": 7.3, "sim_p10": 4.0, "sim_p90": 11.0, "participation_rate": 0.5}
    assert player_score(row, BILANCIATO) == 7.3


def test_prudente_prefers_high_floor_high_pvote_over_boom_or_bust():
    steady = {"sim_mean": 6.0, "sim_p10": 5.5, "sim_p90": 6.6, "participation_rate": 0.95}
    boom = {"sim_mean": 6.0, "sim_p10": 3.0, "sim_p90": 12.0, "participation_rate": 0.55}
    assert player_score(steady, PRUDENTE) > player_score(boom, PRUDENTE)


def test_aggressivo_prefers_boom_or_bust():
    steady = {"sim_mean": 6.0, "sim_p10": 5.5, "sim_p90": 6.6, "participation_rate": 0.95}
    boom = {"sim_mean": 6.0, "sim_p10": 3.0, "sim_p90": 12.0, "participation_rate": 0.55}
    assert player_score(boom, AGGRESSIVO) > player_score(steady, AGGRESSIVO)


def test_nan_participation_falls_back():
    row = {"sim_mean": 6.0, "sim_p10": 5.0, "sim_p90": 7.0, "participation_rate": float("nan")}
    # should not raise, should not produce NaN
    val = player_score(row, PRUDENTE)
    assert val == val
