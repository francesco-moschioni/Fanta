from datetime import datetime

import pandas as pd
import pytest

from fantacalcio.persistence.player_table import (
    REQUIRED_COLUMNS,
    build_player_table,
    connect,
    distinct_values,
    effective_quotazione,
    get_build_meta,
    get_player,
    search_players,
    search_players_fuzzy,
)


def _write_source_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def _row(player_code, display_name="Player", role="A", team_name="Roma", **kwargs):
    defaults = {c: None for c in REQUIRED_COLUMNS}
    defaults.update(
        player_code=player_code, display_name=display_name, role=role, team_name=team_name,
        quotazione_asta=10, sim_mean=6.5, sim_median=6.0, sim_p10=5.0, sim_p90=8.0,
        player_games_in_pool=50, used_role_pool_only=False, replacement_level=5.5,
        var_mean=1.0, var_p10=-0.5, var_p90=2.5, data_quality_tier="full_history",
        round_pool="G2", list_pool_name="forwards_top_1_20", list_state="provisional",
    )
    defaults.update(kwargs)
    return defaults


class TestBuildPlayerTable:
    def test_raises_if_source_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            build_player_table(source_csv=tmp_path / "missing.csv", db_path=tmp_path / "db.duckdb")

    def test_raises_if_required_column_missing(self, tmp_path):
        csv_path = tmp_path / "source.csv"
        pd.DataFrame([{"player_code": 1}]).to_csv(csv_path, index=False)
        with pytest.raises(ValueError, match="missing required columns"):
            build_player_table(source_csv=csv_path, db_path=tmp_path / "db.duckdb")

    def test_build_records_provenance(self, tmp_path):
        csv_path = tmp_path / "source.csv"
        _write_source_csv(csv_path, [_row(1), _row(2)])
        db_path = tmp_path / "db.duckdb"
        result = build_player_table(source_csv=csv_path, db_path=db_path)
        assert result.n_players == 2
        assert db_path.is_file()

        conn = connect(db_path)
        meta = get_build_meta(conn)
        assert meta["source_path"] == str(csv_path)
        assert meta["n_players"] == "2"
        assert meta["source_sha256"] == result.source_sha256
        assert meta["source_generated_at"] == result.source_generated_at
        datetime.fromisoformat(meta["source_generated_at"])  # parses as a real timestamp


class TestSearchAndQuery:
    def _built_conn(self, tmp_path):
        csv_path = tmp_path / "source.csv"
        _write_source_csv(
            csv_path,
            [
                _row(1, display_name="Lautaro Martinez", role="A", team_name="Inter", round_pool="G2", data_quality_tier="full_history"),
                _row(2, display_name="Leao", role="A", team_name="Milan", round_pool="G2", data_quality_tier="full_history"),
                _row(3, display_name="Rookie X", role="D", team_name="Como", round_pool="G3_G4", data_quality_tier="no_history_new_team"),
            ],
        )
        db_path = tmp_path / "db.duckdb"
        build_player_table(source_csv=csv_path, db_path=db_path)
        return connect(db_path)

    def test_search_by_name_case_insensitive(self, tmp_path):
        conn = self._built_conn(tmp_path)
        result = search_players(conn, name_query="leao")
        assert list(result["display_name"]) == ["Leao"]

    def test_search_by_role(self, tmp_path):
        conn = self._built_conn(tmp_path)
        result = search_players(conn, role="D")
        assert list(result["display_name"]) == ["Rookie X"]

    def test_search_combines_filters_with_and(self, tmp_path):
        conn = self._built_conn(tmp_path)
        result = search_players(conn, role="A", team_name="Milan")
        assert list(result["display_name"]) == ["Leao"]

    def test_search_no_filters_returns_all_sorted_by_var_desc(self, tmp_path):
        conn = self._built_conn(tmp_path)
        result = search_players(conn)
        assert len(result) == 3
        assert list(result["var_mean"]) == sorted(result["var_mean"], reverse=True)

    def test_get_player_found(self, tmp_path):
        conn = self._built_conn(tmp_path)
        player = get_player(conn, 2)
        assert player["display_name"] == "Leao"

    def test_get_player_not_found_returns_none(self, tmp_path):
        conn = self._built_conn(tmp_path)
        assert get_player(conn, 999) is None

    def test_distinct_values(self, tmp_path):
        conn = self._built_conn(tmp_path)
        assert set(distinct_values(conn, "role")) == {"A", "D"}

    def test_distinct_values_rejects_unknown_column(self, tmp_path):
        conn = self._built_conn(tmp_path)
        with pytest.raises(ValueError, match="not a filterable column"):
            distinct_values(conn, "nonexistent; DROP TABLE players")


class TestEffectiveQuotazione:
    def test_falls_back_to_fantacalcio_quotazione_when_no_admin_score(self):
        row = pd.Series({"quotazione_asta": 12, "admin_score": None})
        assert effective_quotazione(row) == 12

    def test_falls_back_when_admin_score_is_nan(self):
        row = pd.Series({"quotazione_asta": 12, "admin_score": float("nan")})
        assert effective_quotazione(row) == 12

    def test_uses_admin_score_when_present_even_if_lower(self):
        # The admin's own published score is the real-auction source of
        # truth once a player is official -- it replaces, never averages
        # with, the fantacalcio listone quotation.
        row = pd.Series({"quotazione_asta": 32, "admin_score": 55})
        assert effective_quotazione(row) == 55

    def test_missing_admin_score_column_entirely_falls_back(self):
        row = pd.Series({"quotazione_asta": 12})
        assert effective_quotazione(row) == 12


class TestSearchPlayersFuzzy:
    def _built_conn(self, tmp_path):
        csv_path = tmp_path / "source.csv"
        _write_source_csv(
            csv_path,
            [
                _row(1, display_name="Dovbyk", role="A", team_name="Roma", round_pool="G2"),
                _row(2, display_name="Leao", role="A", team_name="Milan", round_pool="G2"),
                _row(3, display_name="Rookie X", role="D", team_name="Como", round_pool="G3_G4"),
            ],
        )
        db_path = tmp_path / "db.duckdb"
        build_player_table(source_csv=csv_path, db_path=db_path)
        return connect(db_path)

    def test_finds_close_typo(self, tmp_path):
        conn = self._built_conn(tmp_path)
        result = search_players_fuzzy(conn, "Dobvyk")
        assert "Dovbyk" in list(result["display_name"])

    def test_ranked_by_similarity_descending(self, tmp_path):
        conn = self._built_conn(tmp_path)
        result = search_players_fuzzy(conn, "Dovbyk")
        assert result.iloc[0]["display_name"] == "Dovbyk"

    def test_completely_unrelated_query_returns_nothing(self, tmp_path):
        conn = self._built_conn(tmp_path)
        result = search_players_fuzzy(conn, "zzzzxxxqqqq")
        assert result.empty

    def test_respects_other_filters(self, tmp_path):
        conn = self._built_conn(tmp_path)
        result = search_players_fuzzy(conn, "Dobvyk", role="D")
        assert result.empty

    def test_no_helper_column_leaked_in_output(self, tmp_path):
        conn = self._built_conn(tmp_path)
        result = search_players_fuzzy(conn, "Dobvyk")
        assert "_fuzzy_ratio" not in result.columns
