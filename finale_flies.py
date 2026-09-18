"""The finale, part one: the champions and the three mechanical competitors.

    uv run python finale_flies.py --run runs/day4_full
    uv run python finale_flies.py --run runs/day4_full --rehearse 2000

The top 10 flies of each tribe, lifted out of the last generation's log, plus momentum,
random and buy-and-hold, over the whole locked test set. Three passes:

  with_fees          every bar, the real rules: 5 bps a side, a 3-bar minimum hold, fills at
                     the next bar's open
  no_fees            every bar, fees at zero, so the cost of trading can be shown
  hourly_with_fees   the champions only, acting once an hour, real fees - the language model
                     is only ever asked hourly, and this is the flies under that same limit

The minimum hold stays on in every pass: it is a rule, not a fee. In the hourly pass the
brains still see every bar; only their decision on the hour is acted on.

Writes `runs/<run>/finale_flies.json`. `finale_llm.py` writes the other half and
`finale_merge.py` puts them on one chart.

PLAN.md rule 3: this is one of exactly two files allowed to open the locked test set, and
`market.data.load_locked` checks the caller's filename, so the call stays here.

Run once, on camera. `--rehearse N` uses the tail of the evolve set instead, so the rig can
be tested without anyone seeing the ending.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from evolve.competitors import MOMENTUM_LOOKBACK, run_competitors
from evolve.logs import EQUITY_PLACES, rounded
from finale_shared import (HOURLY, HOURLY_PASS, PASSES, TRIBES, build_agents, calibration_charts,
                           champions_of, check_run, common_args, describe, last_generation,
                           require_gpu, trade_champions, window_of, write_part)
from market import START_CASH, load_evolve
from market.data import load_locked          # rule 3: this import belongs to the finale scripts


def main() -> None:
    p = common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
    p.add_argument("--top", type=int, default=10, help="champions per tribe")
    p.add_argument("--momentum-lookback", type=int, default=MOMENTUM_LOOKBACK)
    p.add_argument("--scramble-seed", type=int, default=1, help="must match the run's manifest")
    p.add_argument("--device", default="cuda")
    p.add_argument("--no-hourly", dest="hourly", action="store_false",
                   help="skip the hourly pass (it costs as much as a full five-minute pass)")
    args = p.parse_args()

    require_gpu(args.device)
    check_run(args.run, args.scramble_seed)
    generation, log = last_generation(args.run)
    champions = {name: champions_of(log, name, args.top) for name in TRIBES}

    calibration = calibration_charts()
    if args.rehearse:
        candles, where = load_evolve().iloc[-args.rehearse:].reset_index(drop=True), "evolve (rehearsal)"
    else:
        candles, where = load_locked(), "locked test set"       # the one call, in the one place
    first, last = window_of(candles)

    print(f"{where}: {len(candles):,} bars, {candles['timestamp'].iloc[first]} .. "
          f"{candles['timestamp'].iloc[last + 1]}")
    print(f"champions from {args.run.name} generation {generation}: "
          + ", ".join(f"{n} {champions[n].ids[0]}" for n in TRIBES))
    agents = build_agents(calibration, args.device, "data", args.scramble_seed)

    passes = {}
    for label, forced in PASSES:
        fee = args.fee_bps if forced is None else forced
        print(f"\n{label} ({fee} bps a side):", flush=True)
        started = time.perf_counter()
        out = {"fee_bps": fee, "min_hold_bars": args.min_hold_bars, "tribes": {}, "competitors": {}}
        for name in TRIBES:
            t0 = time.perf_counter()
            out["tribes"][name] = trade_champions(agents[name], champions[name], candles, first, last,
                                                  fee, args.min_hold_bars)
            print(f"  {name:>9} champions: mean ${np.mean(out['tribes'][name]['final_equity']):,.2f} "
                  f"({time.perf_counter() - t0:.0f} s)", flush=True)
        rules = {"fee_bps": fee, "min_hold_bars": args.min_hold_bars, "start_cash": START_CASH}
        for name, run in run_competitors(candles, first, last, seed=args.seed,
                                         lookback=args.momentum_lookback, **rules).items():
            out["competitors"][name] = {**run.summary(START_CASH), "equity": rounded(run.equity, EQUITY_PLACES)}
            print(f"  {name:>9}: ${run.final_equity:,.2f}", flush=True)
        out["seconds"] = round(time.perf_counter() - started, 1)
        out["bars_between_decisions"] = 1
        passes[label] = out

    if args.hourly:
        print(f"\n{HOURLY_PASS} ({args.fee_bps} bps a side, acting every {HOURLY} bars):", flush=True)
        started = time.perf_counter()
        out = {"fee_bps": args.fee_bps, "min_hold_bars": args.min_hold_bars,
               "bars_between_decisions": HOURLY, "tribes": {}, "competitors": {}}
        for name in TRIBES:
            t0 = time.perf_counter()
            out["tribes"][name] = trade_champions(agents[name], champions[name], candles, first, last,
                                                  args.fee_bps, args.min_hold_bars, every=HOURLY)
            print(f"  {name:>9} champions, hourly: mean ${np.mean(out['tribes'][name]['final_equity']):,.2f} "
                  f"({time.perf_counter() - t0:.0f} s)", flush=True)
        out["seconds"] = round(time.perf_counter() - started, 1)
        passes[HOURLY_PASS] = out

    payload = {"part": "flies", "run": args.run.name, "generation": generation,
               "rehearsal": bool(args.rehearse), "champions_per_tribe": args.top,
               **describe(candles, first, last, where), "passes": passes}
    print(f"\nwritten to {write_part(args.run, 'flies', payload, bool(args.rehearse))}")
    print(f"now run finale_llm.py, then finale_merge.py --run {args.run}")


if __name__ == "__main__":
    main()
