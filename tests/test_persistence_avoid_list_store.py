from fantacalcio.persistence.avoid_list_store import add_avoid, connect, is_avoided, list_avoided, remove_avoid


class TestAvoidListStore:
    def test_add_and_list_avoid(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_avoid(conn, "team_01", 123, "A", reason="infortunio lungo")
        avoided = list_avoided(conn, "team_01")
        assert len(avoided) == 1
        assert avoided[0].player_code == 123
        assert avoided[0].role == "A"
        assert avoided[0].reason == "infortunio lungo"

    def test_add_avoid_is_idempotent_per_player(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_avoid(conn, "team_01", 123, "A")
        add_avoid(conn, "team_01", 123, "A", reason="updated reason")
        avoided = list_avoided(conn, "team_01")
        assert len(avoided) == 1
        assert avoided[0].reason == "updated reason"

    def test_remove_avoid(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_avoid(conn, "team_01", 123, "A")
        remove_avoid(conn, "team_01", 123)
        assert list_avoided(conn, "team_01") == []

    def test_is_avoided(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        assert not is_avoided(conn, "team_01", 123)
        add_avoid(conn, "team_01", 123, "A")
        assert is_avoided(conn, "team_01", 123)

    def test_avoid_list_scoped_per_team(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_avoid(conn, "team_01", 123, "A")
        add_avoid(conn, "team_02", 456, "D")
        assert [a.player_code for a in list_avoided(conn, "team_01")] == [123]
        assert [a.player_code for a in list_avoided(conn, "team_02")] == [456]

    def test_list_avoided_no_team_filter_returns_all(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_avoid(conn, "team_01", 123, "A")
        add_avoid(conn, "team_02", 456, "D")
        assert len(list_avoided(conn)) == 2

    def test_reopening_db_preserves_avoid_list(self, tmp_path):
        db_path = tmp_path / "db.sqlite3"
        conn1 = connect(db_path)
        add_avoid(conn1, "team_01", 123, "A")
        conn1.close()
        conn2 = connect(db_path)
        assert len(list_avoided(conn2, "team_01")) == 1
