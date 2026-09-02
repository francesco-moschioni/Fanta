"""Risk profile -- one `risk_aversion` knob interpolating E[points] -> CVaR
(Engine v2 Stage 6, ADR-2026-076; design: docs/research/priorart_stage6.md sec 4).

Scenario-based (sample) Conditional Value-at-Risk, Rockafellar-Uryasev (2000):
for reward samples (roster or single-player seasonal points), lower-tail CVaR at level
`alpha` is the mean of the worst `alpha` fraction of scenarios, expressed via the
convex auxiliary form

    CVaR_alpha = VaR_alpha - (1/alpha) * E[ (VaR_alpha - reward)^+ ]

with `VaR_alpha` the empirical alpha-quantile. `risk_adjusted_objective` blends mean and
CVaR by `rho = risk_aversion in [0, 1]`; `rho = 0` reproduces the plain-mean (today's
VAR) objective exactly, so Stage 6 is backward compatible.

Pure scalar helpers: optimiser integration is via a per-candidate adjusted value, not
by changing the DP.
"""

from __future__ import annotations

import numpy as np


def cvar(samples, alpha: float = 0.10) -> float:
    """Lower-tail Conditional Value-at-Risk of `samples` at level `alpha` (mean of the
    worst `alpha` fraction). `cvar <= mean` for any non-degenerate sample."""
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    arr = np.asarray(samples, dtype=float)
    if arr.size == 0:
        raise ValueError("samples is empty")
    var_alpha = float(np.quantile(arr, alpha))
    shortfall = float(np.mean(np.maximum(var_alpha - arr, 0.0)))
    return var_alpha - shortfall / alpha


def risk_adjusted_objective(mean: float, cvar_value: float, risk_aversion: float) -> float:
    """`(1 - rho) * mean + rho * cvar_value`, `rho = risk_aversion in [0, 1]`.
    `rho = 0` -> `mean`; `rho = 1` -> `cvar_value` (most defensive)."""
    rho = float(risk_aversion)
    if not 0.0 <= rho <= 1.0:
        raise ValueError(f"risk_aversion must be in [0, 1], got {rho}")
    return (1.0 - rho) * float(mean) + rho * float(cvar_value)
