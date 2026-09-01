"""Deterministic feature builders for the level-4 layer.

Every builder CALLS the existing modeling / scoring modules (it never
reimplements their math) and returns a long-format frame that passes
:func:`fantacalcio.features.schema.validate_feature_frame`.

Builders take already-loaded DataFrames so tests can feed synthetic input; a thin
loader in ``scripts/build_features.py`` wires the real staged CSVs.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from fantacalcio.features.schema import LINEAGE_COLUMNS, VALUE_COLUMNS
from fantacalcio.modeling.dixon_coles import DEFAULT_XI, fit_dixon_coles
from fantacalcio.modeling.elo import fit_elo_sequential
from fantacalcio.modeling.odds_priors import DEFAULT_RHO as ODDS_DEFAULT_RHO
from fantacalcio.modeling.odds_priors import season_team_priors
from fantacalcio.modeling.participation import (
    SeasonParticipation,
    decayed_participation_estimate,
    latest_known_participation,
)
from fantacalcio.modeling.player_voto import walk_forward
from fantacalcio.modeling.time_decay import (
    DEFAULT_HALF_LIFE_MATCHDAYS,
    add_global_matchday_index,
    add_recency_weight,
)
from fantacalcio.scoring.fvm_prior import assign_bucket, fit_fvm_bucket_edges

_OUTPUT_COLUMNS = VALUE_COLUMNS + LINEAGE_COLUMNS


def _utcnow() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)


def _season_start(season_label: str) -> pd.Timestamp:
    """Map a season label to its (pre-season) 1 August boundary.

    Handles ``"2021_22"`` / ``"2026_27"`` and the compact ``"2122"`` form.
    """
    s = str(season_label)
    if "_" in s:
        year = int(s.split("_")[0])
    elif len(s) == 4 and s.isdigit():
        year = 2000 + int(s[:2])
    else:
        year = int(s[:4])
    return pd.Timestamp(year=year, month=8, day=1)


def _matchday_time(season_label: str, matchday: int) -> pd.Timestamp:
    """Deterministic timestamp for a (season, matchday): season start + 7 days per round."""
    return _season_start(season_label) + pd.Timedelta(days=7 * (int(matchday) - 1))


def _finalize(
    rows: pd.DataFrame,
    *,
    source_name: str,
    source_version: str,
    quality_tier: str,
    ingested_time: pd.Timestamp | None,
    default_available_time: pd.Timestamp | None = None,
    quality_status: str = "ok",
) -> pd.DataFrame:
    """Attach lineage columns and return the frame in canonical column order.

    ``rows`` must already carry the :data:`VALUE_COLUMNS`. If it also carries an
    ``available_time`` column that is kept; otherwise ``default_available_time``
    is used for every row. ``event_time`` defaults to ``available_time``.
    """
    df = rows.copy()
    ingested = ingested_time if ingested_time is not None else _utcnow()

    if "available_time" not in df.columns:
        if default_available_time is None:
            raise ValueError("no available_time column and no default_available_time given")
        df["available_time"] = default_available_time
    df["available_time"] = pd.to_datetime(df["available_time"])

    if "event_time" not in df.columns:
        df["event_time"] = df["available_time"]
    df["event_time"] = pd.to_datetime(df["event_time"])

    df["ingested_time"] = pd.to_datetime(ingested)
    df["source_name"] = source_name
    df["source_version"] = source_version
    df["quality_tier"] = quality_tier
    df["quality_status"] = quality_status
    return df[_OUTPUT_COLUMNS].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# player running voto baseline                                               #
# --------------------------------------------------------------------------- #
def build_player_voto_features(
    voti_panel: pd.DataFrame,
    *,
    prior_games: float = 60.0,
    source_version: str = "voti_manual_v1",
    ingested_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Running shrunk voto mean, games-seen and shrinkage weight per rated row.

    Thin materialisation of ``modeling.player_voto.walk_forward``: the
    ``voto_running_shrunk_mean`` value is that function's ``shrinkage_pred``
    unchanged (regression lock). ``available_time`` is the start of the
    (season, matchday) the running stat is valid from.
    """
    scored = walk_forward(voti_panel, prior_games=prior_games)
    if scored.empty:
        return _finalize(
            pd.DataFrame(columns=VALUE_COLUMNS),
            source_name="fantacalcio_voti_manual",
            source_version=source_version,
            quality_tier="B",
            ingested_time=ingested_time,
            default_available_time=_utcnow(),
        )

    scored = scored.copy()
    scored["available_time"] = [
        _matchday_time(s, m) for s, m in zip(scored["season_label"], scored["matchday"])
    ]
    n = scored["player_games_seen"].astype(float)
    scored["_weight"] = n / (n + prior_games)

    feature_map = {
        "voto_running_shrunk_mean": scored["shrinkage_pred"],
        "voto_games_seen": n,
        "voto_shrinkage_weight": scored["_weight"],
    }
    parts = []
    for feature_name, values in feature_map.items():
        parts.append(
            pd.DataFrame(
                {
                    "entity_type": "player",
                    "entity_id": scored["player_code"].astype(str),
                    "season": scored["season_label"].astype(str),
                    "feature_name": feature_name,
                    "value": values.astype(float).to_numpy(),
                    "available_time": scored["available_time"].to_numpy(),
                }
            )
        )
    long_df = pd.concat(parts, ignore_index=True)
    return _finalize(
        long_df,
        source_name="fantacalcio_voti_manual",
        source_version=source_version,
        quality_tier="B",
        ingested_time=ingested_time,
    )


