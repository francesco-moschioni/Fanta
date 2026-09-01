"""Odds-implied match / team-goals / clean-sheet priors (Engine v2 Stage 2, ADR-2026-074).

Pipeline (design: ``docs/research/priorart_stage2.md`` §8):

    de-vig 1X2 (+ O/U 2.5)  ->  (p_home, p_draw, p_away), P(Over 2.5)
        --devig()
    supremacy + total inversion on a Dixon-Coles scoreline grid (fixed rho)
        --team_goals_distribution()
    marginals we actually need for the fantavoto engine
        --clean_sheet_prob / expected_goals_conceded / goals_conceded_pmf / match_outcome_probs
    per (season, team) aggregates written to the Stage-1 feature store
        --season_team_priors()

This does NOT fit Dixon-Coles to results (that stays in ``modeling.dixon_coles`` as
the odds-absent fallback). It uses the DC *scoreline shape* (the tau low-score
correction) but pins ``(lambda_home, lambda_away)`` from the market.

numpy / pandas / scipy only. Deterministic. Explicit errors.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import poisson

logger = logging.getLogger(__name__)

DEFAULT_RHO = -0.08
DEFAULT_MAX_GOALS = 12

# Sanity gates (priorart §2f).
_T_MIN, _T_MAX = 0.7, 4.5
_S_ABS_MAX = 2.5

# Season-aware odds column resolver (priorart §7). First tuple whose columns are
# all present with usable (> 1.0) decimal odds wins.
_1X2_COL_SETS: tuple[tuple[str, str, str], ...] = (
    ("AvgH", "AvgD", "AvgA"),
    ("BbAvH", "BbAvD", "BbAvA"),
    ("B365H", "B365D", "B365A"),
)
_OU_COL_SETS: tuple[tuple[str, str], ...] = (
    ("Avg>2.5", "Avg<2.5"),
    ("BbAv>2.5", "BbAv<2.5"),
    ("B365>2.5", "B365<2.5"),
)
_1X2_QUALITY = {"AvgH": "A", "BbAvH": "A", "B365H": "C"}


# --------------------------------------------------------------------------- #
# 1. de-vigging                                                              #
# --------------------------------------------------------------------------- #
def _multiplicative(r: np.ndarray, booksum: float) -> np.ndarray:
    return r / booksum


def _power(r: np.ndarray, booksum: float) -> np.ndarray:
    def g(k: float) -> float:
        return float(np.sum(r ** (1.0 / k)) - 1.0)

    try:
        k = brentq(g, 1e-3, 1.5, xtol=1e-12)
    except ValueError:
        logger.warning("devig(power): could not bracket k; falling back to multiplicative")
        return _multiplicative(r, booksum)
    p = r ** (1.0 / k)
    return p / p.sum()


def _shin_probs(r: np.ndarray, booksum: float, z: float) -> np.ndarray:
    return (np.sqrt(z * z + 4.0 * (1.0 - z) * r * r / booksum) - z) / (2.0 * (1.0 - z))


def shin_z(odds: Sequence[float]) -> float:
    """Fitted Shin (1993) insider-trading share ``z`` for a set of decimal odds.

    Small-margin limit is ``z ~= margin / (n - 1)``. Values outside ``[0, 0.15]``
    are a data-quality red flag (priorart §8); returns ``0.0`` when the solve
    cannot bracket (a zero-margin book).
    """
    r = 1.0 / np.asarray(odds, dtype=float)
    booksum = float(r.sum())
    n = r.size
    if n == 2:
        return 0.0
    if booksum <= 1.0 + 1e-12:
        return 0.0

    def g(z: float) -> float:
        return float(_shin_probs(r, booksum, z).sum() - 1.0)

    try:
        return float(brentq(g, 1e-12, 0.2, xtol=1e-12))
    except ValueError:
        return 0.0


def devig(odds: Sequence[float], method: str = "shin") -> np.ndarray:
    """Remove the bookmaker margin from decimal ``odds``; return fair probabilities.

    ``method``:

    - ``"shin"`` (default): Shin (1993). For ``n == 2`` this is the closed-form
      additive method; for ``n == 3`` a bounded 1-D solve for ``z`` on
      ``[0, 0.2]`` (Brent), falling back to multiplicative if it cannot bracket.
    - ``"multiplicative"``: proportional normalisation ``r_i / sum(r_j)`` (the
      ``market_odds.implied_probabilities`` logic generalised to n outcomes).
    - ``"power"``: solve ``sum r_i^(1/k) = 1`` (favourite-longshot correction).

    Output is a float ``np.ndarray`` that sums to 1.
    """
    r = 1.0 / np.asarray(odds, dtype=float)
    if r.ndim != 1 or r.size < 2:
        raise ValueError("devig: need at least 2 decimal odds in a 1-D sequence")
    if not np.all(np.isfinite(r)) or np.any(r <= 0.0):
        raise ValueError(f"devig: non-positive / non-finite implied probabilities from odds {list(odds)!r}")
    booksum = float(r.sum())

    if method == "multiplicative":
        return _multiplicative(r, booksum)
    if method == "power":
        return _power(r, booksum)
    if method != "shin":
        raise ValueError(f"devig: unknown method {method!r} (shin|multiplicative|power)")

    n = r.size
    if n == 2:
        # Shin == additive/balanced in the 2-outcome case (priorart §1e).
        p = r - (booksum - 1.0) / 2.0
        p = np.clip(p, 1e-9, None)
        return p / p.sum()
    if booksum <= 1.0 + 1e-12:
        return _multiplicative(r, booksum)

    def g(z: float) -> float:
        return float(_shin_probs(r, booksum, z).sum() - 1.0)

    try:
        z = brentq(g, 1e-12, 0.2, xtol=1e-12)
    except ValueError:
        logger.warning("devig(shin): could not bracket z on [0, 0.2]; using multiplicative")
        return _multiplicative(r, booksum)
    p = _shin_probs(r, booksum, z)
    return p / p.sum()


# --------------------------------------------------------------------------- #
# 2. odds -> scoreline grid                                                  #
# --------------------------------------------------------------------------- #
def _tau_matrix(lh: float, la: float, rho: float, k: int) -> np.ndarray:
    tau = np.ones((k + 1, k + 1), dtype=float)
    tau[0, 0] = 1.0 - lh * la * rho
    tau[0, 1] = 1.0 + lh * rho
    tau[1, 0] = 1.0 + la * rho
    tau[1, 1] = 1.0 - rho
    return tau


def _score_grid(lh: float, la: float, rho: float, max_goals: int) -> np.ndarray:
    ks = np.arange(max_goals + 1)
    ph = poisson.pmf(ks, lh)
    pa = poisson.pmf(ks, la)
    grid = np.outer(ph, pa)
    if rho != 0.0:
        grid = grid * _tau_matrix(lh, la, rho, max_goals)
    grid = np.clip(grid, 0.0, None)
    total = grid.sum()
    if total <= 0.0:
        raise ValueError("scoreline grid collapsed to zero mass")
    return grid / total


def _total_from_over_2_5(p_over_2_5: float) -> float:
    """Invert ``P(N > 2.5) = q`` under ``N ~ Pois(T)`` for the expected total ``T``.

    LHS ``1 - e^{-T}(1 + T + T^2/2)`` is strictly increasing in ``T`` (priorart
    §2c); tau perturbs it by < 1e-3 so the independent-Poisson inversion is used.
    """
    q = float(p_over_2_5)
    if not 0.0 < q < 1.0:
        raise ValueError(f"p_over_2_5 must be in (0, 1); got {q}")

    def f(t: float) -> float:
        return float(1.0 - np.exp(-t) * (1.0 + t + t * t / 2.0) - q)

    return float(brentq(f, 1e-3, 8.0, xtol=1e-10))


def _grid_outcome_margin(grid: np.ndarray) -> float:
    p_home = float(np.tril(grid, -1).sum())
    p_away = float(np.triu(grid, 1).sum())
    return p_home - p_away


def team_goals_distribution(
    p_home: float,
    p_draw: float,
    p_away: float,
    *,
    total_goals: float | None = None,
    p_over_2_5: float | None = None,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
    method: str = "dixon_coles",
) -> np.ndarray:
    """Joint pmf over ``(home_goals, away_goals)`` on a ``(max_goals+1)`` square grid.

    Supremacy + total parametrisation (priorart §2c):
    ``lambda_home = (T + s) / 2``, ``lambda_away = (T - s) / 2``.

    - ``T`` is pinned from ``total_goals`` if given, else by inverting
      ``P(Over 2.5) = p_over_2_5``; if neither is supplied a ``ValueError`` is
      raised (the caller must pass a season-average fallback).
    - ``s`` is pinned by a bracketed root-find matching ``p_home - p_away`` on the
      grid.
    - ``method="dixon_coles"`` uses the fixed negative ``rho`` tau correction;
      ``method="independent"`` drops it. When the DC bracketed solve fails the
      function falls back to the independent grid and logs the path taken.

    Sanity gates (priorart §2f): ``T`` in ``[0.7, 4.5]``, ``|s| <= 2.5``, grid
    mass ~= 1. A ``T`` outside the range raises; an out-of-range ``s`` is clamped
    with a warning.
    """
    if total_goals is not None:
        total = float(total_goals)
    elif p_over_2_5 is not None:
        total = _total_from_over_2_5(p_over_2_5)
    else:
        raise ValueError(
            "team_goals_distribution: need total_goals or p_over_2_5 "
            "(caller must supply a season-average fallback when odds lack O/U 2.5)"
        )

    if not _T_MIN <= total <= _T_MAX:
        raise ValueError(f"expected total goals T={total:.3f} outside plausible range [{_T_MIN}, {_T_MAX}]")

    target_margin = float(p_home) - float(p_away)
    use_rho = 0.0 if method == "independent" else float(rho)
    s_bound = min(3.0, total - 0.05)

    def residual(s: float, r: float) -> float:
        lh = (total + s) / 2.0
        la = (total - s) / 2.0
        return _grid_outcome_margin(_score_grid(lh, la, r, max_goals)) - target_margin

    path = "dixon_coles" if use_rho != 0.0 else "independent"
    try:
        s = brentq(lambda s: residual(s, use_rho), -s_bound, s_bound, xtol=1e-8)
    except ValueError:
        if use_rho != 0.0:
            logger.warning(
                "team_goals_distribution: DC supremacy solve failed to bracket; "
                "falling back to independent Poisson"
            )
            use_rho = 0.0
            path = "independent_fallback"
            try:
                s = brentq(lambda s: residual(s, 0.0), -s_bound, s_bound, xtol=1e-8)
            except ValueError:
                logger.warning("team_goals_distribution: independent solve also failed; using s=0")
                s = 0.0
                path = "degenerate_s0"
        else:
            logger.warning("team_goals_distribution: independent solve failed to bracket; using s=0")
            s = 0.0
            path = "degenerate_s0"

    if abs(s) > _S_ABS_MAX:
        logger.warning("team_goals_distribution: supremacy s=%.3f exceeds |%.1f|; clamping", s, _S_ABS_MAX)
        s = float(np.clip(s, -_S_ABS_MAX, _S_ABS_MAX))

    lh = (total + s) / 2.0
    la = (total - s) / 2.0
    grid = _score_grid(lh, la, use_rho, max_goals)
    if not np.isclose(grid.sum(), 1.0, atol=1e-6):
        raise ValueError(f"scoreline grid mass {grid.sum():.6f} != 1")
    logger.debug("team_goals_distribution: T=%.3f s=%.3f lh=%.3f la=%.3f path=%s", total, s, lh, la, path)
    return grid


# --------------------------------------------------------------------------- #
# 3. marginals from the JOINT grid                                           #
# --------------------------------------------------------------------------- #
def _check_side(side: str) -> None:
    if side not in ("home", "away"):
        raise ValueError(f"side must be 'home' or 'away'; got {side!r}")


def clean_sheet_prob(joint_pmf: np.ndarray, side: str) -> float:
    """``P(opponent scores 0)`` from the joint grid (not the ``exp(-lambda)`` shortcut)."""
    _check_side(side)
    j = np.asarray(joint_pmf, dtype=float)
    return float(j[:, 0].sum()) if side == "home" else float(j[0, :].sum())


def goals_conceded_pmf(joint_pmf: np.ndarray, side: str) -> np.ndarray:
    """Marginal pmf of goals conceded by ``side`` (home concedes the away marginal)."""
    _check_side(side)
    j = np.asarray(joint_pmf, dtype=float)
    return j.sum(axis=0) if side == "home" else j.sum(axis=1)


def expected_goals_conceded(joint_pmf: np.ndarray, side: str) -> float:
    pmf = goals_conceded_pmf(joint_pmf, side)
    return float(np.dot(np.arange(pmf.size), pmf))


def match_outcome_probs(joint_pmf: np.ndarray) -> tuple[float, float, float]:
    """``(P(home win), P(draw), P(away win))`` from the grid, for round-tripping."""
    j = np.asarray(joint_pmf, dtype=float)
    p_home = float(np.tril(j, -1).sum())
    p_draw = float(np.trace(j))
    p_away = float(np.triu(j, 1).sum())
    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total


# --------------------------------------------------------------------------- #
# 4. per-season / per-match team priors                                      #
# --------------------------------------------------------------------------- #
def _resolve_1x2(row: pd.Series) -> tuple[tuple[float, float, float] | None, str]:
    for cols in _1X2_COL_SETS:
        if all(c in row.index for c in cols):
            vals = [row[c] for c in cols]
            if all(pd.notna(v) and float(v) > 1.0 for v in vals):
                return (float(vals[0]), float(vals[1]), float(vals[2])), _1X2_QUALITY.get(cols[0], "C")
    return None, "C"


def _resolve_ou(row: pd.Series) -> tuple[float, float] | None:
    for cols in _OU_COL_SETS:
        if all(c in row.index for c in cols):
            vals = [row[c] for c in cols]
            if all(pd.notna(v) and float(v) > 1.0 for v in vals):
                return float(vals[0]), float(vals[1])
    return None


def _kickoff(row: pd.Series) -> pd.Timestamp:
    date = pd.Timestamp(row["Date"])
    t = row.get("Time")
    if isinstance(t, str) and ":" in t:
        try:
            hh, mm = t.split(":")[:2]
            return date + pd.Timedelta(hours=int(hh), minutes=int(mm))
        except ValueError:
            pass
    return date + pd.Timedelta(hours=12)


def _season_of(row: pd.Series, season_col: str | None) -> str:
    if season_col and season_col in row.index and pd.notna(row[season_col]):
        return str(row[season_col])
    if "season_code" in row.index and pd.notna(row["season_code"]):
        return str(row["season_code"])
    return "unknown"


def season_team_priors(
    matches: pd.DataFrame,
    *,
    devig_method: str = "shin",
    rho: float = DEFAULT_RHO,
    season_col: str | None = "season",
    fallback_total_goals: float | None = None,
    granularity: str = "season",
) -> pd.DataFrame:
    """Odds-implied clean-sheet / goals-conceded / expected-points priors per team.

    ``matches`` needs ``HomeTeam, AwayTeam, Date`` plus a resolvable 1X2 odds set
    (``Avg{H,D,A}`` preferred, then ``BbAv*``, then ``B365*``). Over/Under 2.5
    (``Avg>2.5`` / ``Avg<2.5`` etc.) is used when present; otherwise the expected
    total is ``fallback_total_goals`` if given, else that season's realised mean
    ``FTHG + FTAG`` (a mild in-season leak, acceptable for the season aggregate;
    pass ``fallback_total_goals`` for a strictly leak-free per-match build).

    ``granularity="season"`` (default) returns one row per ``(season, team)``
    with ``clean_sheet_rate``, ``expected_goals_conceded``, ``expected_points``,
    ``n_matches`` and ``available_time`` = the season's last kickoff.
    ``granularity="match"`` returns one row per team per fixture with
    ``available_time`` = kickoff -- what the feature builder writes and the
    leakage check runs against.

    Lineage columns (``source_name="football_data_co_uk"``, ``quality_tier``) are
    attached so the frame can go straight to the Stage-1 feature store.
    """
    if granularity not in ("season", "match"):
        raise ValueError("granularity must be 'season' or 'match'")
    for col in ("HomeTeam", "AwayTeam", "Date"):
        if col not in matches.columns:
            raise ValueError(f"season_team_priors: matches is missing required column {col!r}")

    df = matches.copy()
    df["_season"] = df.apply(lambda r: _season_of(r, season_col), axis=1)

    season_mean_total: dict[str, float] = {}
    if {"FTHG", "FTAG"}.issubset(df.columns):
        tot = (df["FTHG"] + df["FTAG"]).groupby(df["_season"]).mean()
        season_mean_total = {k: float(v) for k, v in tot.items()}

    per_match: list[dict] = []
    path_counts: dict[str, int] = {}
    for _, row in df.iterrows():
        season = row["_season"]
        odds_1x2, tier = _resolve_1x2(row)
        if odds_1x2 is None:
            path_counts["no_1x2"] = path_counts.get("no_1x2", 0) + 1
            continue
        p_home, p_draw, p_away = devig(odds_1x2, method=devig_method)
        ou = _resolve_ou(row)
        p_over = None
        total_goals = None
        if ou is not None:
            p_over = float(devig(ou, method=devig_method)[0])
        elif fallback_total_goals is not None:
            total_goals = float(fallback_total_goals)
        else:
            total_goals = season_mean_total.get(season)
            if total_goals is None:
                path_counts["no_total"] = path_counts.get("no_total", 0) + 1
                continue
        try:
            grid = team_goals_distribution(
                p_home, p_draw, p_away,
                total_goals=total_goals, p_over_2_5=p_over, rho=rho,
            )
        except ValueError as exc:
            logger.warning("season_team_priors: skipping %s vs %s: %s", row["HomeTeam"], row["AwayTeam"], exc)
            path_counts["grid_reject"] = path_counts.get("grid_reject", 0) + 1
            continue

        mh, md, ma = match_outcome_probs(grid)
        kickoff = _kickoff(row)
        path_counts["ok"] = path_counts.get("ok", 0) + 1
        per_match.append({
            "season": season, "team": row["HomeTeam"], "is_home": True,
            "clean_sheet_prob": clean_sheet_prob(grid, "home"),
            "expected_goals_conceded": expected_goals_conceded(grid, "home"),
            "expected_points": 3.0 * mh + 1.0 * md,
            "available_time": kickoff, "quality_tier": tier,
        })
        per_match.append({
            "season": season, "team": row["AwayTeam"], "is_home": False,
            "clean_sheet_prob": clean_sheet_prob(grid, "away"),
            "expected_goals_conceded": expected_goals_conceded(grid, "away"),
            "expected_points": 3.0 * ma + 1.0 * md,
            "available_time": kickoff, "quality_tier": tier,
        })

    logger.info("season_team_priors: match paths %s", path_counts)
    detail = pd.DataFrame(per_match)
    if detail.empty:
        return detail.assign(source_name="football_data_co_uk")

    if granularity == "match":
        detail["source_name"] = "football_data_co_uk"
        return detail.reset_index(drop=True)

    agg = (
        detail.groupby(["season", "team"])
        .agg(
            clean_sheet_rate=("clean_sheet_prob", "mean"),
            expected_goals_conceded=("expected_goals_conceded", "mean"),
            expected_points=("expected_points", "mean"),
            n_matches=("clean_sheet_prob", "size"),
            available_time=("available_time", "max"),
            quality_tier=("quality_tier", lambda s: "A" if (s == "A").all() else "B"),
        )
        .reset_index()
    )
    agg["source_name"] = "football_data_co_uk"
    return agg


__all__ = [
    "devig",
    "shin_z",
    "team_goals_distribution",
    "clean_sheet_prob",
    "goals_conceded_pmf",
    "expected_goals_conceded",
    "match_outcome_probs",
    "season_team_priors",
    "DEFAULT_RHO",
]
