import pytest

from fantacalcio.ingest.admin_list_markdown import (
    AdminListParseError,
    parse_admin_list_markdown,
)

_SAMPLE = """\
**Lista 1 (1-20 Portieri)**

1. Roma 35
2. Inter 34

\\-

3. Milan 33

**Lista 2 (1-20 difensori)**

1. Dimarco 55
2. Wesley 45

**Lista 8 (1-20 Attaccanti)**

1. Martinez L. 74
"""


def test_parses_headers_and_rows(tmp_path):
    path = tmp_path / "liste.md"
    path.write_text(_SAMPLE, encoding="utf-8")
    staged = parse_admin_list_markdown(path)
    frame = staged.frame
    assert len(frame) == 6
    assert list(frame["list_number"]) == [1, 1, 1, 2, 2, 8]


def test_list_1_rows_are_team_entities(tmp_path):
    path = tmp_path / "liste.md"
    path.write_text(_SAMPLE, encoding="utf-8")
    staged = parse_admin_list_markdown(path)
    list1 = staged.frame[staged.frame["list_number"] == 1]
    assert (list1["entity_type"] == "team").all()
    assert (list1["role"] == "P").all()
    assert set(list1["display_name"]) == {"Roma", "Inter", "Milan"}


def test_other_lists_are_player_entities(tmp_path):
    path = tmp_path / "liste.md"
    path.write_text(_SAMPLE, encoding="utf-8")
    staged = parse_admin_list_markdown(path)
    others = staged.frame[staged.frame["list_number"] != 1]
    assert (others["entity_type"] == "player").all()


def test_role_inferred_from_header_label(tmp_path):
    path = tmp_path / "liste.md"
    path.write_text(_SAMPLE, encoding="utf-8")
    staged = parse_admin_list_markdown(path)
    frame = staged.frame
    assert frame[frame["list_number"] == 2]["role"].iloc[0] == "D"
    assert frame[frame["list_number"] == 8]["role"].iloc[0] == "A"


def test_separator_lines_ignored_and_rank_score_parsed(tmp_path):
    path = tmp_path / "liste.md"
    path.write_text(_SAMPLE, encoding="utf-8")
    staged = parse_admin_list_markdown(path)
    row = staged.frame.iloc[0]
    assert row["rank"] == 1
    assert row["display_name"] == "Roma"
    assert row["score"] == 35.0


def test_missing_file_raises(tmp_path):
    with pytest.raises(AdminListParseError, match="not found"):
        parse_admin_list_markdown(tmp_path / "missing.md")


def test_no_rows_raises(tmp_path):
    path = tmp_path / "empty.md"
    path.write_text("just some prose, no lists here\n", encoding="utf-8")
    with pytest.raises(AdminListParseError, match="No parseable rows"):
        parse_admin_list_markdown(path)


def test_source_hash_and_id_recorded(tmp_path):
    path = tmp_path / "liste.md"
    path.write_text(_SAMPLE, encoding="utf-8")
    staged = parse_admin_list_markdown(path)
    assert staged.source_id == "admin_list_markdown"
    assert len(staged.file_sha256) == 64
    assert (staged.frame["source_file_hash"] == staged.file_sha256).all()
