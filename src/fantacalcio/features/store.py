"""On-disk feature store: long-format frames with per-row lineage.

One dataset -> one directory under :data:`DEFAULT_FEATURES_ROOT`, holding either
``data.parquet`` (written via DuckDB ``COPY ... (FORMAT parquet)`` so ``pyarrow``
is not required) or, if that fails, ``data.csv.gz`` as a fallback.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from fantacalcio.features.schema import validate_feature_frame

logger = logging.getLogger(__name__)

DEFAULT_FEATURES_ROOT = Path("data/features")

_PARQUET_NAME = "data.parquet"
_CSV_NAME = "data.csv.gz"
_TIME_COLUMNS = ["event_time", "available_time", "ingested_time"]


def write_features(
    df: pd.DataFrame, dataset: str, *, root: Path = DEFAULT_FEATURES_ROOT
) -> Path:
    """Validate ``df`` and persist it as ``<root>/<dataset>/data.parquet``.

    Falls back to ``data.csv.gz`` (pandas gzip CSV) if the DuckDB parquet write
    raises. Returns the path actually written.
    """
    validate_feature_frame(df)
    dataset_dir = Path(root) / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = dataset_dir / _PARQUET_NAME
    csv_path = dataset_dir / _CSV_NAME

    try:
        con = duckdb.connect()
        try:
            con.register("feat_df", df)
            con.execute(
                f"COPY (SELECT * FROM feat_df) TO '{parquet_path.as_posix()}' (FORMAT parquet)"
            )
        finally:
            con.close()
        if csv_path.exists():
            csv_path.unlink()
        logger.info("write_features(%s): wrote parquet %s (%d rows)", dataset, parquet_path, len(df))
        return parquet_path
    except Exception as exc:  # noqa: BLE001 - fall back, but say why
        logger.warning(
            "write_features(%s): parquet write failed (%s); falling back to gzip CSV", dataset, exc
        )
        df.to_csv(csv_path, index=False, compression="gzip")
        if parquet_path.exists():
            parquet_path.unlink()
        logger.info("write_features(%s): wrote gzip CSV %s (%d rows)", dataset, csv_path, len(df))
        return csv_path


def _read_raw(dataset_dir: Path) -> pd.DataFrame:
    parquet_path = dataset_dir / _PARQUET_NAME
    csv_path = dataset_dir / _CSV_NAME
    if parquet_path.exists():
        con = duckdb.connect()
        try:
            return con.execute(
                f"SELECT * FROM read_parquet('{parquet_path.as_posix()}')"
            ).df()
        finally:
            con.close()
    if csv_path.exists():
        return pd.read_csv(csv_path, compression="gzip")
    raise FileNotFoundError(f"no feature file found in {dataset_dir}")


def read_features(
    dataset: str,
    *,
    as_of: datetime | pd.Timestamp | None = None,
    names: list[str] | None = None,
    root: Path = DEFAULT_FEATURES_ROOT,
) -> pd.DataFrame:
    """Read a feature dataset back.

    ``as_of`` keeps only rows with ``available_time <= as_of``; ``names`` keeps
    only rows whose ``feature_name`` is in the list. Time columns are parsed to
    datetime on read.
    """
    dataset_dir = Path(root) / dataset
    df = _read_raw(dataset_dir)
    for col in _TIME_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        df = df[df["available_time"] <= cutoff].reset_index(drop=True)
    if names is not None:
        df = df[df["feature_name"].isin(names)].reset_index(drop=True)
    return df


def list_datasets(root: Path = DEFAULT_FEATURES_ROOT) -> list[str]:
    """Return the sorted names of datasets that hold a readable feature file."""
    root = Path(root)
    if not root.is_dir():
        return []
    out = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (
            (child / _PARQUET_NAME).exists() or (child / _CSV_NAME).exists()
        ):
            out.append(child.name)
    return out
