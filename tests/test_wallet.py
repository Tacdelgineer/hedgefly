"""PLAN.md rule 5 (5 bps per side, 3-bar minimum hold) and the $1,000 / $500 portfolio rules."""

import numpy as np
import pytest

from market import BROKE_BELOW, FEE_BPS, MIN_HOLD_BARS, START_CASH, Wallet

HOLD, BUY, SELL = 0, 1, 2
PRICE = 50_000.0


def test_the_fee_is_five_basis_points_per_side():
    assert FEE_BPS == 5.0


def test_a_round_trip_pays_the_fee_twice():
    wallet = Wallet(1)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    for _ in range(MIN_HOLD_BARS - 1):                            # wait out the minimum hold
        wallet.fill(np.array([HOLD], np.int8), PRICE)
    wallet.fill(np.array([SELL], np.int8), PRICE)
    fee = FEE_BPS / 10_000
    assert wallet.settle(PRICE)[0] == pytest.approx(START_CASH * (1 - fee) ** 2)
    assert wallet.trades[0] == 2


def test_without_fees_a_round_trip_is_free():
    wallet = Wallet(1, fee_bps=0)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    for _ in range(MIN_HOLD_BARS - 1):
        wallet.fill(np.array([HOLD], np.int8), PRICE)
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


def test_a_position_cannot_flip_before_the_minimum_hold():
    """Rule 5: a fly that buys must hold for 3 bars before it may sell."""
    wallet = Wallet(1)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    assert wallet.positions[0] == 1
    for bar in range(MIN_HOLD_BARS - 1):                          # bars 1 and 2 after the fill
        wallet.fill(np.array([SELL], np.int8), PRICE)
        assert wallet.positions[0] == 1, f"the wallet flipped {bar + 1} bar(s) after buying"
        assert wallet.trades[0] == 1
    assert wallet.held_back[0] == MIN_HOLD_BARS - 1
    wallet.fill(np.array([SELL], np.int8), PRICE)                 # bar 3: free again
    assert wallet.positions[0] == 0 and wallet.trades[0] == 2


def test_the_first_decision_of_a_window_may_trade():
    wallet = Wallet(1)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    assert wallet.trades[0] == 1 and wallet.held_back[0] == 0


def test_the_minimum_hold_never_blocks_a_no_op():
    """An action the wallet would ignore anyway is not counted as held back."""
    wallet = Wallet(1)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    wallet.fill(np.array([BUY], np.int8), PRICE)                  # buy while long: nothing to hold back
    assert wallet.held_back[0] == 0 and wallet.trades[0] == 1


def test_no_fly_goes_broke_by_default():
    """Death is elimination by selection now, not bankruptcy: by default a fly that loses 60%
    keeps trading, and its equity keeps moving."""
    assert BROKE_BELOW == 0.0
    wallet = Wallet(1)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    assert wallet.settle(PRICE * 0.4)[0] < 500 and not wallet.broke[0]
    for _ in range(MIN_HOLD_BARS):
        wallet.fill(np.array([SELL], np.int8), PRICE)
    assert wallet.trades[0] == 2


def test_an_explicit_broke_line_still_freezes_a_fly():
    wallet = Wallet(1, broke_below=500.0)
    wallet.fill(np.array([BUY], np.int8), PRICE)
    wallet.settle(PRICE * 0.4)                                    # equity about $400
    assert wallet.broke[0] and wallet.equity[0] < 500.0
    frozen = wallet.equity[0]
    for _ in range(MIN_HOLD_BARS):
        wallet.fill(np.array([SELL], np.int8), PRICE)             # the dead do not trade
    assert wallet.settle(PRICE)[0] == frozen and wallet.trades[0] == 1
