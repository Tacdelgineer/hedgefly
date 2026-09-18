"""Validation days are held out from selection (PLAN.md EVOLUTION, overfitting gauge)."""

import pandas as pd
import pytest

from evolve.loop import Config, draw_fixed_windows, draw_validation_windows
from market.chart import WINDOW


@pytest.fixture(scope="module")
def candles():
    n = 60_000
    return pd.DataFrame({"timestamp": pd.date_range("2023-01-01", periods=n, freq="5min", tz="UTC"),
                         "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0})


def test_validation_days_share_no_bar_and_no_chart_with_training_days(candles):
    cfg = Config(val_windows=2)
    train = draw_fixed_windows(cfg, candles)
    val = draw_validation_windows(cfg, candles, train)
    assert len(train) == 4 and len(val) == 2
    starts = [f for f, _ in train + val]
    for a in starts:
        for b in starts:
            if a != b:
                assert abs(a - b) > cfg.bars + WINDOW, "a validation day may not touch a training day's bars or chart"


def test_adding_validation_days_leaves_the_training_days_alone(candles):
    """The training days of a run with validation must be the ones a run without it trains on,
    so the two runs can be compared day for day."""
    assert draw_fixed_windows(Config(val_windows=2), candles) == draw_fixed_windows(Config(), candles)


def test_no_validation_days_unless_asked(candles):
    assert draw_validation_windows(Config(), candles, draw_fixed_windows(Config(), candles)) == []
