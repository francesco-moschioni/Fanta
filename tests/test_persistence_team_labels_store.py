from fantacalcio.persistence.team_labels_store import (
    connect,
    display_name,
    get_all_labels,
    get_label,
    set_label,
)


class TestTeamLabelsStore:
    def test_set_and_get_label(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        set_label(conn, "team_01", "I Bocconiani")
        assert get_label(conn, "team_01") == "I Bocconiani"

    def test_unset_label_returns_none(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        assert get_label(conn, "team_01") is None

    def test_set_label_overwrites(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        set_label(conn, "team_01", "Vecchio nome")
        set_label(conn, "team_01", "Nuovo nome")
        assert get_label(conn, "team_01") == "Nuovo nome"

    def test_get_all_labels(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        set_label(conn, "team_01", "A")
        set_label(conn, "team_02", "B")
        assert get_all_labels(conn) == {"team_01": "A", "team_02": "B"}

    def test_reopening_db_preserves_labels(self, tmp_path):
        db_path = tmp_path / "db.sqlite3"
        conn1 = connect(db_path)
        set_label(conn1, "team_01", "A")
        conn1.close()
        conn2 = connect(db_path)
        assert get_label(conn2, "team_01") == "A"


class TestDisplayName:
    def test_labeled_team_shows_label_and_id(self):
        assert display_name("team_01", {"team_01": "I Bocconiani"}) == "I Bocconiani (team_01)"

    def test_unlabeled_team_shows_id_only(self):
        assert display_name("team_02", {"team_01": "I Bocconiani"}) == "team_02"
