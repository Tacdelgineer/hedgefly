"""One window end to end: a population of screened random-genome flies trades the evolve set.

    uv run python -m scripts.run_window --population 100 --bars 576

No evolution and no logging: this checks that the brain, the chart, the wallet and the rule-4
ordering work together on real candles, next to the competitors, and shows how long one tribe's
trading takes. `scripts.run_evolution` is the real thing.
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import torch
from nfly import load_malecns

from brain import TribeAgent, build_eye
from brain.agent import MIN_CALIBRATION_CHARTS
from evolve import BARS_PER_WINDOW, run_competitors
from evolve.seeding import seed_population
from market import FEE_BPS, MIN_HOLD_BARS, START_CASH, Wallet, load_evolve, render_range, trade_window
from market.chart import WINDOW

TRIBES = 2


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--population", type=int, default=100)
    p.add_argument("--bars", type=int, default=BARS_PER_WINDOW, help="decision bars in the window")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()

    candles = load_evolve()
    rng = np.random.default_rng(args.seed)
    first = int(rng.integers(WINDOW - 1, len(candles) - args.bars - 1))
    last = first + args.bars - 1
    print(f"{len(candles):,} evolve bars; window {candles['timestamp'].iloc[first]} .. "
          f"{candles['timestamp'].iloc[last]} ({args.bars} decisions)")

    calibration = render_range(candles, WINDOW - 1, WINDOW - 2 + MIN_CALIBRATION_CHARTS)
    conn = load_malecns("data")
    started = time.perf_counter()
    agent = TribeAgent.build(conn, calibration, device=args.device, eye=build_eye(conn))
    print(f"{torch.cuda.get_device_name()}: brain ready in {time.perf_counter() - started:.1f} s, "
          f"{agent.body.steps_per_candle} steps/bar, {agent.n_groups} readout groups")

    wallet_rules = {"start_cash": START_CASH, "fee_bps": FEE_BPS, "min_hold_bars": MIN_HOLD_BARS}
    genome, screen = seed_population(agent, args.population, candles, first, min(last, first + 191),
                                     torch.Generator().manual_seed(args.seed), **wallet_rules)
    print(f"seeding: {screen['share_using_2plus_actions_first_draw']:.0%} of random genomes used "
          f"2+ actions, {screen['genomes_drawn']} drawn over {screen['rounds']} round(s)")

    wallet = Wallet(args.population, **wallet_rules)
    started = time.perf_counter()
    result = trade_window(agent.start(genome).decide, candles, first, last, wallet)
    elapsed = time.perf_counter() - started

    equity = result.final_equity
    quantiles = np.quantile(equity, [0, 0.25, 0.5, 0.75, 1])
    print(f"\n{args.population} flies x {args.bars} bars in {elapsed:.1f} s "
          f"({1000 * elapsed / args.bars:.0f} ms/bar); both tribes: {TRIBES * elapsed / 60:.1f} min")
    print(f"genome: {genome.size():,} numbers per fly")
    print("final equity  min {:.2f}  p25 {:.2f}  median {:.2f}  p75 {:.2f}  max {:.2f}".format(*quantiles))
    print(f"mean {equity.mean():.2f}; broke {int(result.broke.sum())}/{args.population}")
    print(f"trades per fly: median {int(np.median(result.trades))}, min {result.trades.min()}, "
          f"max {result.trades.max()}; held back by the minimum hold: {int(wallet.held_back.sum())}")
    for name, run in run_competitors(candles, first, last, seed=args.seed, **wallet_rules).items():
        print(f"{name:>13}: ${run.final_equity:,.2f} in {run.trades} trades")


if __name__ == "__main__":
    main()
