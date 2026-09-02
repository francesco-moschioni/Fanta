from fantacalcio.lineup.bench import bench_notes, order_bench
from fantacalcio.lineup.formations import parse_formation
from fantacalcio.lineup.optimizer import PlayerSlot


def slot(code, role, score):
    return PlayerSlot(
        player_code=code, role=role, score=score, sim_mean=score,
        p10=score - 1, p90=score + 1, p_vote=1.0,
        display_name=f"P{code}", data_quality_tier="A",
    )


def test_gk_is_first_then_thinnest_role():
    f = parse_formation("3-5-2")  # D=3, C=5, A=2 -> A thinnest field role
    bench = [slot(1, "C", 9), slot(2, "D", 8), slot(3, "A", 5), slot(4, "P", 6)]
    ordered = order_bench(bench, f)
    assert ordered[0].role == "P"
    assert ordered[1].role == "A"  # thinnest field role starts next
    assert [s.role for s in ordered] == ["P", "A", "D", "C"]


def test_order_within_role_by_score_desc():
    f = parse_formation("4-4-2")
    bench = [slot(1, "D", 4.0), slot(2, "D", 7.0), slot(3, "D", 5.5)]
    ordered = order_bench(bench, f)
    assert [s.player_code for s in ordered] == [2, 3, 1]


def test_bench_notes_warns_on_single_backup_gk():
    f = parse_formation("3-4-3")
    bench = [slot(1, "P", 6), slot(2, "D", 6), slot(3, "D", 6), slot(4, "C", 6), slot(5, "A", 6)]
    notes = bench_notes(bench, f)
    assert any("portiere di riserva" in n for n in notes)


def test_bench_notes_warns_on_uncovered_role():
    f = parse_formation("3-4-3")
    bench = [slot(1, "P", 6), slot(2, "P", 6)]
    notes = bench_notes(bench, f)
    assert any("difensore" in n.lower() for n in notes)
