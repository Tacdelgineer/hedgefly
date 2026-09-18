"""The evolution loop: two tribes, one window per generation, logged to the last number.

Every generation:
  1. one window of the evolve set is drawn at random, and BOTH tribes trade exactly that window
     with exactly the same fees, minimum hold and ordering, so the wiring is the only difference;
  2. the competitors (momentum, random, buy-and-hold) trade it too;
  3. fitness is log(final equity / start cash), broke flies share the worst;
  4. the whole generation is written to runs/<run_id>/gen_XXX.json and digested into
     gen_XXX_summary.json (PLAN.md rules 7 and 8);
  5. the top 20% survive, children are a survivor plus noise, 10% are newcomers, and every
     child records its parent.

The brain is never touched (rule 1); only genomes change (rule 2).
"""

from __future__ import annotations

import dataclasses
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import torch
from nfly import load_malecns

from brain import Genome, TribeAgent, build_eye, scramble
from brain.agent import MIN_CALIBRATION_CHARTS, STEPS_PER_CANDLE, VOTE_MEMORY
from market import (FEE_BPS, MIN_HOLD_BARS, START_CASH, WindowResult, Wallet, load_evolve,
                    load_split, render_range, trade_window)
from market.chart import WINDOW

from . import logs
from .competitors import MOMENTUM_LOOKBACK, run_competitors
from .population import Lineage, breed, fitness
from .seeding import PROBE_BARS, SEED_ROUNDS, seed_population

BARS_PER_WINDOW = 288          # PLAN.md: 1 day of 5-minute bars
TOP_FLIES = 5                  # flies named in each summary
ACTION_NAMES = ("hold", "buy", "sell")


@dataclasses.dataclass(frozen=True)
class Config:
    generations: int = 3
    population: int = 100
    bars: int = BARS_PER_WINDOW
    start_cash: float = START_CASH
    fee_bps: float = FEE_BPS
    min_hold_bars: int = MIN_HOLD_BARS
    survive_share: float = 0.20
    newcomer_share: float = 0.10
    mutation_rate: float = 0.15
    momentum_lookback: int = MOMENTUM_LOOKBACK
    steps_per_candle: int = STEPS_PER_CANDLE
    vote_memory: int = VOTE_MEMORY
    probe_bars: int = PROBE_BARS
    seed_rounds: int = SEED_ROUNDS
    seed: int = 0
    scramble_seed: int = 1
    device: str = "cuda"
    data_dir: str = "data"

    @property
    def wallet(self) -> dict:
        return {"start_cash": self.start_cash, "fee_bps": self.fee_bps,
                "min_hold_bars": self.min_hold_bars}

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Tribe:
    """A tribe between generations: its frozen body, its genomes and its family tree."""

    name: str
    agent: TribeAgent
    genome: Genome
    lineage: Lineage
    roster: list[str]


# ---- building ------------------------------------------------------------------------------

def build_tribes(cfg: Config, calibration: np.ndarray, log: Callable[[str], None]) -> tuple[list[Tribe], dict]:
    """The real tribe and the scrambled tribe, sharing the REAL fly's eye layout.

    The eye is computed from edges (nfly places each photoreceptor at the synapse-weighted mean
    hex coordinate of its columnar targets), so building it from scrambled edges would blind
    the scrambled tribe instead of testing its wiring. Both tribes get the real layout: a
    deliberate fairness choice (PLAN.md, README)."""
    conn = load_malecns(cfg.data_dir)
    eye = build_eye(conn)
    log(f"connectome: {conn.n_neurons:,} neurons, {conn.n_edges:,} edges; "
        f"eye: {int(eye.idx.numel()):,} photoreceptors from the real connectome")

    built = {}
    for name, wiring in (("real", conn), ("scrambled", scramble(conn, seed=cfg.scramble_seed))):
        started = time.perf_counter()
        built[name] = TribeAgent.build(wiring, calibration, device=cfg.device, eye=eye,
                                       steps_per_candle=cfg.steps_per_candle, vote_memory=cfg.vote_memory)
        log(f"{name} tribe ready in {time.perf_counter() - started:.1f} s, "
            f"{built[name].n_groups} readout groups")

    facts = {"neurons": int(conn.n_neurons), "edges": int(conn.n_edges),
             "photoreceptors": int(eye.idx.numel()), "readout_groups": int(built["real"].n_groups),
             "shared_eye_from": "real", "steps_per_candle": cfg.steps_per_candle}
    tribes = [Tribe(name, agent, None, Lineage(name), []) for name, agent in built.items()]
    return tribes, facts


