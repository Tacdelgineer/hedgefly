"""A tribe of flies: one frozen connectome stepped for a whole population at once.

    chart (64, 64) --nfly retina--> photoreceptor drive (K,) x per-fly chart gain map --+
    position flag (P,) x per-fly position gain --> proprioceptive neurons ---------------+--> u (P, N)
    u --frozen ConnectomeRNN, steps_per_candle steps--> h (P, N)
    h[:, descending + motor] --fixed standardisation--> z (P, R) --per-fly votes--> logits (P, 3)
    argmax --> HOLD / BUY / SELL

The market side's contract is brain/interface.md. The brain is built with no trainable edge
gains, leaks or biases and only ever runs without autograd (PLAN.md rule 1); flies differ
only in their Genome (rule 2).
"""

from __future__ import annotations

import dataclasses

import gymnasium as gym
import numpy as np
import torch
from nfly import Connectome, ConnectomeRNN
from nfly.interface.decoders import default_readout_nodes
from nfly.interface.encoders import RetinaEncoder

from .genome import Genome

CHART_SHAPE = (64, 64)
HOLD, BUY, SELL = 0, 1, 2          # argmax ties go to the lowest code, so a silent readout holds

# nfly's FlyAgent defaults. With bias 0.1 the whole CNS keeps a stable tonic baseline, so the
# inhibitory (histaminergic) photoreceptors can be read downstream; with alpha 0.7 each step
# carries activity about one synapse further.
ALPHA = 0.7
BIAS = 0.1
INPUT_GAIN = 5.0
REST_STEPS = 64                    # steps with no input that settle the brain into its resting state

# Proprioceptors sense the fly's own body position, so they carry the trading position. In the
# whole CNS they are 1,454 neurons that reach 99% of the readout neurons within two synapses.
POSITION_CLASS = "mechanosensory_proprioceptive"

MIN_CALIBRATION_CHARTS = 256
MIN_STD = 1e-4
Z_CLIP = 10.0


@dataclasses.dataclass(frozen=True)
class ReadoutStats:
    """Per-readout-neuron mean and spread of the tribe's own brain on calibration charts.
    Readout neurons sit on a large resting pattern; standardising removes it so that votes
    weigh what changes with the chart. Fixed once built, the same for every fly."""

    mean: torch.Tensor    # (R,)
    std: torch.Tensor     # (R,)

    def standardise(self, activity: torch.Tensor) -> torch.Tensor:
        return ((activity - self.mean) / self.std).clamp(-Z_CLIP, Z_CLIP)


@dataclasses.dataclass(frozen=True)
class Body:
    """Everything between the market and the readout neurons that is the same for every fly."""

    brain: ConnectomeRNN
    eye: RetinaEncoder
    position_idx: torch.Tensor     # (Q,) proprioceptive neurons
    readout_idx: torch.Tensor      # (R,) descending + motor neurons
    h_rest: torch.Tensor           # (N,) resting state; every window starts here
    steps_per_candle: int

    @property
    def device(self) -> torch.device:
        return self.h_rest.device

    def drive(self, chart: torch.Tensor, previous: torch.Tensor | None, position: torch.Tensor,
              genome: Genome) -> torch.Tensor:
        """Input current (P, N): the chart and its change since the previous candle on the
        photoreceptors, the position flag (flat -1, long +1) on the proprioceptors, each scaled
        by the fly's own gains."""
        change = chart - previous if previous is not None else torch.zeros_like(chart)
        retina = self.eye.encode(torch.stack([chart, change]).unsqueeze(0))              # (1, K)
        u = torch.zeros(genome.population, self.brain.n, device=self.device)
        u[:, self.eye.idx] = INPUT_GAIN * self.chart_gain_per_photoreceptor(genome) * retina
        u[:, self.position_idx] = (INPUT_GAIN * genome.position_gain * (2 * position - 1)).unsqueeze(1)
        return u

    def chart_gain_per_photoreceptor(self, genome: Genome) -> torch.Tensor:
        """(P, K): each fly's gain map sampled where each photoreceptor looks at the chart."""
        grid = self.eye.retina.grid.expand(genome.population, -1, -1, -1)
        gains = torch.nn.functional.grid_sample(genome.chart_gain.unsqueeze(1), grid, mode="bilinear",
                                                align_corners=True)
        return gains.flatten(1)

    def think(self, h: torch.Tensor, u: torch.Tensor) -> torch.Tensor:
        weights = self.brain.weights()
        for _ in range(self.steps_per_candle):
            h = self.brain.step(h, u, weights)
        return h

    def rest(self, population: int) -> torch.Tensor:
        return self.h_rest.expand(population, -1).clone()


