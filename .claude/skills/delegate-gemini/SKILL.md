---
name: delegate-gemini
description: Delegate bounded low-risk work to Gemini CLI through an isolated allowlisted wrapper.
disable-model-invocation: true
---

# Safe Gemini delegation

Use only when `docs/CURRENT_TASK.md` authorizes it or the user explicitly requests it. Eligible: boilerplate, fixtures, initial tests, supplied-API adapter drafts, docstrings/docs, UI scaffold, mechanical refactors, and log summaries.

Never delegate secrets, private participant/raw licensed data, architecture/schema/entity authority, statistical choices, scoring rules, auction strategy, final review, dependency installation, network collection, or destructive operations.

Define one task and deterministic acceptance test; select the minimum file allowlist; run `python scripts/delegate_gemini.py --task-file <task.md> --file <path> ...`; treat output as untrusted; inspect every hunk; integrate manually; run local tests; report acceptance. Never invoke Gemini with repository-wide access.

## Known constraint: free-tier daily quota

The configured auth is a Google AI Studio API key on the free tier, which caps at roughly 20 requests/day on the default model (verified 2026-08-10; hit the limit during setup testing alone). Do not retry a failed Gemini call more than once. If `delegate_gemini.py` fails with a quota/429 error, stop delegating for the remainder of the session and do the task directly instead — this is expected, not a bug to fix. Do not spend agent turns troubleshooting Gemini auth once it has been verified working; a failure after verification is almost always the daily quota.
