"""Stage 5 (ADR-2026-078): lightweight model registry + ship-gate comparison."""

from __future__ import annotations

import pandas as pd
import pytest

from fantacalcio.features.leakage import LeakageError, assert_available_before_decision
from fantacalcio.models.registry import (
    beats_baseline,
    config_hash,
    list_models,
    load,
    register,
)


# --------------------------------------------------------------------------- #
# config_hash
# --------------------------------------------------------------------------- #
def test_config_hash_stable_under_key_reordering():
    a = {"lr": 0.05, "leaves": 31, "nested": {"x": 1, "y": 2}}
    b = {"nested": {"y": 2, "x": 1}, "leaves": 31, "lr": 0.05}
    assert config_hash(a) == config_hash(b)
    assert len(config_hash(a)) == 16


def test_config_hash_changes_on_any_value_change():
    base = {"lr": 0.05, "leaves": 31}
    assert config_hash(base) != config_hash({"lr": 0.05, "leaves": 32})
    assert config_hash(base) != config_hash({"lr": 0.06, "leaves": 31})


# --------------------------------------------------------------------------- #
# register / load round-trip
# --------------------------------------------------------------------------- #
def test_register_load_round_trip(tmp_path):
    artifact = {"weights": [1.0, 2.0, 3.0], "kind": "dummy"}
    metrics = {"mae": 1.23, "spearman": 0.55, "coverage": 0.8}
    folds = [("2223", "2324"), ("2324", "2425")]
    feature_list = ["voto_running_shrunk_mean", "fvm_bucket"]

    path = register(
        "toy",
        config={"lr": 0.1, "depth": 3},
        artifact=artifact,
        folds=folds,
        seed=42,
        metrics=metrics,
        feature_list=feature_list,
        source_filter={"exclude_tier": "C"},
        root=tmp_path,
    )
    assert path.is_dir()

    got = load("toy", root=tmp_path)
    assert got.artifact == artifact
    assert got.metrics == metrics
    assert got.manifest["seed"] == 42
    assert got.manifest["feature_list"] == feature_list
    assert got.manifest["source_filter"] == {"exclude_tier": "C"}
    assert got.manifest["git_sha"]  # non-empty (real sha or "unknown")
    assert len(got.manifest["folds"]) == 2
    assert got.manifest["folds"][0] == ["2223", "2324"]
    assert "created_at" in got.manifest


def test_load_by_pinned_config_hash(tmp_path):
    register("toy", config={"v": 1}, artifact="a1", folds=[], seed=1,
             metrics={"mae": 2.0}, feature_list=["f"], root=tmp_path)
    register("toy", config={"v": 2}, artifact="a2", folds=[], seed=1,
             metrics={"mae": 1.0}, feature_list=["f"], root=tmp_path)

    h1 = config_hash({"v": 1})
    assert load("toy", config_hash=h1, root=tmp_path).artifact == "a1"
    # latest by created_at is the second one
    assert load("toy", root=tmp_path).artifact == "a2"

    with pytest.raises(FileNotFoundError):
        load("toy", config_hash="deadbeefdeadbeef", root=tmp_path)
    with pytest.raises(FileNotFoundError):
        load("missing", root=tmp_path)


def test_list_models_newest_first(tmp_path):
    register("m", config={"v": 1}, artifact=1, folds=[], seed=0,
             metrics={}, feature_list=[], root=tmp_path)
    register("m", config={"v": 2}, artifact=2, folds=[], seed=0,
             metrics={}, feature_list=[], root=tmp_path)
    register("other", config={"v": 1}, artifact=3, folds=[], seed=0,
             metrics={}, feature_list=[], root=tmp_path)

    all_m = list_models(root=tmp_path)
    assert len(all_m) == 3
    keys = [(x["created_at"], x["created_at_ns"]) for x in all_m]
    assert keys == sorted(keys, reverse=True)

    only_m = list_models("m", root=tmp_path)
    assert {x["name"] for x in only_m} == {"m"}
    assert len(only_m) == 2


# --------------------------------------------------------------------------- #
# beats_baseline
# --------------------------------------------------------------------------- #
def test_beats_baseline_all_better_wins():
    model = {"mae": 0.9, "spearman": 0.6, "coverage": 0.82}
    base = {"mae": 1.0, "spearman": 0.5, "coverage": 0.78}
    out = beats_baseline(model, base)
    assert out["overall_wins"] is True
    assert set(out["per_key"]) == {"mae", "spearman", "coverage"}
    assert out["per_key"]["mae"]["direction"] == "lower_is_better"
    assert out["per_key"]["spearman"]["strictly_better"] is True


def test_beats_baseline_one_worse_loses_but_still_reports():
    model = {"mae": 1.1, "spearman": 0.6, "coverage": 0.82}  # mae worse
    base = {"mae": 1.0, "spearman": 0.5, "coverage": 0.78}
    out = beats_baseline(model, base)
    assert out["overall_wins"] is False
    assert out["per_key"]["mae"]["better_or_equal"] is False
    assert out["per_key"]["spearman"]["strictly_better"] is True  # full comparison kept


def test_beats_baseline_equal_everywhere_is_not_a_win():
    m = {"mae": 1.0, "spearman": 0.5, "coverage": 0.8}
    out = beats_baseline(m, dict(m))
    assert out["overall_wins"] is False  # better-or-equal all, but none strictly better


# --------------------------------------------------------------------------- #
# training-time leakage helper (reused from the feature layer)
# --------------------------------------------------------------------------- #
def test_training_rows_available_before_fold_decision_time():
    decision = pd.Timestamp("2025-08-01")
    clean = pd.DataFrame(
        {
            "entity_type": ["player", "player"],
            "entity_id": [1, 2],
            "feature_name": ["voto_running_shrunk_mean", "voto_running_shrunk_mean"],
            "available_time": [pd.Timestamp("2025-05-01"), pd.Timestamp("2025-07-31")],
        }
    )
    assert_available_before_decision(clean, decision)  # no raise

    poisoned = clean.copy()
    poisoned.loc[1, "available_time"] = pd.Timestamp("2025-09-01")
    with pytest.raises(LeakageError):
        assert_available_before_decision(poisoned, decision)
