from pathlib import Path

import pytest

from fantacalcio.config import load_ruleset
from fantacalcio.lineup.formations import (
    Formation,
    FormationError,
    load_formations,
    parse_formation,
)

RULESET = load_ruleset(Path("config/auction_rules.v1.yaml"))

EIGHT = ["3-4-3", "3-5-2", "4-5-1", "4-4-2", "4-3-3", "5-4-1", "5-3-2", "5-2-3"]


@pytest.mark.parametrize("s", EIGHT)
def test_parse_accepts_the_eight(s):
    f = parse_formation(s)
    assert isinstance(f, Formation)
    assert f.goalkeepers == 1
    assert f.defenders + f.midfielders + f.forwards == 10
    assert f.name == s


@pytest.mark.parametrize("bad", ["2-4-4", "3-4-4", "6-3-1", "3-1-6", "", "3-4", "3-4-3-1", "abc", "-1-4-7"])
def test_parse_rejects_malformed_or_illegal(bad):
    with pytest.raises(FormationError):
        parse_formation(bad)


def test_parse_normalises_whitespace():
    assert parse_formation(" 3 - 4 - 3 ").name == "3-4-3"


def test_load_formations_returns_eight_from_real_ruleset():
    fs = load_formations(RULESET)
    assert len(fs) == 8
    assert {f.name for f in fs} == set(EIGHT)


def test_slots_for():
    f = parse_formation("5-3-2")
    assert f.slots_for("P") == 1
    assert f.slots_for("D") == 5
    assert f.slots_for("C") == 3
    assert f.slots_for("A") == 2
