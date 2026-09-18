"""The finale, part two: the local language model, over the same bars.

    uv run python finale_llm.py --run runs/day4_full
    uv run python finale_llm.py --run runs/day4_full --rehearse 2000

Qwen3.8-27B on the local endpoint, reading the same 64 bars the flies see - scaled to their
own high and low, written out in words, because it cannot see a picture - and trading through
the same wallet: 5 bps a side, a 3-bar minimum hold, a decision at the close of a bar filled
at the open of the next one.

It is asked every `--every` bars (hourly by default) and holds in between. One call per
five-minute bar is 52,915 calls over six months, which is days of wall time. That changes how
OFTEN this trader may act; it changes nothing about the rules it acts under. The cadence is
written into the results so a viewer can see it.

Runs twice like everyone else: once with the fees, once with the fees at zero. The second pass
reuses the model's decisions from the first by replaying them through a fee-free wallet: exact,
because its position - the only thing in its prompt that could differ - never depends on the fee,
and it halves the model calls. --no-reuse asks the model again. The endpoint is checked before
the first bar, so a dead model costs a second rather than the whole take.

Writes `runs/<run>/finale_llm.json`, next to `finale_flies.json`; `finale_merge.py` joins them.

PLAN.md rule 3: this is one of exactly two files allowed to open the locked test set.
"""

from __future__ import annotations

import argparse
import time

from evolve.logs import EQUITY_PLACES, rounded
from finale_shared import (PASSES, common_args, describe, last_generation, window_of, write_part)
from market import START_CASH, Wallet, load_evolve, replay
from market.data import load_locked          # rule 3: this import belongs to the finale scripts
from story.llm import LOCAL_MODEL, LOCAL_URL, LLMRun, LLMTrader

HOURLY = 12                 # bars between decisions: 12 five-minute bars


def main() -> None:
    p = common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
    p.add_argument("--llm-url", default=LOCAL_URL, help="OpenAI-compatible endpoint")
    p.add_argument("--llm-model", default=LOCAL_MODEL)
    p.add_argument("--every", type=int, default=HOURLY,
                   help="bars between decisions; the model holds in between")
    p.add_argument("--no-reuse", dest="reuse", action="store_false",
                   help="ask the model again in the fee-free pass instead of replaying its decisions")
    args = p.parse_args()

    generation, _ = last_generation(args.run)          # fail early if the run is not finished
    trader = LLMTrader(args.llm_url, args.llm_model).check()

    if args.rehearse:
        candles, where = load_evolve().iloc[-args.rehearse:].reset_index(drop=True), "evolve (rehearsal)"
    else:
        candles, where = load_locked(), "locked test set"       # the one call, in the one place
    first, last = window_of(candles)
    bars = last - first + 1
    print(f"{where}: {bars:,} decision bars, {candles['timestamp'].iloc[first]} .. "
          f"{candles['timestamp'].iloc[last + 1]}")
    print(f"{args.llm_model} decides every {args.every} bars: about {bars // args.every:,} calls per pass")

    passes, first_run = {}, None
    for label, forced in PASSES:
        fee = args.fee_bps if forced is None else forced
        started = time.perf_counter()
        if first_run is None or not args.reuse:
            print(f"\n{label} ({fee} bps a side, asking the model):", flush=True)
            run = trader.trade(candles, first, last, every=args.every, start_cash=START_CASH,
                               fee_bps=fee, min_hold_bars=args.min_hold_bars)
            source = "model"
        else:
            # The model's decisions depend on the bars and on its position, and its position never
            # depends on the fee, so the second pass is the first pass's decisions replayed through
            # a fee-free wallet: exact, checked trade for trade, and not a single model call.
            print(f"\n{label} ({fee} bps a side, replaying the model's decisions from {PASSES[0][0]}):", flush=True)
            again = replay(first_run.actions, candles, first, last,
                           Wallet(1, start_cash=START_CASH, fee_bps=fee, min_hold_bars=args.min_hold_bars))
            if int(again.trades[0]) != first_run.trades:
                raise RuntimeError("the replay filled differently from the model's own run")
            run = LLMRun("llm", float(again.final_equity[0]), int(again.trades[0]), bool(again.broke[0]),
                         again.equity[:, 0], 0, 0, first_run.actions)
            source = f"replayed from {PASSES[0][0]}"
        first_run = first_run or run
        passes[label] = {"fee_bps": fee, "min_hold_bars": args.min_hold_bars,
                         "competitors": {"llm": {**run.summary(START_CASH),
                                                 "equity": rounded(run.equity, EQUITY_PLACES),
                                                 "model": args.llm_model,
                                                 "bars_between_decisions": args.every,
                                                 "decisions_from": source}},
                         "seconds": round(time.perf_counter() - started, 1)}
        print(f"  llm: ${run.final_equity:,.2f} in {run.trades} trades "
              f"({run.decisions:,} model calls, {run.unparsed} unreadable) "
              f"[{passes[label]['seconds'] / 60:.1f} min]", flush=True)
    print(f"model calls in all: {first_run.decisions if args.reuse else 'two passes'}; "
          f"unreadable replies count as HOLD and are logged as unparsed_replies", flush=True)

    payload = {"part": "llm", "run": args.run.name, "generation": generation,
               "rehearsal": bool(args.rehearse), "model": args.llm_model,
               "bars_between_decisions": args.every,
               **describe(candles, first, last, where), "passes": passes}
    print(f"\nwritten to {write_part(args.run, 'llm', payload, bool(args.rehearse))}")
    print(f"now run finale_merge.py --run {args.run}")


if __name__ == "__main__":
    main()
