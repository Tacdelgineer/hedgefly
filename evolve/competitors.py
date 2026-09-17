"""The flies' competitors, logged on the same window every generation (PLAN.md EVOLUTION).

Momentum, Random and Buy-and-hold all trade through the same `market.trade_window` and the
same `Wallet` as the flies, so they pay the same 5 bps per side, obey the same 3-bar minimum
hold, and fill at the next bar's open like everyone else (rules 4 and 5). None of them sees a
price the flies could not see: their decision for bar t is computed from bars up to t.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from market import BUY, HOLD, SELL, Wallet, trade_window

MOMENTUM_LOOKBACK = 12         # bars in the average a momentum trader chases (1 hour of 5-minute bars)


@dataclasses.dataclass(frozen=True)
class CompetitorRun:
    name: str
    final_equity: float
    trades: int
    broke: bool
    equity: np.ndarray         # (T,) marked at each bar's close

    def summary(self, start_cash: float) -> dict:
        return {"final_equity": round(self.final_equity, 2),
                "fitness": round(float(np.log(max(self.final_equity, 1e-9) / start_cash)), 6),
                "trades": int(self.trades), "broke": bool(self.broke)}


def scripted(actions: np.ndarray):
    """A trader that plays a fixed script: only the market can move its result."""
    step = iter(actions)
    return lambda chart, positions: np.array([next(step)], np.int8)


def momentum_script(candles: pd.DataFrame, first: int, last: int,
                    lookback: int = MOMENTUM_LOOKBACK) -> np.ndarray:
    """Long while the closing price is above the average of the last `lookback` closes.

    The decision for bar t reads closes[t - lookback + 1 : t + 1] and nothing later (rule 4)."""
    close = candles["close"].to_numpy()
    if first - lookback + 1 < 0:
        raise ValueError(f"momentum needs {lookback} bars before the first decision")
    return np.array([BUY if close[t] > close[t - lookback + 1:t + 1].mean() else SELL
                     for t in range(first, last + 1)], np.int8)


def random_script(bars: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 3, bars).astype(np.int8)


def buy_and_hold_script(bars: int) -> np.ndarray:
    """Buy at the first fill and never trade again; the wallet sells nothing, so the final
    equity is what the window's price move paid, minus one fee."""
    script = np.full(bars, HOLD, np.int8)
    script[0] = BUY
    return script


def run_competitors(candles: pd.DataFrame, first: int, last: int, seed: int,
                    lookback: int = MOMENTUM_LOOKBACK, **wallet: object) -> dict[str, CompetitorRun]:
    """One run per competitor on the window the flies just traded."""
    bars = last - first + 1
    scripts = {"momentum": momentum_script(candles, first, last, lookback),
               "random": random_script(bars, seed),
               "buy_and_hold": buy_and_hold_script(bars)}
    runs = {}
    for name, script in scripts.items():
        result = trade_window(scripted(script), candles, first, last, Wallet(1, **wallet))
        runs[name] = CompetitorRun(name, float(result.final_equity[0]), int(result.trades[0]),
                                   bool(result.broke[0]), result.equity[:, 0])
    return runs
