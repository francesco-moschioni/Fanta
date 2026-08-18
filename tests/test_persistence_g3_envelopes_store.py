from fantacalcio.persistence.g3_envelopes_store import connect, list_picks, remove_pick, save_pick


class TestG3EnvelopesStore:
    def test_save_and_list_pick(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", 123, "C", 25)
        picks = list_picks(conn, "team_01")
        assert len(picks) == 1
        assert picks[0].player_code == 123
        assert picks[0].role == "C"
        assert picks[0].bid_amount == 25

    def test_save_pick_is_idempotent_per_player(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", 123, "C", 20)
        save_pick(conn, "team_01", 123, "C", 30)
        picks = list_picks(conn, "team_01")
        assert len(picks) == 1
        assert picks[0].bid_amount == 30

    def test_remove_pick(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", 123, "C", 20)
        remove_pick(conn, "team_01", 123)
        assert list_picks(conn, "team_01") == []

    def test_picks_scoped_per_team(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", 123, "C", 20)
        save_pick(conn, "team_02", 456, "A", 15)
        assert [p.player_code for p in list_picks(conn, "team_01")] == [123]
        assert [p.player_code for p in list_picks(conn, "team_02")] == [456]
