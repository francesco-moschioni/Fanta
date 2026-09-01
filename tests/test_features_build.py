import numpy as np
import pandas as pd
import pytest

from fantacalcio.features.build import (
    build_all_features,
    build_fvm_prior_features,
    build_listone_features,
    build_participation_features,
    build_player_voto_features,
    build_recency_weight_features,
    build_team_strength_features,
)
from fantacalcio.features.schema import LINEAGE_COLUMNS, validate_feature_frame
from fantacalcio.modeling.participation import compute_season_participation
from fantacalcio.modeling.player_voto import walk_forward


def _voti_panel() -> pd.DataFrame:
    rows = []
    for season_rank, season_label in enumerate(["2021_22", "2022_23"]):
        for md in range(1, 7):
            rows.append(
                {
                    "season_rank": season_rank,
                    "season_label": season_label,
                    "matchday": md,
                    "player_code": 1,
                    "role": "D",
                    "voto": 6.0 + 0.1 * md,
                    "voto_no_vote": False,
                }
            )
            rows.append(
                {
                    "season_rank": season_rank,
                    "season_label": season_label,
                    "matchday": md,
                    "player_code": 2,
                    "role": "A",
                    "voto": 7.0,
                    "voto_no_vote": False,
                }
            )
    return pd.DataFrame(rows)


def _matches() -> pd.DataFrame:
    teams = ["Alpha", "Beta", "Gamma"]
    rows = []
    base = pd.Timestamp("2024-09-01")
    n = 0
    for rnd in range(4):
        for i in range(3):
            for j in range(3):
                if i == j:
                    continue
                hg, ag = (2, 1) if (i + rnd) % 2 == 0 else (0, 1)
                ftr = "H" if hg > ag else ("A" if ag > hg else "D")
                rows.append(
                    {
                        "Date": base + pd.Timedelta(days=7 * n),
                        "HomeTeam": teams[i],
                        "AwayTeam": teams[j],
                        "FTHG": hg,
                        "FTAG": ag,
                        "FTR": ftr,
                    }
                )
                n += 1
    return pd.DataFrame(rows)


def _assert_valid(df: pd.DataFrame) -> None:
    validate_feature_frame(df)
    assert not df.empty
    for col in LINEAGE_COLUMNS:
        assert df[col].notna().all(), col


def test_player_voto_builder_valid_and_regression_locked():
    panel = _voti_panel()
    feats = build_player_voto_features(panel, prior_games=60.0)
    _assert_valid(feats)

    reference = walk_forward(panel, prior_games=60.0)
    got = (
        feats[feats["feature_name"] == "voto_running_shrunk_mean"]
        .assign(player_code=lambda d: d["entity_id"].astype(int))
        .sort_values(["season", "player_code"])
        .reset_index(drop=True)
    )
    ref = reference.sort_values(["season_label", "player_code"]).reset_index(drop=True)
    np.testing.assert_allclose(got["value"].to_numpy(), ref["shrinkage_pred"].to_numpy())


def test_participation_builder_valid():
    part = compute_season_participation(_voti_panel())
    feats = build_participation_features(part, target_season="2026_27")
    _assert_valid(feats)
    assert set(feats["feature_name"]) == {
        "participation_decayed_rate",
        "participation_latest_rate",
        "participation_crosscheck_delta",
    }


def test_recency_weight_builder_valid():
    feats = build_recency_weight_features(_voti_panel(), season="2026_27")
    _assert_valid(feats)
    assert (feats["feature_name"] == "recency_weight").all()
    assert feats["value"].max() <= 1.0 + 1e-9


def test_team_strength_builder_valid():
    feats = build_team_strength_features(_matches(), season="2026_27")
    _assert_valid(feats)
    assert set(feats["feature_name"]) == {
        "team_attack_strength",
        "team_defense_strength",
        "team_elo_rating",
    }


def test_fvm_prior_builder_valid():
    rng = np.random.default_rng(0)
    train = pd.DataFrame(
        {
            "role": ["D"] * 20 + ["A"] * 20,
            "fvm_classic": np.concatenate(
                [rng.uniform(1, 100, 20), rng.uniform(1, 200, 20)]
            ),
        }
    )
    targets = pd.DataFrame(
        {"player_code": [10, 11, 12], "role": ["D", "A", "D"], "fvm_classic": [5.0, 150.0, 80.0]}
    )
    feats = build_fvm_prior_features(train, targets, target_season="2026_27")
    _assert_valid(feats)
    assert set(feats["feature_name"]) == {
        "fvm_bucket",
        "fvm_bucket_low_edge",
        "fvm_bucket_high_edge",
    }


def test_listone_builder_valid():
    listone = pd.DataFrame(
        {
            "player_code": [10, 11],
            "role": ["D", "A"],
            "quotazione_asta_classic": [12, 30],
            "fvm_classic": [40, 120],
        }
    )
    admin = pd.DataFrame(
        {"player_code": [10], "rank": [3], "list_header_label": ["1-20 difensori"]}
    )
    feats = build_listone_features(listone, admin, target_season="2026_27")
    _assert_valid(feats)
    assert "listone_admin_rank" in set(feats["feature_name"])
    assert "listone_list_pool_name" in set(feats["feature_name"])


def test_build_all_features_dispatch():
    panel = _voti_panel()
    out = build_all_features(
        voti_panel=panel,
        season_participation=compute_season_participation(panel),
        recency_panel=panel,
        matches=_matches(),
        target_season="2026_27",
    )
    assert set(out) == {"player_voto", "participation", "recency_weight", "team_strength"}
    for df in out.values():
        _assert_valid(df)
