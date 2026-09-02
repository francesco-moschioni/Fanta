"""Per-family / per-source / per-quality-tier ablation harness (ADR-2026-078).

Pure ``numpy`` / ``pandas`` / ``scipy`` / stdlib — runs *without* the ``ml``
extra by taking an arbitrary ``fit_fn`` / ``eval_fn`` (tests pass a trivial
mean / linear fitter). The durable deliverable of Stage 5.

Contract
--------
``feature_frame`` is a **wide** modelling matrix: one row per observation,
feature columns + a target column (``target_col``) + optional bookkeeping
columns. ``folds`` is a list of ``(train_index, test_index)`` pairs of pandas
index labels (leakage discipline is the caller's job — pass rolling-origin
splits).

For each ablation the matching feature columns are *dropped*, the model is
retrained on every fold, and the metric delta vs. the full-feature model is
reported with a fold-spread (or bootstrap) uncertainty column.

Column -> (source_name, quality_tier) membership is taken from
:data:`fantacalcio.features.schema.FEATURE_REGISTRY` when the column is a
registered feature name, or from the optional ``feature_meta`` override
``{col: {"source": ..., "tier": ...}}``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd

from fantacalcio.features.schema import FEATURE_REGISTRY

FitFn = Callable[[pd.DataFrame, pd.Series], Any]
EvalFn = Callable[[Any, pd.DataFrame, pd.Series], float]


def _column_meta(col: str, feature_meta: dict | None) -> tuple[str | None, str | None]:
    if feature_meta and col in feature_meta:
        m = feature_meta[col]
        return m.get("source"), m.get("tier")
    spec = FEATURE_REGISTRY.get(col)
    if spec is not None:
        return spec.source_name, spec.quality_tier
    return None, None


def _fold_split(
    frame: pd.DataFrame, fold: Any, fold_col: str
) -> tuple[pd.Index, pd.Index]:
    if isinstance(fold, (tuple, list)) and len(fold) == 2:
        train_idx, test_idx = fold
        return pd.Index(train_idx), pd.Index(test_idx)
    # scalar fold: match `fold_col` for the test rows, the rest is train.
    if fold_col not in frame.columns:
        raise ValueError(
            f"scalar fold {fold!r} needs column {fold_col!r} in feature_frame"
        )
    test_mask = frame[fold_col] == fold
    return frame.index[~test_mask], frame.index[test_mask]


def _fit_eval_over_folds(
    fit_fn: FitFn,
    eval_fn: EvalFn,
    frame: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    fold_col: str,
    folds: Sequence[Any],
) -> np.ndarray:
    """Return the per-fold metric of ``fit_fn`` restricted to ``feature_cols``."""
    scores: list[float] = []
    for fold in folds:
        train_idx, test_idx = _fold_split(frame, fold, fold_col)
        x_tr = frame.loc[train_idx, feature_cols]
        y_tr = frame.loc[train_idx, target_col]
        x_te = frame.loc[test_idx, feature_cols]
        y_te = frame.loc[test_idx, target_col]
        model = fit_fn(x_tr, y_tr)
        scores.append(float(eval_fn(model, x_te, y_te)))
    return np.asarray(scores, dtype=float)


def _uncertainty(
    deltas: np.ndarray, *, n_boot: int, rng: np.random.Generator
) -> float:
    """Fold-spread SE, or bootstrap SE over folds when ``n_boot > 0``."""
    n = deltas.size
    if n < 2:
        return float("nan")
    if n_boot and n_boot > 0:
        means = [
            float(np.mean(deltas[rng.integers(0, n, n)])) for _ in range(int(n_boot))
        ]
        return float(np.std(means, ddof=1))
    return float(np.std(deltas, ddof=1) / np.sqrt(n))


def run_ablation(
    fit_fn: FitFn,
    eval_fn: EvalFn,
    feature_frame: pd.DataFrame,
    *,
    families: dict[str, list[str]],
    sources: list[str],
    tiers: list[str],
    folds: Sequence[Any],
    target_col: str = "target",
    fold_col: str = "fold",
    feature_meta: dict | None = None,
    metric_name: str = "metric",
    n_boot: int = 0,
    seed: int = 0,
) -> pd.DataFrame:
    """Retrain dropping each feature family / source / whole quality tier.

    Returns a tidy frame with one row per ablation:

        ablation_type   {"full", "family", "source", "tier"}
        dropped         the family / source / tier label ("" for the full model)
        n_features_dropped
        metric          ``metric_name``
        full_metric_mean, ablated_metric_mean, delta_mean, delta_se, n_folds

    ``delta_mean`` is ``mean(ablated_fold) - mean(full_fold)``. A positive delta
    means the metric got *worse* on drop iff the metric is an error; sign is not
    interpreted here — the caller knows the metric's direction.
    """
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(feature_frame)
    reserved = {target_col, fold_col}
    all_features = [c for c in frame.columns if c not in reserved]
    if not all_features:
        raise ValueError("feature_frame has no feature columns")

    full_scores = _fit_eval_over_folds(
        fit_fn, eval_fn, frame, all_features, target_col, fold_col, folds
    )
    full_mean = float(np.mean(full_scores))
    n_folds = int(full_scores.size)

    rows: list[dict] = [
        {
            "ablation_type": "full",
            "dropped": "",
            "n_features_dropped": 0,
            "metric": metric_name,
            "full_metric_mean": full_mean,
            "ablated_metric_mean": full_mean,
            "delta_mean": 0.0,
            "delta_se": 0.0,
            "n_folds": n_folds,
        }
    ]

    def _add(ablation_type: str, label: str, drop_cols: list[str]) -> None:
        drop_set = {c for c in drop_cols if c in all_features}
        kept = [c for c in all_features if c not in drop_set]
        if not kept:
            # nothing left to fit on: record the ablation but leave metrics NaN
            rows.append(
                {
                    "ablation_type": ablation_type,
                    "dropped": label,
                    "n_features_dropped": len(drop_set),
                    "metric": metric_name,
                    "full_metric_mean": full_mean,
                    "ablated_metric_mean": float("nan"),
                    "delta_mean": float("nan"),
                    "delta_se": float("nan"),
                    "n_folds": n_folds,
                }
            )
            return
        scores = _fit_eval_over_folds(
            fit_fn, eval_fn, frame, kept, target_col, fold_col, folds
        )
        deltas = scores - full_scores
        rows.append(
            {
                "ablation_type": ablation_type,
                "dropped": label,
                "n_features_dropped": len(drop_set),
                "metric": metric_name,
                "full_metric_mean": full_mean,
                "ablated_metric_mean": float(np.mean(scores)),
                "delta_mean": float(np.mean(deltas)),
                "delta_se": _uncertainty(deltas, n_boot=n_boot, rng=rng),
                "n_folds": n_folds,
            }
        )

    for fam, cols in families.items():
        _add("family", fam, list(cols))

    for src in sources:
        cols = [c for c in all_features if _column_meta(c, feature_meta)[0] == src]
        _add("source", src, cols)

    for tier in tiers:
        cols = [c for c in all_features if _column_meta(c, feature_meta)[1] == tier]
        _add("tier", tier, cols)

    return pd.DataFrame(rows)


__all__ = ["run_ablation"]
