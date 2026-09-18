"""Turn a run's logs into the one file the HQ reads (visuals/hq/data-contract.md).

    uv run python -m scripts.export_for_visuals --run runs/day4_full
    uv run python -m scripts.export_for_visuals --run runs/day4_full --out visuals/hq/runs.json

The visuals replay logs and never re-run the simulation (PLAN.md rule 7), and every number
they show comes out of those logs (rule 8). This is the only bridge between the two: it reads
`gen_XXX_summary.json` for the tribe figures and `gen_XXX.json` for the per-fly seats the
Trading Floor lights up, and writes one compact JSON the browser can hold in memory.

It never opens the locked test set; the finale writes its own file.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "visuals" / "hq" / "runs.json"
TRIBES = ("real", "scrambled")
COMPETITORS = ("momentum", "random", "buy_and_hold")


def generations(run_dir: Path) -> list[tuple[Path, Path]]:
    """(summary, full log) per generation, in order. A generation without both is skipped."""
    pairs = []
    for summary in sorted(run_dir.glob("gen_[0-9][0-9][0-9]_summary.json")):
        full = run_dir / summary.name.replace("_summary", "")
        if full.exists():
            pairs.append((summary, full))
    if not pairs:
        raise SystemExit(f"no finished generations in {run_dir}")
    return pairs


def seats(log: dict, tribe: str) -> list[dict]:
    """One entry per fly, in log order, which is desk order on the Trading Floor."""
    return [{"equity": round(float(fly["final_equity"]), 2), "broke": bool(fly["broke"]),
             "trades": int(fly["trades"])}
            for fly in log["tribes"][tribe]["flies"]]


def tribe_frame(summary: dict, log: dict, tribe: str) -> dict:
    digest = summary["tribes"][tribe]
    return {"alive": digest["alive"], "broke": digest["broke"],
            "equity": {k: digest["final_equity"][k] for k in ("best", "median", "mean", "worst")},
            "fitness": {k: digest["fitness"][k] for k in ("best", "median")},
            "trades": {k: digest["trades"][k] for k in ("total", "median", "max")},
            "flies": seats(log, tribe)}


def hero_frame(summary: dict, tribe: str) -> dict:
    hero = summary["tribes"][tribe]["hero_lineage"]
    return {"id": hero["id"], "born": hero["born"], "origin": hero["origin"],
            "generations_lived": hero["generations_lived"], "ancestors": list(hero["ancestors"]),
            "equity": hero["final_equity"], "fitness": hero["fitness"],
            "trades": next((f["trades"] for f in summary["tribes"][tribe]["top"]
                            if f["id"] == hero["id"]), 0)}


def frame_of(summary: dict, log: dict) -> dict:
    return {"generation": summary["generation"],
            "window": {k: summary["window"][k] for k in ("first_time", "last_time", "price_move_pct")},
            "tribes": {t: tribe_frame(summary, log, t) for t in TRIBES},
            "competitors": {name: summary["competitors"][name]["final_equity"]
                            for name in COMPETITORS if name in summary["competitors"]},
            "heroes": {t: hero_frame(summary, t) for t in TRIBES}}


def check(payload: dict) -> None:
    """The contract's invariants, verified here rather than discovered in the browser."""
    population = payload["population"]
    for frame in payload["frames"]:
        for tribe, rows in frame["tribes"].items():
            where = f"generation {frame['generation']} / {tribe}"
            if len(rows["flies"]) != population:
                raise SystemExit(f"{where}: {len(rows['flies'])} flies, expected {population}")
            if rows["alive"] + rows["broke"] != population:
                raise SystemExit(f"{where}: alive {rows['alive']} + broke {rows['broke']} != {population}")
            dead = sum(1 for f in rows["flies"] if f["broke"])
            if dead != rows["broke"]:
                raise SystemExit(f"{where}: {dead} flies marked broke but the summary says {rows['broke']}")
            hero = frame["heroes"][tribe]
            if hero["id"] in hero["ancestors"]:
                raise SystemExit(f"{where}: {hero['id']} is its own ancestor")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, required=True, help="a run directory under runs/")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    manifest = json.loads((args.run / "manifest.json").read_text())
    config = manifest["config"]
    frames = []
    for summary_path, log_path in generations(args.run):
        frames.append(frame_of(json.loads(summary_path.read_text()), json.loads(log_path.read_text())))

    payload = {"run_id": manifest["run_id"], "generated": datetime.now(timezone.utc).isoformat(),
               "generations": len(frames), "population": config["population"],
               "bars_per_generation": config["bars"],
               "bar_minutes": manifest["data"]["granularity_seconds"] // 60,
               "start_cash": config["start_cash"], "broke_below": 500.0,
               "fee_bps": config["fee_bps"], "min_hold_bars": config["min_hold_bars"],
               "tribes": list(TRIBES), "competitors": list(COMPETITORS), "frames": frames}
    check(payload)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload) + "\n")
    last = frames[-1]
    print(f"{args.out} : {len(frames)} generations, {payload['population']} flies a tribe, "
          f"{args.out.stat().st_size / 1024:.0f} KB")
    print(f"last generation {last['generation']}: real best ${last['tribes']['real']['equity']['best']:,.2f}, "
          f"scrambled best ${last['tribes']['scrambled']['equity']['best']:,.2f}, "
          f"hero {last['heroes']['real']['id']} with {len(last['heroes']['real']['ancestors'])} ancestors")


if __name__ == "__main__":
    main()
