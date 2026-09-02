"""Counter-based hierarchical seeding for the generative season simulator.

``(base_seed, entity_code, sim_index, module_id)`` is hashed by ``numpy``'s
``SeedSequence`` into an independent stream. Two modules never share a
sub-stream, so toggling one ``module_id`` leaves every other id's draws
byte-identical — the reproducibility contract of ADR-2026-077.

Module ids are append-only; never renumber (that would shift existing streams).
"""

from __future__ import annotations

import numpy as np

MODULE_PARTICIPATION = 1
MODULE_MINUTES = 2
MODULE_SCORELINE = 3
MODULE_EVENTS = 4
MODULE_DISCIPLINE = 5
MODULE_BASE_VOTO = 6

_SEED_MASK = 0x7FFFFFFF


def module_rng(base_seed: int, entity_code: int, sim_index: int, module_id: int) -> np.random.Generator:
    """Independent, reproducible RNG stream for one (entity, sim, module) cell."""
    return np.random.default_rng(
        [int(base_seed) & _SEED_MASK, int(entity_code) & _SEED_MASK, int(sim_index), int(module_id)]
    )


__all__ = [
    "module_rng",
    "MODULE_PARTICIPATION",
    "MODULE_MINUTES",
    "MODULE_SCORELINE",
    "MODULE_EVENTS",
    "MODULE_DISCIPLINE",
    "MODULE_BASE_VOTO",
]
