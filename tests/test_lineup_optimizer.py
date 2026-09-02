import pytest

from fantacalcio.lineup.formations import parse_formation
from fantacalcio.lineup.optimizer import (
    LineupResult,
    PlayerSlot,
    best_xi,
    compare_formations,
)


def slot(code, role, score, mean=None, p10=None, p90=None, pvote=1.0, tier="A"):
    mean = score if mean is None else mean
    return PlayerSlot(
        player_code=code,
        role=role,
        score=score,
        sim_mean=mean,
        p10=mean - 1 if p10 is None else p10,
        p90=mean + 1 if p90 is None else p90,
        p_vote=pvote,
        display_name=f"P{code}",
        data_quality_tier=tier,
    )


def make_roster(n_p=3, n_d=8, n_c=8, n_a=5, base=6.0):
    players = []
    c = 0
    for role, n in (("P", n_p), ("D", n_d), ("C", n_c), ("A", n_a)):
        for i in range(n):
            c += 1
            players.append(slot(c, role, base + n - i))  # first ones score highest
    return players


def test_best_xi_fills_exact_slots_with_top_scored():
    roster = make_roster()
    f = parse_formation("3-4-3")
    res = best_xi(roster, f)
    assert res.feasible
    by_role = {}
    for s in res.starters:
        by_role.setdefault(s.role, []).append(s)
    assert len(by_role["P"]) == 1
    assert len(by_role["D"]) == 3
    assert len(by_role["C"]) == 4
    assert len(by_role["A"]) == 3
    assert len(res.starters) == 11
    # top-scored per role => highest scores chosen
    d_scores = sorted((s.score for s in roster if s.role == "D"), reverse=True)[:3]
    assert sorted((s.score for s in by_role["D"]), reverse=True) == d_scores
    assert len(res.bench) == len(roster) - 11


def test_best_xi_infeasible_when_short_a_defender():
    roster = make_roster(n_d=4)
    res = best_xi(roster, parse_formation("5-3-2"))
    assert res.feasible is False
    assert "difensori" in res.infeasible_reason
    assert res.starters == ()
    assert isinstance(res, LineupResult)


def test_defence_modifier_adds_non_negative_estimate():
    roster = make_roster(base=7.0)  # averages well above 6.0
    f = parse_formation("5-3-2")
    off = best_xi(roster, f, defence_modifier=False)
    on = best_xi(roster, f, defence_modifier=True)
    assert off.defence_modifier_estimate is None
    assert on.defence_modifier_estimate is not None
    assert on.defence_modifier_estimate >= 0.0
    assert on.total_score == pytest.approx(off.total_score + on.defence_modifier_estimate)
    # expected_points is individual-only, unchanged
    assert on.expected_points == pytest.approx(off.expected_points)


def test_compare_formations_sorted_and_flags_infeasible():
    # enough for 3-4-3 / 4-4-2 but not for any 5-defender shape
    roster = make_roster(n_d=4)
    formations = [parse_formation(s) for s in ("3-4-3", "4-4-2", "5-3-2", "5-4-1")]
    results = compare_formations(roster, formations)
    feasible = [r for r in results if r.feasible]
    infeasible = [r for r in results if not r.feasible]
    assert len(feasible) == 2 and len(infeasible) == 2
    # feasible first, sorted desc by total_score
    assert results[0].feasible and results[1].feasible
    assert results[0].total_score >= results[1].total_score
    assert not results[-1].feasible


def test_modifier_can_change_winning_formation_toward_more_defenders():
    # Strong defenders (high sim_mean), weak-ish forwards. Without the modifier a
    # 3-defender shape wins on raw score; with it, the 5-defender shape's defence
    # bonus tips it.
    players = []
    code = 0
    for i in range(2):
        code += 1
        players.append(slot(code, "P", 6.5, mean=6.5))
    for i in range(6):
        code += 1
        players.append(slot(code, "D", 6.4, mean=9.0))  # score modest, sim_mean high
    for i in range(6):
        code += 1
        players.append(slot(code, "C", 6.6, mean=6.0))
    for i in range(4):
        code += 1
        players.append(slot(code, "A", 6.7, mean=6.0))

    f3 = parse_formation("3-4-3")
    f5 = parse_formation("5-3-2")

    off = compare_formations(players, [f3, f5], defence_modifier=False)
    on = compare_formations(players, [f3, f5], defence_modifier=True)
    assert off[0].formation.name == "3-4-3"
    assert on[0].formation.name == "5-3-2"
