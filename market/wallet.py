"""The wallet: long or flat, one row per fly, vectorised over the population.

PLAN.md rules this enforces:
- rule 4: a decision at the close of candle t is filled at the OPEN of candle t+1. `fill` is
  never given a price the deciding fly could not have traded at.
- rule 5: every fill pays `fee_bps` basis points, on the way in and on the way out.
- a fly whose equity drops below `broke_below` is broke: it stops trading and its equity is
  frozen at the value it had when it died.
"""

from __future__ import annotations

import numpy as np

START_CASH = 1000.0
FEE_BPS = 10.0            # per side
BROKE_BELOW = 500.0

HOLD, BUY, SELL = 0, 1, 2          # brain/interface.md


class Wallet:
    """One row per fly. `positions` feeds the next decision; `fill` executes the last one."""

    def __init__(self, population: int, start_cash: float = START_CASH, fee_bps: float = FEE_BPS,
                 broke_below: float = BROKE_BELOW):
        self.fee = fee_bps / 10_000
        self.broke_below = broke_below
        self.cash = np.full(population, float(start_cash))
        self.units = np.zeros(population)                  # BTC held
        self.broke = np.zeros(population, bool)
        self.trades = np.zeros(population, int)
        self.equity = np.full(population, float(start_cash))

    @property
    def population(self) -> int:
        return len(self.cash)

    @property
    def positions(self) -> np.ndarray:
        """(P,) int8: 0 flat, 1 long. This is what the flies are told each candle."""
        return (self.units > 0).astype(np.int8)

    def fill(self, actions: np.ndarray, price: float) -> None:
        """Execute decisions at `price`, the open of the candle after the one they were made on.

        BUY while already long and SELL while flat are no-ops that cost nothing, and a broke
        fly trades no more."""
        actions = np.asarray(actions)
        if actions.shape != (self.population,):
            raise ValueError(f"actions must have shape ({self.population},), got {actions.shape}")
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")
        alive = ~self.broke
        buying = alive & (actions == BUY) & (self.units == 0)
        selling = alive & (actions == SELL) & (self.units > 0)
        self.units[buying] = self.cash[buying] * (1 - self.fee) / price
        self.cash[buying] = 0.0
        self.cash[selling] = self.units[selling] * price * (1 - self.fee)
        self.units[selling] = 0.0
        self.trades += buying + selling

    def settle(self, price: float) -> np.ndarray:
        """Mark every living fly to `price` (the candle's close) and retire the ones that fell
        below the broke line. Returns the equity of every fly, frozen for the broke ones."""
        alive = ~self.broke
        self.equity[alive] = self.cash[alive] + self.units[alive] * price
        self.broke |= self.equity < self.broke_below
        return self.equity.copy()
