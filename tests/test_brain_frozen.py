"""PLAN.md rule 1: running the agent never changes the brain."""

import dataclasses

import numpy as np
import pytest
import torch
from nfly.interface.decoders import default_readout_nodes

from brain import Genome, TribeAgent
from brain.agent import MIN_CALIBRATION_CHARTS, readout_groups

POPULATION = 8
CONNECTOME_TENSORS = {"pre", "post", "sign", "w0", "log_gain", "bias", "alpha_logit"}


def run_window(agent: TribeAgent, charts: np.ndarray, seed: int) -> None:
    rng = np.random.default_rng(seed)
    run = agent.start(Genome.random(POPULATION, agent.n_groups, torch.Generator().manual_seed(seed)))
    for chart in charts:
        run.decide(chart, rng.integers(0, 2, POPULATION).astype(np.int8))


@pytest.mark.parametrize("connectome", ["synthetic_connectome", "malecns"])
def test_brain_weights_never_change(connectome, request, device, charts):
    conn = request.getfixturevalue(connectome)
    agent = TribeAgent.build(conn, charts(MIN_CALIBRATION_CHARTS, seed=0), device=device)
    brain = agent.body.brain
    assert brain.w0.is_cuda
    assert not any(q.requires_grad for q in brain.parameters())

    before = {name: t.detach().clone() for name, t in brain.state_dict().items()}
    assert CONNECTOME_TENSORS <= set(before)
    for seed in (1, 2):                                          # two windows with different genomes
        run_window(agent, charts(24, seed), seed)

    after = brain.state_dict()
    assert set(after) == set(before)
    for name, tensor in before.items():
        assert after[name].data_ptr() != tensor.data_ptr()      # compared against a copy, not a view
        assert torch.equal(after[name], tensor), f"brain tensor {name} changed"


def test_readout_groups_come_from_annotations_not_wiring(synthetic_connectome):
    """Rule 6: the scrambled tribe must vote through exactly the same cell-type groups, so the
    grouping may not depend on the edges. Shuffling every edge must leave it unchanged."""
    conn = synthetic_connectome
    readout_idx = default_readout_nodes(conn)
    group_idx, group_size = readout_groups(conn, readout_idx)

    shuffled = dataclasses.replace(conn, post=conn.post[torch.randperm(conn.n_edges)])
    assert torch.equal(default_readout_nodes(shuffled), readout_idx)
    shuffled_idx, shuffled_size = readout_groups(shuffled, readout_idx)
    assert torch.equal(shuffled_idx, group_idx) and torch.equal(shuffled_size, group_size)
