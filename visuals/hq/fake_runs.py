"""A believable fake runs.json, so the HQ can be built before a real run finishes.

    uv run python -m visuals.hq.fake_runs

Shapes and ranges follow visuals/hq/data-contract.md and the real day-3 and day-4 runs: 100
flies a tribe, most of them finishing within a few percent of $1,000, a real tribe that pulls
ahead slowly, competitors that mostly lose, and a hero lineage whose chain grows as founders
are replaced by their children. The FLIES are invented - the file says so, and
`scripts/export_for_visuals.py` writes the real thing - but the market is not: each generation
is a real day of the evolve set, with its real candles and its real move.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from market import load_evolve
from market.chart import WINDOW
from scripts.export_for_visuals import BARS_PER_CANDLE, candles_for

HERE = Path(__file__).resolve().parent
GENERATIONS, POPULATION = 40, 100
START_CASH, BROKE_BELOW = 1000.0, 500.0
TRIBES = ("real", "scrambled")
COMPETITORS = ("momentum", "random", "buy_and_hold")
EDGE = {"real": 0.00045, "scrambled": 0.00018}      # fitness the tribe gains per generation
SPREAD = 0.022                                      # how far flies scatter around their tribe
RUIN_EARLY, RUIN_LATE = 0.09, 0.01                  # share of flies wiped out, first and last generation


def fly_equities(rng: np.random.Generator, centre: float, population: int, ruin: float) -> np.ndarray:
    """A tribe's flies: a fat-ish tail down, because a bad day compounds, plus a few flies that
    went long into a fall and are wiped out. `ruin` is the share that come to grief, which
    shrinks as selection weeds out the flies that trade themselves to death."""
    draw = rng.normal(centre, SPREAD, population) - rng.exponential(0.006, population)
    equity = START_CASH * np.exp(draw)
    wiped = rng.random(population) < ruin
    equity[wiped] = rng.uniform(0.34, 0.62, int(wiped.sum())) * START_CASH
    return np.round(equity, 2)


def main() -> None:
    rng = np.random.default_rng(7)
    evolve = load_evolve()
    closes, opens = evolve["close"].to_numpy(), evolve["open"].to_numpy()
    lineage = {t: {"id": f"{t}-f{rng.integers(0, 100):05d}", "born": 0, "origin": "founder",
                   "ancestors": [], "minted": 100} for t in TRIBES}
    frames = []

    for generation in range(GENERATIONS):
        first = int(rng.integers(WINDOW - 1, len(evolve) - 288 - 2))
        last = first + 287
        entry, exit_ = float(opens[first + 1]), float(closes[last + 1])
        move = round(100 * (exit_ / entry - 1), 4)
        real_window = {"first_index": first, "last_index": last, "entry_price": round(entry, 2)}
        frame = {"generation": generation,
                 "window": {"first_time": evolve["timestamp"].iloc[first].isoformat(),
                            "last_time": evolve["timestamp"].iloc[last + 1].isoformat(),
                            "price_move_pct": move,
                            "candles": candles_for(evolve, real_window)},
                 "tribes": {}, "competitors": {}, "heroes": {}}

        for tribe in TRIBES:
            centre = EDGE[tribe] * generation + move / 400
            ruin = RUIN_EARLY + (RUIN_LATE - RUIN_EARLY) * generation / max(1, GENERATIONS - 1)
            equity = fly_equities(rng, centre, POPULATION, ruin * (1.0 if tribe == "real" else 1.6))
            broke = equity < BROKE_BELOW
            trades = rng.integers(0, 60 if tribe == "real" else 120, POPULATION)
            fitness = np.log(np.maximum(equity, 1e-9) / START_CASH)
            frame["tribes"][tribe] = {
                "alive": int((~broke).sum()), "broke": int(broke.sum()),
                "equity": {"best": float(equity.max()), "median": float(np.median(equity)),
                           "mean": float(np.round(equity.mean(), 2)), "worst": float(equity.min())},
                "fitness": {"best": round(float(fitness.max()), 4), "median": round(float(np.median(fitness)), 4)},
                "trades": {"total": int(trades.sum()), "median": int(np.median(trades)), "max": int(trades.max())},
                "flies": [{"equity": float(e), "broke": bool(b), "trades": int(n)}
                          for e, b, n in zip(equity, broke, trades)],
            }

            # the hero: usually the same lineage another generation, sometimes a child of it
            book = lineage[tribe]
            if generation and rng.random() < 0.45:
                book["ancestors"] = (book["ancestors"] + [book["id"]])[-6:]
                book["id"] = f"{tribe}-f{book['minted']:05d}"
                book["minted"] += 1
                book["born"], book["origin"] = generation, "child"
            frame["heroes"][tribe] = {"id": book["id"], "born": book["born"], "origin": book["origin"],
                                      "generations_lived": generation - book["born"] + 1,
                                      "ancestors": list(book["ancestors"]),
                                      "equity": float(equity.max()),
                                      "fitness": round(float(fitness.max()), 4),
                                      "trades": int(trades.max())}

        for name in COMPETITORS:
            drift = {"momentum": -0.028, "random": -0.035, "buy_and_hold": 0.0}[name]
            frame["competitors"][name] = float(np.round(
                START_CASH * np.exp(rng.normal(drift, 0.012) + move / 150), 2))
        frames.append(frame)

    out = {"run_id": "fake", "generated": datetime.now(timezone.utc).isoformat(),
           "fake": True, "generations": GENERATIONS, "population": POPULATION,
           "bars_per_generation": 288, "bar_minutes": 5, "candle_minutes": 5 * BARS_PER_CANDLE,
           "start_cash": START_CASH,
           "broke_below": BROKE_BELOW, "fee_bps": 5.0, "min_hold_bars": 3,
           "tribes": list(TRIBES), "competitors": list(COMPETITORS), "frames": frames}
    path = HERE / "runs.json"
    path.write_text(json.dumps(out) + "\n")
    size = path.stat().st_size / 1024
    print(f"{path} : {GENERATIONS} generations, {POPULATION} flies a tribe, {size:.0f} KB")
    worst = min(f["tribes"]["real"]["broke"] for f in frames), max(f["tribes"]["real"]["broke"] for f in frames)
    print(f"real tribe broke per generation: {worst[0]} to {worst[1]}; "
          f"final best ${frames[-1]['tribes']['real']['equity']['best']:,.2f}")


if __name__ == "__main__":
    main()
