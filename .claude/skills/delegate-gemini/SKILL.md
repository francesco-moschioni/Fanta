---
name: delegate-gemini
description: Delegate bounded low-risk work to Gemini CLI through an isolated allowlisted wrapper.
disable-model-invocation: true
---

# Safe Gemini delegation

Use only when `docs/CURRENT_TASK.md` authorizes it or the user explicitly requests it. Eligible: boilerplate, fixtures, initial tests, supplied-API adapter drafts, docstrings/docs, UI scaffold, mechanical refactors, and log summaries.

Never delegate secrets, private participant/raw licensed data, architecture/schema/entity authority, statistical choices, scoring rules, auction strategy, final review, dependency installation, network collection, or destructive operations.

Define one task and deterministic acceptance test; select the minimum file allowlist; run `python scripts/delegate_gemini.py --task-file <task.md> --file <path> ...`; treat output as untrusted; inspect every hunk; integrate manually; run local tests; report acceptance. Never invoke Gemini with repository-wide access.
