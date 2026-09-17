"""Smoke test: 100 random-genome flies with the whole CNS each decide on 336 fake charts.

No wallet yet, so every fly's position flag is random each candle."""

import time

import numpy as np
import torch

from brain import BUY, HOLD, SELL, Genome, TribeAgent
from brain.agent import MIN_CALIBRATION_CHARTS

POPULATION = 100
CANDLES = 336
TRIBES = 2


def test_100_random_flies_decide_on_336_charts(malecns, device, charts, capsys):
    t0 = time.perf_counter()
    agent = TribeAgent.build(malecns, charts(MIN_CALIBRATION_CHARTS, seed=0), device=device)
    torch.cuda.synchronize()
    build_s = time.perf_counter() - t0

    genome = Genome.random(POPULATION, agent.n_readout, torch.Generator().manual_seed(0))
    window, rng = charts(CANDLES, seed=1), np.random.default_rng(1)
    actions = np.empty((CANDLES, POPULATION), np.int8)
    run = agent.start(genome)
    t0 = time.perf_counter()
    for t, chart in enumerate(window):
        actions[t] = run.decide(chart, rng.integers(0, 2, POPULATION).astype(np.int8))
    decide_s = time.perf_counter() - t0                          # decide() copies to the CPU, so the GPU is done

    counts = np.bincount(actions.ravel(), minlength=3)
    reacting = int((actions != actions[0]).any(axis=0).sum())
    with capsys.disabled():
        print(f"\n{agent.body.brain.n:,} neurons, {agent.body.brain.pre.numel():,} edges, "
              f"{agent.body.steps_per_candle} steps/candle on {torch.cuda.get_device_name()}")
        print(f"build + calibration: {build_s:.1f} s")
        print(f"{POPULATION} flies x {CANDLES} candles: {decide_s:.1f} s ({1000 * decide_s / CANDLES:.0f} ms/candle); "
              f"both tribes: {TRIBES * decide_s / 60:.1f} min")
        print(f"actions HOLD/BUY/SELL: {counts.tolist()}; flies that change action during the window: {reacting}/{POPULATION}")

    assert actions.dtype == np.int8 and set(np.unique(actions)) <= {HOLD, BUY, SELL}
    assert (counts > 0).all()
    assert reacting > POPULATION // 2
