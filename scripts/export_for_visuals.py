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
CONTRACT_VERSION = 3        # v3 = v2 + validation, fee-free and finale blocks, all optional
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
    """One entry per fly, in log order. A run with validation days adds each fly's validation
    equity, so a visual can show a fly that is good on the days it was selected on and poor on
    the days it never saw."""
    out = []
    for fly in log["tribes"][tribe]["flies"]:
        seat = {"equity": round(float(fly["final_equity"]), 2), "eliminated": bool(fly["eliminated"]),
                "trades_per_day": round(float(fly["trades_per_day"]), 2)}
        if "validation_final_equity" in fly:
            seat["validation_equity"] = round(float(fly["validation_final_equity"]), 2)
        out.append(seat)
    return out


def tribe_frame(summary: dict, log: dict, tribe: str) -> dict:
    digest = summary["tribes"][tribe]
    return {"survived": digest["survived"], "eliminated": digest["eliminated"],
            "equity": {k: digest["final_equity"][k] for k in ("best", "median", "mean", "worst")},
            "fitness": {k: digest["fitness"][k] for k in ("best", "median")},
            "trades": {k: digest["trades"][k] for k in ("median_per_day", "max_per_day", "total")},
            "flies": seats(log, tribe)} | side_blocks(digest)


def side_blocks(digest: dict) -> dict:
    """The fee-free and validation scores a run logged beside the one selection used."""
    out = {}
    if "fee_free" in digest:
        out["fee_free"] = {"fitness": {k: digest["fee_free"]["fitness"][k] for k in ("best", "median")},
                           "equity": {k: digest["fee_free"]["final_equity"][k] for k in ("best", "median")}}
    if "validation" in digest:
        v = digest["validation"]
        out["validation"] = {"fitness": {k: v["fitness"][k] for k in ("best", "median", "mean")},
                             "equity": {k: v["final_equity"][k] for k in ("best", "median")},
                             "survivors_median_fitness": v["survivors_median_fitness"],
                             "trades": {"median_per_day": v["trades"]["median_per_day"]}}
    return out


def hero_frame(summary: dict, tribe: str) -> dict:
    hero = summary["tribes"][tribe]["hero_lineage"]
    per_day = next((f["trades_per_day"] for f in summary["tribes"][tribe]["top"] if f["id"] == hero["id"]), 0)
    return {"id": hero["id"], "born": hero["born"], "origin": hero["origin"],
            "generations_lived": hero["generations_lived"], "ancestors": list(hero["ancestors"]),
            "equity": hero["final_equity"], "fitness": hero["fitness"], "trades_per_day": per_day} | (
            {"validation_fitness": hero["validation_fitness"], "validation_equity": hero["validation_final_equity"]}
            if "validation_fitness" in hero else {})


def newborn(log: dict, tribe: str, generation: int) -> dict:
    """How this generation's flies came to be: founders, children of last generation's
    survivors, and newcomers - counted from each fly's own record, for the Nursery."""
    counts = {"founder": 0, "child": 0, "newcomer": 0, "survivor": 0}
    for fly in log["tribes"][tribe]["flies"]:
        counts[fly["origin"] if fly["born"] == generation else "survivor"] += 1
    return counts


def frame_of(summary: dict, log: dict) -> dict:
    g = summary["generation"]
    tribes = {t: tribe_frame(summary, log, t) | {"born": newborn(log, t, g)} for t in TRIBES}
    return {"generation": summary["generation"],
            "tribes": tribes,
            "heroes": {t: hero_frame(summary, t) for t in TRIBES}}


def window_of(day: dict, evolve: pd.DataFrame | None) -> dict:
    out = {k: day[k] for k in ("first_time", "last_time", "price_move_pct")}
    if evolve is not None:
        out["candles"] = candles_for(evolve, day)
    return out


FINALE_POINTS = 480          # the finale's equity curves, thinned to this many points each


def thin(curve: list[float], points: int = FINALE_POINTS) -> list[float]:
    step = max(1, len(curve) // points)
    out = curve[::step]
    if out[-1] != curve[-1]:
        out = out + [curve[-1]]
    return [round(float(v), 2) for v in out]


def finale_block(path: Path, rehearsal: bool = False) -> dict | None:
    """The finale as the visuals need it: every trader's final equity and its equity curve,
    thinned, in each pass. Reads the merged finale.json, or the flies' half alone if the merge
    has not happened. The run it came from is recorded, because it need not be the run the rest
    of the file replays."""
    tag = "_rehearsal" if rehearsal else ""
    merged = path / f"finale{tag}.json"
    half = path / f"finale_flies{tag}.json"
    source = merged if merged.exists() else half if half.exists() else None
    if source is None:
        return None
    raw = json.loads(source.read_text())
    passes = {}
    for label, block in raw["passes"].items():
        out = {"fee_bps": block["fee_bps"], "bars_between_decisions": block.get("bars_between_decisions", 1),
               "traders": {}}
        for tribe, rows in block.get("tribes", {}).items():
            out["traders"][f"{tribe}_champions"] = {
                "final_equity": round(float(np.mean(rows["final_equity"])), 2),
                "each": rows["final_equity"], "trades": rows["trades"], "ids": rows["ids"],
                "curve": thin(rows["mean_equity"])}
        for name, row in block.get("competitors", {}).items():
            out["traders"][name] = {"final_equity": row["final_equity"], "trades": row.get("trades"),
                                    "curve": thin(row["equity"])}
            if "replies" in row:                       # what the model actually said
                out["traders"][name]["replies"] = row["replies"]
        passes[label] = out
    return {"run": raw["run"], "generation": raw["generation"], "rehearsal": raw.get("rehearsal", False),
            "data": raw["data"], "bars": raw["bars"], "first_time": raw["first_time"],
            "last_time": raw["last_time"], "parts": raw.get("parts", ["flies"]),
            "llm": raw.get("llm"), "passes": passes, "source": source.name}


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
    p.add_argument("--finale", type=Path, default=None,
                   help="a run directory holding finale.json (default: --run's own, if it has one)")
    p.add_argument("--finale-rehearsal", action="store_true",
                   help="use the finale's rehearsal files, to build the finale visuals before the real one exists")
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
    if manifest.get("validation_windows"):
        payload["validation_windows"] = [window_of(day, evolve) for day in manifest["validation_windows"]]
        payload["validation_competitor_results"] = manifest.get("validation_competitors", {})
    finale = finale_block(args.finale or args.run, args.finale_rehearsal)
    if finale:
        payload["finale"] = finale
    check(payload)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload) + "\n")
    last = frames[-1]
    print(f"{args.out} : {len(frames)} generations, {len(payload['windows'])} fixed days, "
          f"{payload['population']} flies a tribe, {args.out.stat().st_size / 1024:.0f} KB")
    extras = [k for k in ("validation_windows", "finale") if k in payload]
    if extras:
        print(f"with {', '.join(extras)}" + (f" (finale from {payload['finale']['run']}, "
              f"{payload['finale']['source']})" if "finale" in payload else ""))
    print(f"last generation {last['generation']}: real best ${last['tribes']['real']['equity']['best']:,.2f}, "
          f"scrambled best ${last['tribes']['scrambled']['equity']['best']:,.2f}, "
          f"hero {last['heroes']['real']['id']} with {len(last['heroes']['real']['ancestors'])} ancestors")


if __name__ == "__main__":
    main()
