import pandas as pd
import pytest

from fantacalcio.features.schema import (
    LINEAGE_COLUMNS,
    FeatureSchemaError,
    validate_feature_frame,
)


def _good_frame() -> pd.DataFrame:
    ts = pd.Timestamp("2026-08-01")
    return pd.DataFrame(
        {
            "entity_type": ["player", "player"],
            "entity_id": ["1", "2"],
            "season": ["2026_27", "2026_27"],
            "feature_name": ["recency_weight", "recency_weight"],
            "value": [1.0, 0.5],
            "event_time": [ts, ts],
            "available_time": [ts, ts],
            "ingested_time": [ts, ts],
            "source_name": ["fantacalcio_voti_manual", "fantacalcio_voti_manual"],
            "source_version": ["v1", "v1"],
            "quality_tier": ["B", "B"],
            "quality_status": ["ok", "ok"],
        }
    )


def test_accepts_good_frame():
    validate_feature_frame(_good_frame())


@pytest.mark.parametrize("missing", LINEAGE_COLUMNS)
def test_raises_on_missing_lineage_column(missing):
    df = _good_frame().drop(columns=[missing])
    with pytest.raises(FeatureSchemaError, match="missing required columns"):
        validate_feature_frame(df)


def test_raises_on_null_lineage_value():
    df = _good_frame()
    df.loc[0, "available_time"] = None
    with pytest.raises(FeatureSchemaError, match="nulls"):
        validate_feature_frame(df)


def test_raises_on_bad_quality_tier():
    df = _good_frame()
    df.loc[0, "quality_tier"] = "Z"
    with pytest.raises(FeatureSchemaError, match="quality_tier"):
        validate_feature_frame(df)


def test_raises_on_unknown_feature_name():
    df = _good_frame()
    df.loc[0, "feature_name"] = "not_a_real_feature"
    with pytest.raises(FeatureSchemaError, match="FEATURE_REGISTRY"):
        validate_feature_frame(df)


def test_raises_on_bad_entity_type():
    df = _good_frame()
    df.loc[0, "entity_type"] = "banana"
    with pytest.raises(FeatureSchemaError, match="entity_type"):
        validate_feature_frame(df)
