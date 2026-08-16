import pandas as pd
import pytest

from fantacalcio.identity.admin_official_list import (
    CONFIRMED_NEW_PLAYERS,
    MANUAL_VERIFIED_CROSSWALK,
    build_curated_admin_list,
    write_curated_csvs,
)
from fantacalcio.ingest.admin_list_markdown import parse_admin_list_markdown

_MD = """\
**Lista 1 (1-20 Portieri)**

1. Roma 35
2. UnknownClub 10

**Lista 2 (1-20 difensori)**

1. Dimarco 55
2. Spence 25

**Lista 8 (1-20 Attaccanti)**

1. Martinez L. 74
"""

_ANCHOR = pd.DataFrame(
    [
        {"player_code": 1, "display_name": "Dimarco", "role": "D", "team_name": "Inter"},
        {"player_code": 2, "display_name": "Martinez L.", "role": "A", "team_name": "Inter"},
    ]
)
_TEAM_NAMES = ["Roma", "Inter", "Milan"]


def _staged(tmp_path):
    path = tmp_path / "liste.md"
    path.write_text(_MD, encoding="utf-8")
    return parse_admin_list_markdown(path)


def test_confirmed_new_players_kept_without_player_code(tmp_path):
    curated = build_curated_admin_list(_staged(tmp_path), _ANCHOR, _TEAM_NAMES)
    assert "Spence" in set(curated.new_players["display_name"])
    assert "player_code" not in curated.new_players.columns
    assert (curated.new_players["identity_status"] == "new_player_pending_code").all()


def test_resolved_players_get_player_code_and_official_state(tmp_path):
    curated = build_curated_admin_list(_staged(tmp_path), _ANCHOR, _TEAM_NAMES)
    names = set(curated.resolved_players["display_name"])
    assert {"Dimarco", "Martinez L."} <= names
    assert (curated.resolved_players["list_state"] == "official").all()
    assert curated.resolved_players["player_code"].dtype.kind in "iu"


def test_goalkeeper_blocks_matched_against_team_identity(tmp_path):
    curated = build_curated_admin_list(_staged(tmp_path), _ANCHOR, _TEAM_NAMES)
    assert list(curated.goalkeeper_blocks["team_name_canonical"]) == ["Roma"]
    assert (curated.goalkeeper_blocks["list_state"] == "official").all()


def test_unmatched_team_goes_to_its_own_queue_not_silently_dropped(tmp_path):
    curated = build_curated_admin_list(_staged(tmp_path), _ANCHOR, _TEAM_NAMES)
    assert list(curated.unmatched_teams["display_name"]) == ["UnknownClub"]


def test_no_row_is_lost_across_the_split(tmp_path):
    curated = build_curated_admin_list(_staged(tmp_path), _ANCHOR, _TEAM_NAMES)
    total_players_in = len(_staged(tmp_path).frame.query("entity_type == 'player'"))
    total_players_out = len(curated.resolved_players) + len(curated.new_players) + len(curated.review_queue)
    assert total_players_in == total_players_out

    total_teams_in = len(_staged(tmp_path).frame.query("entity_type == 'team'"))
    total_teams_out = len(curated.goalkeeper_blocks) + len(curated.unmatched_teams)
    assert total_teams_in == total_teams_out


def test_manual_verified_crosswalk_resolves_role_mismatch_and_near_miss_names(tmp_path):
    # "Isaksen" appears in the admin list as role A, but the anchor only knows
    # him under role C -- the automatic resolver would refuse this (role
    # mismatch is a deliberate hard stop), so it must come from the manual
    # crosswalk instead.
    md = """\
**Lista 9 (21-40 Attaccanti)**

1. Isaksen 20
"""
    path = tmp_path / "liste.md"
    path.write_text(md, encoding="utf-8")
    anchor = pd.DataFrame(
        [{"player_code": 6398, "display_name": "Isaksen", "role": "C", "team_name": "Lazio"}]
    )
    assert ("Isaksen", "A") in MANUAL_VERIFIED_CROSSWALK
    curated = build_curated_admin_list(parse_admin_list_markdown(path), anchor, _TEAM_NAMES)
    assert list(curated.resolved_players["player_code"]) == [6398]
    assert curated.new_players.empty
    assert curated.review_queue.empty


def test_write_curated_csvs_creates_all_files(tmp_path):
    curated = build_curated_admin_list(_staged(tmp_path), _ANCHOR, _TEAM_NAMES)
    paths = write_curated_csvs(curated, curated_root=tmp_path / "curated")
    for key in ("resolved_players", "new_players", "review_queue", "goalkeeper_blocks", "unmatched_teams", "_meta"):
        assert paths[key].is_file()
