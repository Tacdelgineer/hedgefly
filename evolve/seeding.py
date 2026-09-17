"""Drawing a starting population worth evolving (PLAN.md EVOLUTION).

A fly that emits one action for a whole window is invisible to selection: it always holds, or
buys once and never sells, and its fitness says nothing about its genome. Starting genomes are
therefore screened on a short probe window and the single-action ones are redrawn.

The share of random genomes that pass the screen on the first draw is the number the chart and
vote settings were tuned against; `scripts/check_sensitivity.py` reports it.
"""

from __future__ import annotations

import numpy as np
import torch

from brain import Genome, TribeAgent
from market import Wallet, trade_window

from .population import replace

PROBE_BARS = 192           # 16 hours of 5-minute bars: long enough to judge, short enough to redraw
SEED_ROUNDS = 3            # draws before a stubborn single-action fly is kept anyway
ACTIONS = (0, 1, 2)        # HOLD, BUY, SELL


def action_variety(agent: TribeAgent, genome: Genome, candles, first: int, last: int,
                   **wallet: object) -> np.ndarray:
    """(P,) how many distinct actions each fly emitted over the probe window.

    The flies trade a real wallet, so their position flag feeds back exactly as it will during
    evolution; what is counted is what the brain emitted, not what the wallet executed."""
    result = trade_window(agent.start(genome).decide, candles, first, last,
                          Wallet(genome.population, **wallet))
    return sum((result.actions == a).any(axis=0) for a in ACTIONS)


def seed_population(agent: TribeAgent, population: int, candles, first: int, last: int,
                    generator: torch.Generator, rounds: int = SEED_ROUNDS,
                    **wallet: object) -> tuple[Genome, dict]:
    """A starting population of random genomes with the single-action ones redrawn."""
    genome = Genome.random(population, agent.n_groups, generator)
    variety = action_variety(agent, genome, candles, first, last, **wallet)
    first_draw = float((variety >= 2).mean())
    drawn, used_rounds = population, 1

    for _ in range(rounds - 1):
        stuck = np.flatnonzero(variety < 2)
        if not len(stuck):
            break
        redraw = Genome.random(len(stuck), agent.n_groups, generator)
        genome = replace(genome, stuck, redraw)
        variety[stuck] = action_variety(agent, redraw, candles, first, last, **wallet)
        drawn += len(stuck)
        used_rounds += 1

    report = {"probe": {"first": int(first), "last": int(last), "bars": int(last - first + 1)},
              "rounds": used_rounds, "genomes_drawn": int(drawn),
              "share_using_2plus_actions_first_draw": round(first_draw, 4),
              "share_using_2plus_actions_after_screening": round(float((variety >= 2).mean()), 4),
              "still_single_action": int((variety < 2).sum())}
    return genome, report
