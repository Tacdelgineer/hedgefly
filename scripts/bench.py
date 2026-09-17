"""Milliseconds per brain step of the frozen MaleCNS connectome on the GPU.

    uv run scripts/bench.py
    uv run scripts/bench.py --subsets visual_small --populations 1 50 100 --steps 50

One brain step is one nfly `ConnectomeRNN.step` on a state of shape [population, N_neurons]:
the sparse recurrent product over every edge, bias, external drive on the afferent neurons,
ReLU, saturation and leak. The brain is built with no trainable gains, leaks or biases and
stepped under no_grad, the way evolution will use it (PLAN.md rule 1). Input encoding, readout
and the portfolio are not included.

The minutes-per-generation column assumes both tribes (real and scrambled, separate W) each
step their whole population through one window, one tribe after the other.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import time
from importlib.metadata import distribution
from pathlib import Path

import torch

from nfly import ConnectomeRNN, load_malecns, select_subset
from nfly.connectome import SUBSETS

REPO = Path(__file__).resolve().parents[1]
TRIBES = 2              # real + scrambled, never cut (PLAN.md rule 6)
BUDGET_MIN = 10.0       # PLAN.md speed budget per generation, both tribes combined


@dataclasses.dataclass
class Row:
    subset: str
    neurons: int
    edges: int
    population: int
    ms_per_step: float
    peak_gb: float

    def minutes_per_generation(self, candles: int, steps_per_candle: int) -> float:
        return TRIBES * candles * steps_per_candle * self.ms_per_step / 60_000

    def markdown(self, candles: int, steps_per_candle: int) -> str:
        minutes = self.minutes_per_generation(candles, steps_per_candle)
        verdict = "yes" if minutes <= BUDGET_MIN else "no"
        return (f"| {self.subset} | {self.neurons:,} | {self.edges:,} | {self.population} | "
                f"{self.ms_per_step:.2f} | {self.ms_per_step / self.population:.3f} | "
                f"{self.peak_gb:.2f} | {minutes:.2f} | {verdict} |")


def require_gpu() -> torch.device:
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available in this env; refusing to benchmark on CPU (PLAN.md SETUP)")
    return torch.device("cuda")


def nfly_commit() -> str:
    info = json.loads(distribution("nfly").read_text("direct_url.json") or "{}")
    return info.get("vcs_info", {}).get("commit_id", "unknown")


@torch.no_grad()
def ms_per_step(brain: ConnectomeRNN, inputs: torch.Tensor, population: int, args: argparse.Namespace) -> float:
    """Median over `repeats` of the mean wall time of `steps` consecutive steps."""
    device = brain.w0.device
    weights = brain.weights()
    u = torch.zeros(population, brain.n, device=device)
    u[:, inputs] = torch.rand(population, len(inputs), device=device)
    h = torch.zeros(population, brain.n, device=device)
    for _ in range(args.warmup):
        h = brain.step(h, u, weights)
    samples = []
    for _ in range(args.repeats):
        torch.cuda.synchronize(device)
        t0 = time.perf_counter()
        for _ in range(args.steps):
            h = brain.step(h, u, weights)
        torch.cuda.synchronize(device)             # kernels are async; stop the clock when they finish
        samples.append(1000 * (time.perf_counter() - t0) / args.steps)
    return statistics.median(samples)


def bench_subset(full, name: str, args: argparse.Namespace, device: torch.device) -> list[Row]:
    conn = select_subset(full, name)
    brain = ConnectomeRNN(conn, learn_gain=False, learn_alpha=False, learn_bias=False).to(device)
    assert brain.w0.is_cuda and not any(q.requires_grad for q in brain.parameters())
    inputs = conn.input_nodes().to(device)
    rows = []
    for population in args.populations:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
        ms = ms_per_step(brain, inputs, population, args)
        peak = torch.cuda.max_memory_allocated(device) / 2**30
        rows.append(Row(name, conn.n_neurons, conn.n_edges, population, ms, peak))
        print(f"  {name:>12} pop {population:>4}: {ms:8.2f} ms/step", flush=True)
    del brain
    torch.cuda.empty_cache()
    return rows


def print_table(rows: list[Row], args: argparse.Namespace, device: torch.device) -> None:
    print(f"\n{torch.cuda.get_device_name(device)}, torch {torch.version.__version__} (CUDA {torch.version.cuda}), "
          f"nfly {nfly_commit()[:12]}; median of {args.repeats} x {args.steps} steps after {args.warmup} warm-up")
    print(f"Generation estimate: {TRIBES} tribes x {args.candles} candles x {args.steps_per_candle} steps/candle; "
          f"budget {BUDGET_MIN:.0f} min\n")
    print("| Subset | Neurons | Edges | Population | ms / step | ms / step per fly | Peak GPU GB | Est. min / generation | Fits budget |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        print(row.markdown(args.candles, args.steps_per_candle))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", type=Path, default=REPO / "data", help="directory with the MaleCNS feather files")
    p.add_argument("--subsets", nargs="+", default=["all", "brain", "visual_small"], choices=list(SUBSETS))
    p.add_argument("--populations", nargs="+", type=int, default=[1, 100, 200])
    p.add_argument("--steps", type=int, default=20, help="timed steps per repeat")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--candles", type=int, default=336, help="candles per generation window (2 weeks of 1h)")
    p.add_argument("--steps-per-candle", type=int, default=2)
    args = p.parse_args()

    device = require_gpu()
    full = load_malecns(args.data)
    rows = [row for name in args.subsets for row in bench_subset(full, name, args, device)]
    print_table(rows, args, device)


if __name__ == "__main__":
    main()
