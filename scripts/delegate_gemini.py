#!/usr/bin/env python3
"""Run a bounded Gemini CLI task in a temporary allowlisted workspace."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


BLOCKED_PARTS = {
    ".env",
    "secret",
    "secrets",
    "credential",
    "credentials",
    "cookie",
    "cookies",
    "private_participants",
    ".ssh",
}
BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
MAX_TOTAL_BYTES = 2_000_000
MAX_RESPONSE_CHARS = 30_000
ALLOWED_MODEL_KEYS = {"GEMINI_API_KEY", "GOOGLE_API_KEY"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-file", required=True, type=Path)
    parser.add_argument("--file", action="append", default=[], type=Path)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-response-chars", type=int, default=MAX_RESPONSE_CHARS)
    return parser.parse_args()


def reject_sensitive(path: Path) -> None:
    lowered = {part.lower() for part in path.parts}
    has_blocked_part = any(
        part in BLOCKED_PARTS
        or part.startswith(".env")
        or part.startswith("cookies")
        or part.startswith("credentials")
        for part in lowered
    )
    if has_blocked_part or path.suffix.lower() in BLOCKED_SUFFIXES:
        raise ValueError(f"Blocked sensitive-looking path: {path}")
    if path.is_symlink():
        raise ValueError(f"Symlinks are not allowed: {path}")


def main() -> int:
    args = parse_args()
    root = Path.cwd().resolve()
    task_path = args.task_file.resolve(strict=True)
    reject_sensitive(task_path)
    try:
        task_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Task file is outside repository root: {task_path}") from exc
    if not task_path.is_file() or task_path.stat().st_size > 100_000:
        raise ValueError("Task file must be a regular text file of at most 100 KB")
    task = task_path.read_text(encoding="utf-8")

    selected: list[tuple[Path, Path]] = []
    total_bytes = 0
    for supplied in args.file:
        source = supplied.resolve(strict=True)
        reject_sensitive(source)
        if not source.is_file():
            raise ValueError(f"Only regular files are allowed: {source}")
        try:
            relative = source.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"File is outside repository root: {source}") from exc
        size = source.stat().st_size
        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            raise ValueError(f"Allowlisted inputs exceed {MAX_TOTAL_BYTES} bytes")
        selected.append((source, relative))

    executable = shutil.which("gemini")
    if not executable:
        raise RuntimeError("Gemini CLI not found on PATH")

    with tempfile.TemporaryDirectory(prefix="fantacalcio-gemini-") as temp_name:
        temp_root = Path(temp_name)
        manifest: list[str] = []
        for source, relative in selected:
            destination = temp_root / "inputs" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            manifest.append(str(Path("inputs") / relative))

        prompt = (
            "You are a bounded coding worker. You can inspect only the copied files listed below. "
            "Do not claim to have run repository tests. Do not invent missing project context. "
            "Return a concise JSON-compatible response with: summary, assumptions, proposed_changes, "
            "tests_to_run, and risks. If asked for code, provide a unified diff against the copied paths.\n\n"
            f"TASK:\n{task}\n\nALLOWLISTED FILES:\n"
            + ("\n".join(manifest) if manifest else "(none)")
        )

        command = [executable, "-p", prompt, "--output-format", "json"]
        if args.model:
            command.extend(["--model", args.model])

        env = os.environ.copy()
        for name in list(env):
            upper = name.upper()
            sensitive_name = any(
                token in upper
                for token in ("SECRET", "TOKEN", "PASSWORD", "COOKIE", "CREDENTIAL")
            ) or upper.endswith("_API_KEY")
            if sensitive_name and upper not in ALLOWED_MODEL_KEYS:
                env.pop(name, None)

        result = subprocess.run(
            command,
            cwd=temp_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            print(result.stderr[-4000:], file=sys.stderr)
            return result.returncode

        payload = json.loads(result.stdout)
        response = str(payload.get("response", ""))
        compact = {
            "response": response[: args.max_response_chars],
            "truncated": len(response) > args.max_response_chars,
            "stats": payload.get("stats", {}),
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"delegate_gemini: {exc}", file=sys.stderr)
        raise SystemExit(2)
