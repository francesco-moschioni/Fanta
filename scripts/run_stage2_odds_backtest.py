#!/usr/bin/env python3
"""Engine v2 Stage 2 (ADR-2026-074) backtest: does odds-conditioning beat the
scalar Dixon-Coles shift out-of-sample?

Rolling-origin over 2022/23-2025/26 (train = every completed prior season). Three
arms per target season:

  (a) scalar   -- current team_strength_adjustment.apply_adjustment
  (b) odds     -- modeling.odds_priors -> scoring.odds_conditioning
  (c) none     -- raw bootstrap ensemble, no team adjustment

Metrics per role per arm: CRPS_fair (metrics.crps_fair) vs the player's realised
season fantamedia, P10-P90 coverage, PIT mean; plus clean-sheet Brier for the
odds arm (odds-implied team clean-sheet rate vs realised).

Report (gitignored): data/staged/fantacalcio_voti_manual/_stage2_odds_backtest.md

Honest caveat: this scores rolling/weekly-style forecasts on completed, priced
seasons. It says nothing about the pre-auction 2026/27 seasonal number -- there
are no priced fixtures for a season that has not started.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

from fantacalcio.modeling.dixon_coles import fit_dixon_coles
from fantacalcio.modeling.metrics import coverage, crps_fair, brier, pit_values
from fantacalcio.modeling.odds_priors import season_team_priors
from fantacalcio.modeling.player_voto import load_player_matchday_panel
from fantacalcio.modeling.team_matchday import build_all_seasons
from fantacalcio.scoring.monte_carlo import build_event_pools, simulate_fantavoto
from fantacalcio.scoring.odds_conditioning import condition_samples, scale_scoring_propensity
from fantacalcio.scoring.team_strength_adjustment import (
    apply_adjustment,
    compute_adjustments,
    historical_avg_team_rating,
    team_ratings_from_model,
)

logger = logging.getLogger("stage2_backtest")

REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_stage2_odds_backtest.md")
QUOT_DIR = Path("data/staged/fantacalcio_quotazioni_manual")
STAT_DIR = Path("data/staged/fantacalcio_statistiche_manual")
FD_DIR = Path("data/staged/football_data_co_uk")
FD_CODE = {"2021_22": "2122", "2022_23": "2223", "2023_24": "2324", "2024_25": "2425", "2025_26": "2526"}
SEASONS = ["2021_22", "2022_23", "2023_24", "2024_25", "2025_26"]
TEST_SEASONS = ["2022_23", "2023_24", "2024_25", "2025_26"]
N_SIMS = 500
SEED = 42
TEAM_STRENGTH_K = 0.5
MAX_CONCEDED = 8


def _load_fd(seasons: list[str]) -> pd.DataFrame:
    frames = []
    for s in seasons:
        p = FD_DIR / f"serie_a_{FD_CODE[s]}.csv"
        df = pd.read_csv(p, parse_dates=["Date"])
        df["season"] = s
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _norm(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def _fd_team_index(priors: pd.DataFrame) -> dict[str, str]:
    return {_norm(t): t for t in priors["team"].unique()}


def _match_team(quot_name: str, idx: dict[str, str]) -> str | None:
    key = _norm(quot_name)
    if key in idx:
        return idx[key]
    for k, v in idx.items():
        if key in k or k in key:
            return v
    return None


def _join(voti: pd.DataFrame) -> pd.DataFrame:
    rated = voti[~voti["voto_no_vote"]].copy()
    frames = []
    for s in SEASONS:
        p = QUOT_DIR / f"{s}.csv"
        if p.is_file():
            df = pd.read_csv(p)[["player_code", "team_name"]].copy()
            df["season_label"] = s
            frames.append(df)
    rated = rated.merge(pd.concat(frames, ignore_index=True), on=["player_code", "season_label"], how="left")
    tm = build_all_seasons().frame
    rated = rated.merge(
        tm[["team_name", "season_label", "matchday", "goals_conceded"]].rename(
            columns={"goals_conceded": "team_goals_conceded"}
        ),
        on=["team_name", "season_label", "matchday"], how="left",
    )
    return rated


def _realised_cs_rate(season: str) -> pd.Series:
    tm = build_all_seasons().frame
    g = tm[tm["season_label"] == season]
    return (g["goals_conceded"] == 0).groupby(g["team_name"]).mean()


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    voti = _join(load_player_matchday_panel())

    arms = ("scalar", "odds", "none")
    # accumulators: (arm, role) -> list of per-player crps / pit / (obs, lo, hi)
    crps_acc: dict[tuple, list[float]] = {}
    pit_rows: dict[tuple, list[tuple[np.ndarray, float]]] = {}
    cs_brier: list[tuple[float, float]] = []  # (pred, obs) for odds arm, team level

    for test_season in TEST_SEASONS:
        train_seasons = [s for s in SEASONS if s < test_season]
        train = voti[voti["season_label"].isin(train_seasons)]
        player_pools, role_pools = build_event_pools(train)

        stat_p = STAT_DIR / f"{test_season}.csv"
        quot_p = QUOT_DIR / f"{test_season}.csv"
        if not (stat_p.is_file() and quot_p.is_file()):
            logger.warning("skip %s: missing statistiche/quotazioni", test_season)
            continue
        stat = pd.read_csv(stat_p).astype({"player_code": "int64"})
        quot = pd.read_csv(quot_p)
        current_team = quot.set_index("player_code")["team_name"]
        current_role = quot.set_index("player_code")["role"]

        # --- scalar arm inputs ---
        dc = fit_dixon_coles(_load_fd(train_seasons))
        ratings = team_ratings_from_model(dc)
        h_att = historical_avg_team_rating(voti[voti["season_label"].isin(train_seasons)], ratings, "attack")
        h_def = historical_avg_team_rating(voti[voti["season_label"].isin(train_seasons)], ratings, "defense")
        adjustments = compute_adjustments(current_team, current_role, h_att, h_def, ratings, TEAM_STRENGTH_K)

        # --- odds arm inputs: priors from the priced test season itself ---
        fd_test = _load_fd([test_season])
        priors = season_team_priors(fd_test, season_col=None, granularity="season")
        team_idx = _fd_team_index(priors)
        cs_by_team = priors.set_index("team")["clean_sheet_rate"].to_dict()
        egc_by_team = priors.set_index("team")["expected_goals_conceded"].to_dict()
        # per-match conceded samples -> per-team conceded pmf target
        conceded_pmf: dict[str, np.ndarray] = {}
        # expected league total goals for the scoring-ratio denominator
        league_egc = float(np.mean(list(egc_by_team.values()))) if egc_by_team else 1.3

        realised_cs = _realised_cs_rate(test_season)
        for fd_team, cs_pred in cs_by_team.items():
            if fd_team in realised_cs.index:
                cs_brier.append((float(cs_pred), float(realised_cs.loc[fd_team])))

        # crude per-team conceded pmf: Poisson(egc) truncated (target for SIR)
        for fd_team, egc in egc_by_team.items():
            pmf = poisson.pmf(np.arange(MAX_CONCEDED + 1), egc)
            conceded_pmf[fd_team] = pmf / pmf.sum()

        targets = stat.merge(
            quot[["player_code", "role"]].astype({"player_code": "int64"}),
            on="player_code", how="inner", suffixes=("", "_q"),
        ).dropna(subset=["fantamedia"])

        rng = np.random.default_rng(SEED)
        for r in targets.itertuples(index=False):
            pc, role, obs = int(r.player_code), r.role, float(r.fantamedia)
            sim = simulate_fantavoto(pc, role, player_pools, role_pools, n_sims=N_SIMS, rng=rng, collect_rows=True)
            base_result, drawn_rows = sim
            fd_team = _match_team(current_team.get(pc, ""), team_idx) if pc in current_team.index else None

            for arm in arms:
                if arm == "none":
                    res = base_result
                elif arm == "scalar":
                    adj = float(adjustments.get(pc, 0.0))
                    res = apply_adjustment(base_result, adj) if adj else base_result
                else:  # odds
                    res = base_result
                    if fd_team is not None:
                        if role in ("P", "D") and fd_team in conceded_pmf:
                            res = condition_samples(
                                base_result, target_conceded_pmf=conceded_pmf[fd_team],
                                historical_rows=drawn_rows, role=role,
                                rng=np.random.default_rng(SEED + pc),
                            )
                        elif role in ("A", "C") and fd_team in egc_by_team:
                            ratio = league_egc / max(egc_by_team[fd_team], 0.2)
                            res = scale_scoring_propensity(
                                base_result, team_goals_ratio=ratio, role=role,
                                historical_rows=drawn_rows,
                                rng=np.random.default_rng(SEED + pc),
                            )
                crps_acc.setdefault((arm, role), []).append(crps_fair(res.samples, obs))
                pit_rows.setdefault((arm, role), []).append((res.samples, obs))

    # ---- aggregate & report ----
    roles = ["P", "D", "C", "A"]
    lines = [
        "# Stage 2 odds-conditioning backtest (ADR-2026-074)",
        "",
        f"Rolling-origin, test seasons {TEST_SEASONS}, {N_SIMS} sims/player, seed {SEED}.",
        "Realised target = player season fantamedia (approx: season aggregate vs "
        "single-matchday ensemble, same convention as the M2 walk-forward).",
        "",
        "## CRPS_fair (lower is better) — mean per role",
        "",
        "| role | n | scalar | odds | none |",
        "|---|--:|--:|--:|--:|",
    ]
    for role in roles:
        n = len(crps_acc.get(("none", role), []))
        if not n:
            continue
        vals = {a: float(np.mean(crps_acc.get((a, role), [np.nan]))) for a in arms}
        lines.append(f"| {role} | {n} | {vals['scalar']:.4f} | {vals['odds']:.4f} | {vals['none']:.4f} |")

    lines += ["", "## P10-P90 coverage / PIT mean per role (odds arm)", "",
              "| role | coverage | PIT mean |", "|---|--:|--:|"]
    for role in roles:
        rows = pit_rows.get(("odds", role))
        if not rows:
            continue
        maxlen = max(s.size for s, _ in rows)
        S = np.vstack([np.pad(s, (0, maxlen - s.size), constant_values=s.mean()) for s, _ in rows])
        o = np.array([obs for _, obs in rows])
        lines.append(f"| {role} | {coverage(S, o):.3f} | {float(np.mean(pit_values(S, o))):.3f} |")

    if cs_brier:
        preds = np.array([p for p, _ in cs_brier])
        obs = np.array([o for _, o in cs_brier])
        lines += ["", "## Clean-sheet Brier (odds-implied team CS rate vs realised)", "",
                  f"- teams scored: {len(cs_brier)}",
                  f"- Brier: {brier(preds, obs):.4f}",
                  f"- baseline (predict base rate {obs.mean():.3f}): {brier(np.full_like(obs, obs.mean()), obs):.4f}"]

    # ship gate (ADR-2026-074, refined after the P-regression fix):
    #  - conditioned roles (D, and A/C via scale_scoring_propensity) must BEAT the
    #    scalar shift on CRPS_fair;
    #  - role P is a deliberate no-op (ADR-2026-023), so it must only NOT REGRESS
    #    (a tie is the expected, correct outcome -- not a failure);
    #  - clean-sheet Brier must beat the base-rate baseline.
    _TOL = 1e-4
    gate_ok = True
    gate_notes = []
    for role in ("D", "C", "A"):
        s = np.mean(crps_acc.get(("scalar", role), [np.nan]))
        o = np.mean(crps_acc.get(("odds", role), [np.nan]))
        if not (o < s):
            gate_ok = False
            gate_notes.append(f"{role} (conditioned): odds CRPS_fair {o:.4f} !< scalar {s:.4f}")
    s_p = np.mean(crps_acc.get(("scalar", "P"), [np.nan]))
    o_p = np.mean(crps_acc.get(("odds", "P"), [np.nan]))
    if o_p > s_p + _TOL:
        gate_ok = False
        gate_notes.append(f"P (no-op by design): odds CRPS_fair {o_p:.4f} regressed vs scalar {s_p:.4f}")
    if cs_brier:
        b_odds = brier(np.array([p for p, _ in cs_brier]), np.array([o for _, o in cs_brier]))
        b_base = brier(np.full(len(cs_brier), obs.mean()), obs)
        if not (b_odds < b_base):
            gate_ok = False
            gate_notes.append(f"clean-sheet Brier {b_odds:.4f} !< base rate {b_base:.4f}")
    lines += ["", "## Ship gate", "",
              f"- conditioned roles (D/C/A) beat the scalar shift, P does not regress, "
              f"clean-sheet Brier beats base rate: {'PASS' if gate_ok else 'FAIL'}",
              *[f"  - {n}" for n in gate_notes],
              "- On PASS: the odds path is available opt-in via `--odds-priors`. It is NOT flipped to",
              "  default-on: for the unpriced 2026/27 pre-auction target it degrades to the scalar",
              "  shift anyway (no fixtures priced), so promotion waits for validation on a priced live",
              "  season (ADR-2026-074)."]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport: {REPORT_PATH}")


if __name__ == "__main__":
    main()
