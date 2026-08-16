from fantacalcio.identity.player_name_resolver import (
    AnchorPlayer,
    resolve_against_anchor,
)

_ANCHOR = [
    AnchorPlayer(player_code=4431, display_name="Carnesecchi", role="P", team_name="Atalanta"),
    AnchorPlayer(player_code=1001, display_name="Dimarco", role="D", team_name="Inter"),
    AnchorPlayer(player_code=1002, display_name="Esposito F.P.", role="A", team_name="Inter"),
    AnchorPlayer(player_code=1003, display_name="Esposito Se.", role="A", team_name="Cagliari"),
]


def test_exact_normalized_match_auto_confirmed():
    result = resolve_against_anchor(_ANCHOR, [("Dimarco", "D")])
    assert len(result.crosswalk) == 1
    assert result.crosswalk[0].player_code == 1001
    assert result.crosswalk[0].match_method == "exact_normalized"
    assert not result.review_queue


def test_role_mismatch_goes_to_review_not_forced():
    result = resolve_against_anchor(_ANCHOR, [("Dimarco", "A")])
    assert not result.crosswalk
    assert len(result.review_queue) == 1


def test_ambiguous_homonyms_go_to_review_never_force_matched():
    # A name close to both Esposito variants but role known only as "A" is fine here
    # since we test unresolved input without disambiguating detail.
    result = resolve_against_anchor(_ANCHOR, [("Esposito", "A")])
    assert not result.crosswalk
    assert len(result.review_queue) == 1
    assert "Ambiguous" in result.review_queue[0].reason or result.review_queue[0].confidence < 1.0


def test_unmatched_name_goes_to_review_queue():
    result = resolve_against_anchor(_ANCHOR, [("Totally Unknown Player", "D")])
    assert not result.crosswalk
    assert len(result.review_queue) == 1
    assert result.review_queue[0].matched_display_name == "Totally Unknown Player"


def test_fuzzy_high_confidence_auto_accepted():
    result = resolve_against_anchor(_ANCHOR, [("Carnesechi", "P")])
    assert len(result.crosswalk) == 1
    assert result.crosswalk[0].player_code == 4431
    assert result.crosswalk[0].match_method == "fuzzy_auto"


def test_never_matches_across_roles_even_if_name_identical():
    anchors = _ANCHOR + [
        AnchorPlayer(player_code=2001, display_name="Sameguy", role="D", team_name="Roma"),
        AnchorPlayer(player_code=2002, display_name="Sameguy", role="A", team_name="Milan"),
    ]
    result = resolve_against_anchor(anchors, [("Sameguy", "D")])
    assert len(result.crosswalk) == 1
    assert result.crosswalk[0].player_code == 2001
