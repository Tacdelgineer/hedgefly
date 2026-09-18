"""Turn a run's logs into the one file the visuals read (visuals/hq/data-contract.md, v2).

    uv run python -m scripts.export_for_visuals --run runs/day6_full
    uv run python -m scripts.export_for_visuals --run runs/day6_full --out visuals/hq/runs.json

The visuals replay logs and never re-run the simulation (PLAN.md rule 7), and every number
they show comes out of those logs (rule 8). This is the only bridge between the two: it reads
the run's manifest for the four fixed days and the competitors, `gen_XXX_summary.json` for the
tribe figures, and `gen_XXX.json` for each fly's equity and whether it was eliminated.

The candlesticks are the real bars of each fixed day: the manifest logs each day's first and
last bar index, and the evolve set is read at exactly those rows. Before trusting the indices
it checks that the bar after the first one opens at the entry price the run logged, so a
re-fetched data file whose rows have moved is caught here instead of charting the wrong day.

It never opens the locked test set; the finale writes its own file.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from market import load_evolve

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "visuals" / "hq" / "runs.json"
CONTRACT_VERSION = 2
TRIBES = ("real", "scrambled")
COMPETITORS = ("momentum", "random", "buy_and_hold")
BARS_PER_CANDLE = 6         # 288 five-minute bars -> 48 thirty-minute candles a day
PRICE_TOLERANCE = 0.01      # dollars: the logged entry price is rounded to cents


def candles_for(evolve: pd.DataFrame, window: dict, per: int = BARS_PER_CANDLE) -> list[list[float]]:
    """A day's decision bars as [open, high, low, close] candles of `per` bars each.

    Checks the indices against the price the run logged first: the bar after the day's first
    one is where the flies' first trade filled, so its open must be the logged entry price."""
    first, last = int(window["first_index"]), int(window["last_index"])
    filled = float(evolve["open"].iloc[first + 1])
    if abs(filled - float(window["entry_price"])) > PRICE_TOLERANCE:
        raise SystemExit(f"bar {first + 1} opens at {filled}, but the run logged an entry price of "
                         f"{window['entry_price']}: the evolve file is not the one this run traded")
    bars = evolve.iloc[first:last + 1]
    group = np.arange(len(bars)) // per
    agg = bars.groupby(group).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
    return [[round(float(r.o), 2), round(float(r.h), 2), round(float(r.l), 2), round(float(r.c), 2)]
            for r in agg.itertuples()]


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
    """One entry per fly, in log order."""
    return [{"equity": round(float(fly["final_equity"]), 2), "eliminated": bool(fly["eliminated"]),
             "trades_per_day": round(float(fly["trades_per_day"]), 2)}
            for fly in log["tribes"][tribe]["flies"]]


def tribe_frame(summary: dict, log: dict, tribe: str) -> dict:
    digest = summary["tribes"][tribe]
    return {"survived": digest["survived"], "eliminated": digest["eliminated"],
            "equity": {k: digest["final_equity"][k] for k in ("best", "median", "mean", "worst")},
            "fitness": {k: digest["fitness"][k] for k in ("best", "median")},
            "trades": {k: digest["trades"][k] for k in ("median_per_day", "max_per_day", "total")},
            "flies": seats(log, tribe)}


def hero_frame(summary: dict, tribe: str) -> dict:
    hero = summary["tribes"][tribe]["hero_lineage"]
    per_day = next((f["trades_per_day"] for f in summary["tribes"][tribe]["top"] if f["id"] == hero["id"]), 0)
    return {"id": hero["id"], "born": hero["born"], "origin": hero["origin"],
            "generations_lived": hero["generations_lived"], "ancestors": list(hero["ancestors"]),
            "equity": hero["final_equity"], "fitness": hero["fitness"], "trades_per_day": per_day}


def frame_of(summary: dict, log: dict) -> dict:
    return {"generation": summary["generation"],
            "tribes": {t: tribe_frame(summary, log, t) for t in TRIBES},
            "heroes": {t: hero_frame(summary, t) for t in TRIBES}}


def window_of(day: dict, evolve: pd.DataFrame | None) -> dict:
    out = {k: day[k] for k in ("first_time", "last_time", "price_move_pct")}
    if evolve is not None:
        out["candles"] = candles_for(evolve, day)
    return out


def check(payload: dict) -> None:
    """The contract's invariants, verified here rather than discovered in the browser."""
    population = payload["population"]
    for frame in payload["frames"]:
        for tribe, rows in frame["tribes"].items():
            where = f"generation {frame['generation']} / {tribe}"
            if len(rows["flies"]) != population:
                raise SystemExit(f"{where}: {len(rows['flies'])} flies, expected {population}")
            if rows["survived"] + rows["eliminated"] != population:
                raise SystemExit(f"{where}: survived {rows['survived']} + eliminated {rows['eliminated']} "
                                 f"!= {population}")
            marked = sum(1 for f in rows["flies"] if f["eliminated"])
            if marked != rows["eliminated"]:
                raise SystemExit(f"{where}: {marked} flies marked eliminated but the summary says "
                                 f"{rows['eliminated']}")
            hero = frame["heroes"][tribe]
            if hero["id"] in hero["ancestors"]:
                raise SystemExit(f"{where}: {hero['id']} is its own ancestor")
    for k, window in enumerate(payload["windows"]):
        for o, h, l, c in window.get("candles", []):
            if not (h >= max(o, c) and l <= min(o, c)):
                raise SystemExit(f"day {k}: a candle whose high and low do not contain its open and "
                                 f"close ({o}, {h}, {l}, {c})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, required=True, help="a run directory under runs/")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    manifest = json.loads((args.run / "manifest.json").read_text())
    if "windows" not in manifest:
        raise SystemExit(f"{args.run} predates the fixed days (contract v1); this exporter writes v2")
    config = manifest["config"]
    evolve = load_evolve()
    frames = [frame_of(json.loads(s.read_text()), json.loads(g.read_text())) for s, g in generations(args.run)]
    minutes = manifest["data"]["granularity_seconds"] // 60

    payload = {"contract_version": CONTRACT_VERSION, "run_id": manifest["run_id"],
               "generated": datetime.now(timezone.utc).isoformat(),
               "generations": len(frames), "population": config["population"],
               "survive_share": config["survive_share"], "bars_per_window": config["bars"],
               "bar_minutes": minutes, "candle_minutes": minutes * BARS_PER_CANDLE,
               "start_cash": config["start_cash"], "fee_bps": config["fee_bps"],
               "min_hold_bars": config["min_hold_bars"],
               "tribes": list(TRIBES), "competitors": list(COMPETITORS),
               "windows": [window_of(day, evolve) for day in manifest["windows"]],
               "competitor_results": {n: manifest["competitors"][n] for n in COMPETITORS},
               "frames": frames}
    check(payload)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload) + "\n")
    last = frames[-1]
    print(f"{args.out} : {len(frames)} generations, {len(payload['windows'])} fixed days, "
          f"{payload['population']} flies a tribe, {args.out.stat().st_size / 1024:.0f} KB")
    print(f"last generation {last['generation']}: real best ${last['tribes']['real']['equity']['best']:,.2f}, "
          f"scrambled best ${last['tribes']['scrambled']['equity']['best']:,.2f}, "
          f"hero {last['heroes']['real']['id']} with {len(last['heroes']['real']['ancestors'])} ancestors")


if __name__ == "__main__":
    main()
