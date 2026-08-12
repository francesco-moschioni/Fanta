"""Monte Carlo fantavoto distribution via mixture bootstrap over real historical rows.

Per docs/DATA_AND_MODELING.md and CLAUDE.md ("forecasts are distributions, not
single magic numbers"): rather than assume a parametric shape (normal, Poisson...)
for voto and events, which docs/SCORING_RULES.md and the data don't confirm, this
resamples whole real historical (voto, events) rows. That preserves whatever real
joint correlation exists between voto and events (e.g. a big-goal game tends to
carry a high voto already) instead of sampling voto and events independently and
double-counting.

Mixture weight matches the Empirical-Bayes shrinkage already validated for the
point-estimate model (ADR-2026-012): with probability n/(n+prior_games), draw from
the player's own historical rows; otherwise draw from the role-level pool. A player
with little/no history is dominated by the role pool, same as the point estimate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import PlayerMatchdayEvents, score_fantavoto

DEFAULT_PRIOR_GAMES = 60.0
DEFAULT_N_SIMS = 1000
DEFAULT_SEED = 42

DEFAULT_CALIBRATION_META_PATH = Path("data/staged/fantacalcio_voti_manual/_monte_carlo_validation_meta.json")


@dataclass(frozen=True)
class HistoricalRow:
    voto: float
    role: str
    goals_scored: int
    assists: int
    goals_conceded: int
    own_goals: int
    yellow_cards: int
    red_cards: int
    penalties_missed: int
    team_goals_conceded: float | None  # NaN-safe: None if the join didn't match
    # Recency weight (docs/CURRENT_TASK.md block 4); 1.0 = no decay, the
    # pre-block-4 behavior. Only consulted when simulate_fantavoto is called
    # with use_recency_weights=True -- default sampling is untouched so blocks
    # 1-2's validated k/FVM-bucket results stay reproducible.
    recency_weight: float = 1.0


def build_event_pools(rated_with_team_data: pd.DataFrame) -> tuple[dict, dict]:
    """`rated_with_team_data` must have the columns produced by
    scripts/run_scoring_engine_validation.py's join (voti panel + team_goals_conceded).
    Returns (player_pools, role_pools), each a dict of lists of HistoricalRow."""
    player_pools: dict[int, list[HistoricalRow]] = {}
    role_pools: dict[str, list[HistoricalRow]] = {}

    for row in rated_with_team_data.itertuples(index=False):
        team_conceded = getattr(row, "team_goals_conceded", None)
        weight = getattr(row, "recency_weight", None)
        historical_row = HistoricalRow(
            voto=float(row.voto),
            role=row.role,
            goals_scored=int(row.goals_scored),
            assists=int(row.assists),
            goals_conceded=int(row.goals_conceded),
            own_goals=int(row.own_goals),
            yellow_cards=int(row.yellow_cards),
            red_cards=int(row.red_cards),
            penalties_missed=int(row.penalties_missed),
            team_goals_conceded=float(team_conceded) if pd.notna(team_conceded) else None,
            recency_weight=float(weight) if weight is not None and pd.notna(weight) else 1.0,
        )
        player_pools.setdefault(row.player_code, []).append(historical_row)
        role_pools.setdefault(row.role, []).append(historical_row)

    return player_pools, role_pools


def _row_to_events(row: HistoricalRow, target_role: str) -> PlayerMatchdayEvents:
    """`target_role` (the role we're simulating for) overrides the sampled row's own
    role when drawing from the role pool across roles wouldn't make sense — but pools
    are already role-segmented, so this is mostly a safety/clarity pass-through."""
    return PlayerMatchdayEvents(
        role=target_role,
        played=True,
        goals_scored=row.goals_scored,
        assists=row.assists,
        goals_conceded=row.goals_conceded,
        own_goals=row.own_goals,
        yellow_cards=row.yellow_cards,
        red_cards=row.red_cards,
        penalties_missed=row.penalties_missed,
        team_goals_conceded=int(row.team_goals_conceded) if row.team_goals_conceded is not None else None,
    )


@dataclass(frozen=True)
class SimulationResult:
    player_code: int
    role: str
    n_sims: int
    player_games_in_pool: int
    used_role_pool_only: bool
    samples: np.ndarray

    @property
    def mean(self) -> float:
        return float(np.mean(self.samples))

    @property
    def median(self) -> float:
        return float(np.median(self.samples))

    @property
    def p10(self) -> float:
        return float(np.percentile(self.samples, 10))

    @property
    def p90(self) -> float:
        return float(np.percentile(self.samples, 90))


def _sample_pool_indices(pool: list[HistoricalRow], size: int, rng: np.random.Generator, use_recency_weights: bool) -> np.ndarray:
    if not use_recency_weights:
        return rng.integers(0, len(pool), size=size)
    weights = np.array([row.recency_weight for row in pool], dtype=float)
    total = weights.sum()
    if total <= 0:
        return rng.integers(0, len(pool), size=size)  # degenerate: fall back to uniform
    return rng.choice(len(pool), size=size, p=weights / total)


def simulate_fantavoto(
    player_code: int,
    role: str,
    player_pools: dict,
    role_pools: dict,
    n_sims: int = DEFAULT_N_SIMS,
    prior_games: float = DEFAULT_PRIOR_GAMES,
    rng: np.random.Generator | None = None,
    use_recency_weights: bool = False,
) -> SimulationResult:
    """`use_recency_weights=False` (default) samples uniformly within each pool --
    the pre-block-4 behavior, kept exact so blocks 1-2's validated results stay
    reproducible. Set True to sample proportional to each row's `recency_weight`
    (see time_decay.add_recency_weight), validated separately per ADR-2026-026."""
    if rng is None:
        rng = np.random.default_rng(DEFAULT_SEED)

    own_pool = player_pools.get(player_code, [])
    role_pool = role_pools.get(role, [])
    if not role_pool:
        raise ValueError(f"No role pool available for role {role!r}; cannot simulate.")

    n = len(own_pool)
    weight_own = n / (n + prior_games) if n > 0 else 0.0

    draws_from_own = rng.random(n_sims) < weight_own
    samples = np.empty(n_sims, dtype=float)

    n_own_draws = int(draws_from_own.sum())
    if n_own_draws > 0:
        idx = _sample_pool_indices(own_pool, n_own_draws, rng, use_recency_weights)
        for i, pool_idx in zip(np.where(draws_from_own)[0], idx):
            samples[i] = score_fantavoto(own_pool[pool_idx].voto, _row_to_events(own_pool[pool_idx], role))

    n_role_draws = n_sims - n_own_draws
    if n_role_draws > 0:
        idx = _sample_pool_indices(role_pool, n_role_draws, rng, use_recency_weights)
        for i, pool_idx in zip(np.where(~draws_from_own)[0], idx):
            samples[i] = score_fantavoto(role_pool[pool_idx].voto, _row_to_events(role_pool[pool_idx], role))

    return SimulationResult(
        player_code=player_code,
        role=role,
        n_sims=n_sims,
        player_games_in_pool=n,
        used_role_pool_only=(n == 0),
        samples=samples,
    )


def load_calibration_meta(path: Path = DEFAULT_CALIBRATION_META_PATH) -> dict | None:
    """Reads the P10-P90 empirical coverage backtest written by
    `scripts/run_monte_carlo_fantavoto.py`'s walk-forward validation pass.

    Returns None if the file doesn't exist yet (e.g. the pipeline hasn't been run) --
    callers must degrade gracefully, not crash, since this is optional context, not
    a required input. The UI must show this real, measured number instead of stating
    the nominal 80% target as fact (statistical audit finding B1, ADR-2026-038)."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
