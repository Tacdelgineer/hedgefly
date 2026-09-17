"""The scrambled tribe's connectome (PLAN.md rule 6).

Degree-preserving edge swaps on the same edge list: take two edges a->b and c->d and swap
their targets to get a->d and c->b. Every neuron keeps its in-degree and its out-degree, and
because only targets move, each edge keeps the synapse count and the sign of its own
presynaptic neuron, so Dale's law survives the shuffle. The per-neuron input normalisation is
recomputed from the new targets by `build_connectome`.

What is destroyed is the wiring: which neuron listens to which. That is the whole point - the
scrambled tribe is the control that says whether the fly's actual circuit matters.
"""

from __future__ import annotations

import torch
from nfly import Connectome
from nfly.connectome import build_connectome

ROUNDS = 4          # passes of pairwise swaps; one pass already moves every edge's target


def scramble(conn: Connectome, seed: int = 0, rounds: int = ROUNDS) -> Connectome:
    """A connectome with the same neurons, degrees, signs and synapse counts, and shuffled targets."""
    generator = torch.Generator().manual_seed(seed)
    pre, post = conn.pre, conn.post.clone()
    for _ in range(rounds):
        order = torch.randperm(conn.n_edges, generator=generator)
        half = conn.n_edges // 2
        a, b = order[:half], order[half:2 * half]                 # disjoint pairs of edges
        keep = (pre[a] != post[b]) & (pre[b] != post[a])          # a swap may not invent a self-loop
        a, b = a[keep], b[keep]
        post[a], post[b] = post[b], post[a]
    return build_connectome(conn.neurons, pre, post, conn.syn_count, conn.sign)


def degrees(conn: Connectome) -> tuple[torch.Tensor, torch.Tensor]:
    """(out-degree, in-degree) per neuron, in edges."""
    n = conn.n_neurons
    out = torch.zeros(n, dtype=torch.long).index_add_(0, conn.pre, torch.ones_like(conn.pre))
    into = torch.zeros(n, dtype=torch.long).index_add_(0, conn.post, torch.ones_like(conn.post))
    return out, into
