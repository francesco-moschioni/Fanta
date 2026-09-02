from fantacalcio.lineup.captain import CaptainSuggestion, suggest_captain
from fantacalcio.lineup.risk_profile import BILANCIATO
from fantacalcio.lineup.optimizer import PlayerSlot


def slot(code, role, score):
    return PlayerSlot(
        player_code=code, role=role, score=score, sim_mean=score,
        p10=score - 1, p90=score + 1, p_vote=1.0,
        display_name=f"P{code}", data_quality_tier="A",
    )


def test_returns_top_scored_starter():
    starters = [slot(1, "A", 7.0), slot(2, "C", 9.1), slot(3, "D", 6.0)]
    sugg = suggest_captain(starters, BILANCIATO)
    assert isinstance(sugg, CaptainSuggestion)
    assert sugg.player_code == 2
    assert sugg.display_name == "P2"


def test_reason_mentions_unresolved_bonus_tiers():
    starters = [slot(1, "A", 7.0)]
    sugg = suggest_captain(starters, BILANCIATO)
    assert "bonus capitano" in sugg.reason.lower()
    assert "OPEN_QUESTIONS" in sugg.reason


def test_empty_starters_returns_none():
    assert suggest_captain([], BILANCIATO) is None
