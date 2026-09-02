#!/usr/bin/env python3
"""Monte Carlo fantavoto distributions: validate against real Fm, then apply to the
real 2026/27 auction roster.

Part A: for every player rated in the 2025/26 season, simulate their fantavoto
distribution using only history from *before* that season (2021/22-2024/25) --
walk-forward at the season level, no leakage -- and compare the simulated mean to
their real 2025/26 Fm. This is the same honesty check used throughout M2: report
the gap, don't chase it to zero artificially.

Part B: apply the same simulation, fitted on all 5 seasons, to the real 2026/27
quotazioni roster (498 players) to produce a distribution (not a point estimate)
per player -- mean, median, P10-P90.

Report stays local under data/staged/ (gitignored, personal-use-licensed sources).
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from fantacalcio.features.xg_features import build_xg_features
from fantacalcio.modeling.dixon_coles import fit_dixon_coles
from fantacalcio.modeling.player_voto import load_player_matchday_panel
from fantacalcio.modeling.team_matchday import build_all_seasons
from fantacalcio.scoring.fvm_prior import (
    assign_bucket,
    build_fvm_bucketed_role_pools,
    fit_fvm_bucket_edges,
    load_fvm_lookup,
)
from fantacalcio.scoring.monte_carlo import DEFAULT_PRIOR_GAMES, build_event_pools, simulate_fantavoto
from fantacalcio.scoring.generative import (
    GenerativeConfig,
    PlayerSeasonParticipation,
    default_season_fixtures,
    simulate_season,
)
from fantacalcio.modeling.participation import (
    compute_season_participation,
    decayed_participation_estimate,
    latest_known_participation,
)
from fantacalcio.scoring.xg_propensity import adjust_event_propensity
from fantacalcio.scoring.team_strength_adjustment import (
    apply_adjustment,
    compute_adjustments,
    historical_avg_team_rating,
    team_ratings_from_model,
)

VALIDATION_REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_validation.md")
VALIDATION_META_PATH = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_validation_meta.json")
APPLICATION_CSV_PATH = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_2026_27.csv")
APPLICATION_REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_2026_27.md")
QUOTAZIONI_DIR = Path("data/staged/fantacalcio_quotazioni_manual")
STATISTICHE_DIR = Path("data/staged/fantacalcio_statistiche_manual")
FOOTBALL_DATA_DIR = Path("data/staged/football_data_co_uk")
FD_SEASON_CODES = {"2021_22": "2122", "2022_23": "2223", "2023_24": "2324", "2024_25": "2425", "2025_26": "2526"}
SEASONS = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]
N_SIMS = 1000
SEED = 42
# Validated via scripts/run_team_strength_adjustment_validation.py walk-forward sweep
# (2026-08-11): k=0.5 improved correlation with real Fm from 0.3472 to 0.3522 vs. k=0
# baseline, with a monotonic 0->0.25->0.5 rise then a fall at k=1.0 -- a real, if
# modest, signal rather than noise. See ADR-2026-023.
TEAM_STRENGTH_K = 0.5
# Validated via scripts/run_fvm_prior_validation.py (2026-08-11), restricted to the
# subset where it matters (players with < LOW_HISTORY_GAMES pre-target-season games):
# correlation with real Fm rose from 0.3326 (flat role pool) to 0.4048 (FVM-bucketed
# pool) -- a larger, more convincing effect than the team-strength adjustment. See
# ADR-2026-024.
LOW_HISTORY_GAMES = 10
FVM_N_BUCKETS = 4


UNDERSTAT_STAGED_DIR = Path("data/staged/understat")
XG_SCORING_ROLES = {"A", "C"}

WHOSCORED_STAGED_DIR = Path("data/staged/whoscored")


def _load_availability(listone: pd.DataFrame, *, as_of: pd.Timestamp) -> dict[int, float]:
    """player_code -> availability_prob from staged WhoScored missing-player feeds.

    Absent-safe: returns {} when no WhoScored data has been ingested, so the
    generative pass is byte-identical to Stage 4. Names are resolved
    role-constrained via the identity resolver; unresolved names are skipped
    (never guessed).
    """
    if not WHOSCORED_STAGED_DIR.is_dir():
        return {}
    files = sorted(WHOSCORED_STAGED_DIR.glob("whoscored_missing_players_*.csv"))
    if not files:
        return {}
    from fantacalcio.features.availability import player_availability

    frame = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    anchors = listone[["player_code", "display_name", "role"]].copy()
    long_df, _review = player_availability(
        frame, as_of=as_of, anchor_players=anchors, season="2026_27"
    )
    if long_df.empty:
        return {}
    return {
        int(r.entity_id): float(r.value)
        for r in long_df.itertuples(index=False)
    }


def _load_xg_rates(listone: pd.DataFrame) -> dict[int, tuple[float, float]]:
    """player_code -> (xg_goal_rate, xg_assist_rate) from staged Understat data.

    Absent-safe: returns {} when no Understat data has been ingested. The per-90
    shrunk xG / xA are used directly as per-appearance goal / assist rate proxies
    (an appearance is ~90 minutes) -- a documented Stage 3 approximation.
    """
    if not UNDERSTAT_STAGED_DIR.is_dir():
        return {}
    files = sorted(UNDERSTAT_STAGED_DIR.glob("understat_player_season_*.csv"))
    if not files:
        return {}
    frame = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    anchors = listone[["player_code", "display_name", "role"]].copy()
    long_df, _review = build_xg_features(frame, anchors)
    if long_df.empty:
        return {}
    piv = long_df.pivot_table(
        index="entity_id", columns="feature_name", values="value", aggfunc="last"
    )
    out: dict[int, tuple[float, float]] = {}
    for eid, prow in piv.iterrows():
        gr = float(prow.get("xg_per90_shrunk", float("nan")))
        ar = float(prow.get("xa_per90_shrunk", float("nan")))
        if gr == gr:  # not NaN
            out[int(eid)] = (gr, ar if ar == ar else 0.0)
    return out


def _join_team_data(voti: pd.DataFrame) -> pd.DataFrame:
    rated = voti[~voti["voto_no_vote"]].copy()
    frames = []
    for season in SEASONS:
        path = QUOTAZIONI_DIR / f"{season}.csv"
        if path.is_file():
            df = pd.read_csv(path)[["player_code", "team_name"]].copy()
            df["season_label"] = season
            frames.append(df)
    player_team = pd.concat(frames, ignore_index=True)
    rated = rated.merge(player_team, on=["player_code", "season_label"], how="left")

    team_matchday = build_all_seasons().frame
    rated = rated.merge(
        team_matchday[["team_name", "season_label", "matchday", "goals_conceded"]].rename(
            columns={"goals_conceded": "team_goals_conceded"}
        ),
        on=["team_name", "season_label", "matchday"],
        how="left",
    )

    fvm = load_fvm_lookup(SEASONS)
    rated = rated.merge(fvm, on=["player_code", "season_label"], how="left")
    return rated


def part_a_validation(rated: pd.DataFrame) -> None:
    print("=== Part A: validation (train on pre-2025/26, predict 2025/26) ===")
    train = rated[rated["season_label"] != "2025_26"]
    player_pools, role_pools = build_event_pools(train)

    statistiche = pd.read_csv(STATISTICHE_DIR / "2025_26.csv")
    target_players = rated[rated["season_label"] == "2025_26"][["player_code", "role"]].drop_duplicates()

    rng = np.random.default_rng(SEED)
    rows = []
    for r in target_players.itertuples(index=False):
        result = simulate_fantavoto(r.player_code, r.role, player_pools, role_pools, n_sims=N_SIMS, rng=rng)
        rows.append(
            {
                "player_code": r.player_code,
                "role": r.role,
                "sim_mean": result.mean,
                "sim_p10": result.p10,
                "sim_p90": result.p90,
                "used_role_pool_only": result.used_role_pool_only,
            }
        )

    sim_df = pd.DataFrame(rows).astype({"player_code": "int64"})
    statistiche = statistiche.astype({"player_code": "int64"})
    merged = sim_df.merge(statistiche[["player_code", "fantamedia"]], on="player_code", how="inner").dropna(subset=["fantamedia"])

    corr = merged["sim_mean"].corr(merged["fantamedia"])
    gap = (merged["fantamedia"] - merged["sim_mean"]).mean()
    print(f"Matched {len(merged)} players. Correlation={corr:.4f}, mean gap (theirs-ours)={gap:.4f}")

    # Interval-coverage backtest (statistical audit finding B1, ADR-2026-038): the UI
    # states "80% of outcomes fall in [P10,P90]" as fact, but nothing in the codebase
    # had ever checked whether that's actually true out-of-sample. This is an
    # approximation -- `fantamedia` is a season aggregate, not a single-matchday voto
    # like the ones the bootstrap draws from -- but it reuses the same walk-forward
    # split already validated for the mean (ADR-2026-018), so it's the best empirical
    # check available without new data.
    in_band = (merged["fantamedia"] >= merged["sim_p10"]) & (merged["fantamedia"] <= merged["sim_p90"])
    coverage = in_band.mean()
    print(f"P10-P90 empirical coverage of real season fantamedia: {coverage:.1%} (target 80%)")

    lines = [
        "# Monte Carlo fantavoto — validation (walk-forward, season-level)",
        "",
        f"Trained on 2021/22-2024/25, predicted 2025/26. {len(merged)} players matched "
        f"against real Fm.",
        "",
        f"- Correlation (simulated mean vs. real Fm): {corr:.4f}",
        f"- Mean gap (real Fm - simulated mean): {gap:.4f}",
        f"- Players with no pre-2025/26 history (role-pool-only fallback): "
        f"{sim_df['used_role_pool_only'].sum()} ({sim_df['used_role_pool_only'].mean():.1%})",
        f"- **P10-P90 empirical coverage of real season fantamedia: {coverage:.1%}** "
        f"(nominal target 80%) — approximate: compares a single-matchday simulated "
        "band against a season-aggregate real value, the best check available without "
        "per-matchday real outcomes to compare against.",
        "",
        "This is typically meaningfully lower than the same-season engine validation "
        "(ADR-2026-017: 0.51-0.60 correlation), not just slightly -- report the actual "
        "gap honestly, don't round it toward the in-sample figure. Two plausible, non-"
        "exclusive drivers: (1) predicting an unseen future season is strictly harder "
        "than explaining a season with its own data, and (2) a meaningful fraction of "
        "target players may have zero prior history (transfers/promotions), scored "
        "purely from the role-average pool, which drags correlation down by "
        "construction for that subset. This report doesn't have enough evidence to "
        "say which dominates.",
    ]
    VALIDATION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    VALIDATION_META_PATH.write_text(
        json.dumps(
            {
                "p10_p90_empirical_coverage": round(float(coverage), 4),
                "nominal_target_coverage": 0.80,
                "n_players_validated": int(len(merged)),
                "method": "season fantamedia vs. single-matchday sim P10-P90 band, "
                "walk-forward 2021/22-2024/25 -> 2025/26",
                "computed_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Report: {VALIDATION_REPORT_PATH}")
    print(f"Coverage metadata: {VALIDATION_META_PATH}")
    return coverage


def part_b_application(rated: pd.DataFrame, *, use_xg: bool = False) -> None:
    print("\n=== Part B: apply to real 2026/27 roster ===")
    player_pools, role_pools = build_event_pools(rated)  # all 5 seasons

    listone = pd.read_csv(QUOTAZIONI_DIR / "2026_27.csv")
    rng = np.random.default_rng(SEED)

    xg_rates = _load_xg_rates(listone) if use_xg else {}
    if use_xg:
        print(f"--xg: Understat rates loaded for {len(xg_rates)} player(s) "
              f"({'no staged Understat data -> no-op' if not xg_rates else 'A/C goal/assist propensity routed through xg_propensity'}).")

    print("Fitting Dixon-Coles on all seasons for team-strength adjustment (ADR-2026-023)...")
    fd_all = pd.concat(
        [pd.read_csv(FOOTBALL_DATA_DIR / f"serie_a_{FD_SEASON_CODES[s]}.csv", parse_dates=["Date"]) for s in SEASONS],
        ignore_index=True,
    )
    dc_model = fit_dixon_coles(fd_all)
    ratings = team_ratings_from_model(dc_model)
    hist_attack = historical_avg_team_rating(rated, ratings, "attack")
    hist_defense = historical_avg_team_rating(rated, ratings, "defense")

    current_team = listone.set_index("player_code")["team_name"]
    current_role = listone.set_index("player_code")["role"]
    adjustments = compute_adjustments(current_team, current_role, hist_attack, hist_defense, ratings, TEAM_STRENGTH_K)

    print("Building FVM-bucketed role pools for low/no-history players (ADR-2026-024)...")
    fvm_edges = fit_fvm_bucket_edges(rated[["role", "fvm_classic"]].dropna(), n_buckets=FVM_N_BUCKETS)
    fvm_pools = build_fvm_bucketed_role_pools(rated, fvm_edges)
    listone_fvm = listone.set_index("player_code")["fvm_classic"]

    rows = []
    for r in listone.itertuples(index=False):
        player_code = int(r.player_code)
        own_games = len(player_pools.get(player_code, []))
        use_role_pools = role_pools
        if own_games < LOW_HISTORY_GAMES and pd.notna(listone_fvm.get(player_code)):
            bucket = assign_bucket(listone_fvm[player_code], r.role, fvm_edges)
            fvm_pool = fvm_pools.get((r.role, bucket))
            if fvm_pool:
                use_role_pools = dict(role_pools)
                use_role_pools[r.role] = fvm_pool
        xg_present = use_xg and player_code in xg_rates
        if xg_present and r.role in XG_SCORING_ROLES:
            result, drawn = simulate_fantavoto(
                player_code, r.role, player_pools, use_role_pools,
                n_sims=N_SIMS, rng=rng, collect_rows=True,
            )
            drawn_real = [row for row in drawn if row is not None]
            hist_goal = float(np.mean([row.goals_scored for row in drawn_real])) if drawn_real else 0.0
            hist_assist = float(np.mean([row.assists for row in drawn_real])) if drawn_real else 0.0
            xg_goal_rate, xg_assist_rate = xg_rates[player_code]
            result = adjust_event_propensity(
                result, historical_rows=drawn,
                xg_goal_rate=xg_goal_rate, xg_assist_rate=xg_assist_rate,
                role=r.role, hist_goal_rate=hist_goal, hist_assist_rate=hist_assist,
                rng=rng,
            )
        else:
            result = simulate_fantavoto(player_code, r.role, player_pools, use_role_pools, n_sims=N_SIMS, rng=rng)
        adj = adjustments.get(r.player_code, 0.0)
        if adj != 0.0:
            result = apply_adjustment(result, adj)
        rows.append(
            {
                "player_code": r.player_code,
                "display_name": r.display_name,
                "role": r.role,
                "team_name": r.team_name,
                "quotazione_asta": r.quotazione_asta_classic,
                "xg_data_present": bool(xg_present),
                "sim_mean": round(result.mean, 3),
                "sim_median": round(result.median, 3),
                "sim_p10": round(result.p10, 3),
                "sim_p90": round(result.p90, 3),
                "team_strength_adjustment": round(adj, 3),
                "used_fvm_prior": use_role_pools is not role_pools,
                "player_games_in_pool": result.player_games_in_pool,
                "used_role_pool_only": result.used_role_pool_only,
            }
        )

    out = pd.DataFrame(rows).sort_values("sim_mean", ascending=False)
    out.to_csv(APPLICATION_CSV_PATH, index=False)

    lines = [
        "# Monte Carlo fantavoto — 2026/27 roster (first distributional pass)",
        "",
        f"{len(out)} players, {N_SIMS} simulations each, seed={SEED}. Mixture bootstrap "
        f"(own history vs. role pool, weight n/(n+{DEFAULT_PRIOR_GAMES:.0f})) over real "
        "historical (voto, events) rows -- no assumed distribution shape. Includes a "
        f"Dixon-Coles team-strength adjustment (k={TEAM_STRENGTH_K}, validated via "
        "walk-forward, ADR-2026-023) for A/C/D roles whose 2026/27 team differs in "
        "strength from their historical average team context. For players with "
        f"< {LOW_HISTORY_GAMES} own-history games, the role-pool fallback is replaced "
        "with an FVM-bucketed pool (validated via walk-forward, ADR-2026-024) instead "
        f"of the flat role average -- {int(out['used_fvm_prior'].sum())} players affected.",
        "",
        "## Top 15 by simulated mean, with uncertainty range",
        "",
        "| Player | Role | Team | Mean | Median | P10 | P90 | Games in pool |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in out.head(15).itertuples(index=False):
        lines.append(
            f"| {row.display_name} | {row.role} | {row.team_name} | {row.sim_mean} | "
            f"{row.sim_median} | {row.sim_p10} | {row.sim_p90} | {row.player_games_in_pool} |"
        )

    lines += ["", "## By role: average P10-P90 spread (uncertainty width)", "", "| Role | Avg mean | Avg P90-P10 spread |", "|---|---:|---:|"]
    out["spread"] = out["sim_p90"] - out["sim_p10"]
    for role, g in out.groupby("role"):
        lines.append(f"| {role} | {g['sim_mean'].mean():.3f} | {g['spread'].mean():.3f} |")

    APPLICATION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nCSV: {APPLICATION_CSV_PATH}")
    print(f"Report: {APPLICATION_REPORT_PATH}")


N_SEASON_SIMS = 200
GENERATIVE_CSV_PATH = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_2026_27_generative.csv")


def part_b_generative(rated: pd.DataFrame, voti: pd.DataFrame, *, use_availability: bool = False) -> None:
    """Engine v2 Stage 4 (ADR-2026-077): season simulator per player.

    Additive to Part B — writes the new seasonal columns (titolare/subentro/
    no-vote probabilities, minutes distribution summary, downside/upside). The
    default ``--engine bootstrap`` path is untouched and byte-identical.
    All optional modules are OFF here (no odds priors, no xG, Level-0 voto):
    the degradation contract (season mean ~= bootstrap mean x participation)
    holds by construction.
    """
    print("\n=== Part B (generative): season simulator on the 2026/27 roster ===")
    player_pools, role_pools = build_event_pools(rated)

    part = compute_season_participation(voti)
    latest = latest_known_participation(part).set_index("player_code")["participation_rate"]
    # Multi-season recency-weighted rate (Stage 4 gate fix 2026-09-02, ADR-2026-077
    # addendum): single-prior-season participation under-predicted appearances.
    decayed = decayed_participation_estimate(part, half_life_seasons=1.5).set_index(
        "player_code"
    )["decayed_participation_rate"]

    listone = pd.read_csv(QUOTAZIONI_DIR / "2026_27.csv")
    fixtures = default_season_fixtures()

    # Stage 7 (ADR-2026-079): next-matchday availability cap from a manually
    # imported WhoScored feed. DEFAULT OFF; absent feed -> {} -> byte-identical.
    avail_map: dict[int, float] = {}
    if use_availability:
        from fantacalcio.features.availability import apply_availability_to_participation

        avail_map = _load_availability(listone, as_of=pd.Timestamp("2026-08-24"))
        print(f"--availability: WhoScored availability loaded for {len(avail_map)} player(s) "
              f"({'no staged WhoScored data -> no-op' if not avail_map else 'first-matchday start prob capped'}).")

    rows = []
    for r in listone.itertuples(index=False):
        code = int(r.player_code)
        if r.role not in role_pools:
            continue
        rate = float(decayed.get(code, latest.get(code, 0.5)))
        rate = min(max(rate, 0.0), 1.0)
        keeper = "rate" if r.role == "P" else "none"  # rate-driven keeper, no hard nailed/backup split
        cfg = GenerativeConfig(
            role=r.role,
            participation=PlayerSeasonParticipation(rate, keeper_status=keeper),
            player_pools=player_pools,
            role_pools=role_pools,
        )
        fmp = None
        if code in avail_map:
            fmp = apply_availability_to_participation(cfg.participation, avail_map[code])
        res = simulate_season(
            code, cfg, fixtures, n_sims=N_SEASON_SIMS, base_seed=SEED,
            first_md_participation=fmp,
        )
        rows.append({
            "player_code": code,
            "display_name": r.display_name,
            "role": r.role,
            "team_name": r.team_name,
            "availability_report_present": bool(code in avail_map),
            "season_mean": round(res.mean, 2),
            "season_median": round(res.median, 2),
            "season_p10": round(res.p10, 2),
            "season_p90": round(res.p90, 2),
            "season_downside": round(res.downside, 2),
            "season_upside": round(res.upside, 2),
            "expected_appearances": round(res.expected_appearances, 1),
            "titolare_prob": round(res.titolare_prob, 3),
            "subentro_prob": round(res.subentro_prob, 3),
            "no_vote_prob": round(res.no_vote_prob, 3),
            "minutes_mean": round(res.minutes_mean, 1),
            "minutes_p10": round(res.minutes_p10, 1),
            "minutes_p90": round(res.minutes_p90, 1),
        })
    out = pd.DataFrame(rows).sort_values("season_mean", ascending=False)
    out.to_csv(GENERATIVE_CSV_PATH, index=False)
    print(f"CSV: {GENERATIVE_CSV_PATH} ({len(out)} players, {N_SEASON_SIMS} season sims each)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--odds-priors",
        action="store_true",
        help=(
            "Engine v2 Stage 2 (ADR-2026-074): route the team adjustment through "
            "modeling.odds_priors / scoring.odds_conditioning instead of the scalar "
            "Dixon-Coles shift. DEFAULT OFF -> output byte-identical to today. The "
            "2026/27 target season has no priced fixtures, so with this flag the "
            "application pass logs the degradation and falls back to the scalar "
            "shift; the odds path is exercised by scripts/run_stage2_odds_backtest.py "
            "on completed seasons."
        ),
    )
    parser.add_argument(
        "--xg",
        action="store_true",
        help=(
            "Engine v2 Stage 3 (ADR-2026-075): when staged Understat data is present "
            "(data/staged/understat/), route A/C goal/assist propensity through "
            "scoring.xg_propensity (xG/xA blended into the bootstrap via n/(n+prior) "
            "shrinkage + SIR resample). DEFAULT OFF. Absent Understat data -> no-op. "
            "A provenance column 'xg_data_present' is always written."
        ),
    )
    parser.add_argument(
        "--availability",
        action="store_true",
        help=(
            "Engine v2 Stage 7 (ADR-2026-079). With --engine generative, load a "
            "manually-imported WhoScored injuries/suspensions feed from "
            "data/staged/whoscored/ and cap each player's FIRST-matchday start "
            "probability at the reported availability (later matchdays keep the "
            "season rate). DEFAULT OFF. Absent feed -> no-op, output identical to "
            "Stage 4. A provenance column 'availability_report_present' is written."
        ),
    )
    parser.add_argument(
        "--engine",
        choices=("bootstrap", "generative"),
        default="bootstrap",
        help=(
            "Engine v2 Stage 4 (ADR-2026-077). 'bootstrap' (DEFAULT) -> output "
            "byte-identical to today (row-bootstrap single-match). 'generative' "
            "additionally runs the decomposed season simulator "
            "(scoring.generative.season) with participation/minutes folded in, "
            "writing new seasonal columns to a separate CSV. Default stays "
            "'bootstrap' until the generative engine beats it on seasonal "
            "CRPS/coverage in rolling-origin backtests."
        ),
    )
    args = parser.parse_args()
    if args.odds_priors:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning(
            "--odds-priors: no market odds exist for the unpriced 2026/27 target "
            "season; falling back to the scalar Dixon-Coles shift (documented "
            "degradation, docs/DATA_AND_MODELING.md 'Degradazione controllata')."
        )

    print("Loading voti panel and joining team data...")
    voti = load_player_matchday_panel()
    rated = _join_team_data(voti)

    part_a_validation(rated)
    part_b_application(rated, use_xg=args.xg)
    if args.engine == "generative":
        part_b_generative(rated, voti, use_availability=args.availability)


if __name__ == "__main__":
    main()
