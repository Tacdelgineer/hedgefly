"""PLAN.md rule 6: the scrambled tribe is a fair control, not a crippled one.

Degree-preserving edge swaps keep every neuron's in-degree and out-degree, keep each edge's
synapse count and its presynaptic neuron's sign (Dale's law), and recompute the per-neuron
input normalisation. Only the targets move."""

import numpy as np
import torch

from brain.scramble import degrees, scramble


def test_the_neurons_are_the_same_neurons(synthetic_connectome):
    """The scrambled tribe is the same fly, rewired: same table, same order, same ids."""
    scrambled = scramble(synthetic_connectome, seed=0)
    assert scrambled.n_neurons == synthetic_connectome.n_neurons
    assert np.array_equal(scrambled.root_ids, synthetic_connectome.root_ids)
    assert scrambled.neurons.equals(synthetic_connectome.neurons)


def test_every_neuron_keeps_both_degrees(synthetic_connectome):
    scrambled = scramble(synthetic_connectome, seed=0)
    assert scrambled.n_edges == synthetic_connectome.n_edges
    for before, after in zip(degrees(synthetic_connectome), degrees(scrambled)):
        assert torch.equal(before, after)


def test_sign_and_synapse_count_travel_with_the_presynaptic_neuron(synthetic_connectome):
    scrambled = scramble(synthetic_connectome, seed=0)
    assert torch.equal(scrambled.pre, synthetic_connectome.pre)
    assert torch.equal(scrambled.sign, synthetic_connectome.sign)
    assert torch.equal(scrambled.syn_count, synthetic_connectome.syn_count)


def test_the_targets_actually_move(synthetic_connectome):
    scrambled = scramble(synthetic_connectome, seed=0)
    moved = (scrambled.post != synthetic_connectome.post).float().mean()
    assert moved > 0.9, f"only {moved:.1%} of edges found a new target"


def test_the_input_normalisation_is_recomputed(synthetic_connectome):
    """Rule 6: each neuron's inputs must still sum to 1 after the shuffle."""
    scrambled = scramble(synthetic_connectome, seed=0)
    totals = torch.zeros(scrambled.n_neurons).index_add_(0, scrambled.post, scrambled.weight)
    has_input = torch.zeros(scrambled.n_neurons, dtype=torch.bool).index_fill_(0, scrambled.post, True)
    assert torch.allclose(totals[has_input], torch.ones(int(has_input.sum())), atol=1e-5)
    assert not torch.equal(scrambled.weight, synthetic_connectome.weight)


def test_no_new_self_loops(synthetic_connectome):
    before = int((synthetic_connectome.pre == synthetic_connectome.post).sum())
    scrambled = scramble(synthetic_connectome, seed=0)
    assert int((scrambled.pre == scrambled.post).sum()) <= before


def test_the_scramble_is_reproducible(synthetic_connectome):
    """The same seed must give the same tribe, or a run cannot be replayed from its logs."""
    assert torch.equal(scramble(synthetic_connectome, seed=3).post,
                       scramble(synthetic_connectome, seed=3).post)
    assert not torch.equal(scramble(synthetic_connectome, seed=3).post,
                           scramble(synthetic_connectome, seed=4).post)
