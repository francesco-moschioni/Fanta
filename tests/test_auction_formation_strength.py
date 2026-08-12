import pytest

from fantacalcio.auction.formation_strength import (
    FormationStrengthError,
    RosterPlayer,
    compute_formation_strength,
    parse_formation,
)


class TestParseFormation:
    def test_parses_valid_formation(self):
        assert parse_formation("4-3-3") == {"D": 4, "C": 3, "A": 3}
        assert parse_formation("3-5-2") == {"D": 3, "C": 5, "A": 2}

    def test_rejects_malformed_strings(self):
        for bad in ["4-3", "4-3-3-1", "four-three-three", "4-3-x"]:
            with pytest.raises(FormationStrengthError, match="Malformed formation"):
                parse_formation(bad)


class TestComputeFormationStrength:
    def _owned(self):
        return [
            RosterPlayer(1, "P", 0.5),
            RosterPlayer(2, "P", 0.2),
            RosterPlayer(3, "P", -0.1),
            RosterPlayer(10, "D", 1.0),
            RosterPlayer(11, "D", 0.8),
            RosterPlayer(12, "D", 0.6),
            RosterPlayer(13, "D", 0.1),
            RosterPlayer(20, "C", 1.5),
            RosterPlayer(21, "C", 1.2),
            RosterPlayer(22, "C", 0.9),
            RosterPlayer(30, "A", 2.0),
            RosterPlayer(31, "A", 1.8),
        ]

    def test_picks_best_var_players_up_to_formation_need(self, ruleset):
        results = compute_formation_strength(self._owned(), ruleset)
        by_formation = {r.formation: r for r in results}
        f433 = by_formation["4-3-3"]
        assert {p.player_code for p in f433.starters} == {1, 10, 11, 12, 13, 20, 21, 22, 30, 31}
        # 1P (best=1, var 0.5) + 4D (10,11,12,13) + 3C (20,21,22) + 3A needed but only 2 owned (30,31)
        assert f433.missing_by_role == {"A": 1}
        assert not f433.fully_coverable

    def test_sorted_best_first(self, ruleset):
        results = compute_formation_strength(self._owned(), ruleset)
        totals = [r.total_var for r in results]
        assert totals == sorted(totals, reverse=True)

    def test_short_roster_flags_missing_role_without_crashing(self, ruleset):
        thin = [RosterPlayer(1, "P", 0.5), RosterPlayer(10, "D", 1.0)]
        results = compute_formation_strength(thin, ruleset)
        for r in results:
            assert not r.fully_coverable
            assert r.missing_by_role  # never silently empty when actually short

    def test_empty_roster_returns_zero_strength_for_every_formation(self, ruleset):
        results = compute_formation_strength([], ruleset)
        assert len(results) == len(ruleset.formations)
        assert all(r.total_var == 0.0 for r in results)
        assert all(not r.fully_coverable for r in results)

    def test_unknown_role_raises(self, ruleset):
        with pytest.raises(FormationStrengthError, match="Unknown role"):
            compute_formation_strength([RosterPlayer(1, "X", 1.0)], ruleset)
