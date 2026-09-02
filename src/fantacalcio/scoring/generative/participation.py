"""Sub-module 1 — participation & minutes (hurdle / two-part).

Per ``docs/research/priorart_stage4.md`` §1 and §"Recommended" Module 1:

* an **availability x selection** hurdle collapsed to a per-fixture categorical
  status in ``{0 = unused/absent, 1 = bench cameo, 2 = start}``;
* a conditional **minutes** draw given status and role.

Rate-based heuristic (documented choice): rather than fit logits on a historical
panel (deferred, ADR-2026-077), the generic outfield model is calibrated
directly to the season participation rate produced by
:mod:`fantacalcio.modeling.participation` — ``P(status > 0) = participation_rate``
per fixture, split into start vs. bench by ``start_share``. This keeps the
appearance-count marginal ``E[N] = participation_rate x n_fixtures`` exact by
construction while still producing the over-dispersion that matters for
``Var[S]`` (see :mod:`fantacalcio.scoring.generative.season`).

**Dedicated keeper sub-model** (priorart §1, Risk 3 — the Stage-2 P regression):
keepers are near-binary. A ``nailed`` #1 starts ~all fixtures with low variance;
a ``backup`` starts ~none. This is a separate branch, not the generic rotation
heuristic, precisely because the generic model misfits near-deterministic minutes.

No-vote fixtures: a status of ``0`` contributes nothing to the season sum (the
regulament's no-vote handling — the player is not scored — matches the
row-bootstrap, which only ever sums real appearances).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

KEEPER_NONE = "none"
KEEPER_NAILED = "nailed"
KEEPER_BACKUP = "backup"

# Keeper branch constants (priorart §1: low in-season switch hazard).
_NAILED_P_START = 0.97
_NAILED_P_BENCH = 0.0
_BACKUP_P_START = 0.03
_BACKUP_P_BENCH = 0.005

_DEFAULT_START_SHARE = 0.85


@dataclass(frozen=True)
class PlayerSeasonParticipation:
    """Per-player season participation features consumed by the sampler.

    Parameters
    ----------
    participation_rate:
        Fraction of matchdays the player is on the pitch (start or cameo).
        Directly the output of
        ``modeling.participation.latest_known_participation`` /
        ``decayed_participation_estimate``.
    start_share:
        Of the fixtures the player features in, the fraction that are starts
        (the rest are bench cameos). Outfield only; ignored for keepers.
    keeper_status:
        ``"none"`` (outfield / generic), ``"nailed"`` (first-choice keeper) or
        ``"backup"`` (second keeper). Drives the dedicated keeper branch.
    """

    participation_rate: float
    start_share: float = _DEFAULT_START_SHARE
    keeper_status: str = KEEPER_NONE

    def __post_init__(self) -> None:
        if not 0.0 <= self.participation_rate <= 1.0:
            raise ValueError(f"participation_rate must be in [0, 1]; got {self.participation_rate}")
        if not 0.0 <= self.start_share <= 1.0:
            raise ValueError(f"start_share must be in [0, 1]; got {self.start_share}")
        if self.keeper_status not in (KEEPER_NONE, KEEPER_NAILED, KEEPER_BACKUP):
            raise ValueError(f"unknown keeper_status {self.keeper_status!r}")


def _status_probs(feat: PlayerSeasonParticipation) -> tuple[float, float, float]:
    """Return ``(p_start, p_bench, p_unused)`` for one fixture."""
    if feat.keeper_status == KEEPER_NAILED:
        p_start, p_bench = _NAILED_P_START, _NAILED_P_BENCH
    elif feat.keeper_status == KEEPER_BACKUP:
        p_start, p_bench = _BACKUP_P_START, _BACKUP_P_BENCH
    else:
        p_app = float(np.clip(feat.participation_rate, 0.0, 1.0))
        p_start = p_app * feat.start_share
        p_bench = p_app * (1.0 - feat.start_share)
    p_unused = max(0.0, 1.0 - p_start - p_bench)
    return p_start, p_bench, p_unused


def sample_appearance(
    feat: PlayerSeasonParticipation,
    role: str,
    n_fixtures: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Per-fixture appearance status in ``{0, 1, 2}`` for one season path.

    Returns an ``int`` array of length ``n_fixtures`` (``0`` unused/absent,
    ``1`` bench cameo, ``2`` start). Deterministic given ``rng``.
    """
    if n_fixtures <= 0:
        raise ValueError("n_fixtures must be positive")
    p_start, p_bench, _ = _status_probs(feat)
    u = rng.random(n_fixtures)
    status = np.zeros(n_fixtures, dtype=int)
    status[u < p_start] = 2
    status[(u >= p_start) & (u < p_start + p_bench)] = 1
    return status


def sample_minutes(status: np.ndarray, role: str, rng: np.random.Generator) -> np.ndarray:
    """Minutes played given per-fixture ``status`` and ``role``.

    * ``status == 0`` -> ``0``.
    * ``status == 2`` (start): keepers play a full match (near-zero
      minutes-variance for a nailed #1); outfielders are a two-component mixture
      (completes ~ 89' vs. substituted-off ~ N(66, 12) truncated).
    * ``status == 1`` (bench): right-skewed sub-on minutes, ``Exp(18)`` on
      ``[1, 44]``.
    """
    status = np.asarray(status, dtype=int)
    minutes = np.zeros(status.shape, dtype=float)
    start = status == 2
    bench = status == 1

    n_start = int(start.sum())
    if n_start:
        if role == "P":
            minutes[start] = 90.0
        else:
            completes = rng.random(n_start) < 0.65
            full = np.clip(rng.normal(89.0, 1.5, n_start), 60.0, 90.0)
            subbed = np.clip(rng.normal(66.0, 12.0, n_start), 15.0, 89.0)
            minutes[start] = np.where(completes, full, subbed)

    n_bench = int(bench.sum())
    if n_bench:
        minutes[bench] = np.clip(rng.exponential(18.0, n_bench), 1.0, 44.0)

    return minutes


def simulate_appearance_counts(
    feat: PlayerSeasonParticipation,
    role: str,
    n_fixtures: int,
    n_sims: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Appearance-count distribution: ``(status > 0).sum()`` over ``n_sims`` paths.

    A standalone calibration helper (priorart §8.2, "appearance-count
    calibration") — the season simulator does the same draw inside its loop.
    """
    counts = np.empty(n_sims, dtype=int)
    for i in range(n_sims):
        counts[i] = int((sample_appearance(feat, role, n_fixtures, rng) > 0).sum())
    return counts


__all__ = [
    "PlayerSeasonParticipation",
    "KEEPER_NONE",
    "KEEPER_NAILED",
    "KEEPER_BACKUP",
    "sample_appearance",
    "sample_minutes",
    "simulate_appearance_counts",
]
