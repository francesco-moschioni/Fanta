"""Feature-frame schema, registry and validation for the level-4 feature layer.

Every feature row is long-format:

    entity_type, entity_id, season, feature_name, value  +  the lineage columns

The lineage columns make provenance and ``as_of`` slicing a per-row property, so
no downstream consumer can use a feature without knowing when it became known,
where it came from, and how trustworthy it is.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

LINEAGE_COLUMNS = [
    "event_time",
    "available_time",
    "ingested_time",
    "source_name",
    "source_version",
    "quality_tier",
    "quality_status",
]

#: Long-format value columns every feature frame must carry alongside the lineage.
VALUE_COLUMNS = ["entity_type", "entity_id", "season", "feature_name", "value"]

QUALITY_TIERS = frozenset({"A", "B", "C"})

ENTITY_TYPES = frozenset({"player", "team", "player_season", "team_season"})


class FeatureSchemaError(Exception):
    """Raised when a feature frame violates the level-4 schema contract."""


@dataclass(frozen=True)
class FeatureSpec:
    """Registry description of a single feature produced by ``build.py``."""

    name: str
    dtype: str
    description: str
    source_name: str
    available_time_rule: str
    quality_tier: str


def _spec(
    name: str,
    dtype: str,
    description: str,
    source_name: str,
    available_time_rule: str,
    quality_tier: str,
) -> tuple[str, FeatureSpec]:
    return name, FeatureSpec(
        name=name,
        dtype=dtype,
        description=description,
        source_name=source_name,
        available_time_rule=available_time_rule,
        quality_tier=quality_tier,
    )


FEATURE_REGISTRY: dict[str, FeatureSpec] = dict(
    [
        # --- player running voto baseline (modeling.player_voto) -----------------
        _spec(
            "voto_running_shrunk_mean",
            "float64",
            "Empirical-Bayes shrunk running mean base voto, strictly from earlier matchdays.",
            "fantacalcio_voti_manual",
            "start of the (season, matchday) the running stat is valid from",
            "B",
        ),
        _spec(
            "voto_games_seen",
            "float64",
            "Count of rated matchdays seen for the player before this matchday.",
            "fantacalcio_voti_manual",
            "start of the (season, matchday) the running stat is valid from",
            "B",
        ),
        _spec(
            "voto_shrinkage_weight",
            "float64",
            "Shrinkage weight n / (n + prior_games) applied to the player mean.",
            "fantacalcio_voti_manual",
            "start of the (season, matchday) the running stat is valid from",
            "B",
        ),
        # --- participation (modeling.participation) -----------------------------
        _spec(
            "participation_decayed_rate",
            "float64",
            "Recency-weighted participation rate across seasons strictly before the target.",
            "fantacalcio_voti_manual",
            "target season boundary (pre-season)",
            "B",
        ),
        _spec(
            "participation_latest_rate",
            "float64",
            "Most recent completed season's participation rate.",
            "fantacalcio_voti_manual",
            "target season boundary (pre-season)",
            "B",
        ),
        _spec(
            "participation_crosscheck_delta",
            "float64",
            "latest_rate - decayed_rate: internal consistency delta between the two estimators.",
            "fantacalcio_voti_manual",
            "target season boundary (pre-season)",
            "B",
        ),
        # --- recency weight (modeling.time_decay) ------------------------------
        _spec(
            "recency_weight",
            "float64",
            "Exponential time-decay weight relative to the most recent matchday index.",
            "fantacalcio_voti_manual",
            "as-of matchday boundary",
            "B",
        ),
        # --- team strength (modeling.dixon_coles / modeling.elo) --------------
        _spec(
            "team_attack_strength",
            "float64",
            "Dixon-Coles attack parameter as-of the season boundary.",
            "football_data_co_uk",
            "season boundary (matches strictly before it)",
            "A",
        ),
        _spec(
            "team_defense_strength",
            "float64",
            "Dixon-Coles defense parameter as-of the season boundary.",
            "football_data_co_uk",
            "season boundary (matches strictly before it)",
            "A",
        ),
        _spec(
            "team_elo_rating",
            "float64",
            "Sequential Elo rating as-of the season boundary.",
            "football_data_co_uk",
            "season boundary (matches strictly before it)",
            "A",
        ),
        # --- odds-implied team priors (modeling.odds_priors, Stage 2) --------
        _spec(
            "team_odds_clean_sheet_rate",
            "float64",
            "Mean odds-implied clean-sheet probability across the season's priced fixtures.",
            "football_data_co_uk",
            "season boundary (last kickoff of the priced season) for the aggregate; match kickoff per fixture",
            "A",
        ),
        _spec(
            "team_odds_expected_goals_conceded",
            "float64",
            "Mean odds-implied expected goals conceded across the season's priced fixtures.",
            "football_data_co_uk",
            "season boundary (last kickoff of the priced season) for the aggregate; match kickoff per fixture",
            "A",
        ),
        _spec(
            "team_odds_expected_points",
            "float64",
            "Mean odds-implied expected league points across the season's priced fixtures.",
            "football_data_co_uk",
            "season boundary (last kickoff of the priced season) for the aggregate; match kickoff per fixture",
            "A",
        ),
        # --- FVM prior (scoring.fvm_prior) -----------------------------------
        _spec(
            "fvm_bucket",
            "float64",
            "Role-wise FVM quantile bucket index (edges fit on training data).",
            "fantacalcio_quotazioni_manual",
            "target season boundary (pre-season quotazioni release)",
            "B",
        ),
        _spec(
            "fvm_bucket_low_edge",
            "float64",
            "Lower FVM edge of the assigned bucket.",
            "fantacalcio_quotazioni_manual",
            "target season boundary (pre-season quotazioni release)",
            "B",
        ),
        _spec(
            "fvm_bucket_high_edge",
            "float64",
            "Upper FVM edge of the assigned bucket.",
            "fantacalcio_quotazioni_manual",
            "target season boundary (pre-season quotazioni release)",
            "B",
        ),
        # --- listone / admin list ------------------------------------------
        _spec(
            "listone_role",
            "object",
            "Classic role letter from the fantacalcio listone.",
            "fantacalcio_quotazioni_manual",
            "target season boundary (pre-season listone release)",
            "A",
        ),
        _spec(
            "listone_quotazione",
            "float64",
            "Classic auction quotazione from the fantacalcio listone.",
            "fantacalcio_quotazioni_manual",
            "target season boundary (pre-season listone release)",
            "A",
        ),
        _spec(
            "listone_fvm",
            "float64",
            "Classic FVM from the fantacalcio listone.",
            "fantacalcio_quotazioni_manual",
            "target season boundary (pre-season listone release)",
            "A",
        ),
        _spec(
            "listone_admin_rank",
            "float64",
            "Rank of the player inside the official admin list (if resolved).",
            "admin_list_markdown",
            "admin list publication",
            "A",
        ),
        _spec(
            "listone_list_pool_name",
            "object",
            "List / pool name the player belongs to in the admin list (when available).",
            "admin_list_markdown",
            "admin list publication",
            "A",
        ),
        # --- xG/xA per-90 (ingest.understat, Stage 3) -----------------------
        _spec(
            "xg_per90_shrunk",
            "float64",
            "Empirical-Bayes shrunk per-90 expected goals from manually-imported Understat season aggregates.",
            "understat",
            "end of the Understat season the aggregate covers (30 June of the following year)",
            "C",
        ),
        _spec(
            "npxg_per90_shrunk",
            "float64",
            "Shrunk per-90 non-penalty expected goals (Understat).",
            "understat",
            "end of the Understat season the aggregate covers",
            "C",
        ),
        _spec(
            "xa_per90_shrunk",
            "float64",
            "Shrunk per-90 expected assists (Understat).",
            "understat",
            "end of the Understat season the aggregate covers",
            "C",
        ),
        _spec(
            "shots_per90_shrunk",
            "float64",
            "Shrunk per-90 shot count (Understat).",
            "understat",
            "end of the Understat season the aggregate covers",
            "C",
        ),
        _spec(
            "minutes_understat",
            "float64",
            "Total minutes played in the Understat season aggregate (unshrunk, provenance/coverage signal).",
            "understat",
            "end of the Understat season the aggregate covers",
            "C",
        ),
        _spec(
            "xg_overperformance_shrunk",
            "float64",
            "Per-90 (goals - xG), shrunk heavily toward zero (finishing over/under-performance).",
            "understat",
            "end of the Understat season the aggregate covers",
            "C",
        ),
    ]
)


def validate_feature_frame(df: pd.DataFrame) -> None:
    """Validate a long-format feature frame against the schema contract.

    Raises :class:`FeatureSchemaError` if any required column is missing, any
    lineage column is null, ``quality_tier`` is outside :data:`QUALITY_TIERS`,
    ``entity_type`` is outside :data:`ENTITY_TYPES`, or any ``feature_name`` is
    not registered in :data:`FEATURE_REGISTRY`.
    """
    required = VALUE_COLUMNS + LINEAGE_COLUMNS
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise FeatureSchemaError(f"feature frame is missing required columns: {missing}")

    null_lineage = [c for c in LINEAGE_COLUMNS if df[c].isnull().any()]
    if null_lineage:
        raise FeatureSchemaError(f"lineage columns contain nulls: {null_lineage}")

    bad_tiers = sorted(set(df["quality_tier"].unique()) - QUALITY_TIERS)
    if bad_tiers:
        raise FeatureSchemaError(f"quality_tier values not in {sorted(QUALITY_TIERS)}: {bad_tiers}")

    bad_entities = sorted(set(df["entity_type"].unique()) - ENTITY_TYPES)
    if bad_entities:
        raise FeatureSchemaError(f"entity_type values not in {sorted(ENTITY_TYPES)}: {bad_entities}")

    unknown = sorted(set(df["feature_name"].unique()) - set(FEATURE_REGISTRY))
    if unknown:
        raise FeatureSchemaError(f"feature_name(s) not in FEATURE_REGISTRY: {unknown}")
