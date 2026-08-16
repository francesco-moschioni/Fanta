#!/usr/bin/env python3
"""Adds the genuinely-new admin-list signings (no player_code anywhere, zero
Serie A history under any identity) to `_m3_replacement_values.csv` so they
become searchable/comparable/lockable in the app like any other player
(ADR-2026-051).

Per CLAUDE.md's ban on inventing IDs that could collide with a real future
one: uses negative `player_code`s (every real Fantacalcio.it ID is positive),
clearly out of the real ID space forever, never just "the next free number".

Forecast: these players have literally zero history under any identity, so a
personalized Monte Carlo simulation is impossible -- reuses the exact same
role-average fallback already computed for the `no_history_transfer` tier
(zero Serie A history + an established prior club), rather than inventing new
numbers. `quotazione_asta` reuses the admin list's own score for that player
(same numeric scale as the real `Qt.A` column, cross-checked against known
values in the anchor file).

Team affiliation is from web research (2026-08-16), not from the admin file
or the anchor roster -- flagged `team_verified=False` so the UI can show it
as unconfirmed rather than presenting it with false authority.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fantacalcio.auction.round_pools import assign_round_pools
from fantacalcio.config import load_ruleset

CSV_PATH = Path("data/staged/fantacalcio_voti_manual/_m3_replacement_values.csv")
RULESET_PATH = Path("config/auction_rules.v1.yaml")

# (player_code, display_name, role, team_name, admin_rank, admin_score) --
# team_name from web research 2026-08-16, cross-checked against multiple
# sources (Sky Sport, Eurosport, Goal.com, fantacalcio.it) -- see chat/ADR-2026-051
# for citations. Still flagged unverified since it's not from an admin/anchor file.
NEW_SIGNINGS = [
    (-1, "Molina N.", "D", "Roma", 8, 32.0),
    (-2, "Obrador", "D", "Sassuolo", 51, 12.0),
    (-3, "Spence", "D", "Inter", 4, 36.0),
    (-4, "Schmid", "C", "Frosinone", 43, 21.0),
]


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    ruleset = load_ruleset(RULESET_PATH)

    if (df["player_code"] < 0).any():
        raise RuntimeError(
            f"{CSV_PATH} already has negative (provisional) player_code rows -- "
            "re-running this script on an already-patched file would duplicate them. "
            "Regenerate the base file with scripts/run_m3_replacement_values.py first."
        )

    role_averages = (
        df[df["data_quality_tier"] == "no_history_transfer"]
        .groupby("role")[["sim_mean", "sim_median", "sim_p10", "sim_p90", "replacement_level"]]
        .mean()
    )

    # Team affiliation for every pre-existing row comes from the admin's own
    # Quotazioni file -- authoritative, unlike the web-researched team_name
    # used for the 4 brand-new signings below.
    df = df.copy()
    df["team_verified"] = True
    original_list_state = dict(zip(df["player_code"], df["list_state"]))

    new_rows = []
    for player_code, display_name, role, team_name, admin_rank, admin_score in NEW_SIGNINGS:
        avg = role_averages.loc[role]
        new_rows.append(
            {
                "player_code": player_code,
                "display_name": display_name,
                "role": role,
                "team_name": team_name,
                "quotazione_asta": admin_score,
                "sim_mean": avg["sim_mean"],
                "sim_median": avg["sim_median"],
                "sim_p10": avg["sim_p10"],
                "sim_p90": avg["sim_p90"],
                "team_strength_adjustment": 0.0,
                "used_fvm_prior": True,
                "player_games_in_pool": 0,
                "used_role_pool_only": True,
                "replacement_level": avg["replacement_level"],
                "var_mean": avg["sim_mean"] - avg["replacement_level"],
                "var_p10": avg["sim_p10"] - avg["replacement_level"],
                "var_p90": avg["sim_p90"] - avg["replacement_level"],
                "degenerate_replacement": False,  # D/C have no supply shortfall (P/A do)
                "data_quality_tier": "no_history_transfer",
                "list_state": "official",
                "participation_rate": pd.NA,
                "participation_season": pd.NA,
                "participation_seasons_of_history": pd.NA,
                "admin_rank": admin_rank,
                "admin_score": admin_score,
                "admin_gk_block_score": pd.NA,
                "team_verified": False,
            }
        )

    # round_pool/list_pool_name are filled in below by assign_round_pools(),
    # not needed in new_rows yet.
    missing_from_new_rows = set(df.columns) - set(new_rows[0]) - {"team_verified", "round_pool", "list_pool_name"}
    if missing_from_new_rows:
        raise RuntimeError(
            f"New signing rows are missing columns present in {CSV_PATH}: {missing_from_new_rows} -- "
            "these would silently become NaN/NA and can break downstream code that does "
            "`if player['col']:` on them (real bug found and fixed 2026-08-16: 'used_fvm_prior')."
        )

    combined = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    # round_pool/list_pool_name recomputed over the FULL pool (existing + new)
    # so the new players' G1/G2/G3_G4 slot reflects their real rank among
    # everyone, not a guess.
    combined = assign_round_pools(combined, ruleset)
    # assign_round_pools always stamps list_state="provisional" -- it doesn't
    # know about the admin-list overlay (ADR-2026-046). Restore every
    # pre-existing row's real state, then mark the 4 new signings official
    # (they ARE in the real admin list, just without a stable player_code yet).
    combined["list_state"] = combined["player_code"].map(original_list_state).fillna(combined["list_state"])
    combined.loc[combined["player_code"].isin([r[0] for r in NEW_SIGNINGS]), "list_state"] = "official"

    combined = combined.sort_values("var_mean", ascending=False)
    combined.to_csv(CSV_PATH, index=False)
    print(f"Aggiunti {len(new_rows)} nuovi acquisti senza player_code reale a {CSV_PATH}")
    print(f"Righe totali: {len(combined)}")


if __name__ == "__main__":
    main()
