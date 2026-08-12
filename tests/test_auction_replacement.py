import pandas as pd
import pytest

from fantacalcio.auction.replacement import (
    ReplacementLevelError,
    add_value_above_replacement,
    compute_replacement_levels,
    league_slots_per_role,
)


def test_league_slots_per_role_reads_from_config(ruleset):
    slots = league_slots_per_role(ruleset)
    assert slots["D"] == ruleset.roster.defenders * ruleset.teams
    assert slots["C"] == ruleset.roster.midfielders * ruleset.teams
    assert slots["A"] == ruleset.roster.forwards * ruleset.teams
    assert slots["P"] == ruleset.roster.goalkeeper_block_size * ruleset.teams


def _pool(rows):
    return pd.DataFrame(rows, columns=["role", "sim_mean", "sim_p10", "sim_p90"])


class TestComputeReplacementLevels:
    def test_replacement_is_value_at_the_slot_cutoff_rank(self, ruleset, monkeypatch):
        # Force small slot counts so we can hand-construct a tiny pool.
        import fantacalcio.auction.replacement as replacement_mod

        monkeypatch.setattr(replacement_mod, "league_slots_per_role", lambda rs: {"D": 2, "C": 2, "A": 2, "P": 2})
        rows = [("D", v, v - 1, v + 1) for v in [8.0, 7.0, 6.0, 5.0]]
        rows += [("C", 7.0, 6.0, 8.0), ("C", 6.0, 5.0, 7.0)]
        rows += [("A", 7.0, 6.0, 8.0), ("A", 6.0, 5.0, 7.0)]
        rows += [("P", 6.0, 5.0, 7.0), ("P", 5.0, 4.0, 6.0)]
        pool = _pool(rows)
        levels = compute_replacement_levels(pool, ruleset)
        # For D: 4 players ranked [8,7,6,5], 2 slots -> replacement is rank-2 = 7.0
        assert levels.by_role["D"] == 7.0
        assert levels.n_players_by_role["D"] == 4

    def test_fewer_players_than_slots_uses_lowest_available(self, ruleset, monkeypatch):
        import fantacalcio.auction.replacement as replacement_mod

        monkeypatch.setattr(replacement_mod, "league_slots_per_role", lambda rs: {"D": 100, "C": 1, "A": 1, "P": 1})
        rows = [("D", 8.0, 7.0, 9.0), ("D", 6.0, 5.0, 7.0)]
        rows += [("C", 7.0, 6.0, 8.0), ("A", 7.0, 6.0, 8.0), ("P", 6.0, 5.0, 7.0)]
        pool = _pool(rows)
        levels = compute_replacement_levels(pool, ruleset)
        assert levels.by_role["D"] == 6.0  # only 2 available, replacement = the worse one
        assert levels.n_players_by_role["D"] == 2
        assert levels.shortfall_by_role["D"] == 98  # 100 slots - 2 available
        assert levels.shortfall_by_role["C"] == 0  # exactly enough, no shortfall

    def test_unknown_role_raises(self, ruleset):
        pool = _pool([("X", 6.0, 5.0, 7.0)])
        with pytest.raises(ReplacementLevelError, match="no configured roster slot count"):
            compute_replacement_levels(pool, ruleset)

    def test_missing_role_entirely_raises(self, ruleset):
        pool = _pool([("D", 6.0, 5.0, 7.0)])  # missing C, A, P
        with pytest.raises(ReplacementLevelError, match="No players available"):
            compute_replacement_levels(pool, ruleset)


class TestAddValueAboveReplacement:
    def test_var_computed_relative_to_role_replacement(self, ruleset, monkeypatch):
        import fantacalcio.auction.replacement as replacement_mod

        monkeypatch.setattr(replacement_mod, "league_slots_per_role", lambda rs: {"D": 1, "C": 1, "A": 1, "P": 1})
        rows = [("D", 8.0, 7.0, 9.0), ("D", 6.0, 5.0, 7.0)]
        rows += [("C", 7.0, 6.0, 8.0), ("A", 7.0, 6.0, 8.0), ("P", 6.0, 5.0, 7.0)]
        pool = _pool(rows)
        levels = compute_replacement_levels(pool, ruleset)
        result = add_value_above_replacement(pool, levels)

        top_d = result[(result["role"] == "D") & (result["sim_mean"] == 8.0)].iloc[0]
        # replacement level for D (1 slot) = value of rank-1 player = 8.0 itself
        assert top_d["replacement_level"] == 8.0
        assert top_d["var_mean"] == 0.0

        second_d = result[(result["role"] == "D") & (result["sim_mean"] == 6.0)].iloc[0]
        assert second_d["var_mean"] == 6.0 - 8.0

    def test_var_propagates_uncertainty_quantiles(self, ruleset, monkeypatch):
        import fantacalcio.auction.replacement as replacement_mod

        monkeypatch.setattr(replacement_mod, "league_slots_per_role", lambda rs: {"D": 1, "C": 1, "A": 1, "P": 1})
        rows = [("D", 8.0, 7.0, 9.0)]
        rows += [("C", 7.0, 6.0, 8.0), ("A", 7.0, 6.0, 8.0), ("P", 6.0, 5.0, 7.0)]
        pool = _pool(rows)
        levels = compute_replacement_levels(pool, ruleset)
        result = add_value_above_replacement(pool, levels)
        row = result[result["role"] == "D"].iloc[0]
        assert row["var_p10"] == 7.0 - 8.0
        assert row["var_p90"] == 9.0 - 8.0

    def test_degenerate_replacement_flagged_only_for_shortfall_roles(self, ruleset, monkeypatch):
        import fantacalcio.auction.replacement as replacement_mod

        # D is short (100 slots, 2 available); C has exactly enough (1 slot, 1 available).
        monkeypatch.setattr(replacement_mod, "league_slots_per_role", lambda rs: {"D": 100, "C": 1, "A": 1, "P": 1})
        rows = [("D", 8.0, 7.0, 9.0), ("D", 6.0, 5.0, 7.0)]
        rows += [("C", 7.0, 6.0, 8.0), ("A", 7.0, 6.0, 8.0), ("P", 6.0, 5.0, 7.0)]
        pool = _pool(rows)
        levels = compute_replacement_levels(pool, ruleset)
        result = add_value_above_replacement(pool, levels)

        assert result[result["role"] == "D"]["degenerate_replacement"].all()
        assert not result[result["role"] == "C"]["degenerate_replacement"].any()