def seed_tribes(cfg: Config, tribes: list[Tribe], candles: pd.DataFrame, rng: np.random.Generator,
                log: Callable[[str], None]) -> dict:
    """A screened starting population per tribe, from the same probe window."""
    first = int(rng.integers(WINDOW - 1, len(candles) - cfg.probe_bars - 1))
    last = first + cfg.probe_bars - 1
    reports = {}
    for i, tribe in enumerate(tribes):
        generator = torch.Generator().manual_seed(cfg.seed + 1000 + i)
        tribe.genome, reports[tribe.name] = seed_population(
            tribe.agent, cfg.population, candles, first, last, generator,
            rounds=cfg.seed_rounds, **cfg.wallet)
        tribe.roster = tribe.lineage.found(cfg.population)
        r = reports[tribe.name]
        log(f"{tribe.name}: {r['share_using_2plus_actions_first_draw']:.0%} of random genomes used "
            f"2+ actions on the probe; after {r['rounds']} round(s) "
            f"{r['share_using_2plus_actions_after_screening']:.0%}")
    return reports


# ---- one generation ------------------------------------------------------------------------

def draw_window(cfg: Config, candles: pd.DataFrame, rng: np.random.Generator) -> tuple[int, int]:
    """The same random window for both tribes and every competitor (PLAN.md EVOLUTION)."""
    lowest = max(WINDOW - 1, cfg.momentum_lookback - 1)
    highest = len(candles) - cfg.bars - 1
    if highest <= lowest:
        raise ValueError(f"{len(candles):,} bars are too few for a {cfg.bars}-bar window")
    first = int(rng.integers(lowest, highest))
    return first, first + cfg.bars - 1


def window_facts(candles: pd.DataFrame, first: int, last: int) -> dict:
    """What the window was, so a viewer can look it up (rule 8)."""
    opens, closes = candles["open"].to_numpy(), candles["close"].to_numpy()
    entry, exit_ = float(opens[first + 1]), float(closes[last + 1])
    return {"first_index": int(first), "last_index": int(last), "bars": int(last - first + 1),
            "first_time": candles["timestamp"].iloc[first].isoformat(),
            "last_time": candles["timestamp"].iloc[last + 1].isoformat(),
            "entry_price": round(entry, 2), "exit_price": round(exit_, 2),
            "price_move_pct": round(100 * (exit_ / entry - 1), 4)}


def fly_records(tribe: Tribe, result: WindowResult, scores: np.ndarray, wallet: Wallet,
                generation: int) -> list[dict]:
    counts = np.stack([(result.actions == a).sum(axis=0) for a in range(3)])       # (3, P)
    return [{"id": tribe.roster[i], **{k: v for k, v in tribe.lineage.flies[tribe.roster[i]].as_dict().items()
                                       if k != "id"},
             "generations_lived": generation - tribe.lineage.flies[tribe.roster[i]].born + 1,
             "fitness": round(float(scores[i]), logs.FITNESS_PLACES),
             "final_equity": round(float(result.final_equity[i]), logs.EQUITY_PLACES),
             "trades": int(result.trades[i]), "held_back": int(wallet.held_back[i]),
             "broke": bool(result.broke[i]),
             "actions": dict(zip(ACTION_NAMES, counts[:, i].tolist())),
             "distinct_actions": int((counts[:, i] > 0).sum())}
            for i in range(len(tribe.roster))]


