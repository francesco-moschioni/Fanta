"""Stage 3 (ADR-2026-075): xG/xA per-90 shrunk features."""

from __future__ import annotations

import pandas as pd
import pytest

from fantacalcio.features.leakage import assert_available_before_decision
from fantacalcio.features.schema import LINEAGE_COLUMNS, validate_feature_frame
from fantacalcio.features.xg_features import XG_FEATURE_NAMES, build_xg_features


def _understat_frame() -> pd.DataFrame:
    rows = [
        ("Rossi", "A", "2023_24", 12, 10.5, 5, 4.2, 8.1, 60, 2500),
        ("Bianchi", "A", "2023_24", 4, 6.0, 2, 3.0, 5.0, 40, 2000),
        ("Verdi", "C", "2023_24", 3, 2.5, 9, 7.5, 2.0, 25, 2600),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "understat_player_name", "understat_role", "season_label",
            "goals", "xG", "assists", "xA", "npxG", "shots", "minutes",
        ],
    )


def _anchors() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_code": [101, 102, 103],
            "display_name": ["Rossi", "Bianchi", "Verdi"],
            "role": ["A", "A", "C"],
        }
    )


def test_build_xg_features_valid_and_tier_c():
    feats, review = build_xg_features(_understat_frame(), _anchors())
    validate_feature_frame(feats)
    assert not feats.empty
    for col in LINEAGE_COLUMNS:
        assert feats[col].notna().all(), col
    assert feats["quality_tier"].eq("C").all()
    assert feats["source_name"].eq("understat").all()
    assert set(feats["feature_name"]) == set(XG_FEATURE_NAMES)
    assert review == []


def test_ambiguous_name_goes_to_review_queue_never_a_code():
    frame = _understat_frame()
    frame.loc[len(frame)] = ["Esposito", "A", "2023_24", 1, 1.0, 0, 0.5, 0.8, 10, 900]
    anchors = _anchors()
    # two same-role homonyms -> unresolved
    anchors.loc[len(anchors)] = [201, "Esposito", "A"]
    anchors.loc[len(anchors)] = [202, "Esposito", "A"]

    feats, review = build_xg_features(frame, anchors)
    resolved_codes = set(feats["entity_id"].astype(int))
    assert 201 not in resolved_codes and 202 not in resolved_codes
    assert any(e.matched_display_name == "Esposito" for e in review)


def test_xg_feature_available_time_precedes_2026_27_preseason():
    feats, _ = build_xg_features(_understat_frame(), _anchors())
    decision_time = pd.Timestamp("2026-08-01")
    assert_available_before_decision(feats, decision_time)
    assert (feats["available_time"] == pd.Timestamp("2024-06-30")).all()


def test_unresolved_all_returns_empty_frame_and_queue():
    feats, review = build_xg_features(_understat_frame(), _anchors().iloc[0:0])
    assert feats.empty
    assert len(review) == 3
