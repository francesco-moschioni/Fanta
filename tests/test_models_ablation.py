"""Stage 5 (ADR-2026-078): per-family / per-source / per-tier ablation harness."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fantacalcio.models.ablation import run_ablation


def _mean_fitter():
    def fit_fn(x_tr, y_tr):
        return float(np.mean(y_tr))

    def eval_fn(model, x_te, y_te):
        pred = np.full(len(y_te), model, dtype=float)
        return float(np.mean(np.abs(pred - np.asarray(y_te, dtype=float))))

    return fit_fn, eval_fn


def _frame(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 200
    df = pd.DataFrame(
        {
            "f_a1": rng.normal(size=n),
            "f_a2": rng.normal(size=n),
            "f_b1": rng.normal(size=n),
        }
    )
    df["target"] = 6.0 + rng.normal(scale=0.5, size=n)
    df["fold"] = np.repeat(np.arange(4), n // 4)
    return df


def _folds(df):
    out = []
    for f in sorted(df["fold"].unique()):
        te = df.index[df["fold"] == f].to_numpy()
        tr = df.index[df["fold"] != f].to_numpy()
        out.append((tr, te))
    return out


def test_ablation_table_shape_and_types():
    df = _frame()
    fit_fn, eval_fn = _mean_fitter()
    meta = {
        "f_a1": {"source": "src1", "tier": "B"},
        "f_a2": {"source": "src1", "tier": "B"},
        "f_b1": {"source": "src2", "tier": "C"},
    }
    table = run_ablation(
        fit_fn,
        eval_fn,
        df,
        families={"A": ["f_a1", "f_a2"], "B": ["f_b1"]},
        sources=["src1", "src2"],
        tiers=["A", "B", "C"],
        folds=_folds(df),
        feature_meta=meta,
        metric_name="mae",
    )
    assert set(table["ablation_type"]) == {"full", "family", "source", "tier"}
    # one full + 2 families + 2 sources + 3 tiers
    assert len(table) == 1 + 2 + 2 + 3
    assert {"delta_mean", "delta_se", "full_metric_mean", "ablated_metric_mean"} <= set(
        table.columns
    )
    # tier A maps to no columns here -> nothing dropped -> zero delta
    tier_a = table[(table.ablation_type == "tier") & (table.dropped == "A")].iloc[0]
    assert tier_a["n_features_dropped"] == 0


def test_dropping_family_ignored_by_trivial_model_gives_zero_delta():
    df = _frame()
    fit_fn, eval_fn = _mean_fitter()
    table = run_ablation(
        fit_fn,
        eval_fn,
        df,
        families={"A": ["f_a1", "f_a2"], "B": ["f_b1"]},
        sources=[],
        tiers=[],
        folds=_folds(df),
        metric_name="mae",
        n_boot=50,
    )
    fam_b = table[(table.ablation_type == "family") & (table.dropped == "B")].iloc[0]
    assert abs(fam_b["delta_mean"]) < 1e-9  # mean predictor ignores every feature
    fam_a = table[(table.ablation_type == "family") & (table.dropped == "A")].iloc[0]
    assert abs(fam_a["delta_mean"]) < 1e-9


def test_ablation_uses_feature_registry_when_no_meta_given():
    # real registered feature names -> source/tier resolved from FEATURE_REGISTRY
    rng = np.random.default_rng(0)
    n = 120
    df = pd.DataFrame(
        {
            "voto_running_shrunk_mean": rng.normal(size=n),  # source fantacalcio_voti_manual, tier B
            "team_elo_rating": rng.normal(size=n),  # source football_data_co_uk, tier A
        }
    )
    df["target"] = rng.normal(size=n)
    df["fold"] = np.repeat(np.arange(3), n // 3)
    fit_fn, eval_fn = _mean_fitter()
    table = run_ablation(
        fit_fn,
        eval_fn,
        df,
        families={"voto": ["voto_running_shrunk_mean"]},
        sources=["football_data_co_uk"],
        tiers=["A"],
        folds=_folds(df),
    )
    src_row = table[table.dropped == "football_data_co_uk"].iloc[0]
    tier_row = table[(table.ablation_type == "tier") & (table.dropped == "A")].iloc[0]
    assert src_row["n_features_dropped"] == 1  # team_elo_rating
    assert tier_row["n_features_dropped"] == 1