def tribe_summary(tribe: Tribe, records: list[dict], scores: np.ndarray, result: WindowResult,
                  generation: int, seconds: float) -> dict:
    # Ranked on the raw scores, the way `breed` ranks them, so the hero named here is exactly
    # the fly that survives first; the fitness inside a record is rounded for the log.
    ranked = [records[i] for i in np.argsort(-scores, kind="stable")]
    equity, trades = result.final_equity, result.trades
    counts = np.stack([(result.actions == a).sum(axis=0) for a in range(3)]).sum(axis=1)
    variety = np.array([r["distinct_actions"] for r in records])
    hero = ranked[0]
    return {
        "population": len(records),
        "broke": int(result.broke.sum()),
        "alive": int((~result.broke).sum()),
        "seconds": round(seconds, 2),
        "fitness": {"best": ranked[0]["fitness"], "median": round(float(np.median(scores)), logs.FITNESS_PLACES),
                    "mean": round(float(scores.mean()), logs.FITNESS_PLACES), "worst": ranked[-1]["fitness"]},
        "final_equity": {"best": round(float(equity.max()), 2), "median": round(float(np.median(equity)), 2),
                         "mean": round(float(equity.mean()), 2), "worst": round(float(equity.min()), 2)},
        "trades": {"total": int(trades.sum()), "median": int(np.median(trades)),
                   "min": int(trades.min()), "max": int(trades.max())},
        "held_back_by_minimum_hold": int(sum(r["held_back"] for r in records)),
        "action_share": {name: round(float(c / counts.sum()), 4) for name, c in zip(ACTION_NAMES, counts)},
        "flies_using_2plus_actions": int((variety >= 2).sum()),
        "share_using_2plus_actions": round(float((variety >= 2).mean()), 4),
        "top": ranked[:TOP_FLIES],
        "hero_lineage": {**tribe.lineage.record(hero["id"], generation),
                         "fitness": hero["fitness"], "final_equity": hero["final_equity"]},
    }


def generation_payload(cfg: Config, run_id: str, generation: int, window: dict,
                       tribes: dict[str, dict], competitors: dict, seconds: float) -> dict:
    return {"run_id": run_id, "generation": generation, "seconds": round(seconds, 2),
            "window": window, "config": cfg.as_dict(), "tribes": tribes, "competitors": competitors}


def tribe_log(tribe: Tribe, records: list[dict], result: WindowResult) -> dict:
    """Everything about one tribe's generation: rule 7 says the logs hold the genomes, the
    equity curves and the trades, because the visuals replay the logs and never the simulation."""
    genome = tribe.genome
    return {"flies": records,
            "equity": logs.rounded(result.equity, logs.EQUITY_PLACES),        # (T, P)
            "actions": result.actions.T.tolist(),                             # (P, T) int8
            "genomes": {name: logs.rounded(getattr(genome, name), logs.GENE_PLACES)
                        for name in ("chart_gain", "position_gain", "readout_w")},
            "genome_size": int(genome.size())}


# ---- the run -------------------------------------------------------------------------------

def run(cfg: Config, run_id: str | None = None, log: Callable[[str], None] = print) -> dict:
    """Run `cfg.generations` generations and return the run's own summary."""
    candles = load_evolve()
    split = load_split()
    bar_seconds = int(split["granularity_seconds"])
    log(f"{len(candles):,} evolve bars of {bar_seconds // 60} minutes "
        f"({split['evolve']['first']} .. {split['evolve']['last']}); "
        f"{split['locked']['rows']:,} locked bars stay shut (rule 3)")

    calibration = render_range(candles, WINDOW - 1, WINDOW - 2 + MIN_CALIBRATION_CHARTS)
    tribes, facts = build_tribes(cfg, calibration, log)

    rng = np.random.default_rng(cfg.seed)
    seeding = seed_tribes(cfg, tribes, candles, rng, log)
    log(f"genome: {tribes[0].genome.size():,} numbers per fly "
        f"({facts['readout_groups']} readout groups x 2 votes + 64 chart gains + 1 position gain)")

    run_dir = logs.new_run_dir(run_id)
    started = time.perf_counter()
    logs.write_manifest(run_dir, {"run_id": run_dir.name, "config": cfg.as_dict(), "brain": facts,
                                  "seeding": seeding, "data": split,
                                  "genome_size": int(tribes[0].genome.size()),
                                  "started": datetime.now(timezone.utc).isoformat()})

    summaries = []
    for generation in range(cfg.generations):
        summaries.append(one_generation(cfg, run_dir, tribes, candles, rng, generation, log))
    elapsed = time.perf_counter() - started

    minutes = [s["seconds"] / 60 for s in summaries]
    report = {"run_id": run_dir.name, "run_dir": str(run_dir), "generations": cfg.generations,
              "minutes_per_generation": round(float(np.mean(minutes)), 3),
              "minutes_total": round(elapsed / 60, 3), "brain": facts, "seeding": seeding,
              "genome_size": int(tribes[0].genome.size()), "summaries": summaries}
    logs.write_json(run_dir / "run_summary.json", report)
    return report


