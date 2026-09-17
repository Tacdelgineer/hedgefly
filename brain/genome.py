"""Genome: the only part of a fly that evolves (PLAN.md rule 2).

A genome holds, for every fly of a population, the cables between the market and the frozen
brain: how strongly each region of the chart drives the eye, how strongly the position flag
drives the proprioceptive neurons, and how the descending and motor neurons vote for a trade.
Nothing in the connectome itself is part of it.

Votes are shared by readout group: descending neurons vote by cell type, motor neurons pool by
sub-class, so the fly's legs, wings, neck and abdomen each vote as one muscle group instead of
186 individual muscles. The grouping comes from the release's annotations, so it is identical
for the real and the scrambled tribe.

There are two votes, BUY and SELL, and no vote for HOLD: a fly holds when it raises neither.
There is no bias either. A fly is judged on the change in its vote against its own recent
average (`brain/agent.py`), and a constant survives neither subtraction, so a bias would be a
gene that cannot reach behaviour.
"""

from __future__ import annotations

import dataclasses

import torch

GAIN_GRID = 8       # chart gains form an 8 x 8 map over the image: flies differ in where they look
N_VOTES = 2         # BUY and SELL, in that order; HOLD is what happens when neither is raised

GAIN_SPREAD = 0.5   # how far apart random flies' gains start, around 1


def vote_spread(n_groups: int) -> float:
    """Votes scaled so that logits of unit-variance group activity have unit variance."""
    return n_groups ** -0.5


@dataclasses.dataclass(frozen=True)
class Genome:
    chart_gain: torch.Tensor      # (P, GAIN_GRID, GAIN_GRID) gain on the eye's drive per chart region
    position_gain: torch.Tensor   # (P,) gain on the position flag
    readout_w: torch.Tensor       # (P, G, N_VOTES) vote of each readout group for BUY and SELL

    def __post_init__(self) -> None:
        p, groups = self.readout_w.shape[:2]
        expected = {"chart_gain": (p, GAIN_GRID, GAIN_GRID), "position_gain": (p,),
                    "readout_w": (p, groups, N_VOTES)}
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
    def spreads(n_groups: int) -> dict[str, float]:
        """The spread each gene starts with. Mutation is measured in these units, so one
        mutation rate means the same thing to a gain around 1 and to a vote around 0.04."""
        return {"chart_gain": GAIN_SPREAD, "position_gain": GAIN_SPREAD,
                "readout_w": vote_spread(n_groups)}

    @staticmethod
    def random(population: int, n_groups: int, generator: torch.Generator | None = None) -> "Genome":
        """Gains around 1, votes around 0."""
        g, spread = generator, Genome.spreads(n_groups)
        return Genome(chart_gain=1 + spread["chart_gain"] * torch.randn(population, GAIN_GRID, GAIN_GRID, generator=g),
                      position_gain=1 + spread["position_gain"] * torch.randn(population, generator=g),
                      readout_w=spread["readout_w"] * torch.randn(population, n_groups, N_VOTES, generator=g))

    @staticmethod
    def neutral(population: int, n_groups: int) -> "Genome":
        """Unit gains and a silent readout (every fly holds)."""
        return Genome(chart_gain=torch.ones(population, GAIN_GRID, GAIN_GRID),
                      position_gain=torch.ones(population),
                      readout_w=torch.zeros(population, n_groups, N_VOTES))

    def size(self) -> int:
        """Numbers per fly, the dimension evolution searches in."""
        return sum(getattr(self, f.name)[0].numel() for f in dataclasses.fields(self))

    def to(self, device: torch.device | str) -> "Genome":
        return Genome(*(getattr(self, f.name).to(device) for f in dataclasses.fields(self)))
