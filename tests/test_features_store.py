import pandas as pd
import pytest

from fantacalcio.features.store import list_datasets, read_features, write_features


def _frame() -> pd.DataFrame:
    rows = []
    for i, day in enumerate(["2026-07-01", "2026-08-01", "2026-09-01"]):
        ts = pd.Timestamp(day)
        rows.append(
            {
                "entity_type": "player",
                "entity_id": str(i),
                "season": "2026_27",
                "feature_name": "recency_weight" if i % 2 == 0 else "voto_games_seen",
                "value": float(i),
                "event_time": ts,
                "available_time": ts,
                "ingested_time": pd.Timestamp("2026-09-15"),
                "source_name": "fantacalcio_voti_manual",
                "source_version": "v1",
                "quality_tier": "B",
                "quality_status": "ok",
            }
        )
    return pd.DataFrame(rows)


def test_round_trip(tmp_path):
    write_features(_frame(), "demo", root=tmp_path)
    back = read_features("demo", root=tmp_path)
    assert len(back) == 3
    assert set(back["feature_name"]) == {"recency_weight", "voto_games_seen"}
    assert pd.api.types.is_datetime64_any_dtype(back["available_time"])


def test_parquet_path_used_when_duckdb_available(tmp_path):
    path = write_features(_frame(), "demo", root=tmp_path)
    assert path.name == "data.parquet"
    assert (tmp_path / "demo" / "data.parquet").exists()


def test_as_of_strictly_excludes_later_rows(tmp_path):
    write_features(_frame(), "demo", root=tmp_path)
    back = read_features("demo", as_of=pd.Timestamp("2026-08-01"), root=tmp_path)
    assert set(back["available_time"]) == {
        pd.Timestamp("2026-07-01"),
        pd.Timestamp("2026-08-01"),
    }
    back2 = read_features("demo", as_of=pd.Timestamp("2026-07-31"), root=tmp_path)
    assert list(back2["available_time"]) == [pd.Timestamp("2026-07-01")]


def test_names_filter(tmp_path):
    write_features(_frame(), "demo", root=tmp_path)
    back = read_features("demo", names=["recency_weight"], root=tmp_path)
    assert set(back["feature_name"]) == {"recency_weight"}


def test_list_datasets(tmp_path):
    assert list_datasets(root=tmp_path) == []
    write_features(_frame(), "demo", root=tmp_path)
    write_features(_frame(), "other", root=tmp_path)
    assert list_datasets(root=tmp_path) == ["demo", "other"]


def test_missing_dataset_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_features("nope", root=tmp_path)