def one_generation(cfg: Config, run_dir: Path, tribes: list[Tribe], candles: pd.DataFrame,
                   rng: np.random.Generator, generation: int, log: Callable[[str], None]) -> dict:
    started = time.perf_counter()
    first, last = draw_window(cfg, candles, rng)
    window = window_facts(candles, first, last)
    log(f"\ngeneration {generation}: bars {first:,}..{last:,} "
        f"({window['first_time']} .. {window['last_time']}, {window['price_move_pct']:+.2f}%)")

    full, digest, scored = {}, {}, {}
    for tribe in tribes:
        t0 = time.perf_counter()
        wallet = Wallet(cfg.population, **cfg.wallet)
        result = trade_window(tribe.agent.start(tribe.genome).decide, candles, first, last, wallet)
        seconds = time.perf_counter() - t0
        scores = fitness(result.final_equity, result.broke, cfg.start_cash)
        records = fly_records(tribe, result, scores, wallet, generation)
        full[tribe.name] = tribe_log(tribe, records, result)
        digest[tribe.name] = tribe_summary(tribe, records, scores, result, generation, seconds)
        scored[tribe.name] = scores
        d = digest[tribe.name]
        log(f"  {tribe.name:>9}: best ${d['final_equity']['best']:,.2f} "
            f"median ${d['final_equity']['median']:,.2f} | fitness {d['fitness']['best']:+.4f} "
            f"| {d['broke']} broke | {d['trades']['median']} trades (median) | {seconds:.0f} s")

    competitors = run_competitors(candles, first, last, seed=cfg.seed + generation,
                                 lookback=cfg.momentum_lookback, **cfg.wallet)
    comp_digest = {name: run_.summary(cfg.start_cash) for name, run_ in competitors.items()}
    log("  competitors: " + ", ".join(f"{n} ${c['final_equity']:,.2f}" for n, c in comp_digest.items()))

    seconds = time.perf_counter() - started
    logs.write_generation(run_dir, generation, generation_payload(
        cfg, run_dir.name, generation, window, full, comp_digest, seconds) |
        {"competitor_equity": {n: logs.rounded(r.equity, logs.EQUITY_PLACES) for n, r in competitors.items()}})
    summary = {"run_id": run_dir.name, "generation": generation, "seconds": round(seconds, 2),
               "window": window, "tribes": digest, "competitors": comp_digest}
    logs.write_summary(run_dir, generation, summary)

    for tribe in tribes:
        generator = torch.Generator().manual_seed(cfg.seed + 7919 * (generation + 1) + len(tribe.name))
        offspring = breed(tribe.genome, tribe.roster, scored[tribe.name], tribe.lineage, generation,
                          rng, generator, cfg.survive_share, cfg.newcomer_share, cfg.mutation_rate)
        tribe.genome, tribe.roster = offspring.genome, offspring.roster
    log(f"  bred: {offspring.n_survive} survivors, {offspring.n_child} children, "
        f"{offspring.n_newcomer} newcomers; generation took {seconds / 60:.2f} min")
    return summary
