import pytest

from fantacalcio.lineup.optimizer import PlayerSlot
from fantacalcio.lineup.sv_risk import (
    SVRiskLevel,
    flag_sv_risk,
    sv_risk,
    sv_risk_level,
)


def slot(code, pvote):
    return PlayerSlot(
        player_code=code, role="C", score=6.0, sim_mean=6.0,
        p10=5.0, p90=7.0, p_vote=pvote,
        display_name=f"P{code}", data_quality_tier="A",
    )


def test_sv_risk_from_participation_rate():
    assert sv_risk({"participation_rate": 1.0}) == 0.0
    assert sv_risk({"participation_rate": 0.5}) == 0.5
    assert sv_risk({"participation_rate": 0.0}) == 1.0


def test_sv_risk_clamped():
    assert sv_risk({"participation_rate": 1.2}) == 0.0
    assert sv_risk({"participation_rate": -0.3}) == 1.0


def test_sv_risk_from_player_slot():
    assert sv_risk(slot(1, 0.8)) == pytest.approx(0.2)


def test_flag_sv_risk_picks_right_players():
    starters = [slot(1, 0.95), slot(2, 0.7), slot(3, 0.5)]
    flagged = flag_sv_risk(starters, threshold=0.35)
    assert flagged == [3]


def test_sv_risk_level_buckets():
    assert sv_risk_level(0.1) is SVRiskLevel.LOW
    assert sv_risk_level(0.25) is SVRiskLevel.MED
    assert sv_risk_level(0.5) is SVRiskLevel.HIGH
