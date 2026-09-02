"""Lightweight versioned model registry — taxonomy level 5 (ADR-2026-078).

No server, no DB, no MLflow/DVC. One registered model =

    data/models/<name>/<config_hash>/
        manifest.json   config, git sha, seed, serialised folds, feature_list,
                        source_filter, metrics, created_at (UTC ISO-8601)
        artifact.pkl    the fitted object, pickled
        metrics.json    the metrics dict on its own, for quick scanning

``config_hash`` is stable under dict key reordering (canonical JSON, sorted keys,
sha256 truncated to 16 hex chars) and changes on any value change.

``beats_baseline`` returns the *full* per-key comparison so the caller / ADR
records the ship decision; CI only asserts that the comparison ran.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pickle
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MODELS_ROOT = Path("data/models")

_MANIFEST_NAME = "manifest.json"
_ARTIFACT_NAME = "artifact.pkl"
_METRICS_NAME = "metrics.json"

#: Metric names where a *lower* value is better. Anything else is treated as
#: higher-is-better by :func:`beats_baseline` (coverage included — see docstring).
_LOWER_IS_BETTER = frozenset(
    {
        "mae",
        "rmse",
        "crps",
        "crps_fair",
        "crps_ensemble",
        "log_loss",
        "logloss",
        "brier",
        "pinball",
        "mape",
    }
)


# --------------------------------------------------------------------------- #
# config hashing
# --------------------------------------------------------------------------- #
def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def config_hash(config: dict) -> str:
    """Stable 16-hex-char sha256 of the canonical JSON of ``config``.

    Invariant under dict key reordering; changes on any value change.
    """
    return hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# manifest helpers
# --------------------------------------------------------------------------- #
def _git_sha() -> str:
    """``git rev-parse HEAD`` or ``"unknown"`` — the registry never fails on git."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 - a missing/broken git must not break register()
        return "unknown"


