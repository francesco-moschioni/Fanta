import pandas as pd

from fantacalcio.auction.apply_official_admin_list import apply_official_admin_list

_POOL = pd.DataFrame(
    [
        {
            "player_code": 1,
            "role": "D",
            "team_name": "Inter",
            "list_state": "provisional",
            "round_pool": "G3_G4",
            "list_pool_name": "remaining_players",
        },
        {
            "player_code": 2,
            "role": "A",
            "team_name": "Roma",
            "list_state": "provisional",
            "round_pool": "G3_G4",
            "list_pool_name": "remaining_players",
        },
        {
            "player_code": 3,
            "role": "P",
            "team_name": "Atalanta",
            "list_state": "provisional",
            "round_pool": "G3_G4",
            "list_pool_name": "remaining_players",
        },
        {
            "player_code": 4,
            "role": "P",
            "team_name": "UnknownClub",
            "list_state": "provisional",
            "round_pool": "G3_G4",
            "list_pool_name": "remaining_players",
        },
        {
            "player_code": 5,
            "role": "D",
            "team_name": "Napoli",
            "list_state": "provisional",
            # This player was in the model's own top-60 (G1), but the admin
            # list doesn't cover them -- must stay exactly as-is (admin list
            # is "closed": it decides only for players it resolves).
            "round_pool": "G1",
            "list_pool_name": "defenders_top_1_60",
        },
    ]
)

_RESOLVED = pd.DataFrame([{"player_code": 1, "rank": 1, "score": 55.0, "role": "D"}])
_GK_BLOCKS = pd.DataFrame([{"team_name_canonical": "Atalanta", "score": 28.0}])


def test_matched_player_becomes_official_with_admin_rank_score(ruleset):
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS, ruleset)
    row = out[out["player_code"] == 1].iloc[0]
    assert row["list_state"] == "official"
    assert row["admin_rank"] == 1
    assert row["admin_score"] == 55.0


def test_admin_list_hard_overrides_round_pool(ruleset):
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS, ruleset)
    row = out[out["player_code"] == 1].iloc[0]
    assert row["round_pool"] == "G1"
    assert row["list_pool_name"] == "defenders_top_1_60"


def test_player_outside_admin_list_keeps_model_round_pool(ruleset):
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS, ruleset)
    row = out[out["player_code"] == 5].iloc[0]
    assert row["list_state"] == "provisional"
    assert row["round_pool"] == "G1"


def test_unmatched_player_stays_provisional(ruleset):
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS, ruleset)
    row = out[out["player_code"] == 2].iloc[0]
    assert row["list_state"] == "provisional"
    assert pd.isna(row["admin_rank"])
    assert row["round_pool"] == "G3_G4"


def test_goalkeeper_matched_by_team_gets_block_score_and_round_pool(ruleset):
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS, ruleset)
    row = out[out["player_code"] == 3].iloc[0]
    assert row["list_state"] == "official"
    assert row["admin_gk_block_score"] == 28.0
    assert pd.isna(row["admin_rank"])
    assert row["round_pool"] == "G1"
    assert row["list_pool_name"] == "goalkeeper_blocks"


def test_goalkeeper_unmatched_club_stays_provisional(ruleset):
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS, ruleset)
    row = out[out["player_code"] == 4].iloc[0]
    assert row["list_state"] == "provisional"
    assert pd.isna(row["admin_gk_block_score"])
    assert row["round_pool"] == "G3_G4"


def test_input_not_mutated(ruleset):
    original_state = _POOL["list_state"].copy()
    apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS, ruleset)
    assert (_POOL["list_state"] == original_state).all()


def test_empty_goalkeeper_blocks_leaves_players_untouched(ruleset):
    out = apply_official_admin_list(
        _POOL, _RESOLVED, pd.DataFrame(columns=["team_name_canonical", "score"]), ruleset
    )
    row = out[out["player_code"] == 3].iloc[0]
    assert row["list_state"] == "provisional"
