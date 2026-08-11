import pandas as pd
import pytest

from fantacalcio.auction.round_pools import assign_round_pools
from fantacalcio.config import ConfigError


def _pool(rows):
    return pd.DataFrame(rows, columns=["role", "var_mean"])


class TestAssignRoundPools:
    def test_goalkeepers_all_go_to_g1(self, ruleset):
        pool = _pool([("P", 0.5), ("P", -0.5), ("P", 0.0)])
        result = assign_round_pools(pool, ruleset)
        assert (result["round_pool"] == "G1").all()
        assert (result["list_pool_name"] == "goalkeeper_blocks").all()

    def test_top_defenders_go_to_g1_rest_to_remaining(self, ruleset):
        # 65 defenders: top 60 by var_mean should land in G1, the worst 5 in G3_G4.
        rows = [("D", float(65 - i)) for i in range(65)]
        pool = _pool(rows)
        result = assign_round_pools(pool, ruleset)
        g1 = result[result["round_pool"] == "G1"]
        remaining = result[result["round_pool"] == "G3_G4"]
        assert len(g1) == 60
        assert len(remaining) == 5
        assert g1["var_mean"].min() > remaining["var_mean"].max()

    def test_ties_at_cutoff_are_all_included_not_arbitrarily_broken(self, ruleset):
        # 61 defenders, but the 60th and 61st are tied -- both should be included
        # in G1 rather than picking one arbitrarily (no tie-break rule exists yet).
        rows = [("D", float(65 - i)) for i in range(59)] + [("D", 1.0), ("D", 1.0)]
        pool = _pool(rows)
        result = assign_round_pools(pool, ruleset)
        g1_defenders = result[(result["round_pool"] == "G1")]
        assert len(g1_defenders) == 61  # both tied players included

    def test_top_midfielders_and_forwards_go_to_g2(self, ruleset):
        rows = [("C", float(70 - i)) for i in range(70)] + [("A", float(50 - i)) for i in range(50)]
        pool = _pool(rows)
        result = assign_round_pools(pool, ruleset)
        g2 = result[result["round_pool"] == "G2"]
        assert len(g2[g2["role"] == "C"]) == 60
        assert len(g2[g2["role"] == "A"]) == 40
        remaining = result[result["round_pool"] == "G3_G4"]
        assert len(remaining[remaining["role"] == "C"]) == 10
        assert len(remaining[remaining["role"] == "A"]) == 10

    def test_fewer_players_than_cutoff_all_go_to_g1_or_g2(self, ruleset):
        pool = _pool([("D", 1.0), ("D", 2.0)])  # only 2, cutoff is 60
        result = assign_round_pools(pool, ruleset)
        assert (result["round_pool"] == "G1").all()

    def test_list_state_is_provisional(self, ruleset):
        pool = _pool([("P", 0.0)])
        result = assign_round_pools(pool, ruleset)
        assert (result["list_state"] == "provisional").all()

    def test_custom_rank_col(self, ruleset):
        pool = pd.DataFrame({"role": ["D", "D"], "quotazione": [10, 5]})
        result = assign_round_pools(pool, ruleset, rank_col="quotazione")
        assert result.iloc[0]["round_pool"] == "G1"
