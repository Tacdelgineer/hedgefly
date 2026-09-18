"""A fee-free score from a replay is exactly a fee-free run (PLAN.md rule 5, finale caching).

The validation run logs a fee-free score and the finale reuses decisions across its two fee
passes, both by replaying actions instead of re-running a brain or a model. That is only
honest if the replay is exact, so it is checked here against a real fee-free run with a trader
whose decisions depend on its position, as a brain's do."""

import numpy as np
import pytest

from market import BUY, HOLD, SELL, Wallet, replay, trade_window
from market.chart import WINDOW
from tests.test_no_lookahead import candles

FIRST, LAST = WINDOW - 1, WINDOW + 150


def position_minded(seed: int, population: int = 5):
    """A trader that looks at its own position, like a fly does: it buys when flat and sells when
    long, on its own random schedule."""
    rng = np.random.default_rng(seed)

    def decide(chart, positions):
        act = rng.random(len(positions)) < 0.3
        return np.where(act, np.where(positions == 0, BUY, SELL), HOLD).astype(np.int8)
    return decide


def test_replaying_with_no_fees_is_a_no_fee_run():
    frame = candles(400)
    with_fees = trade_window(position_minded(1), frame, FIRST, LAST, Wallet(5, fee_bps=5.0))
    replayed = replay(with_fees.actions, frame, FIRST, LAST, Wallet(5, fee_bps=0.0))
    fee_free = trade_window(position_minded(1), frame, FIRST, LAST, Wallet(5, fee_bps=0.0))
    assert np.array_equal(replayed.trades, fee_free.trades)
    assert np.allclose(replayed.equity, fee_free.equity)
    assert (replayed.final_equity >= with_fees.final_equity - 1e-9).all(), "fees can only cost money"


def test_a_replay_fills_exactly_as_the_original_did():
    frame = candles(400)
    run = trade_window(position_minded(2), frame, FIRST, LAST, Wallet(5))
    again = replay(run.actions, frame, FIRST, LAST, Wallet(5))
    assert np.array_equal(again.trades, run.trades) and np.allclose(again.equity, run.equity)


def test_a_single_trader_replays_from_a_flat_list():
    frame = candles(400)
    script = np.array([BUY] + [HOLD] * (LAST - FIRST), np.int8)
    one = replay(script, frame, FIRST, LAST, Wallet(1, fee_bps=0.0))
    assert one.trades[0] == 1 and one.equity.shape == (LAST - FIRST + 1, 1)


def test_the_wrong_number_of_decisions_is_refused():
    with pytest.raises(ValueError, match="decisions for"):
        replay(np.zeros(3, np.int8), candles(400), FIRST, LAST, Wallet(1))
