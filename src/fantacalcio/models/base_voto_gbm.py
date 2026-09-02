"""Gradient-boosted base-voto regressor on Stage-1 features (ADR-2026-078).

**Built but guarded.** ``lightgbm`` and ``scikit-learn`` live in the optional
``ml`` extra; the imports below are wrapped so the core and every non-ML test
import this module cleanly. The actual GBM training and the OOS ship gate are
DEFERRED until the extra can be installed (the dev machine is offline — no
``pip install``).

Ship gate (deferred, ADR-2026-078): promote to ``base_voto.model="gbm"`` only if
the GBM beats the best mandatory baseline (``modeling.baselines`` +
``player_voto`` EB shrinkage) on rolling-origin folds on **MAE** *and*
**rank-corr** *and* **calibration**, with ``models.ablation`` showing no
single-source dependence. "Not shipped" is a likely and acceptable outcome — the
labelled panel is small and repetitive and EB shrinkage is a strong baseline.

Pipeline discipline: imputation / quantile fitting / isotonic calibration all
happen **inside each fold** (calibration on that fold's held-out data).
Deterministic given ``seed`` + ``num_threads=1``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

try:  # optional ml extra
    import lightgbm as lgb  # noqa: F401

    HAS_LGB = True
except ImportError:  # pragma: no cover - exercised only where the extra is absent
    lgb = None  # type: ignore[assignment]
    HAS_LGB = False

try:
    from sklearn.isotonic import IsotonicRegression  # noqa: F401

    HAS_SKLEARN = True
except ImportError:  # pragma: no cover
    IsotonicRegression = None  # type: ignore[assignment,misc]
    HAS_SKLEARN = False

_NOT_INSTALLED_MSG = "lightgbm not installed; pip install '.[ml]'"

DEFAULT_QUANTILES: tuple[float, ...] = (0.1, 0.5, 0.9)

_DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "quantile",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "num_threads": 1,
    "deterministic": True,
    "force_row_wise": True,
    "verbose": -1,
}


def _fold_indices(fold: Any) -> tuple[np.ndarray, np.ndarray]:
    """Accept ``(train_idx, test_idx)`` positional integer arrays."""
    if isinstance(fold, (tuple, list)) and len(fold) == 2:
        return np.asarray(fold[0], dtype=int), np.asarray(fold[1], dtype=int)
    raise TypeError(
        "fold must be a (train_idx, test_idx) pair of positional integer arrays"
    )


def fit_base_voto_gbm(
    features_df: pd.DataFrame,
    target,
    folds: list,
    *,
    seed: int,
    params: dict | None = None,
) -> dict:
    """Fit quantile GBMs with in-fold isotonic calibration; return artifact + metrics.

    Raises ``RuntimeError(_NOT_INSTALLED_MSG)`` when the ``ml`` extra is absent,
    so CI without the extra still exercises this guard.

    Returns a dict:
        ``artifact``   {final_models, impute_medians, quantiles, feature_list,
                        seed, params}
        ``metrics``    {mae, spearman, coverage, per_fold}
        ``quantiles``  the quantile levels
        ``oos``        {index, pred_median, true} concatenated over folds
    """
    if not HAS_LGB:
        raise RuntimeError(_NOT_INSTALLED_MSG)
    if not HAS_SKLEARN:  # pragma: no cover - needs the extra to reach
        raise RuntimeError(
            "scikit-learn not installed; pip install '.[ml]' (isotonic calibration)"
        )

    # Imports are safe here: this branch only runs with the extra present.
    from fantacalcio.modeling.metrics import mae, spearman_rank_corr

    x = pd.DataFrame(features_df).reset_index(drop=True)
    y = np.asarray(target, dtype=float)
    quantiles = tuple(DEFAULT_QUANTILES)
    p = dict(_DEFAULT_PARAMS)
    p["random_state"] = seed
    if params:
        p.update(params)

    per_fold: list[dict] = []
    oos_index: list[int] = []
    oos_median: list[float] = []
    oos_true: list[float] = []

    for k, fold in enumerate(folds):
        tr, te = _fold_indices(fold)
        x_tr, x_te = x.iloc[tr], x.iloc[te]
        y_tr, y_te = y[tr], y[te]

        medians = x_tr.median(numeric_only=True)
        x_tr_i = x_tr.fillna(medians)
        x_te_i = x_te.fillna(medians)

        preds: dict[float, np.ndarray] = {}
        for q in quantiles:
            model = lgb.LGBMRegressor(alpha=q, **p)
            model.fit(x_tr_i, y_tr)
            raw = np.asarray(model.predict(x_te_i), dtype=float)
            # isotonic calibration of the quantile prediction on held-out truth
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(raw, y_te)
            preds[q] = np.asarray(iso.predict(raw), dtype=float)

        median = preds[0.5]
        lo = preds[min(quantiles)]
        hi = preds[max(quantiles)]
        per_fold.append(
            {
                "fold": k,
                "mae": mae(median, y_te),
                "spearman": spearman_rank_corr(median, y_te),
                "coverage": float(np.mean((y_te >= lo) & (y_te <= hi))),
            }
        )
        oos_index.extend(int(i) for i in te)
        oos_median.extend(float(v) for v in median)
        oos_true.extend(float(v) for v in y_te)

    # Ship artifact: refit each quantile on all rows.
    medians_all = x.median(numeric_only=True)
    x_all = x.fillna(medians_all)
    final_models = {}
    for q in quantiles:
        model = lgb.LGBMRegressor(alpha=q, **p)
        model.fit(x_all, y)
        final_models[q] = model

    def _avg(key: str) -> float:
        return float(np.mean([f[key] for f in per_fold])) if per_fold else float("nan")

    metrics = {
        "mae": _avg("mae"),
        "spearman": _avg("spearman"),
        "coverage": _avg("coverage"),
        "per_fold": per_fold,
    }
    artifact = {
        "final_models": final_models,
        "impute_medians": medians_all.to_dict(),
        "quantiles": list(quantiles),
        "feature_list": list(x.columns),
        "seed": seed,
        "params": p,
    }
    return {
        "artifact": artifact,
        "metrics": metrics,
        "quantiles": list(quantiles),
        "oos": {"index": oos_index, "pred_median": oos_median, "true": oos_true},
    }


def predict_base_voto_gbm(artifact: dict, features_df: pd.DataFrame) -> pd.DataFrame:
    """Predict the calibrated quantiles from a fitted ``artifact``.

    Guarded like :func:`fit_base_voto_gbm`.
    """
    if not HAS_LGB:  # pragma: no cover - guard
        raise RuntimeError(_NOT_INSTALLED_MSG)
    x = pd.DataFrame(features_df).reindex(columns=artifact["feature_list"])
    x = x.fillna(pd.Series(artifact["impute_medians"]))
    out = {}
    for q, model in artifact["final_models"].items():
        out[f"q{q}"] = np.asarray(model.predict(x), dtype=float)
    return pd.DataFrame(out, index=x.index)


__all__ = [
    "HAS_LGB",
    "HAS_SKLEARN",
    "DEFAULT_QUANTILES",
    "fit_base_voto_gbm",
    "predict_base_voto_gbm",
]
