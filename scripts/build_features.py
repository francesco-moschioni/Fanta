#!/usr/bin/env python3
"""M7 Engine v2 — Stage 1: materialise the level-4 feature store from real staged data.

Loads the staged CSVs, calls ``features.build.build_all_features`` and writes each
dataset under ``data/features/<dataset>/`` (gitignored). Deterministic, offline.

Any input group that cannot be loaded is skipped with a printed note rather than
aborting the whole run.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.features.build import build_all_features
from fantacalcio.features.store import write_features
from fantacalcio.modeling.participation import compute_season_participation
from fantacalcio.modeling.player_voto import load_player_matchday_panel
from fantacalcio.modeling.validation import load_seasons
from fantacalcio.scoring.fvm_prior import load_fvm_lookup

QUOTAZIONI_DIR = Path("data/staged/fantacalcio_quotazioni_manual")
ADMIN_RESOLVED = Path("data/curated/admin_list_2026_27/resolved_players.csv")
TRAIN_SEASONS_VOTI = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]
TRAIN_SEASONS_FOOTBALL = ["2122", "2223", "2324", "2425", "2526"]
TARGET_SEASON = "2026_27"


def _try(label, fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - report and skip
        print(f"  [skip] {label}: {exc}")
        return None


def _load_voti_panel():
    return load_player_matchday_panel()


def _load_recency_panel():
    return load_player_matchday_panel()


def _load_matches():
    return load_seasons(TRAIN_SEASONS_FOOTBALL)


def _load_fvm_train_by_role():
    fvm = load_fvm_lookup(TRAIN_SEASONS_VOTI)
    voti = load_player_matchday_panel()
    roles = voti[["player_code", "role"]].drop_duplicates()
    merged = fvm.merge(roles, on="player_code", how="inner")
    return merged[["role", "fvm_classic"]].dropna()


def _load_target_players():
    path = QUOTAZIONI_DIR / f"{TARGET_SEASON}.csv"
    df = pd.read_csv(path)
    return df.rename(columns={"role": "role"})[["player_code", "role", "fvm_classic"]]


def _load_listone():
    path = QUOTAZIONI_DIR / f"{TARGET_SEASON}.csv"
    return pd.read_csv(path)[["player_code", "role", "quotazione_asta_classic", "fvm_classic"]]


def _load_admin_ranks():
    if not ADMIN_RESOLVED.is_file():
        return None
    df = pd.read_csv(ADMIN_RESOLVED)
    cols = {"player_code", "rank"}
    if not cols.issubset(df.columns):
        return None
    keep = ["player_code", "rank"]
    if "list_header_label" in df.columns:
        keep.append("list_header_label")
    return df.dropna(subset=["player_code"])[keep]


def run() -> None:
    print("Loading staged inputs...")
    voti_panel = _try("voti panel", _load_voti_panel)
    season_participation = (
        compute_season_participation(voti_panel) if voti_panel is not None else None
    )
    recency_panel = _try("recency panel", _load_recency_panel)
    matches = _try("football-data seasons", _load_matches)
    fvm_train_by_role = _try("fvm train-by-role", _load_fvm_train_by_role)
    fvm_target_players = _try("fvm target players", _load_target_players)
    listone = _try("listone", _load_listone)
    admin_ranks = _try("admin ranks", _load_admin_ranks)

    print("Building features...")
    datasets = build_all_features(
        voti_panel=voti_panel,
        season_participation=season_participation,
        recency_panel=recency_panel,
        matches=matches,
        fvm_train_by_role=fvm_train_by_role,
        fvm_target_players=fvm_target_players,
        listone=listone,
        admin_ranks=admin_ranks,
        target_season=TARGET_SEASON,
    )

    for name, df in datasets.items():
        path = write_features(df, name)
        print(f"  wrote {name}: {len(df)} rows -> {path}")

    print("Done.")


if __name__ == "__main__":
    run()
