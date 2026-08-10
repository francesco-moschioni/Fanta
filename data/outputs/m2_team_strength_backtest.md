# M2 team-strength backtest — Elo and Dixon-Coles vs naive baselines

Seed: 42. Rolling-origin, expanding window, leave-one-season-out. No-leakage check passed for every fold (train strictly before test).

| Season | Matches | Unknown-team matches | Baseline log loss | Elo log loss | Dixon-Coles log loss | Baseline goals MAE | Dixon-Coles goals MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2223 | 380 | 108 | 1.0826 | 1.0117 | 1.0323 | 0.9377 | 0.8843 |
| 2324 | 380 | 38 | 1.0885 | 1.0158 | 1.0199 | 0.9403 | 0.8646 |
| 2425 | 380 | 74 | 1.0892 | 0.9814 | 0.9734 | 0.9177 | 0.8271 |
| 2526 | 380 | 38 | 1.0875 | 1.0223 | 1.0151 | 0.9439 | 0.9031 |

## Summary (mean across folds)

- Outcome log loss: baseline=1.0869, Elo=1.0078, Dixon-Coles=1.0102 (lower is better)
- Goals MAE: baseline=0.9349, Dixon-Coles=0.8698 (lower is better)

Elo beats the constant-outcome baseline on log loss: True. Dixon-Coles beats it too: True. Dixon-Coles beats the average-goals baseline on MAE: True.

Unknown-team matches (promoted teams with no training history) fall back to average strength per `docs/CURRENT_TASK.md` scope note — a real, expected source of extra error, not a bug; see the per-fold column above for how many matches this affected.