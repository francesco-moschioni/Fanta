#!/usr/bin/env python3
"""M7 Engine v2 — Stage 5 (ADR-2026-078): fit + register the base-voto GBM.

Degrades gracefully when the optional ``ml`` extra is absent (the dev machine is
offline — ``pip install`` fails on SSL): prints a clear note and exits 0. The
durable Stage-5 deliverable is the registry + the ablation harness; the GBM fit
and its OOS ship gate are deferred until the extra can be installed.
"""

from __future__ import annotations

import sys

from fantacalcio.models.base_voto_gbm import HAS_LGB, HAS_SKLEARN, fit_base_voto_gbm

_ML_ABSENT_NOTE = (
    "ml extra not installed (scikit-learn / lightgbm) -- offline machine cannot "
    "`pip install`. Build the Stage-1 feature store and re-run this after "
    "`pip install '.[ml]'`. Nothing registered; this is an accepted Stage-5 "
    "outcome (ADR-2026-078)."
)


def main() -> int:
    if not (HAS_LGB and HAS_SKLEARN):
        print(_ML_ABSENT_NOTE)
        return 0

    # --- real path: only reachable where the ml extra is installed ------------
    try:
        import numpy as np
        import pandas as pd

        from fantacalcio.features.store import read_features
        from fantacalcio.models.registry import register
        from fantacalcio.modeling.validation import SEASON_ORDER  # noqa: F401

        feats = read_features("player_voto_running")  # long-format Stage-1 store
        wide = (
            feats.pivot_table(
                index=["entity_id", "season"],
                columns="feature_name",
                values="value",
                aggfunc="last",
            )
            .reset_index()
        )
        target_col = "actual_voto"
        if target_col not in wide.columns:
            print(
                "feature store has no 'actual_voto' column yet — wire the target "
                "join before fitting. Nothing registered."
            )
            return 0

        feature_cols = [c for c in wide.columns if c not in {"entity_id", "season", target_col}]
        x = wide[feature_cols]
        y = wide[target_col].to_numpy(dtype=float)

        # naive rolling-origin over seasons present
        seasons = sorted(wide["season"].unique())
        folds = []
        for i in range(1, len(seasons)):
            tr = np.where(wide["season"].isin(seasons[:i]))[0]
            te = np.where(wide["season"] == seasons[i])[0]
            if len(tr) and len(te):
                folds.append((tr, te))
        if not folds:
            print("not enough seasons for a rolling-origin fold; nothing registered.")
            return 0

        seed = 20260902
        result = fit_base_voto_gbm(x, y, folds, seed=seed)
        config = {
            "model": "base_voto_gbm",
            "quantiles": result["quantiles"],
            "params": result["artifact"]["params"],
            "feature_cols": feature_cols,
        }
        path = register(
            "base_voto_gbm",
            config=config,
            artifact=result["artifact"],
            folds=[{"train_season": seasons[:i], "test_season": seasons[i]} for i in range(1, len(seasons))],
            seed=seed,
            metrics=result["metrics"],
            feature_list=feature_cols,
            source_filter=None,
        )
        print(f"registered base_voto_gbm at {path}")
        print(f"OOS metrics: {result['metrics']['mae']=:.4f}  "
              f"{result['metrics']['spearman']=:.4f}  {result['metrics']['coverage']=:.4f}")
        print("Ship decision: run models.registry.beats_baseline vs the best "
              "mandatory baseline and record it in an ADR — CI does not decide.")
        return 0
    except Exception as exc:  # noqa: BLE001 - report and exit 0, nothing is shipped
        print(f"[skip] base-voto GBM fit not run: {exc}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
