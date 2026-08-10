from pathlib import Path

import pytest

from fantacalcio.config import load_ruleset

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "auction_rules.v1.yaml"


@pytest.fixture(scope="session")
def ruleset():
    return load_ruleset(CONFIG_PATH)
