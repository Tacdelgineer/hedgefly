"""The competitors play by the flies' rules (PLAN.md EVOLUTION, rules 4 and 5)."""

import numpy as np
import pytest

from evolve.competitors import MOMENTUM_LOOKBACK, momentum_script, run_competitors, scripted
from market import BUY, FEE_BPS, MIN_HOLD_BARS, SELL, START_CASH, Wallet, trade_window
from market.chart import WINDOW
from tests.test_no_lookahead import candles, rewrite_future

FIRST, LAST = WINDOW - 1, WINDOW + 79


def test_momentum_never_reads_a_bar_it_has_not_reached():
    """Rule 4 for the competitors: rewriting the future may not change an earlier decision."""
    frame = candles(300)
    plain = momentum_script(frame, FIRST, LAST)
    for cut in (0, 20, LAST - FIRST):
        crashed = momentum_script(rewrite_future(frame, FIRST + cut), FIRST, LAST)
        assert np.array_equal(plain[:cut + 1], crashed[:cut + 1])


def test_momentum_is_long_above_its_own_average():
    frame = candles(300)
    close = frame["close"].to_numpy()
    script = momentum_script(frame, FIRST, LAST, MOMENTUM_LOOKBACK)
    for i, t in enumerate(range(FIRST, LAST + 1)):
        above = close[t] > close[t - MOMENTUM_LOOKBACK + 1:t + 1].mean()
        assert script[i] == (BUY if above else SELL)


def test_every_competitor_pays_the_fees_and_waits_out_the_hold():
    frame = candles(300)
    runs = run_competitors(frame, FIRST, LAST, seed=0)
    assert set(runs) == {"momentum", "random", "buy_and_hold"}
    for run in runs.values():
        assert run.equity.shape == (LAST - FIRST + 1,)
        assert np.isfinite(run.final_equity)


def test_buy_and_hold_buys_once_and_pays_one_fee():
    frame = candles(300)
    run = run_competitors(frame, FIRST, LAST, seed=0)["buy_and_hold"]
    units = START_CASH * (1 - FEE_BPS / 10_000) / frame["open"].iloc[FIRST + 1]
    assert run.trades == 1
    assert run.final_equity == pytest.approx(units * frame["close"].iloc[LAST + 1])


def test_a_competitor_cannot_flip_faster_than_a_fly():
    """A script that flips every bar is throttled to one trade per 3 bars, like the flies."""
    frame = candles(300)
    bars = LAST - FIRST + 1
    flip = np.array([BUY if t % 2 == 0 else SELL for t in range(bars)], np.int8)
    result = trade_window(scripted(flip), frame, FIRST, LAST, Wallet(1))
    assert result.trades[0] <= bars // MIN_HOLD_BARS + 1
