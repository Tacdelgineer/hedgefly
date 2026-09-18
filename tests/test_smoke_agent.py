"""Smoke test: 100 random-genome flies with the whole CNS decide on a stretch of charts.

No wallet here, so every fly's position flag is random each bar. The chart-sensitivity figure
PLAN.md asks for (the share of flies that use two or more actions) is measured on real candles
by `scripts/check_sensitivity.py`; this test is the cheap guard that it stays there."""

import time

import numpy as np
import torch

from brain import BUY, HOLD, SELL, Genome, TribeAgent
from brain.agent import MIN_CALIBRATION_CHARTS

POPULATION = 100
BARS = 128                 # a slice of a 288-bar generation window, to keep the suite runnable
TRIBES = 2
WINDOW_BARS = 288
VARIETY_TARGET = 0.70      # PLAN.md: past ~70% of flies using 2+ actions


def test_100_random_flies_decide_on_a_stretch_of_charts(malecns, device, charts, capsys):
    t0 = time.perf_counter()
    agent = TribeAgent.build(malecns, charts(MIN_CALIBRATION_CHARTS, seed=0), device=device)
    torch.cuda.synchronize()
    build_s = time.perf_counter() - t0

    genome = Genome.random(POPULATION, agent.n_groups, torch.Generator().manual_seed(0))
    window, rng = charts(BARS, seed=1), np.random.default_rng(1)
    actions = np.empty((BARS, POPULATION), np.int8)
    run = agent.start(genome)
    t0 = time.perf_counter()
    for t, chart in enumerate(window):
        actions[t] = run.decide(chart, rng.integers(0, 2, POPULATION).astype(np.int8))
    decide_s = time.perf_counter() - t0                          # decide() copies to the CPU, so the GPU is done

    counts = np.bincount(actions.ravel(), minlength=3)
    variety = sum((actions == a).any(axis=0) for a in (HOLD, BUY, SELL))
    reacting = int((actions != actions[0]).any(axis=0).sum())
    with capsys.disabled():
        print(f"\n{agent.body.brain.n:,} neurons, {agent.body.brain.pre.numel():,} edges, "
              f"{agent.n_groups} readout groups, {agent.body.steps_per_candle} steps/bar "
              f"on {torch.cuda.get_device_name()}")
        print(f"build + calibration: {build_s:.1f} s")
        print(f"{POPULATION} flies x {BARS} bars: {decide_s:.1f} s ({1000 * decide_s / BARS:.0f} ms/bar); "
              f"a {WINDOW_BARS}-bar window, both tribes: {TRIBES * WINDOW_BARS * decide_s / BARS / 60:.1f} min")
        print(f"genome: {genome.size():,} numbers per fly")
        print(f"actions HOLD/BUY/SELL: {counts.tolist()}; flies using 2+ actions: "
              f"{int((variety >= 2).sum())}/{POPULATION}; flies that change action: {reacting}/{POPULATION}")

    assert actions.dtype == np.int8 and set(np.unique(actions)) <= {HOLD, BUY, SELL}
    assert (counts > 0).all()
    assert (variety >= 2).mean() >= VARIETY_TARGET
    assert reacting > POPULATION // 2
