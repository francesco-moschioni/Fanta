import pytest

from fantacalcio.persistence.team_labels_store import (
    connect,
    display_name,
    get_all_labels,
    get_label,
    load_labels_config,
    seed_missing_labels,
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


class TestLoadLabelsConfig:
    def test_loads_mapping_from_yaml(self, tmp_path):
        path = tmp_path / "team_labels.v1.yaml"
        path.write_text("team_01: Garlascow Rangers\nteam_02: Scooby-diouf\n", encoding="utf-8")
        assert load_labels_config(path) == {"team_01": "Garlascow Rangers", "team_02": "Scooby-diouf"}

    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert load_labels_config(tmp_path / "missing.yaml") == {}

    def test_non_mapping_yaml_raises(self, tmp_path):
        path = tmp_path / "team_labels.v1.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must contain a mapping"):
            load_labels_config(path)


class TestSeedMissingLabels:
    def test_seeds_empty_database(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        seeded = seed_missing_labels(conn, {"team_01": "Garlascow Rangers", "team_02": "Scooby-diouf"})
        assert set(seeded) == {"team_01", "team_02"}
        assert get_all_labels(conn) == {"team_01": "Garlascow Rangers", "team_02": "Scooby-diouf"}

    def test_never_overwrites_an_existing_label(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        set_label(conn, "team_01", "Nome scelto dall'utente")
        seeded = seed_missing_labels(conn, {"team_01": "Garlascow Rangers"})
        assert seeded == []
        assert get_label(conn, "team_01") == "Nome scelto dall'utente"

    def test_seeds_only_the_missing_ones(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        set_label(conn, "team_01", "Gia' presente")
        seeded = seed_missing_labels(conn, {"team_01": "Garlascow Rangers", "team_02": "Scooby-diouf"})
        assert seeded == ["team_02"]
        assert get_all_labels(conn) == {"team_01": "Gia' presente", "team_02": "Scooby-diouf"}

    def test_idempotent_across_repeated_calls(self, tmp_path):
        conn = connect(tmp_path / "db.sqlite3")
        mapping = {"team_01": "Garlascow Rangers"}
        seed_missing_labels(conn, mapping)
        second_run = seed_missing_labels(conn, mapping)
        assert second_run == []
        assert get_label(conn, "team_01") == "Garlascow Rangers"
