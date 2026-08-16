from fantacalcio.persistence.locks_store import add_lock, connect, is_locked, list_locks, remove_lock


class TestLocksStore:
    def test_add_and_list_lock(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_lock(conn, "team_01", 123, "A", note="target attacker")
        locks = list_locks(conn, "team_01")
        assert len(locks) == 1
        assert locks[0].player_code == 123
        assert locks[0].role == "A"
        assert locks[0].note == "target attacker"

    def test_add_lock_is_idempotent_per_player(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_lock(conn, "team_01", 123, "A")
        add_lock(conn, "team_01", 123, "A", note="updated note")
        locks = list_locks(conn, "team_01")
        assert len(locks) == 1
        assert locks[0].note == "updated note"

    def test_remove_lock(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_lock(conn, "team_01", 123, "A")
        remove_lock(conn, "team_01", 123)
        assert list_locks(conn, "team_01") == []

    def test_is_locked(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        assert not is_locked(conn, "team_01", 123)
        add_lock(conn, "team_01", 123, "A")
        assert is_locked(conn, "team_01", 123)

    def test_locks_scoped_per_team(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_lock(conn, "team_01", 123, "A")
        add_lock(conn, "team_02", 456, "D")
        assert [lock.player_code for lock in list_locks(conn, "team_01")] == [123]
        assert [lock.player_code for lock in list_locks(conn, "team_02")] == [456]

    def test_list_locks_no_team_filter_returns_all(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_lock(conn, "team_01", 123, "A")
        add_lock(conn, "team_02", 456, "D")
        assert len(list_locks(conn)) == 2

    def test_reopening_db_preserves_locks(self, tmp_path):
        db_path = tmp_path / "db.sqlite3"
        conn1 = connect(db_path)
        add_lock(conn1, "team_01", 123, "A")
        conn1.close()
        conn2 = connect(db_path)
        assert len(list_locks(conn2, "team_01")) == 1

    def test_planned_price_defaults_to_none(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_lock(conn, "team_01", 123, "A")
        assert list_locks(conn, "team_01")[0].planned_price is None

    def test_planned_price_stored_and_updatable(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        add_lock(conn, "team_01", 123, "A", planned_price=45)
        assert list_locks(conn, "team_01")[0].planned_price == 45
        add_lock(conn, "team_01", 123, "A", planned_price=60)
        assert list_locks(conn, "team_01")[0].planned_price == 60

    def test_planned_price_column_migrates_onto_pre_existing_db(self, tmp_path):
        # Simulate a database created before planned_price existed: create the
        # table with the old schema directly, then connect() must add the
        # column without losing existing rows.
        import sqlite3

        db_path = tmp_path / "db.sqlite3"
        raw = sqlite3.connect(str(db_path))
        raw.execute(
            "CREATE TABLE locks (team_id TEXT, player_code INTEGER, role TEXT, "
            "note TEXT DEFAULT '', locked_at TEXT, PRIMARY KEY (team_id, player_code))"
        )
        raw.execute(
            "INSERT INTO locks (team_id, player_code, role, note, locked_at) VALUES (?, ?, ?, ?, ?)",
            ("team_01", 123, "A", "", "2026-01-01T00:00:00Z"),
        )
        raw.commit()
        raw.close()

        conn = connect(db_path)
        locks = list_locks(conn, "team_01")
        assert len(locks) == 1
        assert locks[0].planned_price is None
