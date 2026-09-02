"""Sub-module 5 — base voto (Level 0 only for v1).

Per ``docs/research/priorart_stage4.md`` §5 and §"Recommended" Module 5:

* **Level 0 (v1, kept)**: the current empirical-Bayes shrinkage of the base voto.
  ``sample_base_voto`` resamples a voto value from the shrunk mixture (own pool
  vs. role pool, weight ``n / (n + prior_games)``) exactly as the bootstrap does
  today.
* ``sample_appearance_scores`` goes one step further and resamples the **whole**
  historical ``(voto, events)`` row and scores it through
  ``scoring.engine.score_fantavoto`` — i.e. voto *and its shape* co-move as they
  did in a real match. This is what the season simulator uses as its per-
  appearance base, so that with every optional module off the season sum
  degrades to ``E[N] x bootstrap_mean`` (the ADR-2026-077 degradation contract).

The ordinal / cumulative-link model is a clearly-marked seam
(``model="ordinal"`` -> ``NotImplementedError``); see prior-art §5 for the form.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..monte_carlo import HistoricalRow, _row_to_events
from ..engine import score_fantavoto

DEFAULT_PRIOR_GAMES = 60.0


def _voto_value(x: object) -> float:
    return float(x.voto) if isinstance(x, HistoricalRow) else float(x)  # type: ignore[union-attr]


def sample_base_voto(
    player_pool: Sequence[object],
    role_pool: Sequence[object],
    n: int,
    rng: np.random.Generator,
    *,
    prior_games: float = DEFAULT_PRIOR_GAMES,
    model: str = "level0",
) -> np.ndarray:
    """Resample ``n`` base voto values from the shrunk own/role mixture.

    ``model="level0"`` (default) is the empirical-Bayes shrinkage kept from
    ADR-2026-012. ``model="ordinal"`` raises ``NotImplementedError`` — a future
    cumulative-link ordered logit with player + role random effects, see
    ``docs/research/priorart_stage4.md`` §5. ``model="gbm"`` (ADR-2026-078,
    Stage 5) loads a registered LightGBM base-voto model from
    ``models.registry``; it raises a clear error when no model is registered yet
    and is otherwise DEFERRED until the ``ml`` extra is installed offline.
    """
    if model == "ordinal":
        raise NotImplementedError(
            "base voto model 'ordinal' (cumulative-link ordered logit with "
            "player + role random effects) is not implemented for v1; see "
            "docs/research/priorart_stage4.md §5."
        )
    if model == "gbm":
        from fantacalcio.models.registry import load as _load_registered_model

        try:
            _load_registered_model("base_voto_gbm")
        except FileNotFoundError as exc:
            raise RuntimeError(
                "base voto model 'gbm' requested but no model is registered "
                "under 'base_voto_gbm'; fit and register one with "
                "scripts/run_base_voto_model.py after `pip install '.[ml]'` "
                "(ADR-2026-078)."
            ) from exc
        raise NotImplementedError(
            "base voto model 'gbm' registry seam is wired but GBM scoring is "
            "DEFERRED until the 'ml' extra is installed offline; see "
            "ADR-2026-078. Use model='level0' (the unchanged default)."
        )
    if model != "level0":
        raise NotImplementedError(
            f"unknown base voto model {model!r}; expected 'level0', 'gbm' or 'ordinal'."
        )
    pp = np.asarray([_voto_value(x) for x in player_pool], dtype=float)
    rp = np.asarray([_voto_value(x) for x in role_pool], dtype=float)
    if rp.size == 0:
        raise ValueError("empty role pool; cannot sample base voto")

    k = pp.size
    weight_own = k / (k + prior_games) if k > 0 else 0.0
    from_own = rng.random(n) < weight_own
    out = np.empty(n, dtype=float)
    n_own = int(from_own.sum())
    if n_own:
        out[from_own] = pp[rng.integers(0, k, n_own)]
    if n - n_own:
        out[~from_own] = rp[rng.integers(0, rp.size, n - n_own)]
    return out


def sample_appearance_scores(
    player_pools: dict,
    role_pools: dict,
    player_code: int,
    role: str,
    n: int,
    rng: np.random.Generator,
    *,
    prior_games: float = DEFAULT_PRIOR_GAMES,
) -> tuple[np.ndarray, list[HistoricalRow]]:
    """Resample ``n`` whole historical rows and score each via the rules engine.

    Mirrors ``monte_carlo.simulate_fantavoto``'s mixture logic (own vs. role
    pool, uniform within pool). Returns ``(scores, rows)`` so the season
    simulator can keep the score as-is (degradation path) or rebuild the
    ``PlayerMatchdayEvents`` with module overrides and re-score.
    """
    own = list(player_pools.get(player_code, []))
    role_pool = list(role_pools.get(role, []))
    if not role_pool:
        raise ValueError(f"No role pool available for role {role!r}; cannot simulate.")

    k = len(own)
    weight_own = k / (k + prior_games) if k > 0 else 0.0
    from_own = rng.random(n) < weight_own

    rows: list[HistoricalRow] = [None] * n  # type: ignore[list-item]
    n_own = int(from_own.sum())
    if n_own:
        idx = rng.integers(0, k, n_own)
        for i, j in zip(np.where(from_own)[0], idx):
            rows[i] = own[j]
    if n - n_own:
        idx = rng.integers(0, len(role_pool), n - n_own)
        for i, j in zip(np.where(~from_own)[0], idx):
            rows[i] = role_pool[j]

    scores = np.array(
        [score_fantavoto(r.voto, _row_to_events(r, role)) for r in rows], dtype=float
    )
    return scores, rows


__all__ = ["sample_base_voto", "sample_appearance_scores", "DEFAULT_PRIOR_GAMES"]