def _fold_scalar(v: Any) -> Any:
    """Best-effort JSON-friendly rendering of one fold field."""
    import pandas as pd  # local: keep import cost off module load

    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, pd.DataFrame):
        return {"__dataframe_shape__": list(v.shape)}
    if isinstance(v, pd.Series):
        return {"__series_len__": int(v.shape[0])}
    if hasattr(v, "item"):  # numpy scalar
        try:
            return v.item()
        except Exception:  # noqa: BLE001
            return str(v)
    if isinstance(v, (list, tuple)):
        return [_fold_scalar(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _fold_scalar(x) for k, x in v.items()}
    return str(v)


def _serialise_folds(folds: list) -> list:
    """Render a list of fold definitions (tuples / dicts / dataclasses / namedtuples)."""
    out: list = []
    for fold in folds:
        if hasattr(fold, "_asdict"):  # namedtuple
            out.append({k: _fold_scalar(x) for k, x in fold._asdict().items()})
        elif dataclasses.is_dataclass(fold) and not isinstance(fold, type):
            out.append(
                {f.name: _fold_scalar(getattr(fold, f.name)) for f in dataclasses.fields(fold)}
            )
        elif isinstance(fold, dict):
            out.append({str(k): _fold_scalar(x) for k, x in fold.items()})
        elif isinstance(fold, (list, tuple)):
            out.append([_fold_scalar(x) for x in fold])
        else:
            out.append(_fold_scalar(fold))
    return out


# --------------------------------------------------------------------------- #
# register / load / list
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RegisteredModel:
    """A model read back from the registry."""

    manifest: dict
    artifact: Any
    metrics: dict
    path: Path


def register(
    name: str,
    *,
    config: dict,
    artifact: Any,
    folds: list,
    seed: int,
    metrics: dict,
    feature_list: list[str],
    source_filter: dict | None = None,
    root: Path = DEFAULT_MODELS_ROOT,
) -> Path:
    """Persist a fitted model under ``<root>/<name>/<config_hash>/``.

    Returns the directory written. Re-registering the same ``config`` overwrites
    that config's directory (and refreshes ``created_at``).
    """
    root = Path(root)
    chash = config_hash(config)
    target = root / name / chash
    target.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    manifest = {
        "name": name,
        "config": config,
        "config_hash": chash,
        "git_sha": _git_sha(),
        "seed": seed,
        "folds": _serialise_folds(list(folds)),
        "feature_list": list(feature_list),
        "source_filter": source_filter,
        "metrics": metrics,
        "created_at": now.isoformat(),
        "created_at_ns": time.time_ns(),
    }
    (target / _MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    (target / _METRICS_NAME).write_text(
        json.dumps(metrics, indent=2, default=str), encoding="utf-8"
    )
    with (target / _ARTIFACT_NAME).open("wb") as fh:
        pickle.dump(artifact, fh)
    return target


def _manifest_sort_key(manifest: dict) -> tuple:
    return (manifest.get("created_at", ""), manifest.get("created_at_ns", 0))


def load(
    name: str,
    *,
    config_hash: str | None = None,  # noqa: A002 - deliberate: mirrors the field name
    root: Path = DEFAULT_MODELS_ROOT,
) -> RegisteredModel:
    """Load the newest registered model for ``name`` (or the pinned ``config_hash``)."""
    root = Path(root)
    base = root / name
    if not base.is_dir():
        raise FileNotFoundError(f"no registered model {name!r} under {base}")

    if config_hash is not None:
        target = base / config_hash
        if not (target / _MANIFEST_NAME).exists():
            raise FileNotFoundError(
                f"no registered model {name!r} with config_hash {config_hash!r}"
            )
    else:
        candidates = [
            d for d in base.iterdir() if d.is_dir() and (d / _MANIFEST_NAME).exists()
        ]
        if not candidates:
            raise FileNotFoundError(f"no registered configs for model {name!r} under {base}")
        target = max(
            candidates,
            key=lambda d: _manifest_sort_key(
                json.loads((d / _MANIFEST_NAME).read_text(encoding="utf-8"))
            ),
        )

    manifest = json.loads((target / _MANIFEST_NAME).read_text(encoding="utf-8"))
    metrics = json.loads((target / _METRICS_NAME).read_text(encoding="utf-8"))
    with (target / _ARTIFACT_NAME).open("rb") as fh:
        artifact = pickle.load(fh)
    return RegisteredModel(manifest=manifest, artifact=artifact, metrics=metrics, path=target)


def list_models(name: str | None = None, root: Path = DEFAULT_MODELS_ROOT) -> list[dict]:
    """Return manifests, newest first. ``name`` filters to one model family."""
    root = Path(root)
    if not root.is_dir():
        return []
    families = (
        [name]
        if name is not None
        else [d.name for d in sorted(root.iterdir()) if d.is_dir()]
    )
    manifests: list[dict] = []
    for fam in families:
        base = root / fam
        if not base.is_dir():
            continue
        for d in base.iterdir():
            mpath = d / _MANIFEST_NAME
            if mpath.exists():
                manifests.append(json.loads(mpath.read_text(encoding="utf-8")))
    manifests.sort(key=_manifest_sort_key, reverse=True)
    return manifests


# --------------------------------------------------------------------------- #
# ship-gate comparison
# --------------------------------------------------------------------------- #
def beats_baseline(
    model_metrics: dict,
    baseline_metrics: dict,
    *,
    keys: tuple[str, ...] = ("mae", "spearman", "coverage"),
) -> dict:
    """Per-key comparison of a model against a baseline, plus an overall verdict.

    Overall rule: **wins iff better-or-equal on ALL keys and strictly better on
    at least one**. Direction per key: names in :data:`_LOWER_IS_BETTER` are
    lower-is-better; everything else (``coverage`` included, treated
    monotonically here — read the honest caveat in ADR-2026-078) is
    higher-is-better.

    Returns the whole comparison dict; the *caller* (and the ADR) records the
    ship decision — CI only asserts that the comparison ran.
    """
    per_key: dict[str, dict] = {}
    all_better_or_equal = True
    any_strictly_better = False

    for k in keys:
        if k not in model_metrics or k not in baseline_metrics:
            per_key[k] = {
                "model": model_metrics.get(k),
                "baseline": baseline_metrics.get(k),
                "comparable": False,
                "better_or_equal": False,
                "strictly_better": False,
            }
            all_better_or_equal = False
            continue

        m = float(model_metrics[k])
        b = float(baseline_metrics[k])
        lower = k in _LOWER_IS_BETTER
        if lower:
            boe, sb = (m <= b), (m < b)
        else:
            boe, sb = (m >= b), (m > b)
        per_key[k] = {
            "model": m,
            "baseline": b,
            "direction": "lower_is_better" if lower else "higher_is_better",
            "comparable": True,
            "better_or_equal": boe,
            "strictly_better": sb,
        }
        all_better_or_equal = all_better_or_equal and boe
        any_strictly_better = any_strictly_better or sb

    return {
        "per_key": per_key,
        "keys": list(keys),
        "overall_wins": bool(all_better_or_equal and any_strictly_better),
        "rule": "better-or-equal on all keys AND strictly better on at least one",
    }


__all__ = [
    "DEFAULT_MODELS_ROOT",
    "RegisteredModel",
    "beats_baseline",
    "config_hash",
    "list_models",
    "load",
    "register",
]
