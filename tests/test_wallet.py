"""PLAN.md rule 5 (fees on every trade) and the $1,000 / $500 portfolio rules."""

import numpy as np
import pytest

from market import BROKE_BELOW, FEE_BPS, START_CASH, Wallet

HOLD, BUY, SELL = 0, 1, 2
PRICE = 50_000.0


def test_a_round_trip_pays_the_fee_twice():
    wallet = Wallet(1)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    wallet.fill(np.array([SELL], np.int8), PRICE)
    fee = FEE_BPS / 10_000
    assert wallet.settle(PRICE)[0] == pytest.approx(START_CASH * (1 - fee) ** 2)
    assert wallet.trades[0] == 2


def test_without_fees_a_round_trip_is_free():
    wallet = Wallet(1, fee_bps=0)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    wallet.fill(np.array([SELL], np.int8), PRICE * 2)
    assert wallet.settle(PRICE)[0] == pytest.approx(2 * START_CASH)


def test_impossible_and_idle_actions_cost_nothing():
    wallet = Wallet(3)
    wallet.fill(np.array([SELL, HOLD, BUY], np.int8), PRICE)      # sell while flat, hold, buy
    assert np.array_equal(wallet.trades, [0, 0, 1])
    wallet.fill(np.array([HOLD, HOLD, BUY], np.int8), PRICE)      # buy while already long
    assert np.array_equal(wallet.trades, [0, 0, 1])
    assert np.array_equal(wallet.positions, [0, 0, 1])
    equity = wallet.settle(PRICE)
    assert equity[0] == equity[1] == START_CASH
    assert equity[2] == pytest.approx(START_CASH * (1 - FEE_BPS / 10_000))


def test_a_fly_below_the_broke_line_dies_and_its_equity_freezes():
    wallet = Wallet(1)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    wallet.settle(PRICE * 0.4)                                    # equity about $400
    assert wallet.broke[0] and wallet.equity[0] < BROKE_BELOW
    frozen = wallet.equity[0]
    wallet.fill(np.array([SELL], np.int8), PRICE)                 # the dead do not trade
    assert wallet.settle(PRICE)[0] == frozen and wallet.trades[0] == 1
