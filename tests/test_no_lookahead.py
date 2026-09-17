"""PLAN.md rule 4: a decision at the close of candle t executes at the open of candle t+1,
and nothing after candle t can reach the flies that made it."""

import numpy as np
import pandas as pd
import pytest

from market import FEE_BPS, START_CASH, Wallet, render, trade_window
from market.chart import WINDOW

FIRST, LAST = WINDOW - 1, WINDOW + 19        # 20 decision candles after the chart warm-up


def candles(n: int, seed: int = 0) -> pd.DataFrame:
    """A random-walk price series with distinct opens and closes."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + abs(rng.normal(0, 0.002, n)))
    low = np.minimum(open_, close) * (1 - abs(rng.normal(0, 0.002, n)))
    return pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"),
                         "open": open_, "high": high, "low": low, "close": close, "volume": 1.0})


def rewrite_future(frame: pd.DataFrame, after: int) -> pd.DataFrame:
    """The same candles, with everything after position `after` replaced by a crash."""
    changed = frame.copy()
    for column in ("open", "high", "low", "close"):
        changed.loc[after + 1:, column] = frame[column].iloc[after + 1:].to_numpy() * 0.1
    return changed


def scripted(actions: np.ndarray):
    """A fly that plays a fixed script, so only the market can move the result."""
    step = iter(actions)
    return lambda chart, positions: next(step)


def test_chart_cannot_see_past_its_own_candle():
    frame = candles(200)
    for t in (FIRST, FIRST + 7, LAST):
        assert np.array_equal(render(frame.iloc[t - WINDOW + 1:t + 1]),
                              render(rewrite_future(frame, t).iloc[t - WINDOW + 1:t + 1]))


def test_order_fills_at_the_next_open_not_this_close():
    frame = candles(200)
    wallet = Wallet(1)
    buy_then_hold = [np.array([1], np.int8)] + [np.array([0], np.int8)] * (LAST - FIRST)
    trade_window(scripted(buy_then_hold), frame, FIRST, LAST, wallet)
    fill_price = frame["open"].iloc[FIRST + 1]
    assert fill_price != frame["close"].iloc[FIRST]
    assert wallet.units[0] == pytest.approx(START_CASH * (1 - FEE_BPS / 10_000) / fill_price)


def test_future_candles_cannot_change_earlier_equity():
    frame = candles(200)
    rng = np.random.default_rng(1)
    script = [rng.integers(0, 3, 4).astype(np.int8) for _ in range(LAST - FIRST + 1)]
    plain = trade_window(scripted(list(script)), frame, FIRST, LAST, Wallet(4))
    cut = 5                                                  # the candle whose future we rewrite
    crashed = trade_window(scripted(list(script)), rewrite_future(frame, FIRST + cut + 1), FIRST, LAST, Wallet(4))
    assert np.array_equal(plain.equity[:cut + 1], crashed.equity[:cut + 1])
    assert not np.array_equal(plain.equity[cut + 1:], crashed.equity[cut + 1:])


def test_a_decision_needs_a_candle_after_it():
    frame = candles(FIRST + 3)
    with pytest.raises(ValueError, match="filled at the next candle's open"):
        trade_window(scripted([]), frame, FIRST, len(frame) - 1, Wallet(1))
