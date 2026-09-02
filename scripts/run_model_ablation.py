#!/usr/bin/env python3
"""M7 Engine v2 — Stage 5 (ADR-2026-078): per-source / per-tier ablation harness.

The harness itself is pure numpy/pandas/scipy and always runs: with the ``ml``
extra absent it does a **smoke demo** on a small synthetic frame with the
built-in trivial mean fitter, so the tidy delta table shape can be inspected
offline. With the extra present it would swap in a real LightGBM fitter over the
Stage-1 feature store. Exits 0 either way.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from fantacalcio.models.ablation import run_ablation

try:
    from fantacalcio.models.base_voto_gbm import HAS_LGB
except Exception:  # noqa: BLE001
    HAS_LGB = False


def _trivial_fitter():
    def fit_fn(x_tr: pd.DataFrame, y_tr: pd.Series):
        # mean predictor: ignores features entirely (ablation deltas ~ 0)
        return float(np.mean(y_tr))

    def eval_fn(model, x_te: pd.DataFrame, y_te: pd.Series) -> float:
        pred = np.full(len(y_te), model, dtype=float)
        return float(np.mean(np.abs(pred - np.asarray(y_te, dtype=float))))

    return fit_fn, eval_fn


def _synthetic_frame(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 240
    df = pd.DataFrame(
        {
            "feat_hist_a": rng.normal(size=n),
            "feat_hist_b": rng.normal(size=n),
            "feat_odds_a": rng.normal(size=n),
            "feat_xg_a": rng.normal(size=n),
        }
    )
    df["target"] = 6.0 + 0.4 * df["feat_hist_a"] + rng.normal(scale=0.5, size=n)
    df["fold"] = np.repeat(np.arange(4), n // 4)
    return df


def main() -> int:
    if not HAS_LGB:
        print(
            "ml extra not installed -- running the ablation harness smoke demo "
            "with the built-in trivial mean fitter. Re-run with a real fitter "
            "after `pip install '.[ml]'` (ADR-2026-078)."
        )

    df = _synthetic_frame()
    fit_fn, eval_fn = _trivial_fitter()
    folds = []
    for f in sorted(df["fold"].unique()):
        te = df.index[df["fold"] == f].to_numpy()
        tr = df.index[df["fold"] != f].to_numpy()
        folds.append((tr, te))

    feature_meta = {
        "feat_hist_a": {"source": "fantacalcio_voti_manual", "tier": "B"},
        "feat_hist_b": {"source": "fantacalcio_voti_manual", "tier": "B"},
        "feat_odds_a": {"source": "football_data_co_uk", "tier": "A"},
        "feat_xg_a": {"source": "understat", "tier": "C"},
    }
    table = run_ablation(
        fit_fn,
        eval_fn,
        df,
        families={
            "history": ["feat_hist_a", "feat_hist_b"],
            "odds": ["feat_odds_a"],
            "xg": ["feat_xg_a"],
        },
        sources=["fantacalcio_voti_manual", "football_data_co_uk", "understat"],
        tiers=["A", "B", "C"],
        folds=folds,
        feature_meta=feature_meta,
        metric_name="mae",
        n_boot=200,
        seed=0,
    )
    with pd.option_context("display.max_columns", None, "display.width", 160):
        print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
