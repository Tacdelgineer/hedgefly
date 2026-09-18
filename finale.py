"""The ending: the champions of both tribes trade six months nobody has ever seen.

    uv run python finale.py --run runs/day4_full            # the take
    uv run python finale.py --run runs/day4_full --rehearse 2000   # a dress rehearsal

PLAN.md rule 3: `data/btc_locked_test.parquet` is the last six months and THIS FILE IS THE
ONLY ONE ALLOWED TO OPEN IT. `market.data.load_locked` checks its caller and refuses everybody
else, so the call below has to stay here, in this module, spelled out.

What runs:
  - the top 10 flies of the real tribe and of the scrambled tribe, from the last generation of
    a finished run, lifted out of that generation's log;
  - momentum, random and buy-and-hold, the same three that ran every generation;
  - a local Qwen3.8-27B reading the same 64 bars, described in words instead of drawn.

Everything trades the same bars under the same rules: 5 bps a side, a 3-bar minimum hold, and
a decision at the close of bar t filled at the open of t+1 (rules 4 and 5). Then the whole
thing runs a second time with the fees set to zero, which is the only way to show what the
fees actually cost.

Run once, on camera. Whatever happens is the ending. `--rehearse N` trades the last N bars of
the EVOLVE set instead, so the rig can be tested without anyone peeking at the ending.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from nfly import load_malecns

from brain import Genome, TribeAgent, build_eye, scramble
from brain.agent import MIN_CALIBRATION_CHARTS
from evolve.competitors import MOMENTUM_LOOKBACK, run_competitors
from evolve.logs import EQUITY_PLACES, rounded, write_json
from market import FEE_BPS, MIN_HOLD_BARS, START_CASH, Wallet, load_evolve, render_range, trade_window
from market.chart import WINDOW
from market.data import load_locked           # rule 3: this import belongs to finale.py alone
from story.llm import LOCAL_MODEL, LOCAL_URL, LLMTrader

TOP_N = 10                  # champions per tribe (PLAN.md FINALE)
LLM_EVERY = 12              # bars between the language model's decisions; see `llm_cadence` below
TRIBES = ("real", "scrambled")


@dataclasses.dataclass(frozen=True)
class Champions:
    tribe: str
    genome: Genome
    flies: list[dict]       # the log's record of each one: id, parent, fitness, ancestry

    @property
    def ids(self) -> list[str]:
        return [f["id"] for f in self.flies]


def last_generation(run_dir: Path) -> tuple[int, dict]:
    """The last generation a run finished, and its full log."""
    logs = sorted(run_dir.glob("gen_[0-9][0-9][0-9].json"))
    if not logs:
        raise SystemExit(f"no generation logs in {run_dir}; has the run finished?")
    return int(logs[-1].stem.split("_")[1]), json.loads(logs[-1].read_text())


def champions_of(log: dict, tribe: str, top_n: int = TOP_N) -> Champions:
    """The `top_n` fittest flies of a tribe, rebuilt from the generation log.

    Rule 8 in the other direction: the finale runs the flies the logs say won, not a copy kept
    in memory. The logs round a gene to five decimals, which is the quantisation the champions
    carry into the test."""
    rows = log["tribes"][tribe]
    order = sorted(range(len(rows["flies"])), key=lambda i: rows["flies"][i]["fitness"], reverse=True)
    picked = order[:top_n]
    genes = rows["genomes"]
    genome = Genome(chart_gain=torch.tensor([genes["chart_gain"][i] for i in picked], dtype=torch.float32),
                    position_gain=torch.tensor([genes["position_gain"][i] for i in picked], dtype=torch.float32),
                    readout_w=torch.tensor([genes["readout_w"][i] for i in picked], dtype=torch.float32))
    return Champions(tribe, genome, [rows["flies"][i] for i in picked])


def build_agents(calibration: np.ndarray, device: str, data_dir: str, scramble_seed: int) -> dict[str, TribeAgent]:
    """Both tribes, built exactly as they were during evolution: same steps per bar, same
    scramble seed, and the eye layout from the REAL connectome for both of them."""
    conn = load_malecns(data_dir)
    eye = build_eye(conn)
    wirings = {"real": conn, "scrambled": scramble(conn, seed=scramble_seed)}
    return {name: TribeAgent.build(w, calibration, device=device, eye=eye) for name, w in wirings.items()}


def trade_champions(agent: TribeAgent, champs: Champions, candles: pd.DataFrame, first: int, last: int,
                    fee_bps: float, min_hold_bars: int) -> dict:
    wallet = Wallet(champs.genome.population, fee_bps=fee_bps, min_hold_bars=min_hold_bars)
    result = trade_window(agent.start(champs.genome).decide, candles, first, last, wallet)
    return {"ids": champs.ids,
            "final_equity": [round(float(e), EQUITY_PLACES) for e in result.final_equity],
            "trades": [int(t) for t in result.trades],
            "broke": [bool(b) for b in result.broke],
            "held_back": [int(h) for h in wallet.held_back],
            "equity": rounded(result.equity, EQUITY_PLACES),                 # (T, 10)
            "mean_equity": rounded(result.equity.mean(axis=1), EQUITY_PLACES),
            "flies": champs.flies}


def one_pass(agents: dict[str, TribeAgent], champions: dict[str, Champions], candles: pd.DataFrame,
             first: int, last: int, fee_bps: float, args: argparse.Namespace, llm: LLMTrader | None) -> dict:
    """Every trader over the same bars under one fee regime."""
    started = time.perf_counter()
    rules = {"fee_bps": fee_bps, "min_hold_bars": args.min_hold_bars, "start_cash": START_CASH}
    out = {"fee_bps": fee_bps, "min_hold_bars": args.min_hold_bars, "tribes": {}, "competitors": {}}

    for name in TRIBES:
        t0 = time.perf_counter()
        out["tribes"][name] = trade_champions(agents[name], champions[name], candles, first, last,
                                              fee_bps, args.min_hold_bars)
        print(f"  {name:>9} champions: mean ${np.mean(out['tribes'][name]['final_equity']):,.2f} "
              f"({time.perf_counter() - t0:.0f} s)", flush=True)

    for name, run in run_competitors(candles, first, last, seed=args.seed,
                                     lookback=args.momentum_lookback, **rules).items():
        out["competitors"][name] = {**run.summary(START_CASH), "equity": rounded(run.equity, EQUITY_PLACES)}
        print(f"  {name:>9}: ${run.final_equity:,.2f}", flush=True)

    if llm is not None:
        run = llm.trade(candles, first, last, every=args.llm_every, **rules)
        out["competitors"]["llm"] = {**run.summary(START_CASH), "equity": rounded(run.equity, EQUITY_PLACES),
                                     "model": llm.model, "decisions": run.decisions,
                                     "bars_between_decisions": args.llm_every}
        print(f"  {'llm':>9}: ${run.final_equity:,.2f} ({run.decisions:,} decisions)", flush=True)

    out["seconds"] = round(time.perf_counter() - started, 1)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, required=True, help="the finished run directory under runs/")
    p.add_argument("--top", type=int, default=TOP_N, help="champions per tribe")
    p.add_argument("--fee-bps", type=float, default=FEE_BPS, help="first pass, per side")
    p.add_argument("--min-hold-bars", type=int, default=MIN_HOLD_BARS)
    p.add_argument("--momentum-lookback", type=int, default=MOMENTUM_LOOKBACK)
    p.add_argument("--llm-url", default=LOCAL_URL, help="OpenAI-compatible endpoint")
    p.add_argument("--llm-model", default=LOCAL_MODEL)
    p.add_argument("--llm-every", type=int, default=LLM_EVERY,
                   help="bars between the model's decisions; it holds in between")
    p.add_argument("--no-llm", action="store_true", help="leave the language model out")
    p.add_argument("--rehearse", type=int, default=0,
                   help="trade the last N bars of the EVOLVE set instead of the locked one")
    p.add_argument("--scramble-seed", type=int, default=1, help="must match the run's manifest")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA is not available; the finale does not run on CPU (PLAN.md SETUP)")

    generation, log = last_generation(args.run)
    champions = {name: champions_of(log, name, args.top) for name in TRIBES}
    manifest = json.loads((args.run / "manifest.json").read_text())
    if manifest["config"]["scramble_seed"] != args.scramble_seed:
        raise SystemExit(f"this run scrambled with seed {manifest['config']['scramble_seed']}, "
                         f"not {args.scramble_seed}; the champions would meet a different opponent")

    # The language model is checked BEFORE the long run, so a dead endpoint costs a second
    # rather than the whole take.
    llm = None if args.no_llm else LLMTrader(args.llm_url, args.llm_model).check()

    evolve_candles = load_evolve()
    calibration = render_range(evolve_candles, WINDOW - 1, WINDOW - 2 + MIN_CALIBRATION_CHARTS)

    if args.rehearse:
        candles, where = evolve_candles.iloc[-args.rehearse:].reset_index(drop=True), "evolve (rehearsal)"
    else:
        candles, where = load_locked(), "locked test set"       # rule 3, the one call in the codebase
    first, last = WINDOW - 1, len(candles) - 2                  # the last decision needs a bar after it

    print(f"{where}: {len(candles):,} bars, {candles['timestamp'].iloc[first]} .. "
          f"{candles['timestamp'].iloc[last + 1]}")
    print(f"champions from {args.run.name} generation {generation}: "
          + ", ".join(f"{n} {champions[n].ids[0]}" for n in TRIBES))

    agents = build_agents(calibration, args.device, "data", args.scramble_seed)

    passes = {}
    for label, fee in (("with_fees", args.fee_bps), ("no_fees", 0.0)):
        print(f"\n{label} ({fee} bps a side):", flush=True)
        passes[label] = one_pass(agents, champions, candles, first, last, fee, args, llm)

    out = {"run": args.run.name, "generation": generation, "rehearsal": bool(args.rehearse),
           "data": where, "bars": int(last - first + 1),
           "first_time": candles["timestamp"].iloc[first].isoformat(),
           "last_time": candles["timestamp"].iloc[last + 1].isoformat(),
           "passes": passes, "champions_per_tribe": args.top}
    path = write_json(args.run / ("finale_rehearsal.json" if args.rehearse else "finale.json"), out)

    print(f"\nwritten to {path}")
    print("\n| trader | with fees | no fees | what the fees cost |")
    print("| --- | --- | --- | --- |")
    for name in TRIBES:
        a = np.mean(passes["with_fees"]["tribes"][name]["final_equity"])
        b = np.mean(passes["no_fees"]["tribes"][name]["final_equity"])
        print(f"| {name} champions (mean of {args.top}) | ${a:,.2f} | ${b:,.2f} | ${b - a:,.2f} |")
    for name in passes["with_fees"]["competitors"]:
        a = passes["with_fees"]["competitors"][name]["final_equity"]
        b = passes["no_fees"]["competitors"][name]["final_equity"]
        print(f"| {name} | ${a:,.2f} | ${b:,.2f} | ${b - a:,.2f} |")


if __name__ == "__main__":
    main()
