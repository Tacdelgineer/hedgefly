"""Genome: the only part of a fly that evolves (PLAN.md rule 2).

A genome holds, for every fly of a population, the cables between the market and the frozen
brain: how strongly each region of the chart drives the eye, how strongly the position flag
drives the proprioceptive neurons, and how the descending and motor neurons vote for an action.
Nothing in the connectome itself is part of it.

Votes are shared by cell type: all neurons of one type (DNp01, MNad01, ...) vote with the same
weight, so the genome is one vote per cell type instead of one per neuron. The grouping comes
from the release's annotations, so it is identical for the real and the scrambled tribe.
"""

from __future__ import annotations

import dataclasses

import torch

GAIN_GRID = 8       # chart gains form an 8 x 8 map over the image: flies differ in where they look
N_ACTIONS = 3       # HOLD, BUY, SELL


@dataclasses.dataclass(frozen=True)
class Genome:
    chart_gain: torch.Tensor      # (P, GAIN_GRID, GAIN_GRID) gain on the eye's drive per chart region
    position_gain: torch.Tensor   # (P,) gain on the position flag
    readout_w: torch.Tensor       # (P, G, N_ACTIONS) vote of each readout cell type for each action
    readout_b: torch.Tensor       # (P, N_ACTIONS)

    def __post_init__(self) -> None:
        p, groups = self.readout_w.shape[:2]
        expected = {"chart_gain": (p, GAIN_GRID, GAIN_GRID), "position_gain": (p,),
                    "readout_w": (p, groups, N_ACTIONS), "readout_b": (p, N_ACTIONS)}
        for name, shape in expected.items():
            if tuple(getattr(self, name).shape) != shape:
                raise ValueError(f"genome {name} has shape {tuple(getattr(self, name).shape)}, expected {shape}")

    @property
    def population(self) -> int:
        return self.readout_w.shape[0]

    @property
    def n_groups(self) -> int:
        return self.readout_w.shape[1]

    @staticmethod
    def random(population: int, n_groups: int, generator: torch.Generator | None = None) -> "Genome":
        """Gains around 1, votes scaled so that logits of unit-variance group activity have
        unit variance."""
        g = generator
        return Genome(chart_gain=1 + 0.5 * torch.randn(population, GAIN_GRID, GAIN_GRID, generator=g),
                      position_gain=1 + 0.5 * torch.randn(population, generator=g),
                      readout_w=torch.randn(population, n_groups, N_ACTIONS, generator=g) / n_groups ** 0.5,
                      readout_b=torch.zeros(population, N_ACTIONS))

    @staticmethod
    def neutral(population: int, n_groups: int) -> "Genome":
        """Unit gains and a silent readout (every fly holds)."""
        return Genome(chart_gain=torch.ones(population, GAIN_GRID, GAIN_GRID),
                      position_gain=torch.ones(population),
                      readout_w=torch.zeros(population, n_groups, N_ACTIONS),
                      readout_b=torch.zeros(population, N_ACTIONS))

    def size(self) -> int:
        """Numbers per fly, the dimension evolution searches in."""
        return sum(getattr(self, f.name)[0].numel() for f in dataclasses.fields(self))

    def to(self, device: torch.device | str) -> "Genome":
        return Genome(*(getattr(self, f.name).to(device) for f in dataclasses.fields(self)))
