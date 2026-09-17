"""How a fly turns two votes into a trade (PLAN.md SIMULATION ARCHITECTURE).

There is no HOLD logit: a fly holds when it raises neither vote. And a fly is judged on the
CHANGE in its vote against its own running average, not on the level, because readout neurons
sit on a large resting pattern that differs from fly to fly - judged on levels, a fly picks one
action on the first bar and repeats it for the whole window.
"""

import numpy as np
import torch

from brain import BUY, HOLD, SELL, Genome, TribeAgent
from brain.agent import MIN_CALIBRATION_CHARTS

POPULATION = 16
BARS = 40


def built(conn, device, charts):
    return TribeAgent.build(conn, charts(MIN_CALIBRATION_CHARTS, seed=0), device=device)


def window_actions(agent, genome, window):
    flat = np.zeros(genome.population, np.int8)
    return np.stack([agent_run.decide(c, flat) for agent_run in [agent.start(genome)] for c in window])


def test_the_first_bar_of_a_window_is_a_hold(synthetic_connectome, device, charts):
    """Nothing to compare the first vote with, so no fly trades on it."""
    agent = built(synthetic_connectome, device, charts)
    run = agent.start(Genome.random(POPULATION, agent.n_groups, torch.Generator().manual_seed(0)))
    actions = run.decide(charts(1, seed=1)[0], np.zeros(POPULATION, np.int8))
    assert np.array_equal(actions, np.full(POPULATION, HOLD))


def test_a_fly_that_raises_neither_vote_holds(synthetic_connectome, device, charts):
    """A silent readout is no vote at all, which is a hold - not a third logit."""
    agent = built(synthetic_connectome, device, charts)
    actions = window_actions(agent, Genome.neutral(POPULATION, agent.n_groups), charts(BARS, seed=2))
    assert (actions == HOLD).all()


def test_the_same_fly_on_the_same_chart_decides_the_same_way(synthetic_connectome, device, charts):
    """Deterministic: the logs can be replayed and the finale can be run once, on camera."""
    agent = built(synthetic_connectome, device, charts)
    genome = Genome.random(POPULATION, agent.n_groups, torch.Generator().manual_seed(0))
    window = charts(BARS, seed=3)
    assert np.array_equal(window_actions(agent, genome, window), window_actions(agent, genome, window))


def test_actions_are_the_three_the_market_knows(synthetic_connectome, device, charts):
    agent = built(synthetic_connectome, device, charts)
    genome = Genome.random(POPULATION, agent.n_groups, torch.Generator().manual_seed(0))
    actions = window_actions(agent, genome, charts(BARS, seed=4))
    assert actions.dtype == np.int8
    assert set(np.unique(actions)) <= {HOLD, BUY, SELL}


def test_a_fly_is_judged_on_the_change_in_its_vote_not_its_level(synthetic_connectome, device, charts):
    """The running average is what keeps a fly from freezing on one action all window.

    Same brain, same charts, same genomes, scored both ways: on the raw logit (the level) every
    fly picks one action and repeats it; on the change against its own recent average it reacts."""
    agent = built(synthetic_connectome, device, charts)
    genome = Genome.random(POPULATION, agent.n_groups, torch.Generator().manual_seed(0)).to(agent.body.device)
    run, body, stats = agent.start(genome), agent.body, agent.stats
    flat = np.zeros(POPULATION, np.int8)
    levels = []
    for chart in charts(BARS, seed=5):
        run.decide(chart, flat)
        votes = body.vote_inputs(run.h, stats).unsqueeze(1)
        levels.append(torch.bmm(votes, genome.readout_w).squeeze(1).argmax(1).cpu().numpy())
    by_level = np.stack(levels)
    by_change = window_actions(agent, genome.to("cpu"), charts(BARS, seed=5))

    stuck = int((by_level == by_level[0]).all(axis=0).sum())
    reacting = int((by_change != by_change[0]).any(axis=0).sum())
    assert stuck > POPULATION // 2, "the level rule was supposed to be the stuck one"
    assert reacting > stuck, f"only {reacting}/{POPULATION} flies reacted, against {stuck} stuck on levels"
