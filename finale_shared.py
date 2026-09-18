"""The parts of the finale that are the same whoever is trading.

The finale is two scripts: `finale_flies.py` puts the champions and the three mechanical
competitors on the GPU, `finale_llm.py` walks the local language model through the same bars.
They run separately because they want different hardware, they each write their own part file,
and `finale_merge.py` puts the parts on one chart.

Nothing in here opens the last six months. Rule 3 checks the name of the calling file, so each
finale script makes that one call itself, in its own module, spelled out - and the guard test
greps this file too, which is why it does not even name the loader.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from brain import Genome, TribeAgent, build_eye, scramble
from brain.agent import MIN_CALIBRATION_CHARTS
from evolve.logs import EQUITY_PLACES, rounded, write_json
from market import FEE_BPS, MIN_HOLD_BARS, START_CASH, Wallet, load_evolve, render_range, trade_window
from market.chart import WINDOW

TOP_N = 10                  # champions per tribe (PLAN.md FINALE)
TRIBES = ("real", "scrambled")
PASSES = (("with_fees", None), ("no_fees", 0.0))    # None means "whatever --fee-bps says"
HOURLY = 12                 # five-minute bars in an hour
# The flies' extra pass: decisions once an hour, real fees, so they can be charted against the
# language model, which is only ever asked hourly.
HOURLY_PASS = "hourly_with_fees"


@dataclasses.dataclass(frozen=True)
class Champions:
    tribe: str
    genome: Genome
    flies: list[dict]

    @property
    def ids(self) -> list[str]:
        return [f["id"] for f in self.flies]


def common_args(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The arguments both finale scripts must agree on, so the two parts describe one race."""
    p.add_argument("--run", type=Path, required=True, help="the finished run directory under runs/")
    p.add_argument("--fee-bps", type=float, default=FEE_BPS, help="first pass, per side")
    p.add_argument("--min-hold-bars", type=int, default=MIN_HOLD_BARS)
    p.add_argument("--rehearse", type=int, default=0,
                   help="trade the last N bars of the EVOLVE set instead of the locked one")
    p.add_argument("--seed", type=int, default=0)
    return p


def last_generation(run_dir: Path) -> tuple[int, dict]:
    logs = sorted(run_dir.glob("gen_[0-9][0-9][0-9].json"))
    if not logs:
        raise SystemExit(f"no generation logs in {run_dir}; has the run finished?")
    return int(logs[-1].stem.split("_")[1]), json.loads(logs[-1].read_text())


def champions_of(log: dict, tribe: str, top_n: int = TOP_N) -> Champions:
    """The `top_n` fittest flies of a tribe, rebuilt from the generation log, so the finale
    runs the flies the logs say won. The logs round a gene to five decimals; that quantisation
    is what the champions carry into the test."""
    rows = log["tribes"][tribe]
    order = sorted(range(len(rows["flies"])), key=lambda i: rows["flies"][i]["fitness"], reverse=True)
    picked = order[:top_n]
    genes = rows["genomes"]
    genome = Genome(chart_gain=torch.tensor([genes["chart_gain"][i] for i in picked], dtype=torch.float32),
                    position_gain=torch.tensor([genes["position_gain"][i] for i in picked], dtype=torch.float32),
                    readout_w=torch.tensor([genes["readout_w"][i] for i in picked], dtype=torch.float32))
    return Champions(tribe, genome, [rows["flies"][i] for i in picked])


def calibration_charts() -> np.ndarray:
    """The same calibration charts evolution used, from the evolve set only (rule 3)."""
    candles = load_evolve()
    return render_range(candles, WINDOW - 1, WINDOW - 2 + MIN_CALIBRATION_CHARTS)


def build_agents(calibration: np.ndarray, device: str, data_dir: str, scramble_seed: int) -> dict[str, TribeAgent]:
    """Both tribes as evolution built them: same steps per bar, same scramble seed, and the eye
    layout from the REAL connectome for both."""
    from nfly import load_malecns
    conn = load_malecns(data_dir)
    eye = build_eye(conn)
    wiring = {"real": conn, "scrambled": scramble(conn, seed=scramble_seed)}
    return {name: TribeAgent.build(w, calibration, device=device, eye=eye) for name, w in wiring.items()}


def acting_every(decide, first: int, every: int):
    """A decision function that is only acted on every `every` bars and holds in between.

    The brain is still called on EVERY bar: it is a continuously running animal, and the
    champions evolved with a running vote average measured in five-minute bars. Showing it one
    chart an hour instead would put them in a world they never evolved in and confuse cadence
    with a change of scenery. What changes is only how often they may act - which is exactly
    the concession the language model gets."""
    if every <= 1:
        return decide
    bar = {"t": first}

    def hourly(chart, positions):
        t = bar["t"]
        bar["t"] += 1
        actions = decide(chart, positions)                        # the brain sees this bar
        return actions if (t - first) % every == 0 else np.zeros_like(actions)   # HOLD is 0
    return hourly


def trade_champions(agent: TribeAgent, champs: Champions, candles: pd.DataFrame, first: int, last: int,
                    fee_bps: float, min_hold_bars: int, every: int = 1) -> dict:
    wallet = Wallet(champs.genome.population, fee_bps=fee_bps, min_hold_bars=min_hold_bars)
    decide = acting_every(agent.start(champs.genome).decide, first, every)
    result = trade_window(decide, candles, first, last, wallet)
    return {"ids": champs.ids,
            "final_equity": [round(float(e), EQUITY_PLACES) for e in result.final_equity],
            "trades": [int(t) for t in result.trades],
            "broke": [bool(b) for b in result.broke],
            "held_back": [int(h) for h in wallet.held_back],
            "equity": rounded(result.equity, EQUITY_PLACES),
            "mean_equity": rounded(result.equity.mean(axis=1), EQUITY_PLACES),
            "flies": champs.flies}


def window_of(candles: pd.DataFrame) -> tuple[int, int]:
    """Every bar the file has: the first needs 63 bars of chart behind it, the last needs a
    bar after it to fill at."""
    return WINDOW - 1, len(candles) - 2


def check_run(run_dir: Path, scramble_seed: int) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if manifest["config"]["scramble_seed"] != scramble_seed:
        raise SystemExit(f"this run scrambled with seed {manifest['config']['scramble_seed']}, "
                         f"not {scramble_seed}; the champions would meet a different opponent")
    return manifest


def part_path(run_dir: Path, name: str, rehearsal: bool) -> Path:
    return run_dir / f"finale_{name}{'_rehearsal' if rehearsal else ''}.json"


def write_part(run_dir: Path, name: str, payload: dict, rehearsal: bool) -> Path:
    """One half of the finale. `finale_merge.py` puts the halves together."""
    return write_json(part_path(run_dir, name, rehearsal), payload)


def describe(candles: pd.DataFrame, first: int, last: int, where: str) -> dict:
    return {"data": where, "bars": int(last - first + 1),
            "first_time": candles["timestamp"].iloc[first].isoformat(),
            "last_time": candles["timestamp"].iloc[last + 1].isoformat(),
            "entry_price": round(float(candles["open"].iloc[first + 1]), 2),
            "exit_price": round(float(candles["close"].iloc[last + 1]), 2)}


def require_gpu(device: str) -> None:
    if device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA is not available; the finale does not run on CPU (PLAN.md SETUP)")
