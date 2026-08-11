import numpy as np
import pandas as pd

from fantacalcio.scoring.fvm_prior import (
    assign_bucket,
    build_fvm_bucketed_role_pools,
    fit_fvm_bucket_edges,
)


class TestFitFvmBucketEdges:
    def test_produces_edges_per_role(self):
        df = pd.DataFrame({"role": ["A"] * 8 + ["D"] * 8, "fvm_classic": list(range(1, 9)) + list(range(1, 9))})
        edges = fit_fvm_bucket_edges(df, n_buckets=4)
        assert set(edges.keys()) == {"A", "D"}
        assert edges["A"][0] == 1
        assert edges["A"][-1] == 8

    def test_handles_constant_fvm_without_crashing(self):
        df = pd.DataFrame({"role": ["A"] * 5, "fvm_classic": [10, 10, 10, 10, 10]})
        edges = fit_fvm_bucket_edges(df, n_buckets=4)
        assert len(edges["A"]) >= 2


class TestAssignBucket:
    def test_low_value_lands_in_first_bucket(self):
        edges = {"A": np.array([1.0, 10.0, 20.0, 30.0, 40.0])}
        assert assign_bucket(2.0, "A", edges) == 0

    def test_high_value_lands_in_last_bucket(self):
        edges = {"A": np.array([1.0, 10.0, 20.0, 30.0, 40.0])}
        assert assign_bucket(1000.0, "A", edges) == 3

    def test_unknown_role_defaults_to_bucket_zero(self):
        edges = {"A": np.array([1.0, 10.0])}
        assert assign_bucket(5.0, "Z", edges) == 0


class TestBuildFvmBucketedRolePools:
    def test_groups_rows_by_role_and_bucket(self):
        df = pd.DataFrame(
            {
                "role": ["A", "A"],
                "fvm_classic": [2.0, 35.0],
                "voto": [6.0, 7.0],
                "goals_scored": [0, 1],
                "assists": [0, 0],
                "goals_conceded": [0, 0],
                "own_goals": [0, 0],
                "yellow_cards": [0, 0],
                "red_cards": [0, 0],
                "penalties_missed": [0, 0],
                "team_goals_conceded": [np.nan, np.nan],
            }
        )
        edges = {"A": np.array([1.0, 10.0, 20.0, 30.0, 40.0])}
        pools = build_fvm_bucketed_role_pools(df, edges)
        assert pools[("A", 0)][0].voto == 6.0
        assert pools[("A", 3)][0].voto == 7.0

    def test_excludes_rows_with_unknown_fvm(self):
        df = pd.DataFrame(
            {
                "role": ["A"],
                "fvm_classic": [np.nan],
                "voto": [6.0],
                "goals_scored": [0],
                "assists": [0],
                "goals_conceded": [0],
                "own_goals": [0],
                "yellow_cards": [0],
                "red_cards": [0],
                "penalties_missed": [0],
                "team_goals_conceded": [np.nan],
            }
        )
        edges = {"A": np.array([1.0, 10.0])}
        pools = build_fvm_bucketed_role_pools(df, edges)
        assert pools == {}
