"""Stage 0 (ADR-2026-070): numpy is now an explicit dependency.

It was already used transitively (scoring/monte_carlo.py, modeling/participation.py);
Engine v2 makes the reliance first-class. The `ml` / `solver` extras are declared
but intentionally not installed by default.
"""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_numpy_importable():
    import numpy  # noqa: F401


def test_numpy_declared_explicitly():
    deps = _pyproject()["project"]["dependencies"]
    assert any(d.replace(" ", "").lower().startswith("numpy") for d in deps), deps


def test_requirements_txt_mirrors_numpy():
    reqs = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "numpy" in reqs


def test_engine_v2_extras_declared():
    extras = _pyproject()["project"]["optional-dependencies"]
    assert "ml" in extras and "solver" in extras
    assert any("lightgbm" in d for d in extras["ml"])
    assert any("scikit-learn" in d for d in extras["ml"])
