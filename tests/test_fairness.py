"""The two tribes must differ in their wiring and in nothing else (PLAN.md rule 6).

Two things are computed from the connectome but are not the wiring under test:

- the eye layout. nfly places each photoreceptor at the synapse-weighted mean hex coordinate
  of its columnar targets, so scrambled edges scatter the photoreceptors at random. Both tribes
  therefore get the layout computed from the REAL connectome: a deliberate fairness choice.
- the readout groups. They come from the release's annotations, so they are the same groups in
  the same order for both tribes whatever the edges do.
"""

import numpy as np
import pytest
import torch
from nfly.interface.decoders import default_readout_nodes

from brain import Genome, TribeAgent, build_eye, scramble
from brain.agent import MIN_CALIBRATION_CHARTS, MOTOR_SUPERCLASSES, readout_groups

POPULATION = 4


@pytest.fixture(scope="module")
def scrambled(synthetic_connectome):
    return scramble(synthetic_connectome, seed=0)


def test_the_eye_layout_is_computed_from_the_edges(synthetic_connectome, scrambled):
    """Why the eye has to be shared: scrambling the edges moves the photoreceptors."""
    real, fake = build_eye(synthetic_connectome), build_eye(scrambled)
    assert not torch.equal(real.retina.grid, fake.retina.grid), (
        "if a scrambled eye landed in the same place, sharing the layout would be pointless")


def test_both_tribes_get_the_real_flys_eye(synthetic_connectome, scrambled, device, charts):
    eye = build_eye(synthetic_connectome)
    calibration = charts(MIN_CALIBRATION_CHARTS, seed=0)
    tribes = [TribeAgent.build(conn, calibration, device=device, eye=eye)
              for conn in (synthetic_connectome, scrambled)]
    a, b = (t.body.eye for t in tribes)
    assert torch.equal(a.idx, b.idx)
    assert torch.equal(a.retina.grid, b.retina.grid)
    assert torch.equal(a.retina.grid.cpu(), build_eye(synthetic_connectome).retina.grid), \
        "both tribes must look at the chart the way the real fly does"


def test_a_shared_eye_must_fit_the_connectome_it_is_given_to(synthetic_connectome, charts, device):
    """A layout from a different release would silently drive the wrong neurons."""
    eye = build_eye(synthetic_connectome)
    eye.idx[-1] = synthetic_connectome.n_neurons + 10
    with pytest.raises(ValueError, match="does not have"):
        TribeAgent.build(synthetic_connectome, charts(MIN_CALIBRATION_CHARTS, seed=0),
                         device=device, eye=eye)


def test_both_tribes_vote_through_the_same_groups(synthetic_connectome, scrambled):
    readout_idx = default_readout_nodes(synthetic_connectome)
    assert torch.equal(default_readout_nodes(scrambled), readout_idx)
    real_idx, real_size = readout_groups(synthetic_connectome, readout_idx)
    fake_idx, fake_size = readout_groups(scrambled, readout_idx)
    assert torch.equal(real_idx, fake_idx) and torch.equal(real_size, fake_size)


def test_motor_neurons_pool_by_sub_class(malecns):
    """The genome decision: one vote per muscle group, not per muscle."""
    readout_idx = default_readout_nodes(malecns)
    rows = malecns.neurons.iloc[readout_idx.numpy()]
    group_idx, group_size = readout_groups(malecns, readout_idx)

    motor = rows["super_class"].isin(MOTOR_SUPERCLASSES).to_numpy()
    sub_class = rows["sub_class"].fillna("").astype(str).to_numpy()
    groups = group_idx.numpy()
    for name in np.unique(sub_class[motor]):
        same = motor & (sub_class == name)
        assert len(np.unique(groups[same])) == 1, f"motor sub-class {name} is split across groups"
    assert len(np.unique(groups[motor])) == len(np.unique(sub_class[motor]))
    assert int(group_size.sum()) == len(readout_idx)
    assert len(group_size) < rows["cell_type"].nunique(), "pooling must shrink the genome"


def test_the_genome_is_one_vote_per_group_and_no_hold_logit(malecns):
    readout_idx = default_readout_nodes(malecns)
    _, group_size = readout_groups(malecns, readout_idx)
    genome = Genome.random(POPULATION, len(group_size), torch.Generator().manual_seed(0))
    assert genome.readout_w.shape == (POPULATION, len(group_size), 2)
    assert genome.size() == 64 + 1 + 2 * len(group_size)
