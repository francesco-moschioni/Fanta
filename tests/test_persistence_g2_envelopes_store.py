from fantacalcio.persistence.g2_envelopes_store import connect, list_picks, remove_pick, save_pick


class TestG2EnvelopesStore:
    def test_save_and_list_pick(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", "midfielders_top_1_20", 123, "C", 1, 20)
        picks = list_picks(conn, "team_01")
        assert len(picks) == 1
        assert picks[0].player_code == 123
        assert picks[0].preference_rank == 1
        assert picks[0].bid_amount == 20

    def test_save_pick_is_idempotent_per_player_per_band(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", "midfielders_top_1_20", 123, "C", 1, 20)
        save_pick(conn, "team_01", "midfielders_top_1_20", 123, "C", 2, 25)
        picks = list_picks(conn, "team_01", "midfielders_top_1_20")
        assert len(picks) == 1
        assert picks[0].preference_rank == 2
        assert picks[0].bid_amount == 25

    def test_remove_pick(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", "midfielders_top_1_20", 123, "C", 1, 20)
        remove_pick(conn, "team_01", "midfielders_top_1_20", 123)
        assert list_picks(conn, "team_01") == []

    def test_picks_scoped_per_team(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", "midfielders_top_1_20", 123, "C", 1, 20)
        save_pick(conn, "team_02", "forwards_top_1_20", 456, "A", 1, 15)
        assert [p.player_code for p in list_picks(conn, "team_01")] == [123]
        assert [p.player_code for p in list_picks(conn, "team_02")] == [456]

    def test_list_picks_filtered_by_band(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", "midfielders_top_1_20", 1, "C", 1, 20)
        save_pick(conn, "team_01", "forwards_top_1_20", 2, "A", 1, 15)
        assert [p.player_code for p in list_picks(conn, "team_01", "midfielders_top_1_20")] == [1]

    def test_list_picks_ordered_by_preference_rank(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        save_pick(conn, "team_01", "midfielders_top_1_20", 3, "C", 3, 10)
        save_pick(conn, "team_01", "midfielders_top_1_20", 1, "C", 1, 30)
        save_pick(conn, "team_01", "midfielders_top_1_20", 2, "C", 2, 20)
        ranks = [p.preference_rank for p in list_picks(conn, "team_01", "midfielders_top_1_20")]
        assert ranks == [1, 2, 3]
