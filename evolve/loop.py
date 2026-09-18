"""The evolution loop: two tribes, four fixed days, logged to the last number.

Once per run, `windows` non-overlapping days are drawn from the evolve set. Then every
generation:
  1. every fly of BOTH tribes trades every one of those same days, with the same fees, minimum
     hold and ordering, so the wiring is the only difference between the tribes and the genome
     is the only difference between the flies;
  2. fitness is the mean log return over the days - the same days every generation, so a
     genome's score is its own and not the luck of which day it drew;
  3. the top 20% reproduce and survive unchanged (elitism: the best genomes so far are always
     in the population); the other 80% are ELIMINATED, which is what dying means now;
  4. the whole generation is written to runs/<run_id>/gen_XXX.json and digested into
     gen_XXX_summary.json (PLAN.md rules 7 and 8);
  5. children are a survivor plus noise, 10% are newcomers, and every child records its parent.

The competitors (momentum, random, buy-and-hold) trade the same days once, at the start: the
days never change, so neither do they.

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
from market import (FEE_BPS, MIN_HOLD_BARS, START_CASH, Wallet, load_evolve,
                    load_split, render_range, replay, trade_window)
from market.chart import WINDOW

from . import logs
from .competitors import MOMENTUM_LOOKBACK, run_competitors
from .population import Lineage, breed, fitness_over_windows, survivors_of
from .seeding import PROBE_BARS, SEED_ROUNDS, seed_population

BARS_PER_WINDOW = 288          # PLAN.md: 1 day of 5-minute bars
FIXED_WINDOWS = 4              # PLAN.md: every fly, every generation, the same four days
TOP_FLIES = 5                  # flies named in each summary
ACTION_NAMES = ("hold", "buy", "sell")


@dataclasses.dataclass(frozen=True)
class Config:
    generations: int = 3
    population: int = 100
    bars: int = BARS_PER_WINDOW
    windows: int = FIXED_WINDOWS
    val_windows: int = 0           # validation days: every fly is scored on them, none is selected on them
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


# ---- the fixed days ------------------------------------------------------------------------

def draw_fixed_windows(cfg: Config, candles: pd.DataFrame) -> list[tuple[int, int]]:
    """`cfg.windows` days of the evolve set, drawn once per run, oldest first.

    No two share a bar, and no two share a chart either: each one needs 63 bars of history
    before its first decision, so they are kept a window plus a chart apart. Drawn from their own
    seed, so the days depend on the run's seed and nothing else."""
    rng = np.random.default_rng(cfg.seed + 97)
    lowest = max(WINDOW - 1, cfg.momentum_lookback - 1)
    highest = len(candles) - cfg.bars - 1
    if highest - lowest < cfg.windows * (cfg.bars + WINDOW):
        raise ValueError(f"{len(candles):,} bars are too few for {cfg.windows} separate {cfg.bars}-bar windows")
    picked: list[int] = []
    while len(picked) < cfg.windows:
        first = int(rng.integers(lowest, highest))
        if all(abs(first - other) > cfg.bars + WINDOW for other in picked):
            picked.append(first)
    return [(first, first + cfg.bars - 1) for first in sorted(picked)]


