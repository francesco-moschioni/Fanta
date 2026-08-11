from fantacalcio.auction.roster_risk import compute_club_concentration


class TestComputeClubConcentration:
    def test_groups_by_club(self):
        pairs = [(1, "Inter"), (2, "Inter"), (3, "Milan")]
        result = compute_club_concentration(pairs)
        assert len(result) == 1  # Milan has only 1 player, excluded
        assert result[0].team_name == "Inter"
        assert result[0].player_count == 2
        assert result[0].player_codes == (1, 2)

    def test_single_player_clubs_excluded(self):
        pairs = [(1, "Inter"), (2, "Milan"), (3, "Roma")]
        assert compute_club_concentration(pairs) == []

    def test_sorted_by_count_descending(self):
        pairs = [(1, "Inter"), (2, "Inter"), (3, "Inter"), (4, "Milan"), (5, "Milan")]
        result = compute_club_concentration(pairs)
        assert [c.team_name for c in result] == ["Inter", "Milan"]
        assert [c.player_count for c in result] == [3, 2]

    def test_ties_sorted_alphabetically(self):
        pairs = [(1, "Roma"), (2, "Roma"), (3, "Milan"), (4, "Milan")]
        result = compute_club_concentration(pairs)
        assert [c.team_name for c in result] == ["Milan", "Roma"]

    def test_empty_input_returns_empty(self):
        assert compute_club_concentration([]) == []
