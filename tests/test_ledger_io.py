import csv

import pytest

from fantacalcio.domain import BudgetAdjustmentEvent, replay
from fantacalcio.fixtures import generate_demo_events
from fantacalcio.ledger_io import (
    LedgerIOError,
    event_from_dict,
    event_to_dict,
    export_assignments_csv,
    export_ledger_json,
    import_ledger_json,
)


def test_json_roundtrip_preserves_replay_result(ruleset, tmp_path):
    events = generate_demo_events(ruleset)
    path = tmp_path / "ledger.json"

    export_ledger_json(events, path)
    reimported = import_ledger_json(path)

    state_original = replay(ruleset, events)
    state_reimported = replay(ruleset, reimported)

    assert state_original.assigned_players == state_reimported.assigned_players
    for team_id in state_original.teams:
        assert state_original.teams[team_id].roster == state_reimported.teams[team_id].roster


def test_import_missing_file_raises(tmp_path):
    with pytest.raises(LedgerIOError, match="not found"):
        import_ledger_json(tmp_path / "missing.json")


def test_import_malformed_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(LedgerIOError, match="not valid JSON"):
        import_ledger_json(path)


def test_import_non_list_root_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"type": "assignment"}', encoding="utf-8")
    with pytest.raises(LedgerIOError, match="must be a list"):
        import_ledger_json(path)


def test_import_missing_field_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('[{"type": "assignment", "event_id": "e1"}]', encoding="utf-8")
    with pytest.raises(LedgerIOError, match="missing field"):
        import_ledger_json(path)


def test_csv_export_reflects_status(ruleset, tmp_path):
    events = generate_demo_events(ruleset)
    path = tmp_path / "assignments.csv"
    export_assignments_csv(events, path)

    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == len(events)  # demo fixture has no void/correction events
    assert all(row["status"] == "valid" for row in rows)
    assert {row["team_id"] for row in rows} == {f"team-{i:02d}" for i in range(1, ruleset.teams + 1)}


def _bonus_event() -> BudgetAdjustmentEvent:
    return BudgetAdjustmentEvent(
        event_id="b1", ts="2026-01-01T00:00:00Z", round_id="G1", team_id="team-01",
        amount=3, reason="custom_logo_bonus", author="admin",
    )


def test_budget_adjustment_event_dict_roundtrip():
    event = _bonus_event()
    d = event_to_dict(event)
    assert d["type"] == "budget_adjustment"
    reconstructed = event_from_dict(d)
    assert reconstructed == event


def test_budget_adjustment_event_json_roundtrip(tmp_path):
    events = [_bonus_event()]
    path = tmp_path / "ledger.json"
    export_ledger_json(events, path)
    reimported = import_ledger_json(path)
    assert reimported == events


def test_csv_export_skips_budget_adjustment_events(ruleset, tmp_path):
    events = generate_demo_events(ruleset) + [_bonus_event()]
    path = tmp_path / "assignments.csv"
    export_assignments_csv(events, path)
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(generate_demo_events(ruleset))  # bonus event excluded
