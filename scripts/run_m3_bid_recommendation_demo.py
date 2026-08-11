#!/usr/bin/env python3
"""Demo: max-bid recommendation on the real 2026/27 G1 defender pool.

The real auction hasn't started (it opens Sunday per the admin recap), so there's no
real ledger yet -- this builds a small synthetic sequence of G1 events (other teams
already winning some defenders) to show the recommendation actually responding to
what's been assigned, not a static snapshot. Uses real VAR values from
scripts/run_m3_replacement_values.py output.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.auction.bid_recommendation import recommend_max_bid
from fantacalcio.config import load_ruleset
from fantacalcio.domain import AssignmentEvent, AssignmentItem, Role, replay

VALUES_CSV = Path("data/staged/fantacalcio_voti_manual/_m3_replacement_values.csv")
RULESET_PATH = Path("config/auction_rules.v1.yaml")


def main() -> None:
    ruleset = load_ruleset(RULESET_PATH)
    values = pd.read_csv(VALUES_CSV)

    g1_defenders = values[(values["round_pool"] == "G1") & (values["role"] == "D")]
    pool = g1_defenders[["player_code", "var_mean"]].copy()

    my_target = g1_defenders.sort_values("var_mean", ascending=False).iloc[0]
    print(f"Target player: {my_target['display_name']} ({my_target['team_name']}), VAR={my_target['var_mean']:.2f}")

    print("\n=== Before any assignments (round just opened) ===")
    state = replay(ruleset, [])
    rec = recommend_max_bid(state, ruleset, "my_team", "G1", int(my_target["player_code"]), float(my_target["var_mean"]), pool)
    print(f"Remaining budget: {rec.remaining_budget}, slots left: {rec.remaining_slots_total}, "
          f"reserve: {rec.reserve_for_other_slots}, discretionary: {rec.discretionary_budget}")
    print(f"VAR share of pool: {rec.var_share:.4f} -> MAX BID: {rec.max_bid}")

    print("\n=== After 3 other teams already won top defenders (VAR pool shrinks) ===")
    top3 = g1_defenders.sort_values("var_mean", ascending=False).iloc[1:4]  # skip our target
    events = [
        AssignmentEvent(
            event_id=f"e{i}", ts="t", round_id="G1", team_id=f"rival-{i}",
            pool_id="defenders_top_1_60", role=Role.DEF,
            item=AssignmentItem(player_ids=(str(int(row.player_code)),)),
            amount=int(max(1, row.var_mean * 20 + 20)),  # arbitrary plausible winning bid
            source="demo", author="demo",
        )
        for i, row in enumerate(top3.itertuples(index=False), start=1)
    ]
    state2 = replay(ruleset, events)
    rec2 = recommend_max_bid(state2, ruleset, "my_team", "G1", int(my_target["player_code"]), float(my_target["var_mean"]), pool)
    print(f"Remaining budget: {rec2.remaining_budget} (unchanged: our team hasn't bought anything), "
          f"pool VAR sum: {rec2.pool_var_sum:.2f} (was {rec.pool_var_sum:.2f})")
    print(f"VAR share of pool: {rec2.var_share:.4f} -> MAX BID: {rec2.max_bid} (was {rec.max_bid})")
    print("\nThe recommendation goes UP because the same discretionary budget is now "
          "split among fewer remaining high-VAR players -- our target is relatively "
          "more valuable now that 3 alternatives are gone.")

    print("\n=== After OUR team also wins 2 defenders (budget/slots shrink) ===")
    my_wins = g1_defenders.sort_values("var_mean", ascending=False).iloc[10:12]
    events3 = events + [
        AssignmentEvent(
            event_id=f"my{i}", ts="t", round_id="G1", team_id="my_team",
            pool_id="defenders_top_1_60", role=Role.DEF,
            item=AssignmentItem(player_ids=(str(int(row.player_code)),)),
            amount=15, source="demo", author="demo",
        )
        for i, row in enumerate(my_wins.itertuples(index=False), start=1)
    ]
    state3 = replay(ruleset, events3)
    pool3 = pool[~pool["player_code"].astype(str).isin(state3.assigned_players)]
    rec3 = recommend_max_bid(state3, ruleset, "my_team", "G1", int(my_target["player_code"]), float(my_target["var_mean"]), pool3)
    print(f"Remaining budget: {rec3.remaining_budget} (was {rec2.remaining_budget}), "
          f"slots left: {rec3.remaining_slots_total} (was {rec2.remaining_slots_total})")
    print(f"MAX BID: {rec3.max_bid} (was {rec2.max_bid})")
    print("\nThe recommendation reflects OUR team's own shrinking budget and slots now, "
          "not just the market -- this is what makes it a live, ledger-aware "
          "recommendation instead of a static ranking.")


if __name__ == "__main__":
    main()
