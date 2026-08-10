import pytest

from fantacalcio.identity.teams import normalize_name, resolve_against_anchor


def test_normalize_strips_legal_form_noise_and_case():
    assert normalize_name("Bologna FC 1909") == "bologna"
    assert normalize_name("US Sassuolo Calcio") == "sassuolo"
    assert normalize_name("AC Milan") == "milan"


def test_normalize_strips_accents():
    assert normalize_name("Atalético") == normalize_name("Ataletico")


def test_exact_normalized_match():
    result = resolve_against_anchor(
        anchor_names=["Milan", "Napoli"],
        anchor_source_id="anchor",
        other_names=["AC Milan", "SSC Napoli"],
        other_source_id="other",
    )
    assert len(result.crosswalk) == 2
    assert not result.review_queue
    methods = {e.matched_name: e.match_method for e in result.crosswalk}
    assert methods["AC Milan"] == "exact_normalized"


def test_low_confidence_goes_to_review_queue_not_forced():
    result = resolve_against_anchor(
        anchor_names=["Inter"],
        anchor_source_id="anchor",
        other_names=["FC Internazionale Milano"],
        other_source_id="other",
    )
    assert not result.crosswalk
    assert len(result.review_queue) == 1
    entry = result.review_queue[0]
    assert entry.matched_name == "FC Internazionale Milano"
    assert entry.best_candidate_team_id == "inter"
    assert entry.confidence < 0.9


def test_fuzzy_match_above_threshold_is_auto_accepted():
    result = resolve_against_anchor(
        anchor_names=["Fiorentina"],
        anchor_source_id="anchor",
        other_names=["Fiorentin"],  # one-character typo, ratio should clear 0.9
        other_source_id="other",
        auto_accept_threshold=0.9,
    )
    assert len(result.crosswalk) == 1
    assert result.crosswalk[0].match_method == "fuzzy_auto"
    assert not result.review_queue


def test_colliding_anchor_names_raise():
    with pytest.raises(ValueError, match="collide"):
        resolve_against_anchor(
            anchor_names=["AC Milan", "Milan"],  # normalize to the same token, different team_id
            anchor_source_id="anchor",
            other_names=[],
            other_source_id="other",
        )


def test_duplicate_other_names_are_deduplicated():
    result = resolve_against_anchor(
        anchor_names=["Roma"],
        anchor_source_id="anchor",
        other_names=["AS Roma", "AS Roma", "AS Roma"],
        other_source_id="other",
    )
    total = len(result.crosswalk) + len(result.review_queue)
    assert total == 1
