"""The finale, part three: put the two halves on one chart.

    uv run python finale_merge.py --run runs/day4_full

`finale_flies.py` writes the champions and the mechanical competitors, `finale_llm.py` writes
the language model, each on its own hardware and in its own time. This reads both part files
and writes `runs/<run>/finale.json`, the single file the visuals and the video read.

It refuses to merge halves that did not trade the same bars, because two traders judged on
different data are not a race. It never opens the locked test set itself: the parts already
carry every number, which is rule 8 (a viewer's numbers come from the logs) doing its job.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from evolve.logs import write_json
from finale_shared import PASSES, TRIBES, part_path

MUST_MATCH = ("run", "bars", "first_time", "last_time", "data", "rehearsal")


def read_part(run_dir: Path, name: str, rehearsal: bool) -> dict | None:
    path = part_path(run_dir, name, rehearsal)
    return json.loads(path.read_text()) if path.exists() else None


def agree(flies: dict, llm: dict) -> None:
    """Both halves must have traded the same bars of the same data."""
    wrong = {k: (flies.get(k), llm.get(k)) for k in MUST_MATCH if flies.get(k) != llm.get(k)}
    if wrong:
        raise SystemExit("the two halves did not trade the same thing: "
                         + "; ".join(f"{k}: flies {a!r} vs llm {b!r}" for k, (a, b) in wrong.items()))


def merge(flies: dict, llm: dict | None) -> dict:
    out = {k: flies[k] for k in ("run", "generation", "rehearsal", "data", "bars",
                                 "first_time", "last_time", "entry_price", "exit_price")}
    out["champions_per_tribe"] = flies["champions_per_tribe"]
    out["merged"] = datetime.now(timezone.utc).isoformat()
    out["parts"] = ["flies"] + (["llm"] if llm else [])
    if llm:
        out["llm"] = {"model": llm["model"], "bars_between_decisions": llm["bars_between_decisions"]}
    out["passes"] = {}
    for label, _ in PASSES:
        one = flies["passes"][label]
        joined = {"fee_bps": one["fee_bps"], "min_hold_bars": one["min_hold_bars"],
                  "tribes": one["tribes"], "competitors": dict(one["competitors"])}
        if llm:
            joined["competitors"].update(llm["passes"][label]["competitors"])
        out["passes"][label] = joined
    return out


def table(merged: dict) -> None:
    with_fees, no_fees = merged["passes"]["with_fees"], merged["passes"]["no_fees"]
    print("\n| trader | with fees | no fees | what the fees cost |")
    print("| --- | --- | --- | --- |")
    for name in TRIBES:
        a = float(np.mean(with_fees["tribes"][name]["final_equity"]))
        b = float(np.mean(no_fees["tribes"][name]["final_equity"]))
        print(f"| {name} champions (mean of {merged['champions_per_tribe']}) | ${a:,.2f} | ${b:,.2f} | ${b - a:,.2f} |")
    for name in with_fees["competitors"]:
        a = with_fees["competitors"][name]["final_equity"]
        b = no_fees["competitors"].get(name, {}).get("final_equity", float("nan"))
        print(f"| {name} | ${a:,.2f} | ${b:,.2f} | ${b - a:,.2f} |")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--rehearsal", action="store_true", help="merge the rehearsal parts instead")
    p.add_argument("--allow-missing-llm", action="store_true",
                   help="write the chart with the flies alone")
    args = p.parse_args()

    flies = read_part(args.run, "flies", args.rehearsal)
    if flies is None:
        raise SystemExit(f"{part_path(args.run, 'flies', args.rehearsal)} is missing; run finale_flies.py first")
    llm = read_part(args.run, "llm", args.rehearsal)
    if llm is None and not args.allow_missing_llm:
        raise SystemExit(f"{part_path(args.run, 'llm', args.rehearsal)} is missing; run finale_llm.py, "
                         f"or pass --allow-missing-llm to chart the flies alone")
    if llm:
        agree(flies, llm)

    merged = merge(flies, llm)
    name = "finale_rehearsal.json" if args.rehearsal else "finale.json"
    print(f"merged {' + '.join(merged['parts'])} -> {write_json(args.run / name, merged)}")
    table(merged)


if __name__ == "__main__":
    main()
