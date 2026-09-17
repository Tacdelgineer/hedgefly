"""Are the flies sensitive enough to the chart to be worth evolving?

    uv run python -m scripts.check_sensitivity --population 100 --bars 192

Draws random genomes, lets them trade a probe window of the evolve set, and reports the share
that used two or more actions. A fly that emits one action all window tells selection nothing,
so PLAN.md wants this share past ~70% before the evolution loop is worth running. The three
settings it measures (per-window chart scaling, decisions on the change in a fly's own recent
average vote, and redrawing single-action genomes) are identical for both tribes.

Also reports the timing the speed budget is judged against: seconds per bar per tribe.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import torch

from brain import Genome, TribeAgent, build_eye, scramble
from brain.agent import MIN_CALIBRATION_CHARTS, VOTE_MEMORY
from evolve.seeding import action_variety, seed_population
from market import FEE_BPS, MIN_HOLD_BARS, START_CASH, load_evolve, render_range
from market.chart import WINDOW

from nfly import load_malecns


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--population", type=int, default=100)
    p.add_argument("--bars", type=int, default=192, help="bars in the probe window")
    p.add_argument("--vote-memory", type=int, default=VOTE_MEMORY, help="bars in a fly's running vote average")
    p.add_argument("--tribes", nargs="+", default=["real"], choices=["real", "scrambled"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="cuda")
    p.add_argument("--screen", action="store_true", help="also redraw the single-action genomes")
    args = p.parse_args()

    candles = load_evolve()
    rng = np.random.default_rng(args.seed)
    first = int(rng.integers(WINDOW - 1, len(candles) - args.bars - 1))
    last = first + args.bars - 1
    print(f"{len(candles):,} evolve bars; probe {candles['timestamp'].iloc[first]} .. "
          f"{candles['timestamp'].iloc[last]} ({args.bars} decisions)")

    calibration = render_range(candles, WINDOW - 1, WINDOW - 2 + MIN_CALIBRATION_CHARTS)
    conn = load_malecns("data")
    eye = build_eye(conn)
    wiring = {"real": conn, "scrambled": None}
    if "scrambled" in args.tribes:
        wiring["scrambled"] = scramble(conn, seed=1)

    wallet = {"start_cash": START_CASH, "fee_bps": FEE_BPS, "min_hold_bars": MIN_HOLD_BARS}
    for name in args.tribes:
        t0 = time.perf_counter()
        agent = TribeAgent.build(wiring[name], calibration, device=args.device, eye=eye,
                                 vote_memory=args.vote_memory)
        build_s = time.perf_counter() - t0
        genome = Genome.random(args.population, agent.n_groups, torch.Generator().manual_seed(args.seed))

        t0 = time.perf_counter()
        variety = action_variety(agent, genome, candles, first, last, **wallet)
        trade_s = time.perf_counter() - t0

        share = float((variety >= 2).mean())
        print(f"\n{name}: {agent.n_groups} readout groups, genome {genome.size():,} numbers per fly, "
              f"built in {build_s:.1f} s")
        print(f"  {args.population} flies x {args.bars} bars in {trade_s:.1f} s "
              f"({1000 * trade_s / args.bars:.0f} ms/bar); 576-bar window, both tribes: "
              f"{2 * 576 * trade_s / args.bars / 60:.2f} min")
        print(f"  distinct actions per fly: {np.bincount(variety, minlength=4)[1:].tolist()} "
              f"(1, 2, 3 actions)")
        print(f"  share using 2+ actions: {share:.1%}  {'PASS' if share >= 0.70 else 'BELOW 70%'}")

        if args.screen:
            generator = torch.Generator().manual_seed(args.seed + 1000)
            _, report = seed_population(agent, args.population, candles, first, last, generator, **wallet)
            print("  after screening: " + json.dumps(report, indent=None))


if __name__ == "__main__":
    main()
