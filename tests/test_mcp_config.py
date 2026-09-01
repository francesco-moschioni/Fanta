"""Stage 0 (ADR-2026-070): `.mcp.json` must not be tracked with a machine-absolute path.

The football-docs MCP config carries an absolute Windows path to a global
node_modules install, so it is gitignored and kept per-machine. This test guards
against it being committed by accident.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return set(out.stdout.splitlines())


def test_mcp_json_not_tracked():
    tracked = _tracked_files()
    assert ".mcp.json" not in tracked, ".mcp.json must stay gitignored (machine-local path)"
    assert ".mcp.local.json" not in tracked


def test_gitignore_covers_mcp_and_feature_dirs():
    gi = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for needle in (".mcp.json", ".mcp.local.json", "data/features/", "data/models/"):
        assert needle in gi, f"{needle!r} missing from .gitignore"


def test_committed_mcp_configs_have_no_drive_letter_path():
    """Any *committed* .mcp*.json (none expected) must not embed a C:/ or G:/ path."""
    for path in REPO_ROOT.glob(".mcp*.json"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _tracked_files():
            text = path.read_text(encoding="utf-8")
            assert ":/" not in text and ":\\" not in text, (
                f"{rel} is tracked and contains an absolute drive path"
            )
