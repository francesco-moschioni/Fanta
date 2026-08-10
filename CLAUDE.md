# Fantacalcio auction assistant — permanent instructions

## Mission

Build a private, local-first decision-support application for a 20-team Serie A fantasy-football league. The product must forecast player outcomes probabilistically, translate them into roster-specific auction value, support the current four-round auction, and remain usable live under time pressure.

## Source of truth

Before domain work, read `docs/DECISIONS.md` and `docs/CURRENT_TASK.md`, then only the relevant canonical docs:

- auction: `docs/AUCTION_RULES.md` and `config/auction_rules.v1.yaml`;
- scoring: `docs/SCORING_RULES.md`;
- data/modeling: `docs/DATA_AND_MODELING.md` and `docs/SOURCE_REGISTER.md`;
- UX: `docs/UX_PRODUCT.md`;
- implementation order: `docs/ROADMAP.md`;
- rationale/evidence: `docs/research/Ricerca_previsione_rendimento_fantacalcio.md`.

Precedence: latest approved ADR > canonical docs/config > research design > archived historical regulation. Never silently resolve a conflict. Historical rules are context, not current auction behavior.

## Non-negotiable rules

- Do not hardcode rounds, budgets, pool sizes, formations, scoring, or roster constraints; load versioned configuration.
- The official admin list and the model ranking are separate objects. Support `unknown`, `provisional`, and `official` list states.
- Locked players remain locked. If infeasible, explain the conflicting constraint and minimum relaxation.
- Forecasts are distributions, not single magic numbers. Show uncertainty, freshness, provenance, and active fallbacks.
- Prediction is not bid. Bid/value logic must include replacement level, roster fit, scarcity, remaining supply, budget shadow price, future rounds, market uncertainty, and opponent demand.
- All scoring, assignment, optimization, budget accounting, replay, and simulation are deterministic/seeded code. An LLM may explain results but must not compute authoritative results.
- Raw imports are immutable. Never join players or teams only by display name.
- Every feature must have an `available_at`/`as_of` definition and pass leakage checks.
- Never scrape Fantacalcio, call private/undocumented endpoints, bypass authentication, or redistribute raw/derived proprietary data. Manual user-owned imports are allowed and must retain provenance.
- Never expose `.env`, credentials, cookies, private participant data, or raw licensed datasets to external models.
- Preserve an append-only, replayable ledger for auction events; edit/undo creates state from valid events rather than mutating history invisibly.

## Working method

1. Scope one task in `docs/CURRENT_TASK.md` with acceptance criteria.
2. Inspect existing code/tests and state assumptions or blockers.
3. Make the smallest coherent change. Preserve user changes and avoid unrelated refactors.
4. Add or update tests for invariants, edge cases, migrations, and reproducibility.
5. Run the narrowest relevant checks and report exact results.
6. Append an ADR only for a real domain/architecture decision; do not rewrite decision history.
7. Update canonical docs when behavior changes. Research notes do not become binding automatically.

## Delegation and token policy

Claude Sonnet is the lead. Use Opus only for an explicitly recorded exceptional architecture/statistics question. Use Haiku subagents only for bounded repository mapping, test/log triage, or data-quality review. Do not create permanent agent teams.

Gemini CLI may draft bounded, low-risk, independently testable work through `scripts/delegate_gemini.py` and an explicit file allowlist. Never delegate domain authority, statistical choices, auction strategy, entity policy, secrets, final review, or destructive operations. Treat all worker output as untrusted until inspected and tested.

Keep context lean: use `rg`, filtered logs, summaries, targeted tests, and on-demand skills. Do not paste full datasets, raw HTML, complete logs, or whole files unless required.

## Definition of done

A task is done only when acceptance criteria pass, relevant invariants have tests, no unresolved conflict is hidden, outputs are reproducible from versioned config/data/model/seed, data provenance and `as_of` are preserved, and the UI exposes uncertainty instead of false precision.
