"""Level-4 feature layer (ADR-2026-070, M7 Engine v2 — Stage 1).

A long-format feature store with per-row lineage and ``as_of`` slicing. The
builders in :mod:`fantacalcio.features.build` materialise features that were
previously computed implicitly inside the modeling modules; they call those
modules rather than reimplementing any math.
"""

from __future__ import annotations

from fantacalcio.features.schema import (
    FEATURE_REGISTRY,
    LINEAGE_COLUMNS,
    QUALITY_TIERS,
    FeatureSchemaError,
    FeatureSpec,
    validate_feature_frame,
)

__all__ = [
    "FEATURE_REGISTRY",
    "LINEAGE_COLUMNS",
    "QUALITY_TIERS",
    "FeatureSchemaError",
    "FeatureSpec",
    "validate_feature_frame",
]