# --------------------------------------------------------------------------- #
# participation                                                              #
# --------------------------------------------------------------------------- #
def build_participation_features(
    season_participation: SeasonParticipation,
    *,
    target_season: str = "2026_27",
    half_life_seasons: float | None = None,
    as_of_season_rank: int | None = None,
    source_version: str = "voti_manual_v1",
    ingested_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Decayed participation rate, latest known rate and their consistency delta.

    Calls ``modeling.participation.decayed_participation_estimate`` and
    ``latest_known_participation``. ``available_time`` is the target season's
    pre-season boundary (all inputs are completed prior seasons).
    """
    decayed = decayed_participation_estimate(
        season_participation, half_life_seasons, as_of_season_rank
    )
    latest = latest_known_participation(season_participation)

    merged = decayed.merge(
        latest[["player_code", "participation_rate"]], on="player_code", how="outer"
    )
    merged = merged.rename(
        columns={
            "decayed_participation_rate": "participation_decayed_rate",
            "participation_rate": "participation_latest_rate",
        }
    )
    merged["participation_crosscheck_delta"] = (
        merged["participation_latest_rate"] - merged["participation_decayed_rate"]
    )

    available_time = _season_start(target_season)
    parts = []
    for feature_name in (
        "participation_decayed_rate",
        "participation_latest_rate",
        "participation_crosscheck_delta",
    ):
        parts.append(
            pd.DataFrame(
                {
                    "entity_type": "player",
                    "entity_id": merged["player_code"].astype("Int64").astype(str),
                    "season": target_season,
                    "feature_name": feature_name,
                    "value": pd.to_numeric(merged[feature_name], errors="coerce").astype(float),
                }
            )
        )
    long_df = pd.concat(parts, ignore_index=True)
    return _finalize(
        long_df,
        source_name="fantacalcio_voti_manual",
        source_version=source_version,
        quality_tier="B",
        ingested_time=ingested_time,
        default_available_time=available_time,
    )


# --------------------------------------------------------------------------- #
# recency weight                                                             #
# --------------------------------------------------------------------------- #
def build_recency_weight_features(
    panel: pd.DataFrame,
    *,
    half_life_matchdays: float | None = DEFAULT_HALF_LIFE_MATCHDAYS,
    as_of: pd.Timestamp | None = None,
    season: str = "2026_27",
    entity_type: str = "player",
    entity_id_col: str = "player_code",
    source_version: str = "voti_manual_v1",
    ingested_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Exponential recency weight per row, via ``modeling.time_decay``.

    ``panel`` needs ``season_rank`` and ``matchday``; the entity id is taken from
    ``entity_id_col``. ``available_time`` is the single ``as_of`` boundary
    (defaults to ``season``'s pre-season date).
    """
    indexed = add_global_matchday_index(panel)
    weighted = add_recency_weight(indexed, half_life_matchdays)
    available_time = as_of if as_of is not None else _season_start(season)

    long_df = pd.DataFrame(
        {
            "entity_type": entity_type,
            "entity_id": weighted[entity_id_col].astype(str),
            "season": season,
            "feature_name": "recency_weight",
            "value": weighted["recency_weight"].astype(float),
        }
    )
    return _finalize(
        long_df,
        source_name="fantacalcio_voti_manual",
        source_version=source_version,
        quality_tier="B",
        ingested_time=ingested_time,
        default_available_time=available_time,
    )


# --------------------------------------------------------------------------- #
# team strength (Dixon-Coles + Elo)                                          #
# --------------------------------------------------------------------------- #
def build_team_strength_features(
    matches: pd.DataFrame,
    *,
    season: str,
    as_of: pd.Timestamp | None = None,
    xi: float = DEFAULT_XI,
    k_factor: float = 20.0,
    home_advantage: float = 60.0,
    source_version: str = "football_data_v1",
    ingested_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Per-team attack/defense (Dixon-Coles) and Elo rating as-of a boundary.

    ``matches`` needs ``HomeTeam, AwayTeam, FTHG, FTAG, FTR, Date`` and must
    contain only matches strictly before the boundary. Calls
    ``modeling.dixon_coles.fit_dixon_coles`` and
    ``modeling.elo.fit_elo_sequential`` unchanged.
    """
    dc_model = fit_dixon_coles(matches, xi=xi)
    elo, _ = fit_elo_sequential(matches, k_factor=k_factor, home_advantage=home_advantage)

    teams = sorted(set(matches["HomeTeam"]) | set(matches["AwayTeam"]))
    records = []
    for team in teams:
        records.append(("team_attack_strength", team, float(dc_model.attack.get(team, 0.0))))
        records.append(("team_defense_strength", team, float(dc_model.defense.get(team, 0.0))))
        records.append(("team_elo_rating", team, float(elo.get(team))))

    long_df = pd.DataFrame(records, columns=["feature_name", "entity_id", "value"])
    long_df["entity_type"] = "team"
    long_df["season"] = season
    available_time = as_of if as_of is not None else _season_start(season)
    return _finalize(
        long_df,
        source_name="football_data_co_uk",
        source_version=source_version,
        quality_tier="A",
        ingested_time=ingested_time,
        default_available_time=available_time,
    )


# --------------------------------------------------------------------------- #
# odds-implied team priors (Stage 2)                                         #
# --------------------------------------------------------------------------- #
def build_odds_prior_features(
    matches: pd.DataFrame,
    *,
    season: str,
    devig_method: str = "shin",
    rho: float = ODDS_DEFAULT_RHO,
    fallback_total_goals: float | None = None,
    source_version: str = "football_data_v1",
    ingested_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Per-team odds-implied clean-sheet / goals-conceded / expected-points priors.

    ``matches`` needs ``HomeTeam, AwayTeam, Date`` and a resolvable 1X2 odds set
    (``Avg{H,D,A}`` / ``BbAv*`` / ``B365*``); it must hold only the priced season.
    Calls ``modeling.odds_priors.season_team_priors`` unchanged; ``available_time``
    is that season's last kickoff (the aggregate is known once the season ends).
    """
    priors = season_team_priors(
        matches, devig_method=devig_method, rho=rho,
        season_col=None, fallback_total_goals=fallback_total_goals, granularity="season",
    )
    feature_map = {
        "team_odds_clean_sheet_rate": "clean_sheet_rate",
        "team_odds_expected_goals_conceded": "expected_goals_conceded",
        "team_odds_expected_points": "expected_points",
    }
    records = []
    for row in priors.itertuples(index=False):
        for feature_name, col in feature_map.items():
            records.append(
                {
                    "feature_name": feature_name,
                    "entity_id": str(row.team),
                    "value": float(getattr(row, col)),
                    "available_time": row.available_time,
                }
            )
    long_df = pd.DataFrame(records, columns=["feature_name", "entity_id", "value", "available_time"])
    long_df["entity_type"] = "team"
    long_df["season"] = season
    if long_df.empty:
        long_df["available_time"] = pd.NaT
    return _finalize(
        long_df,
        source_name="football_data_co_uk",
        source_version=source_version,
        quality_tier="A",
        ingested_time=ingested_time,
        default_available_time=_season_start(season),
    )


# --------------------------------------------------------------------------- #
# FVM prior buckets                                                          #
# --------------------------------------------------------------------------- #
def build_fvm_prior_features(
    train_fvm_by_role: pd.DataFrame,
    target_players: pd.DataFrame,
    *,
    target_season: str = "2026_27",
    n_buckets: int = 4,
    source_version: str = "quotazioni_manual_v1",
    ingested_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """FVM quantile bucket + bucket edges per target player.

    ``train_fvm_by_role`` needs ``[role, fvm_classic]`` (training seasons only);
    ``target_players`` needs ``[player_code, role, fvm_classic]``. Calls
    ``scoring.fvm_prior.fit_fvm_bucket_edges`` / ``assign_bucket`` unchanged.
    """
    edges = fit_fvm_bucket_edges(train_fvm_by_role, n_buckets=n_buckets)

    records = []
    for row in target_players.dropna(subset=["fvm_classic"]).itertuples(index=False):
        bucket = assign_bucket(float(row.fvm_classic), row.role, edges)
        role_edges = edges.get(row.role)
        if role_edges is not None and len(role_edges) >= 2:
            lo_edge = float(role_edges[min(bucket, len(role_edges) - 2)])
            hi_edge = float(role_edges[min(bucket + 1, len(role_edges) - 1)])
        else:
            lo_edge = hi_edge = float("nan")
        pid = str(int(row.player_code))
        records.append(("fvm_bucket", pid, float(bucket)))
        records.append(("fvm_bucket_low_edge", pid, lo_edge))
        records.append(("fvm_bucket_high_edge", pid, hi_edge))

    long_df = pd.DataFrame(records, columns=["feature_name", "entity_id", "value"])
    long_df["entity_type"] = "player"
    long_df["season"] = target_season
    return _finalize(
        long_df,
        source_name="fantacalcio_quotazioni_manual",
        source_version=source_version,
        quality_tier="B",
        ingested_time=ingested_time,
        default_available_time=_season_start(target_season),
    )


# --------------------------------------------------------------------------- #
# listone / admin list                                                       #
# --------------------------------------------------------------------------- #
def build_listone_features(
    listone: pd.DataFrame,
    admin_ranks: pd.DataFrame | None = None,
    *,
    target_season: str = "2026_27",
    source_version: str = "quotazioni_manual_v1",
    ingested_time: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Role, quotazione, FVM, admin rank and (when present) list pool name.

    ``listone`` needs ``[player_code, role]`` plus ``quotazione_asta_classic``
    and ``fvm_classic`` (missing numeric columns are simply skipped). Optional
    ``admin_ranks`` needs ``[player_code, rank]`` and, when present,
    ``list_header_label``.
    """
    df = listone.copy()
    df["player_code"] = df["player_code"].astype("Int64")

    records: list[tuple[str, str, object]] = []
    for row in df.itertuples(index=False):
        pid = str(int(row.player_code))
        if getattr(row, "role", None) is not None and pd.notna(row.role):
            records.append(("listone_role", pid, str(row.role)))
        q = getattr(row, "quotazione_asta_classic", None)
        if q is not None and pd.notna(q):
            records.append(("listone_quotazione", pid, float(q)))
        fvm = getattr(row, "fvm_classic", None)
        if fvm is not None and pd.notna(fvm):
            records.append(("listone_fvm", pid, float(fvm)))

    if admin_ranks is not None and not admin_ranks.empty:
        ar = admin_ranks.copy()
        ar["player_code"] = ar["player_code"].astype("Int64")
        for row in ar.dropna(subset=["player_code"]).itertuples(index=False):
            pid = str(int(row.player_code))
            if getattr(row, "rank", None) is not None and pd.notna(row.rank):
                records.append(("listone_admin_rank", pid, float(row.rank)))
            label = getattr(row, "list_header_label", None)
            if label is not None and pd.notna(label):
                records.append(("listone_list_pool_name", pid, str(label)))

    long_df = pd.DataFrame(records, columns=["feature_name", "entity_id", "value"])
    long_df["entity_type"] = "player"
    long_df["season"] = target_season
    long_df["value"] = long_df["value"].astype(object)
    return _finalize(
        long_df,
        source_name="fantacalcio_quotazioni_manual",
        source_version=source_version,
        quality_tier="A",
        ingested_time=ingested_time,
        default_available_time=_season_start(target_season),
    )


# --------------------------------------------------------------------------- #
# top-level orchestration                                                     #
# --------------------------------------------------------------------------- #
def build_all_features(
    *,
    voti_panel: pd.DataFrame | None = None,
    season_participation: SeasonParticipation | None = None,
    recency_panel: pd.DataFrame | None = None,
    matches: pd.DataFrame | None = None,
    odds_matches: pd.DataFrame | None = None,
    fvm_train_by_role: pd.DataFrame | None = None,
    fvm_target_players: pd.DataFrame | None = None,
    listone: pd.DataFrame | None = None,
    admin_ranks: pd.DataFrame | None = None,
    target_season: str = "2026_27",
    ingested_time: pd.Timestamp | None = None,
) -> dict[str, pd.DataFrame]:
    """Run every builder whose input was supplied; return ``{dataset: frame}``."""
    out: dict[str, pd.DataFrame] = {}
    if voti_panel is not None:
        out["player_voto"] = build_player_voto_features(
            voti_panel, ingested_time=ingested_time
        )
    if season_participation is not None:
        out["participation"] = build_participation_features(
            season_participation, target_season=target_season, ingested_time=ingested_time
        )
    if recency_panel is not None:
        out["recency_weight"] = build_recency_weight_features(
            recency_panel, season=target_season, ingested_time=ingested_time
        )
    if matches is not None:
        out["team_strength"] = build_team_strength_features(
            matches, season=target_season, ingested_time=ingested_time
        )
    if odds_matches is not None:
        out["odds_prior"] = build_odds_prior_features(
            odds_matches, season=target_season, ingested_time=ingested_time
        )
    if fvm_train_by_role is not None and fvm_target_players is not None:
        out["fvm_prior"] = build_fvm_prior_features(
            fvm_train_by_role,
            fvm_target_players,
            target_season=target_season,
            ingested_time=ingested_time,
        )
    if listone is not None:
        out["listone"] = build_listone_features(
            listone, admin_ranks, target_season=target_season, ingested_time=ingested_time
        )
    return out
