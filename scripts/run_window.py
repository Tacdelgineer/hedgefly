"""One real window end to end: a population of random-genome flies trades the evolve set.

    uv run python -m scripts.run_window --population 100 --candles 336

No evolution and no logging yet: this checks that the brain, the chart, the wallet and the
rule-4 ordering work together on real candles, and shows how long one tribe's trading takes.
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import torch
from nfly import load_malecns

from brain import Genome, TribeAgent
from brain.agent import MIN_CALIBRATION_CHARTS
from market import FEE_BPS, START_CASH, Wallet, load_evolve, render_range, trade_window
from market.chart import WINDOW


def buy_and_hold(candles, first: int, last: int) -> float:
    """What a fly that bought at the first fill and sold at the last close would have."""
    fee = FEE_BPS / 10_000
    units = START_CASH * (1 - fee) / candles["open"].iloc[first + 1]
    return float(units * candles["close"].iloc[last + 1] * (1 - fee))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--population", type=int, default=100)
    p.add_argument("--candles", type=int, default=336, help="decision candles in the window")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()

    candles = load_evolve()
    rng = np.random.default_rng(args.seed)
    first = int(rng.integers(WINDOW - 1, len(candles) - args.candles - 1))
    last = first + args.candles - 1
    print(f"{len(candles):,} evolve candles; window {candles['timestamp'].iloc[first]} .. "
          f"{candles['timestamp'].iloc[last]} ({args.candles} decisions)")

    calibration = render_range(candles, WINDOW - 1, WINDOW - 2 + MIN_CALIBRATION_CHARTS)
    started = time.perf_counter()
    agent = TribeAgent.build(load_malecns("data"), calibration, device=args.device)
    print(f"{torch.cuda.get_device_name()}: brain ready in {time.perf_counter() - started:.1f} s, "
          f"{agent.body.steps_per_candle} steps/candle, {agent.n_groups} readout cell types")

    genome = Genome.random(args.population, agent.n_groups, torch.Generator().manual_seed(args.seed))
    run = agent.start(genome)
    wallet = Wallet(args.population)
    started = time.perf_counter()
    result = trade_window(run.decide, candles, first, last, wallet)
    elapsed = time.perf_counter() - started

    equity = result.final_equity
    quantiles = np.quantile(equity, [0, 0.25, 0.5, 0.75, 1])
    print(f"\n{args.population} flies x {args.candles} candles in {elapsed:.1f} s "
          f"({1000 * elapsed / args.candles:.0f} ms/candle); both tribes: {2 * elapsed / 60:.1f} min")
    print(f"genome: {genome.size():,} numbers per fly")
    print("final equity  min {:.2f}  p25 {:.2f}  median {:.2f}  p75 {:.2f}  max {:.2f}".format(*quantiles))
    print(f"mean {equity.mean():.2f}; buy-and-hold {buy_and_hold(candles, first, last):.2f}; "
          f"broke {int(result.broke.sum())}/{args.population}")
    print(f"trades per fly: median {int(np.median(result.trades))}, min {result.trades.min()}, "
          f"max {result.trades.max()}; flies that never traded: {int((result.trades == 0).sum())}")


if __name__ == "__main__":
    main()
