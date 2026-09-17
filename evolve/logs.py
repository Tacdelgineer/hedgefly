"""Where a run writes itself down (PLAN.md rule 7).

    runs/<run_id>/manifest.json      the configuration the run was started with
    runs/<run_id>/gen_XXX.json       everything: genomes, equity curves, actions, fitness
    runs/<run_id>/gen_XXX_summary.json   the compact digest the narrator and the visuals read

Rule 8: every number a viewer ever sees comes out of these files, so anything the story might
want has to be in them. Nothing here re-runs the simulation, and nothing downstream may.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

RUNS = Path(__file__).resolve().parents[1] / "runs"

EQUITY_PLACES = 2          # dollars and cents
GENE_PLACES = 5
FITNESS_PLACES = 6


def new_run_dir(run_id: str | None = None, root: Path = RUNS) -> Path:
    run_id = run_id or datetime.now(timezone.utc).strftime("run_%Y%m%d-%H%M%S")
    path = root / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def rounded(values, places: int) -> list:
    return np.round(np.asarray(values, dtype=float), places).tolist()


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=1, sort_keys=False, allow_nan=False) + "\n")
    return path


def write_manifest(run_dir: Path, manifest: dict) -> Path:
    return write_json(run_dir / "manifest.json", manifest)


def write_generation(run_dir: Path, generation: int, payload: dict) -> Path:
    return write_json(run_dir / f"gen_{generation:03d}.json", payload)


def write_summary(run_dir: Path, generation: int, summary: dict) -> Path:
    return write_json(run_dir / f"gen_{generation:03d}_summary.json", summary)
