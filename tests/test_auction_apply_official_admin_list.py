import pandas as pd

from fantacalcio.auction.apply_official_admin_list import apply_official_admin_list

_POOL = pd.DataFrame(
    [
        {"player_code": 1, "role": "D", "team_name": "Inter", "list_state": "provisional"},
        {"player_code": 2, "role": "A", "team_name": "Roma", "list_state": "provisional"},
        {"player_code": 3, "role": "P", "team_name": "Atalanta", "list_state": "provisional"},
        {"player_code": 4, "role": "P", "team_name": "UnknownClub", "list_state": "provisional"},
    ]
)

_RESOLVED = pd.DataFrame([{"player_code": 1, "rank": 1, "score": 55.0}])
_GK_BLOCKS = pd.DataFrame([{"team_name_canonical": "Atalanta", "score": 28.0}])


def test_matched_player_becomes_official_with_admin_rank_score():
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS)
    row = out[out["player_code"] == 1].iloc[0]
    assert row["list_state"] == "official"
    assert row["admin_rank"] == 1
    assert row["admin_score"] == 55.0


def test_unmatched_player_stays_provisional():
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS)
    row = out[out["player_code"] == 2].iloc[0]
    assert row["list_state"] == "provisional"
    assert pd.isna(row["admin_rank"])


def test_goalkeeper_matched_by_team_gets_block_score_not_admin_rank():
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS)
    row = out[out["player_code"] == 3].iloc[0]
    assert row["list_state"] == "official"
    assert row["admin_gk_block_score"] == 28.0
    assert pd.isna(row["admin_rank"])


def test_goalkeeper_unmatched_club_stays_provisional():
    out = apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS)
    row = out[out["player_code"] == 4].iloc[0]
    assert row["list_state"] == "provisional"
    assert pd.isna(row["admin_gk_block_score"])


def test_input_not_mutated():
    original_state = _POOL["list_state"].copy()
    apply_official_admin_list(_POOL, _RESOLVED, _GK_BLOCKS)
    assert (_POOL["list_state"] == original_state).all()


def test_empty_goalkeeper_blocks_leaves_players_untouched():
    out = apply_official_admin_list(_POOL, _RESOLVED, pd.DataFrame(columns=["team_name_canonical", "score"]))
    row = out[out["player_code"] == 3].iloc[0]
    assert row["list_state"] == "provisional"
