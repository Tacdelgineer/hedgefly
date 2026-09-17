"""PLAN.md rule 3: the locked test set is loaded only by finale.py."""

from pathlib import Path

import pytest

from market.data import LOCKED_READER, load_locked

REPO = Path(__file__).resolve().parents[1]
CODE_DIRS = ("brain", "market", "evolve", "story", "scripts", "visuals", "tests")

# The writer, the loader that guards it, the one reader, and this test.
MAY_MENTION_THE_LOCKED_FILE = {"market/fetch_btc.py", "market/data.py", "finale.py",
                               "tests/test_locked_test_set.py"}
MENTIONS = ("btc_locked_test", "LOCKED_PATH", "load_locked")


def python_files() -> list[Path]:
    files = [p for d in CODE_DIRS for p in (REPO / d).rglob("*.py")]
    return files + list(REPO.glob("*.py"))


def test_loading_the_locked_set_from_anywhere_else_is_refused():
    with pytest.raises(PermissionError, match=LOCKED_READER):
        load_locked()


def test_only_finale_and_the_market_plumbing_name_the_locked_file():
    offenders = {}
    for path in python_files():
        relative = path.relative_to(REPO).as_posix()
        if relative in MAY_MENTION_THE_LOCKED_FILE:
            continue
        hits = [word for word in MENTIONS if word in path.read_text()]
        if hits:
            offenders[relative] = hits
    assert not offenders, f"these files reach for the locked test set: {offenders}"
