"""The evolve / locked split: no candle is in both files (PLAN.md rule 3).

The check reads data/split.json and the evolve candles. It never opens the locked candles,
because a test is not finale.py.
"""

import pandas as pd
import pytest

from market import EVOLVE_PATH, load_evolve, load_split
from market.data import SPLIT_PATH


@pytest.fixture(scope="module")
def split():
    if not SPLIT_PATH.exists() or not EVOLVE_PATH.exists():
        pytest.skip("no candles yet; run `uv run python -m market.fetch_btc`")
    return load_split()


def test_the_two_files_do_not_overlap_in_time(split):
    evolve_last = pd.Timestamp(split["evolve"]["last"])
    locked_first = pd.Timestamp(split["locked"]["first"])
    assert evolve_last < locked_first
    assert locked_first - evolve_last == pd.Timedelta(seconds=split["granularity_seconds"])
    assert pd.Timestamp(split["evolve"]["first"]) < evolve_last
    assert locked_first < pd.Timestamp(split["locked"]["last"])
    assert split["evolve"]["rows"] > 0 and split["locked"]["rows"] > 0


def test_the_candles_are_five_minute_bars(split):
    """PLAN.md SETUP: the flies trade 5-minute bars, 288 of them to a generation window."""
    assert split["granularity_seconds"] == 300
    candles = load_evolve()
    gaps = candles["timestamp"].diff().dropna()
    assert gaps.min() == pd.Timedelta(minutes=5)
    assert (gaps == pd.Timedelta(minutes=5)).mean() > 0.999      # a handful of exchange outages


def test_the_evolve_file_stops_at_the_boundary(split):
    candles = load_evolve()
    assert len(candles) == split["evolve"]["rows"]
    assert candles["timestamp"].is_monotonic_increasing and not candles["timestamp"].duplicated().any()
    assert candles["timestamp"].max() == pd.Timestamp(split["evolve"]["last"])
    assert candles["timestamp"].max() < pd.Timestamp(split["boundary"])
    assert (candles[["open", "high", "low", "close"]] > 0).all().all()
    assert (candles["high"] >= candles["low"]).all()


def test_the_locked_set_is_the_last_six_months(split):
    locked_span = pd.Timestamp(split["locked"]["last"]) - pd.Timestamp(split["locked"]["first"])
    assert pd.Timedelta(days=180) <= locked_span <= pd.Timedelta(days=185)
