import pandas as pd

from fantacalcio.auction.market_supply import compute_goalkeeper_club_supply, compute_role_supply
from fantacalcio.config import RosterComposition, Round, Ruleset


def _ruleset(teams=2, forwards=2, goalkeeper_block_size=2):
    return Ruleset(
        schema_version=1, ruleset_id="test", status="working_current", effective_from="2026-01-01",
        teams=teams, custom_logo_bonus_credits=3, max_releases_per_team=5,
        roster=RosterComposition(
            total_players=4 + forwards, goalkeeper_block_size=goalkeeper_block_size, goalkeeper_same_club=True,
            defenders=1, midfielders=1, forwards=forwards, forwards_fallback=1,
        ),
        formations=("3-4-3",), list_states=("unknown", "provisional", "official"),
        official_pool_authority="admin_import", model_ranking_is_official_pool=False,
        rounds=(Round(id="G1", order=1, mode="sealed_bid_list", budget_increment=100, budget_available_expr="100", pools=("pool_a",)),),
        runtime_invariants={}, uncertain_historical_fields={},
    )


class TestComputeRoleSupply:
    def test_counts_available_per_role(self):
        pool = pd.DataFrame({"role": ["A", "A", "D", "D", "D"]})
        ruleset = _ruleset(teams=2, forwards=2)  # requires 2*2=4 A, 2*1=2 D
        result = compute_role_supply(pool, ruleset)
        by_role = {r.role: r for r in result}
        assert by_role["A"].available == 2
        assert by_role["A"].required == 4
        assert by_role["A"].shortfall == 2
        assert by_role["D"].available == 3
        assert by_role["D"].required == 2
        assert by_role["D"].shortfall == 0

    def test_returns_fixed_role_order(self):
        pool = pd.DataFrame({"role": ["A", "D", "P", "C"]})
        ruleset = _ruleset()
        result = compute_role_supply(pool, ruleset)
        assert [r.role for r in result] == ["P", "D", "C", "A"]

    def test_zero_available_gives_full_shortfall(self):
        pool = pd.DataFrame({"role": []})
        ruleset = _ruleset(teams=1, forwards=1)
        result = compute_role_supply(pool, ruleset)
        by_role = {r.role: r for r in result}
        assert by_role["A"].available == 0
        assert by_role["A"].shortfall == by_role["A"].required


class TestComputeGoalkeeperClubSupply:
    def test_identifies_clubs_below_block_size(self):
        pool = pd.DataFrame(
            {
                "role": ["P", "P", "P", "P", "P"],
                "team_name": ["Inter", "Inter", "Milan", "Milan", "Milan"],
            }
        )
        ruleset = _ruleset(goalkeeper_block_size=3)
        result = compute_goalkeeper_club_supply(pool, ruleset)
        by_club = {c.team_name: c for c in result}
        assert by_club["Inter"].goalkeeper_count == 2
        assert not by_club["Inter"].can_form_same_club_block
        assert by_club["Milan"].goalkeeper_count == 3
        assert by_club["Milan"].can_form_same_club_block

    def test_ignores_non_goalkeeper_rows(self):
        pool = pd.DataFrame({"role": ["P", "D"], "team_name": ["Inter", "Inter"]})
        ruleset = _ruleset(goalkeeper_block_size=1)
        result = compute_goalkeeper_club_supply(pool, ruleset)
        assert len(result) == 1
        assert result[0].goalkeeper_count == 1

    def test_sorted_by_count_ascending(self):
        pool = pd.DataFrame(
            {
                "role": ["P"] * 5,
                "team_name": ["Roma", "Roma", "Roma", "Lazio", "Milan"],
            }
        )
        ruleset = _ruleset(goalkeeper_block_size=3)
        result = compute_goalkeeper_club_supply(pool, ruleset)
        assert [c.team_name for c in result] == ["Lazio", "Milan", "Roma"]
