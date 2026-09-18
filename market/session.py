"""One trading window: candles in, one decision per candle, equity out.

The order of events is PLAN.md rule 4 and lives only here, so nothing else has to get it
right: at the close of candle t the flies see a chart that ends at t and the position they
hold; that decision is filled at the open of t+1; equity is marked at the close of t+1.
"""

from __future__ import annotations

import dataclasses
from typing import Callable

import numpy as np
import pandas as pd

from .chart import WINDOW, render_range
from .wallet import Wallet

Decide = Callable[[np.ndarray, np.ndarray], np.ndarray]     # (chart, positions) -> actions


@dataclasses.dataclass(frozen=True)
class WindowResult:
    actions: np.ndarray       # (T, P) int8, one decision per candle per fly
    equity: np.ndarray        # (T, P) dollars, marked at the close after each decision was filled
    trades: np.ndarray        # (P,) fills
    broke: np.ndarray         # (P,) bool

    @property
    def final_equity(self) -> np.ndarray:
        return self.equity[-1]


def trade_window(decide: Decide, candles: pd.DataFrame, first: int, last: int, wallet: Wallet) -> WindowResult:
    """Trade the decision candles `first` .. `last` (positions in `candles`)."""
    if first < WINDOW - 1:
        raise ValueError(f"the first chart needs {WINDOW - 1} candles before it, so `first` must be >= {WINDOW - 1}")
    if last + 1 >= len(candles):
        raise ValueError("the decision on the last candle is filled at the next candle's open, which must exist")
    charts = render_range(candles, first, last)             # drawn before any decision is made
    opens, closes = candles["open"].to_numpy(), candles["close"].to_numpy()
    actions = np.empty((len(charts), wallet.population), np.int8)
    equity = np.empty((len(charts), wallet.population))
    for i, t in enumerate(range(first, last + 1)):
        actions[i] = decide(charts[i], wallet.positions)
        wallet.fill(actions[i], opens[t + 1])
        equity[i] = wallet.settle(closes[t + 1])
    return WindowResult(actions, equity, wallet.trades.copy(), wallet.broke.copy())


def replay(actions: np.ndarray, candles: pd.DataFrame, first: int, last: int, wallet: Wallet) -> WindowResult:
    """Re-trade a window from actions already decided, in exactly trade_window's order.

    This is how a fee-free score is had without running a brain or a model again. A decision
    depends on the chart and on the position; a position depends only on which fills happened;
    and whether a fill happens never depends on the fee - a BUY spends all the cash whatever it
    is, and there is no bankruptcy line (market.wallet). So the same actions, replayed through
    a wallet with different fees, are exactly the run that wallet would have produced.
    `actions` is (T, P) or (T,) for a single trader."""
    actions = np.asarray(actions)
    if actions.ndim == 1:
        actions = actions[:, None]
    if len(actions) != last - first + 1:
        raise ValueError(f"{len(actions)} decisions for {last - first + 1} bars")
    if last + 1 >= len(candles):
        raise ValueError("the decision on the last candle is filled at the next candle's open, which must exist")
    opens, closes = candles["open"].to_numpy(), candles["close"].to_numpy()
    equity = np.empty((len(actions), wallet.population))
    for i, t in enumerate(range(first, last + 1)):
        wallet.fill(actions[i], opens[t + 1])
        equity[i] = wallet.settle(closes[t + 1])
    return WindowResult(actions.astype(np.int8), equity, wallet.trades.copy(), wallet.broke.copy())