class TribeAgent:
    """One tribe (real or scrambled connectome): its frozen body and readout statistics.
    `start(genome)` begins a trading window for a population of flies."""

    def __init__(self, body: Body, stats: ReadoutStats):
        self.body, self.stats = body, stats

    @property
    def n_readout(self) -> int:
        return int(self.body.readout_idx.numel())

    @classmethod
    @torch.no_grad()
    def build(cls, conn: Connectome, calibration_charts: np.ndarray, device: str = "cuda",
              steps_per_candle: int = 2) -> "TribeAgent":
        """calibration_charts (T, 64, 64): consecutive charts from the evolve set only."""
        device = torch.device(device)
        if device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available; refusing to fall back to CPU")
        brain = ConnectomeRNN(conn, alpha_init=ALPHA, bias_init=BIAS,
                              learn_gain=False, learn_alpha=False, learn_bias=False).to(device)
        assert not any(q.requires_grad for q in brain.parameters()), "brain weights must be frozen"
        position_idx = conn.where(**{"class": POSITION_CLASS})
        if len(position_idx) == 0:
            raise ValueError(f"connectome has no {POSITION_CLASS} neurons for the position flag")
        chart_space = gym.spaces.Box(0.0, 1.0, (2, *CHART_SHAPE), np.float32)
        body = Body(brain, RetinaEncoder(conn, chart_space).to(device), position_idx.to(device),
                    default_readout_nodes(conn).to(device), resting_state(brain), steps_per_candle)
        return cls(body, calibrate(body, calibration_charts))

    @torch.no_grad()
    def start(self, genome: Genome) -> "FlyRun":
        if genome.n_readout != self.n_readout:
            raise ValueError(f"genome has {genome.n_readout} readout votes, the brain has {self.n_readout} readout neurons")
        return FlyRun(self, genome.to(self.body.device))


class FlyRun:
    """One trading window for a population: every fly's brain state carries from candle to candle."""

    def __init__(self, agent: TribeAgent, genome: Genome):
        self.agent, self.genome = agent, genome
        self.h = agent.body.rest(genome.population)
        self.previous: torch.Tensor | None = None

    @torch.no_grad()
    def decide(self, chart: np.ndarray, position: np.ndarray) -> np.ndarray:
        """chart (64, 64) float in [0, 1], position (P,) 0 flat / 1 long -> (P,) int8 HOLD/BUY/SELL."""
        body, stats, genome = self.agent.body, self.agent.stats, self.genome
        chart_t = chart_tensor(chart, body.device)
        position_t = position_tensor(position, genome.population, body.device)
        self.h = body.think(self.h, body.drive(chart_t, self.previous, position_t, genome))
        self.previous = chart_t
        z = stats.standardise(self.h[:, body.readout_idx])                                  # (P, R)
        logits = torch.baddbmm(genome.readout_b.unsqueeze(1), z.unsqueeze(1), genome.readout_w).squeeze(1)
        return logits.argmax(1).to(torch.int8).cpu().numpy()


def resting_state(brain: ConnectomeRNN) -> torch.Tensor:
    h = torch.zeros(1, brain.n, device=brain.w0.device)
    weights = brain.weights()
    for _ in range(REST_STEPS):
        h = brain.step(h, None, weights)
    return h[0]


def calibrate(body: Body, charts: np.ndarray) -> ReadoutStats:
    """Readout statistics from two probe flies with unit gains, one flat and one long, watching
    the calibration charts in order from the resting state."""
    charts = np.asarray(charts, dtype=np.float32)
    if charts.ndim != 3 or charts.shape[1:] != CHART_SHAPE or len(charts) < MIN_CALIBRATION_CHARTS:
        raise ValueError(f"calibration charts must have shape (T >= {MIN_CALIBRATION_CHARTS}, {CHART_SHAPE[0]}, "
                         f"{CHART_SHAPE[1]}), got {charts.shape}")
    probe = Genome.neutral(2, int(body.readout_idx.numel())).to(body.device)
    position = torch.tensor([0.0, 1.0], device=body.device)
    h, previous, samples = body.rest(2), None, []
    for chart in charts:
        chart_t = chart_tensor(chart, body.device)
        h = body.think(h, body.drive(chart_t, previous, position, probe))
        samples.append(h[:, body.readout_idx])
        previous = chart_t
    activity = torch.cat(samples)
    return ReadoutStats(activity.mean(0), activity.std(0).clamp_min(MIN_STD))


def chart_tensor(chart: np.ndarray, device: torch.device) -> torch.Tensor:
    chart = np.asarray(chart, dtype=np.float32)
    if chart.shape != CHART_SHAPE:
        raise ValueError(f"chart must have shape {CHART_SHAPE}, got {chart.shape}")
    if not (np.isfinite(chart).all() and chart.min() >= 0.0 and chart.max() <= 1.0):
        raise ValueError("chart values must be finite and within [0, 1]")
    return torch.from_numpy(chart).to(device)


def position_tensor(position: np.ndarray, population: int, device: torch.device) -> torch.Tensor:
    position = np.asarray(position)
    if position.shape != (population,):
        raise ValueError(f"position must have shape ({population},), got {position.shape}")
    if not np.isin(position, (0, 1)).all():
        raise ValueError("position flags must be 0 (flat) or 1 (long)")
    return torch.from_numpy(position.astype(np.float32)).to(device)
