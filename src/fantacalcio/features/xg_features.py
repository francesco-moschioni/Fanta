"""Level-4 xG/xA features from manually-imported Understat season aggregates.

Engine v2 Stage 3 (ADR-2026-075). Quality tier C: Understat's xG is a
proprietary model, aggregated, not provider-direct.

Every rate is per-90 and Empirical-Bayes shrunk with the same ``n / (n + prior)``
form used by ``modeling.player_voto.shrunk_estimate`` — here ``n`` is the
player's shot count, shrinking a noisy per-90 rate toward the role-level pooled
per-90 rate. ``xg_overperformance_shrunk`` (goals - xG, per 90) is shrunk
*heavily toward zero* (finishing over/under-performance rarely persists).

Understat rows are joined to ``player_code`` only via
``identity.player_name_resolver`` (role-constrained). Names that do not resolve
cleanly — including same-role homonyms — are returned in a review queue and
never given a guessed code.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from fantacalcio.features.schema import LINEAGE_COLUMNS, VALUE_COLUMNS
from fantacalcio.identity.player_name_resolver import (
    AnchorPlayer,
    PlayerReviewQueueEntry,
    resolve_against_anchor,
)

_OUTPUT_COLUMNS = VALUE_COLUMNS + LINEAGE_COLUMNS
SOURCE_NAME = "understat"

XG_FEATURE_NAMES = (
    "xg_per90_shrunk",
    "npxg_per90_shrunk",
    "xa_per90_shrunk",
    "shots_per90_shrunk",
    "minutes_understat",
    "xg_overperformance_shrunk",
)


def _utcnow() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)


def _season_end_time(season_label: str) -> pd.Timestamp:
    start = int(str(season_label).split("_")[0])
    return pd.Timestamp(year=start + 1, month=6, day=30)


def _anchor_list(anchor_players) -> list[AnchorPlayer]:
    if anchor_players is None:
        return []
    if isinstance(anchor_players, list):
        return anchor_players
    rows = []
    for r in anchor_players.itertuples(index=False):
        rows.append(
            AnchorPlayer(
                player_code=int(r.player_code),
                display_name=str(r.display_name),
                role=str(r.role),
                team_name=str(getattr(r, "team_name", "") or ""),
            )
        )
    return rows


def build_xg_features(
    understat_season: pd.DataFrame,
    anchor_players,
    *,
    prior_shots: float = 50.0,
    prior_overperformance: float = 400.0,
    source_version: str = "understat_manual_v1",
    ingested_time: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, list[PlayerReviewQueueEntry]]:
    """Return (long-format feature frame, review queue).

    ``understat_season`` is one or more :class:`~fantacalcio.ingest.understat.
    StagedUnderstat` ``player_season`` frames concatenated: needs
    ``understat_player_name, understat_role, season_label, goals, xG, assists,
    xA, npxG, shots`` and ``minutes`` (or ``time``).
    """
    df = understat_season.copy()
    if "minutes" not in df.columns:
        df["minutes"] = df.get("time")
    for col in ("goals", "xG", "assists", "xA", "npxG", "shots", "minutes"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["minutes"])
    df = df[df["minutes"] > 0].reset_index(drop=True)

    anchors = _anchor_list(anchor_players)
    other_names = [
        (str(n), (str(r) if pd.notna(r) else None))
        for n, r in df[["understat_player_name", "understat_role"]].drop_duplicates().itertuples(index=False)
    ]
    resolution = resolve_against_anchor(anchors, other_names)
    name_to_code = {e.matched_display_name: e.player_code for e in resolution.crosswalk}

    df = df[df["understat_player_name"].isin(name_to_code)].reset_index(drop=True)
    if df.empty:
        empty = pd.DataFrame(columns=_OUTPUT_COLUMNS)
        return empty, resolution.review_queue

    df["player_code"] = df["understat_player_name"].map(name_to_code)
    df["n90"] = df["minutes"] / 90.0
    df["role_key"] = df["understat_role"].astype(str)

    # role-level pooled per-90 baselines (shrinkage target)
    pooled = df.groupby("role_key").agg(
        xg=("xG", "sum"), npxg=("npxG", "sum"), xa=("xA", "sum"),
        shots=("shots", "sum"), n90=("n90", "sum"),
    )
    role_xg90 = (pooled["xg"] / pooled["n90"]).to_dict()
    role_npxg90 = (pooled["npxg"] / pooled["n90"]).to_dict()
    role_xa90 = (pooled["xa"] / pooled["n90"]).to_dict()
    role_shots90 = (pooled["shots"] / pooled["n90"]).to_dict()

    records = []
    for r in df.itertuples(index=False):
        n90 = float(r.n90)
        shots = float(r.shots) if pd.notna(r.shots) else 0.0
        w = shots / (shots + prior_shots) if (shots + prior_shots) > 0 else 0.0
        w_op = shots / (shots + prior_overperformance) if (shots + prior_overperformance) > 0 else 0.0
        rk = str(r.role_key)

        def _shrink(raw: float, role_mean: float) -> float:
            rm = float(role_mean) if role_mean == role_mean else 0.0  # NaN guard
            return w * raw + (1.0 - w) * rm

        xg90 = _shrink(float(r.xG) / n90, role_xg90.get(rk, float("nan")))
        npxg90 = _shrink(float(r.npxG) / n90, role_npxg90.get(rk, float("nan")))
        xa90 = _shrink(float(r.xA) / n90, role_xa90.get(rk, float("nan")))
        shots90 = _shrink(shots / n90, role_shots90.get(rk, float("nan")))
        op90 = w_op * ((float(r.goals) - float(r.xG)) / n90)

        pid = str(int(r.player_code))
        season = str(r.season_label)
        avail = _season_end_time(season)
        for feature_name, value in (
            ("xg_per90_shrunk", xg90),
            ("npxg_per90_shrunk", npxg90),
            ("xa_per90_shrunk", xa90),
            ("shots_per90_shrunk", shots90),
            ("minutes_understat", float(r.minutes)),
            ("xg_overperformance_shrunk", op90),
        ):
            records.append(
                {
                    "entity_type": "player",
                    "entity_id": pid,
                    "season": season,
                    "feature_name": feature_name,
                    "value": float(value),
                    "event_time": avail,
                    "available_time": avail,
                }
            )

    long_df = pd.DataFrame.from_records(records)
    long_df["ingested_time"] = pd.to_datetime(ingested_time if ingested_time is not None else _utcnow())
    long_df["source_name"] = SOURCE_NAME
    long_df["source_version"] = source_version
    long_df["quality_tier"] = "C"
    long_df["quality_status"] = "ok"
    long_df["event_time"] = pd.to_datetime(long_df["event_time"])
    long_df["available_time"] = pd.to_datetime(long_df["available_time"])
    return long_df[_OUTPUT_COLUMNS].reset_index(drop=True), resolution.review_queue


__all__ = ["build_xg_features", "XG_FEATURE_NAMES"]
