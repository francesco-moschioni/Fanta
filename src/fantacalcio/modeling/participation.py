"""Season-level participation rate, derived from the voti panel and cross-checked
against the Fantacalcio.it "statistiche" export's `Pv` field.

Framing note: the 2025/26 season is already complete in our data (38/38 matchdays,
confirmed in M1), so this is not a mid-season walk-forward problem — the useful
question is whether a player's participation rate in one completed season predicts
their rate in the next, which is exactly what's needed to prep for an auction ahead
of a season that hasn't started yet (2026/27). Every season boundary in this module
only ever uses seasons strictly before the one being predicted.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

MATCHDAYS_PER_SEASON = 38
PRIMARY_PANEL = "Fantacalcio"


@dataclass(frozen=True)
class SeasonParticipation:
    frame: pd.DataFrame  # columns: player_code, season_label, season_rank, role, matchdays_rated, participation_rate


def compute_season_participation(voti_panel: pd.DataFrame) -> SeasonParticipation:
    """`voti_panel` is the output of player_voto.load_player_matchday_panel (already
    filtered to the primary panel, ALL/coach rows dropped). Rate is computed over
    *rated* matchdays only (voto_no_vote rows still count as "the player was listed
    that matchday", i.e. available but not scored — included in the denominator
    context by construction since the panel only contains rows the export produced)."""
    if voti_panel.empty:
        empty_cols = ["player_code", "season_label", "season_rank", "role", "matchdays_rated", "participation_rate"]
        return SeasonParticipation(frame=pd.DataFrame(columns=empty_cols))

    rated = voti_panel[~voti_panel["voto_no_vote"]]
    grouped = (
        rated.groupby(["player_code", "season_label", "season_rank"])
        .agg(matchdays_rated=("matchday", "nunique"), role=("role", lambda s: s.mode().iat[0]))
        .reset_index()
    )
    grouped["participation_rate"] = grouped["matchdays_rated"] / MATCHDAYS_PER_SEASON
    return SeasonParticipation(frame=grouped.sort_values(["season_rank", "player_code"]).reset_index(drop=True))


@dataclass(frozen=True)
class PersistenceResult:
    n_pairs: int
    correlation: float
    mae_vs_carry_forward: float
    mae_vs_global_mean_baseline: float


def season_to_season_persistence(participation: SeasonParticipation) -> PersistenceResult:
    """For each player present in two consecutive seasons, does last season's
    participation rate predict this season's? Compares a naive carry-forward
    prediction against the global-mean baseline (same spirit as the other M2
    baselines: a model only earns its complexity if it beats a trivial constant)."""
    frame = participation.frame
    pairs = []
    global_mean = frame["participation_rate"].mean()

    by_player = {code: g.sort_values("season_rank") for code, g in frame.groupby("player_code")}
    for code, g in by_player.items():
        ranks = list(g["season_rank"])
        rates = dict(zip(g["season_rank"], g["participation_rate"]))
        for i in range(1, len(ranks)):
            prev_rank, curr_rank = ranks[i - 1], ranks[i]
            if curr_rank == prev_rank + 1:  # only consecutive seasons, no gaps
                pairs.append((rates[prev_rank], rates[curr_rank]))

    if not pairs:
        return PersistenceResult(n_pairs=0, correlation=float("nan"), mae_vs_carry_forward=float("nan"), mae_vs_global_mean_baseline=float("nan"))

    prev_vals = pd.Series([p[0] for p in pairs])
    curr_vals = pd.Series([p[1] for p in pairs])
    correlation = float(prev_vals.corr(curr_vals))
    mae_carry_forward = float((curr_vals - prev_vals).abs().mean())
    mae_global_mean = float((curr_vals - global_mean).abs().mean())

    return PersistenceResult(
        n_pairs=len(pairs),
        correlation=correlation,
        mae_vs_carry_forward=mae_carry_forward,
        mae_vs_global_mean_baseline=mae_global_mean,
    )


def latest_known_participation(participation: SeasonParticipation) -> pd.DataFrame:
    """One row per player: their most recent season's participation rate, plus how
    many seasons of history back it. For predicting a season that hasn't been
    played yet — the "last known" rate, not an average across a possibly-stale
    career (a player's most recent season is more informative than their rookie
    year for what to expect next)."""
    frame = participation.frame
    idx = frame.groupby("player_code")["season_rank"].idxmax()
    latest = frame.loc[idx, ["player_code", "season_label", "role", "matchdays_rated", "participation_rate"]].copy()
    seasons_count = frame.groupby("player_code").size().rename("seasons_of_history")
    return latest.merge(seasons_count, on="player_code", how="left").reset_index(drop=True)


@dataclass(frozen=True)
class CrossCheckResult:
    n_matched: int
    correlation: float
    mae: float


def cross_check_against_statistiche(
    participation: SeasonParticipation, statistiche: pd.DataFrame, season_label: str
) -> CrossCheckResult:
    """Independent consistency check between two different ingested sources
    (voti-derived participation vs. the statistiche export's own `Pv` field) for the
    same season — per docs/DATA_AND_MODELING.md's cross-source validation principle."""
    ours = participation.frame[participation.frame["season_label"] == season_label][["player_code", "matchdays_rated"]]
    theirs = statistiche[["player_code", "matches_with_vote"]].dropna(subset=["player_code"])
    theirs = theirs.astype({"player_code": "int64"})
    ours = ours.astype({"player_code": "int64"})

    merged = ours.merge(theirs, on="player_code", how="inner")
    if merged.empty:
        return CrossCheckResult(n_matched=0, correlation=float("nan"), mae=float("nan"))

    correlation = float(merged["matchdays_rated"].corr(merged["matches_with_vote"]))
    mae = float((merged["matchdays_rated"] - merged["matches_with_vote"]).abs().mean())
    return CrossCheckResult(n_matched=len(merged), correlation=correlation, mae=mae)
