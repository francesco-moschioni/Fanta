import textwrap
from pathlib import Path

import pytest

from fantacalcio.config import ConfigError, evaluate_budget_expr, load_ruleset


def test_loads_real_ruleset(ruleset):
    assert ruleset.ruleset_id == "fantacalcio-asta-2026-v1"
    assert ruleset.teams == 20
    assert [r.id for r in ruleset.rounds] == ["G1", "G2", "G3", "G4"]
    assert ruleset.rounds[0].mode == "sealed_bid_list"
    assert ruleset.rounds[2].mode == "sealed_bid_free"


def test_roster_composition_sums_to_total(ruleset):
    r = ruleset.roster
    assert r.goalkeeper_block_size + r.defenders + r.midfielders + r.forwards == r.total_players


def test_resolved_fields_are_confirmed(ruleset):
    # Resolved 2026-08-11 by the admin's auction-rules recap (ADR-2026-013).
    for key in ("sealed_bid_preference_count", "automatic_fallback_assignment"):
        assert ruleset.is_field_confirmed(key)


def test_still_uncertain_fields_are_unconfirmed(ruleset):
    # These must stay null until an approved ADR fills them in; a passing test here
    # would mean someone silently guessed a value instead of recording a decision.
    for key in ("sealed_bid_tie_breaker", "minimum_bid_source"):
        assert not ruleset.is_field_confirmed(key)


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "ruleset.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _minimal_valid_yaml(**overrides: str) -> str:
    base = """\
    schema_version: 1
    ruleset_id: test
    status: working_current
    effective_from: 2026-01-01
    league:
      teams: 2
      roster:
        total_players: 4
        goalkeeper_block:
          players: 1
          same_club: true
        defenders: 1
        midfielders: 1
        forwards: 1
        forwards_fallback_if_supply_insufficient: 1
      formations:
        - "3-4-3"
    auction:
      list_states: [unknown, provisional, official]
      official_pool_authority: admin_import
      model_ranking_is_official_pool: false
      rounds:
        - id: G1
          order: 1
          mode: sealed_bid_list
          budget_increment: 100
          budget_available: "100"
          pools: [pool_a]
        - id: G2
          order: 2
          mode: sealed_bid_free
          budget_increment: 10
          budget_available: "remaining_G1 + 10"
          pools: [pool_b]
    runtime_invariants:
      require_versioned_config: true
    """
    return textwrap.dedent(base)


def test_missing_required_field_raises(tmp_path):
    yaml_text = _minimal_valid_yaml().replace("ruleset_id: test\n", "")
    path = _write(tmp_path, yaml_text)
    with pytest.raises(ConfigError, match="ruleset_id"):
        load_ruleset(path)


def test_roster_mismatch_raises(tmp_path):
    yaml_text = _minimal_valid_yaml().replace("total_players: 4", "total_players: 5")
    path = _write(tmp_path, yaml_text)
    with pytest.raises(ConfigError, match="does not sum to total_players"):
        load_ruleset(path)


def test_non_contiguous_round_order_raises(tmp_path):
    yaml_text = _minimal_valid_yaml().replace("order: 2", "order: 3")
    path = _write(tmp_path, yaml_text)
    with pytest.raises(ConfigError, match="contiguous"):
        load_ruleset(path)


def test_forward_budget_reference_raises(tmp_path):
    # G1 (the first round) may not reference a later round's remaining budget.
    yaml_text = _minimal_valid_yaml().replace(
        'budget_available: "100"', 'budget_available: "remaining_G2 + 5"'
    )
    path = _write(tmp_path, yaml_text)
    with pytest.raises(ConfigError, match="not an earlier round"):
        load_ruleset(path)


def test_unsupported_mode_raises(tmp_path):
    yaml_text = _minimal_valid_yaml().replace("mode: sealed_bid_free", "mode: dutch_auction")
    path = _write(tmp_path, yaml_text)
    with pytest.raises(ConfigError, match="unsupported mode"):
        load_ruleset(path)


def test_bad_list_states_raises(tmp_path):
    yaml_text = _minimal_valid_yaml().replace(
        "list_states: [unknown, provisional, official]", "list_states: [unknown, official]"
    )
    path = _write(tmp_path, yaml_text)
    with pytest.raises(ConfigError, match="list_states"):
        load_ruleset(path)


def test_file_not_found_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_ruleset(tmp_path / "does_not_exist.yaml")


class TestEvaluateBudgetExpr:
    def test_plain_integer(self):
        assert evaluate_budget_expr("200", {}) == 200

    def test_reference_plus_integer(self):
        assert evaluate_budget_expr("remaining_G1 + 100", {"G1": 50}) == 150

    def test_unknown_reference_raises(self):
        with pytest.raises(ConfigError, match="no recorded remaining budget"):
            evaluate_budget_expr("remaining_G9", {"G1": 50})

    def test_malformed_expression_raises(self):
        with pytest.raises(ConfigError):
            evaluate_budget_expr("100 * 2", {})

    def test_trailing_operator_raises(self):
        with pytest.raises(ConfigError, match="ends with an operator"):
            evaluate_budget_expr("100 +", {})

    def test_double_operand_raises(self):
        with pytest.raises(ConfigError, match="Unexpected token"):
            evaluate_budget_expr("100 100", {})
