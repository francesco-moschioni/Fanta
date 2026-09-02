"""Stage 5 (ADR-2026-078): guarded LightGBM base-voto module + the model="gbm" seam.

The GBM only trains where the optional ``ml`` extra is installed. The offline dev
machine has neither ``lightgbm`` nor ``scikit-learn``, so the always-run tests
here exercise the import guard and the registry seam; the training test is
skipped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fantacalcio.models import base_voto_gbm
from fantacalcio.models.base_voto_gbm import HAS_LGB, fit_base_voto_gbm


def test_module_imports_without_ml_extra():
    assert isinstance(base_voto_gbm.HAS_LGB, bool)
    assert isinstance(base_voto_gbm.HAS_SKLEARN, bool)


def test_fit_raises_clear_runtime_error_when_lightgbm_absent():
    if HAS_LGB:
        pytest.skip("lightgbm is installed; the guard cannot fire")
    x = pd.DataFrame({"f": [1.0, 2.0, 3.0]})
    with pytest.raises(RuntimeError, match=r"lightgbm not installed"):
        fit_base_voto_gbm(x, [1.0, 2.0, 3.0], folds=[], seed=0)


@pytest.mark.skipif(not HAS_LGB, reason="needs the optional 'ml' extra")
def test_fit_base_voto_gbm_smoke():
    rng = np.random.default_rng(0)
    n = 120
    x = pd.DataFrame({"f1": rng.normal(size=n), "f2": rng.normal(size=n)})
    y = 6.0 + 0.5 * x["f1"].to_numpy() + rng.normal(scale=0.3, size=n)
    folds = [(np.arange(0, 80), np.arange(80, n))]
    out = fit_base_voto_gbm(x, y, folds, seed=7)
    assert set(out) == {"artifact", "metrics", "quantiles", "oos"}
    assert {"mae", "spearman", "coverage"} <= set(out["metrics"])
    assert out["artifact"]["feature_list"] == ["f1", "f2"]


# --------------------------------------------------------------------------- #
# scoring/generative/base_voto.py model="gbm" seam
# --------------------------------------------------------------------------- #
def test_base_voto_gbm_seam_errors_without_registered_model(monkeypatch):
    import fantacalcio.models.registry as registry
    from fantacalcio.scoring.generative.base_voto import sample_base_voto

    def _no_model(name, **kwargs):
        raise FileNotFoundError(f"no registered model {name!r}")

    monkeypatch.setattr(registry, "load", _no_model)

    rng = np.random.default_rng(0)
    with pytest.raises(RuntimeError) as excinfo:
        sample_base_voto([6.0, 6.5], [5.5, 6.0, 7.0], 4, rng, model="gbm")
    msg = str(excinfo.value).lower()
    assert "gbm" in msg and "register" in msg


def test_base_voto_level0_default_unchanged():
    from fantacalcio.scoring.generative.base_voto import sample_base_voto

    a = sample_base_voto([6.0, 6.5, 7.0], [5.0, 6.0, 7.0], 8, np.random.default_rng(123))
    b = sample_base_voto([6.0, 6.5, 7.0], [5.0, 6.0, 7.0], 8, np.random.default_rng(123))
    assert a.shape == (8,)
    assert np.array_equal(a, b)  # deterministic under seed, level0 path untouched


def test_base_voto_ordinal_still_raises():
    from fantacalcio.scoring.generative.base_voto import sample_base_voto

    with pytest.raises(NotImplementedError, match="ordinal"):
        sample_base_voto([6.0], [6.0], 2, np.random.default_rng(0), model="ordinal")