def draw_validation_windows(cfg: Config, candles: pd.DataFrame,
                            train: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """`cfg.val_windows` more days of the evolve set, drawn once per run from their own seed.

    They are kept a window plus a chart clear of every training day and of each other, so no
    bar a fly is selected on is ever part of a bar it is validated on. Flies are scored on them
    every generation and never selected on them: that score is the overfitting gauge."""
    if not cfg.val_windows:
        return []
    rng = np.random.default_rng(cfg.seed + 211)
    lowest = max(WINDOW - 1, cfg.momentum_lookback - 1)
    highest = len(candles) - cfg.bars - 1
    taken = [first for first, _ in train]
    picked: list[int] = []
    for _ in range(100_000):
        if len(picked) == cfg.val_windows:
            break
        first = int(rng.integers(lowest, highest))
        if all(abs(first - other) > cfg.bars + WINDOW for other in taken + picked):
            picked.append(first)
    if len(picked) < cfg.val_windows:
        raise ValueError(f"could not place {cfg.val_windows} validation days clear of the training days")
    return [(first, first + cfg.bars - 1) for first in sorted(picked)]


def window_facts(candles: pd.DataFrame, first: int, last: int) -> dict:
    """What a day was, so a viewer can look it up (rule 8)."""
    opens, closes = candles["open"].to_numpy(), candles["close"].to_numpy()
    entry, exit_ = float(opens[first + 1]), float(closes[last + 1])
    return {"first_index": int(first), "last_index": int(last), "bars": int(last - first + 1),
            "first_time": candles["timestamp"].iloc[first].isoformat(),
            "last_time": candles["timestamp"].iloc[last + 1].isoformat(),
            "entry_price": round(entry, 2), "exit_price": round(exit_, 2),
            "price_move_pct": round(100 * (exit_ / entry - 1), 4)}


# ---- one tribe on the fixed days -------------------------------------------------------------

@dataclasses.dataclass
class Evaluation:
    finals: np.ndarray          # (K, P) final equity on each day
    trades: np.ndarray          # (K, P) fills on each day
    held_back: np.ndarray       # (K, P) trades the minimum hold refused
    actions: list[np.ndarray]   # K x (T, P)
    equity: list[np.ndarray]    # K x (T, P)
    seconds: float


def evaluate(tribe: "Tribe", candles: pd.DataFrame, windows: list[tuple[int, int]], cfg: Config) -> Evaluation:
    """Every fly of a tribe on every fixed day. A fresh wallet and a fresh brain state each day:
    the days are separate trials, not one long run."""
    started = time.perf_counter()
    finals, trades, held, actions, equity = [], [], [], [], []
    for first, last in windows:
        wallet = Wallet(cfg.population, **cfg.wallet)
        result = trade_window(tribe.agent.start(tribe.genome).decide, candles, first, last, wallet)
        finals.append(result.final_equity); trades.append(result.trades); held.append(wallet.held_back.copy())
        actions.append(result.actions); equity.append(result.equity)
    return Evaluation(np.stack(finals), np.stack(trades), np.stack(held), actions, equity,
                      time.perf_counter() - started)


def fee_free_finals(ev: Evaluation, candles: pd.DataFrame, windows: list[tuple[int, int]],
                    cfg: Config) -> np.ndarray:
    """(K, P) what every fly would have ended each day with at zero fees.

    No brain runs again: the same actions are replayed through a fee-free wallet
    (market.session.replay), which is exact because no fill depends on the fee. The fills are
    checked against the real run anyway, so an inexact replay could never be logged quietly."""
    finals = []
    for k, (first, last) in enumerate(windows):
        free = replay(ev.actions[k], candles, first, last,
                      Wallet(ev.actions[k].shape[1], start_cash=cfg.start_cash, fee_bps=0.0,
                             min_hold_bars=cfg.min_hold_bars))
        if not np.array_equal(free.trades, ev.trades[k]):
            raise RuntimeError(f"the fee-free replay of day {k} filled differently from the real run")
        finals.append(free.final_equity)
    return np.stack(finals)


def spread(scores: np.ndarray, start_cash: float) -> dict:
    """Best, median and mean of a set of fitness scores, and the equity each implies."""
    geo = start_cash * np.exp(scores)
    return {"fitness": {"best": round(float(scores.max()), logs.FITNESS_PLACES),
                        "median": round(float(np.median(scores)), logs.FITNESS_PLACES),
                        "mean": round(float(scores.mean()), logs.FITNESS_PLACES)},
            "final_equity": {"best": round(float(geo.max()), 2), "median": round(float(np.median(geo)), 2)}}


def fly_records(tribe: "Tribe", ev: Evaluation, scores: np.ndarray, survived: np.ndarray,
                cfg: Config, generation: int) -> list[dict]:
    counts = sum(np.stack([(a == k).sum(axis=0) for k in range(3)]) for a in ev.actions)   # (3, P)
    geo = cfg.start_cash * np.exp(scores)
    out = []
    for i, fly_id in enumerate(tribe.roster):
        fly = tribe.lineage.flies[fly_id]
        out.append({"id": fly_id, "parent": fly.parent, "born": fly.born, "origin": fly.origin,
                    "generations_lived": generation - fly.born + 1,
                    "fitness": round(float(scores[i]), logs.FITNESS_PLACES),
                    "final_equity": round(float(geo[i]), logs.EQUITY_PLACES),
                    "final_equity_by_window": [round(float(e), logs.EQUITY_PLACES) for e in ev.finals[:, i]],
                    "trades": int(ev.trades[:, i].sum()),
                    "trades_per_day": round(float(ev.trades[:, i].mean()), 2),
                    "held_back": int(ev.held_back[:, i].sum()),
                    "survived": bool(survived[i]), "eliminated": not bool(survived[i]),
                    "actions": dict(zip(ACTION_NAMES, counts[:, i].tolist())),
                    "distinct_actions": int((counts[:, i] > 0).sum())})
    return out


def tribe_summary(tribe: "Tribe", records: list[dict], scores: np.ndarray, ev: Evaluation,
                  cfg: Config, generation: int) -> dict:
    ranked = [records[i] for i in np.argsort(-scores, kind="stable")]     # as breeding ranks them
    geo = cfg.start_cash * np.exp(scores)
    per_day = ev.trades.mean(axis=0)
    counts = sum(np.stack([(a == k).sum(axis=0) for k in range(3)]) for a in ev.actions).sum(axis=1)
    variety = np.array([r["distinct_actions"] for r in records])
    survived = sum(r["survived"] for r in records)
    hero = ranked[0]
    return {
        "population": len(records), "survived": int(survived), "eliminated": int(len(records) - survived),
        "seconds": round(ev.seconds, 2),
        "fitness": {"best": ranked[0]["fitness"], "median": round(float(np.median(scores)), logs.FITNESS_PLACES),
                    "mean": round(float(scores.mean()), logs.FITNESS_PLACES), "worst": ranked[-1]["fitness"]},
        "final_equity": {"best": round(float(geo.max()), 2), "median": round(float(np.median(geo)), 2),
                         "mean": round(float(geo.mean()), 2), "worst": round(float(geo.min()), 2)},
        "median_equity_by_window": [round(float(np.median(ev.finals[k])), 2) for k in range(len(ev.finals))],
        "trades": {"total": int(ev.trades.sum()), "median_per_day": round(float(np.median(per_day)), 2),
                   "mean_per_day": round(float(per_day.mean()), 2), "max_per_day": round(float(per_day.max()), 2)},
        "held_back_by_minimum_hold": int(ev.held_back.sum()),
        "action_share": {n: round(float(c / counts.sum()), 4) for n, c in zip(ACTION_NAMES, counts)},
        "flies_using_2plus_actions": int((variety >= 2).sum()),
        "share_using_2plus_actions": round(float((variety >= 2).mean()), 4),
        "top": ranked[:TOP_FLIES],
        "hero_lineage": {**tribe.lineage.record(hero["id"], generation),
                         "fitness": hero["fitness"], "final_equity": hero["final_equity"]},
    }


def tribe_log(tribe: "Tribe", records: list[dict], ev: Evaluation, val: Evaluation | None = None) -> dict:
    """Everything about one tribe's generation (rule 7): the visuals replay the logs, never the
    simulation. Curves and actions are per fixed day, in day order."""
    genome = tribe.genome
    return {"flies": records,
            "equity_by_window": [logs.rounded(e, logs.EQUITY_PLACES) for e in ev.equity],     # K x (T, P)
            "actions_by_window": [a.T.tolist() for a in ev.actions],                          # K x (P, T)
            "genomes": {name: logs.rounded(getattr(genome, name), logs.GENE_PLACES)
                        for name in ("chart_gain", "position_gain", "readout_w")},
            "genome_size": int(genome.size())} | ({
               "validation_equity_by_window": [logs.rounded(e, logs.EQUITY_PLACES) for e in val.equity],
               "validation_actions_by_window": [a.T.tolist() for a in val.actions]} if val else {})


def competitors_on(cfg: Config, candles: pd.DataFrame, windows: list[tuple[int, int]]) -> tuple[dict, dict]:
    """Momentum, random and buy-and-hold on the fixed days, scored the way the flies are.
    The days never change, so this runs once; random is seeded per day, so it is fixed too."""
    finals: dict[str, list[float]] = {}
    curves: dict[str, list] = {}
    trades: dict[str, int] = {}
    for k, (first, last) in enumerate(windows):
        for name, run_ in run_competitors(candles, first, last, seed=cfg.seed + 1_000 * (k + 1),
                                          lookback=cfg.momentum_lookback, **cfg.wallet).items():
            finals.setdefault(name, []).append(run_.final_equity)
            curves.setdefault(name, []).append(logs.rounded(run_.equity, logs.EQUITY_PLACES))
            trades[name] = trades.get(name, 0) + run_.trades
    digest = {}
    for name, days in finals.items():
        score = float(np.log(np.maximum(np.array(days), 1e-9) / cfg.start_cash).mean())
        digest[name] = {"fitness": round(score, logs.FITNESS_PLACES),
                        "final_equity": round(cfg.start_cash * float(np.exp(score)), 2),
                        "final_equity_by_window": [round(float(d), 2) for d in days],
                        "trades_per_day": round(trades[name] / len(windows), 2)}
    return digest, curves


# ---- the run -------------------------------------------------------------------------------

def run(cfg: Config, run_id: str | None = None, log: Callable[[str], None] = print) -> dict:
    """Run `cfg.generations` generations on fixed days and return the run's own summary."""
    candles = load_evolve()
    split = load_split()
    bar_seconds = int(split["granularity_seconds"])
    log(f"{len(candles):,} evolve bars of {bar_seconds // 60} minutes "
        f"({split['evolve']['first']} .. {split['evolve']['last']}); "
        f"{split['locked']['rows']:,} locked bars stay shut (rule 3)")

    windows = draw_fixed_windows(cfg, candles)
    days = [window_facts(candles, first, last) for first, last in windows]
    for d in days:
        log(f"fixed day: {d['first_time']} .. {d['last_time']}  {d['price_move_pct']:+.2f}%")
    val_windows = draw_validation_windows(cfg, candles, windows)
    val_days = [window_facts(candles, first, last) for first, last in val_windows]
    for d in val_days:
        log(f"validation day (scored, never selected on): {d['first_time']} .. {d['last_time']}  "
            f"{d['price_move_pct']:+.2f}%")

    calibration = render_range(candles, WINDOW - 1, WINDOW - 2 + MIN_CALIBRATION_CHARTS)
    tribes, facts = build_tribes(cfg, calibration, log)

    rng = np.random.default_rng(cfg.seed)
    seeding = seed_tribes(cfg, tribes, candles, rng, log)
    log(f"genome: {tribes[0].genome.size():,} numbers per fly "
        f"({facts['readout_groups']} readout groups x 2 votes + 64 chart gains + 1 position gain)")

    competitors, competitor_curves = competitors_on(cfg, candles, windows)
    log("competitors on the fixed days: " + ", ".join(
        f"{n} ${c['final_equity']:,.2f}" for n, c in competitors.items()))
    val_competitors, val_competitor_curves = competitors_on(cfg, candles, val_windows) if val_windows else ({}, {})
    if val_windows:
        log("competitors on the validation days: " + ", ".join(
            f"{n} ${c['final_equity']:,.2f}" for n, c in val_competitors.items()))

    run_dir = logs.new_run_dir(run_id)
    started = time.perf_counter()
    logs.write_manifest(run_dir, {"run_id": run_dir.name, "config": cfg.as_dict(), "brain": facts,
                                  "seeding": seeding, "data": split, "windows": days,
                                  "competitors": competitors, "competitor_equity": competitor_curves,
                                  "validation_windows": val_days, "validation_competitors": val_competitors,
                                  "validation_competitor_equity": val_competitor_curves,
                                  "genome_size": int(tribes[0].genome.size()),
                                  "started": datetime.now(timezone.utc).isoformat()})

    summaries = []
    for generation in range(cfg.generations):
        summaries.append(one_generation(cfg, run_dir, tribes, candles, windows, days, competitors,
                                        rng, generation, log, val_windows, val_days, val_competitors))
    elapsed = time.perf_counter() - started

    minutes = [s["seconds"] / 60 for s in summaries]
    report = {"run_id": run_dir.name, "run_dir": str(run_dir), "generations": cfg.generations,
              "minutes_per_generation": round(float(np.mean(minutes)), 3),
              "minutes_total": round(elapsed / 60, 3), "brain": facts, "seeding": seeding,
              "windows": days, "competitors": competitors,
              "validation_windows": val_days, "validation_competitors": val_competitors,
              "genome_size": int(tribes[0].genome.size()), "summaries": summaries}
    logs.write_json(run_dir / "run_summary.json", report)
    return report


def one_generation(cfg: Config, run_dir: Path, tribes: list["Tribe"], candles: pd.DataFrame,
                   windows: list[tuple[int, int]], days: list[dict], competitors: dict,
                   rng: np.random.Generator, generation: int, log: Callable[[str], None],
                   val_windows: list[tuple[int, int]] | None = None, val_days: list[dict] | None = None,
                   val_competitors: dict | None = None) -> dict:
    started = time.perf_counter()
    val_windows = val_windows or []
    log(f"\ngeneration {generation}: {len(windows)} fixed days" +
        (f" + {len(val_windows)} validation days" if val_windows else ""))

    full, digest, scored = {}, {}, {}
    for tribe in tribes:
        ev = evaluate(tribe, candles, windows, cfg)
        scores = fitness_over_windows(ev.finals, cfg.start_cash)            # the ONLY thing selection sees
        survived = np.zeros(len(scores), bool)
        survived[survivors_of(scores, cfg.survive_share)] = True
        free = fitness_over_windows(fee_free_finals(ev, candles, windows, cfg), cfg.start_cash)
        val = evaluate(tribe, candles, val_windows, cfg) if val_windows else None
        if val:
            val_scores = fitness_over_windows(val.finals, cfg.start_cash)
            val_free = fitness_over_windows(fee_free_finals(val, candles, val_windows, cfg), cfg.start_cash)
        records = fly_records(tribe, ev, scores, survived, cfg, generation)
        for i, r in enumerate(records):
            r["fitness_fee_free"] = round(float(free[i]), logs.FITNESS_PLACES)
            if val:
                r["validation_fitness"] = round(float(val_scores[i]), logs.FITNESS_PLACES)
                r["validation_final_equity"] = round(float(cfg.start_cash * np.exp(val_scores[i])), 2)
                r["validation_final_equity_by_window"] = [round(float(e), 2) for e in val.finals[:, i]]
                r["validation_fitness_fee_free"] = round(float(val_free[i]), logs.FITNESS_PLACES)
        full[tribe.name] = tribe_log(tribe, records, ev, val)
        d = digest[tribe.name] = tribe_summary(tribe, records, scores, ev, cfg, generation)
        d["fee_free"] = spread(free, cfg.start_cash)
        hero_row = int(np.argsort(-scores, kind="stable")[0])
        if val:
            kept = survivors_of(scores, cfg.survive_share)
            d["validation"] = spread(val_scores, cfg.start_cash) | {
                "survivors_median_fitness": round(float(np.median(val_scores[kept])), logs.FITNESS_PLACES),
                "trades": {"median_per_day": round(float(np.median(val.trades.mean(axis=0))), 2)},
                "fee_free": spread(val_free, cfg.start_cash), "seconds": round(val.seconds, 2)}
            d["hero_lineage"]["validation_fitness"] = round(float(val_scores[hero_row]), logs.FITNESS_PLACES)
            d["hero_lineage"]["validation_final_equity"] = round(float(cfg.start_cash * np.exp(val_scores[hero_row])), 2)
        scored[tribe.name] = scores
        log(f"  {tribe.name:>9}: best ${d['final_equity']['best']:,.2f} "
            f"median ${d['final_equity']['median']:,.2f} | fitness {d['fitness']['best']:+.5f} "
            f"| fee-free median {d['fee_free']['fitness']['median']:+.5f}"
            + (f" | VALIDATION median {d['validation']['fitness']['median']:+.5f} "
               f"hero {d['hero_lineage']['validation_fitness']:+.5f}" if val else "")
            + f" | {d['trades']['median_per_day']:g} trades/day | {ev.seconds + (val.seconds if val else 0):.0f} s")

    seconds = time.perf_counter() - started
    logs.write_generation(run_dir, generation, {
        "run_id": run_dir.name, "generation": generation, "seconds": round(seconds, 2),
        "windows": days, "config": cfg.as_dict(), "tribes": full, "competitors": competitors,
        "validation_windows": val_days or [], "validation_competitors": val_competitors or {}})
    summary = {"run_id": run_dir.name, "generation": generation, "seconds": round(seconds, 2),
               "windows": days, "tribes": digest, "competitors": competitors,
               "validation_windows": val_days or [], "validation_competitors": val_competitors or {}}
    logs.write_summary(run_dir, generation, summary)

    for tribe in tribes:
        generator = torch.Generator().manual_seed(cfg.seed + 7919 * (generation + 1) + len(tribe.name))
        offspring = breed(tribe.genome, tribe.roster, scored[tribe.name], tribe.lineage, generation,
                          rng, generator, cfg.survive_share, cfg.newcomer_share, cfg.mutation_rate)
        tribe.genome, tribe.roster = offspring.genome, offspring.roster
    log(f"  bred: {offspring.n_survive} survivors, {offspring.n_child} children, "
        f"{offspring.n_newcomer} newcomers; generation took {seconds / 60:.2f} min")
    return summary
