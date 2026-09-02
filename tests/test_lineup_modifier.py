import pytest

from fantacalcio.lineup.modifier import MODIFIER_DISCLAIMER, historical_defence_modifier


def test_worked_points_from_doc():
    assert historical_defence_modifier([6.0, 6.0, 6.0]) == pytest.approx(0.0)
    assert historical_defence_modifier([6.25, 6.25]) == pytest.approx(1.0)
    assert historical_defence_modifier([6.5]) == pytest.approx(2.0)


def test_clamped_at_zero_below_baseline():
    assert historical_defence_modifier([5.0, 4.0]) == 0.0


def test_monotone_non_decreasing():
    prev = -1.0
    for avg in [5.5, 6.0, 6.25, 6.5, 7.0, 8.0]:
        cur = historical_defence_modifier([avg])
        assert cur >= prev
        prev = cur


def test_empty_sequence_is_zero():
    assert historical_defence_modifier([]) == 0.0


def test_fewer_than_four_defenders_is_zero():
    # doc: "disponibile con almeno 4 difensori" -> a back-three gets no modifier
    assert historical_defence_modifier([7.0, 7.0, 7.0, 7.0], n_defenders=3) == 0.0
    assert historical_defence_modifier([7.0, 7.0, 7.0, 7.0], n_defenders=4) > 0.0
    # unspecified n_defenders keeps the old (ungated) behaviour
    assert historical_defence_modifier([7.0, 7.0]) > 0.0


def test_disclaimer_mentions_unratified():
    assert "non ratificata" in MODIFIER_DISCLAIMER.lower()
    assert "OPEN_QUESTIONS" in MODIFIER_DISCLAIMER
