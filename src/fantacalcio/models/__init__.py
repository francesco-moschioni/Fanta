"""Taxonomy level 5 — ``models``: config, fit, folds, seed, metrics, artifact.

Lightweight by design (ADR-2026-078): no server, no database, no MLflow/DVC. A
registered model is a directory ``data/models/<name>/<config_hash>/`` holding
``manifest.json`` + ``artifact.pkl`` + ``metrics.json``.

``base_voto_gbm`` imports of ``lightgbm`` / ``scikit-learn`` are guarded so the
core and every non-ML test run without the optional ``ml`` extra.
"""

from __future__ import annotations

from fantacalcio.models.registry import (
    RegisteredModel,
    beats_baseline,
    config_hash,
    list_models,
    load,
    register,
)

__all__ = [
    "RegisteredModel",
    "beats_baseline",
    "config_hash",
    "list_models",
    "load",
    "register",
]
