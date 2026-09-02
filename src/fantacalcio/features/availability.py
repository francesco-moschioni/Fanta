"""Level-4 availability feature from manually-imported WhoScored reports.

Engine v2 Stage 7 (ADR-2026-079). Replaces the "senza feed infortuni: stato
manuale" degradation branch of ``docs/DATA_AND_MODELING.md`` §"Degradazione
controllata": when a real WhoScored injuries/suspensions report exists it
produces a per-player ``availability_prob`` for the next matchday; when it does
not, every player is ``None`` and the caller falls back to the season
participation rate (degradation contract — an absent report is a no-op).

``availability_prob`` semantics (next matchday / ``horizon_days`` window):

* ``suspended``  -> ``0.0`` (serving a ban).
* ``out`` with an ``expected_return`` **after** the horizon -> ``~0.05``;
  **within** the horizon -> ramps linearly toward ``1.0`` as the return date
  approaches; no ``expected_return`` -> treated as long-term out (``~0.05``).
* ``doubtful`` -> starts at ``~0.5`` and decays toward the player's base rate as
  the report ages (``as_of - report_time``), half-life ``horizon_days``.
* ``available`` -> ``1.0`` (an explicit fitness clearance).
* no row for a player -> **no feature row** (caller falls back to season rate).

Names are joined to ``player_code`` only via
``identity.player_name_resolver`` (role-constrained). Unresolved names — same-role
homonyms included — go to a review queue and never get a guessed code.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from fantacalcio.features.schema import LINEAGE_COLUMNS, VALUE_COLUMNS
from fantacalcio.identity.player_name_resolver import (
    AnchorPlayer,
    PlayerReviewQueueEntry,
    resolve_against_anchor,
)
from fantacalcio.scoring.generative import participation as _part
from fantacalcio.scoring.generative.participation import (
    KEEPER_NONE,
    PlayerSeasonParticipation,
)

_OUTPUT_COLUMNS = VALUE_COLUMNS + LINEAGE_COLUMNS
SOURCE_NAME = "whoscored"
FEATURE_NAME = "availability_prob"

_LONG_TERM_OUT_PROB = 0.05
_DOUBTFUL_FRESH_PROB = 0.5
DEFAULT_BASE_RATE = 0.75


def _utcnow() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)


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


def _row_prob(
    status: str,
    *,
    as_of: pd.Timestamp,
    report_time: pd.Timestamp,
    expected_return,
    horizon_days: int,
    base_rate: float,
) -> float:
    if status == "suspended":
        return 0.0
    if status == "available":
        return 1.0
    if status == "out":
        if expected_return is None or pd.isna(expected_return):
            return _LONG_TERM_OUT_PROB
        days_until = (pd.Timestamp(expected_return) - as_of).days
        frac = days_until / float(horizon_days)
        if frac >= 1.0:
            return _LONG_TERM_OUT_PROB
        # 1.0 when the return date is now/past, 0.05 at the horizon edge
        return float(np.clip(1.0 - 0.95 * max(frac, 0.0), _LONG_TERM_OUT_PROB, 1.0))
    if status == "doubtful":
        age_days = max((as_of - pd.Timestamp(report_time)).days, 0)
        w = 0.5 ** (age_days / float(horizon_days))
        return float(base_rate + w * (_DOUBTFUL_FRESH_PROB - base_rate))
    raise ValueError(f"unknown availability status {status!r}")


def player_availability(
    missing_players_df: pd.DataFrame,
    *,
    as_of,
    horizon_days: int = 7,
    anchor_players=None,
    season: str = "2026_27",
    base_rates: Mapping[int, float] | None = None,
    default_base_rate: float = DEFAULT_BASE_RATE,
    source_version: str = "whoscored_manual_v1",
    ingested_time: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, list[PlayerReviewQueueEntry]]:
    """Return ``(long-format availability feature frame, review queue)``.

    ``missing_players_df`` is one or more
    :class:`~fantacalcio.ingest.whoscored.StagedWhoScored` ``missing_players``
    frames concatenated: needs ``player_name``, ``status`` and ``report_time``;
    optional ``role`` (role-constrains the identity match) and
    ``expected_return``. ``as_of`` is the decision time (matchday time). The
    per-row ``available_time`` is that row's ``report_time`` (leakage-safe: a
    report precedes the matchday it informs).
    """
    as_of = pd.Timestamp(as_of)
    df = missing_players_df.copy()
    if df.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS), []

    if "role" not in df.columns:
        df["role"] = None
    if "expected_return" not in df.columns:
        df["expected_return"] = pd.NaT
    df["report_time"] = pd.to_datetime(df["report_time"], errors="coerce")
    df["report_time"] = df["report_time"].fillna(as_of)
    df["expected_return"] = pd.to_datetime(df["expected_return"], errors="coerce")

    anchors = _anchor_list(anchor_players)
    other_names = [
        (str(n), (str(r) if pd.notna(r) else None))
        for n, r in df[["player_name", "role"]].drop_duplicates().itertuples(index=False)
    ]
    resolution = resolve_against_anchor(anchors, other_names)
    name_to_code = {e.matched_display_name: e.player_code for e in resolution.crosswalk}

    df = df[df["player_name"].isin(name_to_code)].reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS), resolution.review_queue

    records = []
    for r in df.itertuples(index=False):
        code = int(name_to_code[r.player_name])
        base_rate = float(
            base_rates.get(code, default_base_rate) if base_rates else default_base_rate
        )
        prob = _row_prob(
            str(r.status),
            as_of=as_of,
            report_time=pd.Timestamp(r.report_time),
            expected_return=r.expected_return,
            horizon_days=horizon_days,
            base_rate=base_rate,
        )
        tier = "B" if str(r.status) == "suspended" else "C"
        avail_t = pd.Timestamp(r.report_time)
        records.append(
            {
                "entity_type": "player",
                "entity_id": str(code),
                "season": str(season),
                "feature_name": FEATURE_NAME,
                "value": float(prob),
                "event_time": avail_t,
                "available_time": avail_t,
                "quality_tier": tier,
            }
        )

    long_df = pd.DataFrame.from_records(records)
    # keep the most conservative (lowest) probability per player if duplicated
    long_df = (
        long_df.sort_values("value")
        .drop_duplicates(subset=["entity_id", "season", "feature_name"], keep="first")
        .reset_index(drop=True)
    )
    long_df["ingested_time"] = pd.to_datetime(
        ingested_time if ingested_time is not None else _utcnow()
    )
    long_df["source_name"] = SOURCE_NAME
    long_df["source_version"] = source_version
    long_df["quality_status"] = "ok"
    return long_df[_OUTPUT_COLUMNS], resolution.review_queue


def apply_availability_to_participation(
    player_season_participation: PlayerSeasonParticipation,
    availability_prob: float | None,
) -> PlayerSeasonParticipation:
    """Cap the next-matchday play probability at ``availability_prob``.

    ``availability_prob is None`` -> return the input **unchanged** (same object;
    degradation contract). Otherwise return a plain outfield
    :class:`PlayerSeasonParticipation` whose per-fixture play probability is
    ``min(current_play_prob, availability_prob)`` with the original
    start/bench split preserved. The season simulator applies the result to the
    first fixture only; later matchdays keep the season rate.
    """
    if availability_prob is None:
        return player_season_participation

    p = float(np.clip(availability_prob, 0.0, 1.0))
    p_start, p_bench, _ = _part._status_probs(player_season_participation)
    base_play = p_start + p_bench
    if base_play <= 0.0:
        return PlayerSeasonParticipation(
            participation_rate=0.0,
            start_share=player_season_participation.start_share,
            keeper_status=KEEPER_NONE,
        )
    capped = min(base_play, p)
    start_share = p_start / base_play
    return PlayerSeasonParticipation(
        participation_rate=capped,
        start_share=float(np.clip(start_share, 0.0, 1.0)),
        keeper_status=KEEPER_NONE,
    )


__all__ = [
    "player_availability",
    "apply_availability_to_participation",
    "FEATURE_NAME",
    "SOURCE_NAME",
    "DEFAULT_BASE_RATE",
]
