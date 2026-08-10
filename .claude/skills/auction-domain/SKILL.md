---
name: auction-domain
description: Load current roster, four-round auction, pool/list, budget, ledger, optimization, and live-assistant rules for any auction task.
---

# Auction domain workflow

Before acting, read `docs/DECISIONS.md`, `docs/AUCTION_RULES.md`, `config/auction_rules.v1.yaml`, relevant `docs/PROJECT_SPEC.md`/`docs/UX_PRODUCT.md`, and affected tests/code. If archive conflicts, current ADR/config wins. If a field in `docs/OPEN_QUESTIONS.md` is material, block only that branch and ask; never invent.

Verify as applicable: deterministic tie-breaking; pool eligibility/list state; bid minimum and affordability; no duplicate assignment; roster/slot/module feasibility; goalkeeper block; budget increments/conservation; reserve to complete future slots; locked players; future-round supply; behavior after no win; replay, correction and undo; recomputation of price/opponent profiles.

Every recommendation exposes assumptions, binding constraints, alternatives, uncertainty, `as_of`, market state and cost-opportunity. The LLM explains but never acts as the authoritative allocation, budget, optimization or scoring engine.
