"""A believable fake runs.json (data contract v2), so visuals can be built without a run.

    uv run python -m visuals.hq.fake_runs

The FLIES are invented - the file says `"fake": true` - but the market is not: the four fixed
days are real days of the evolve set, with their real candles and real moves, drawn the way a
run draws them. Fitness climbs slowly on those days, the real tribe a little faster, and every
generation the bottom 80% of each tribe is eliminated, as in a real run. Nothing here is a
measurement; `scripts/export_for_visuals.py` writes the real thing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from evolve.loop import Config, draw_fixed_windows, window_facts
from market import load_evolve
from scripts.export_for_visuals import BARS_PER_CANDLE, CONTRACT_VERSION, candles_for

HERE = Path(__file__).resolve().parent
GENERATIONS, POPULATION, SURVIVE = 40, 100, 0.2
START_CASH = 1000.0
TRIBES = ("real", "scrambled")
COMPETITORS = ("momentum", "random", "buy_and_hold")
CLIMB = {"real": 0.00030, "scrambled": 0.00018}     # fitness the best genomes gain per generation


def main() -> None:
    rng = np.random.default_rng(7)
    evolve = load_evolve()
    cfg = Config()
    days = [window_facts(evolve, first, last) for first, last in draw_fixed_windows(cfg, evolve)]
    lineage = {t: {"id": f"{t}-f{rng.integers(0, 100):05d}", "born": 0, "origin": "founder",
                   "ancestors": [], "minted": 100} for t in TRIBES}
    frames = []
    for generation in range(GENERATIONS):
        frame = {"generation": generation, "tribes": {}, "heroes": {}}
        for tribe in TRIBES:
            # the elite rise and the population closes in behind them
            elite = CLIMB[tribe] * generation
            spread = 0.02 * np.exp(-generation / 25) + 0.006
            fitness = rng.normal(elite - spread, spread, POPULATION)
            fitness[:int(SURVIVE * POPULATION)] = np.maximum(fitness[:int(SURVIVE * POPULATION)], elite)
            equity = np.round(START_CASH * np.exp(fitness), 2)
            order = np.argsort(-fitness, kind="stable")
            eliminated = np.ones(POPULATION, bool)
            eliminated[order[:int(SURVIVE * POPULATION)]] = False
            per_day = np.round(np.maximum(0, rng.normal(8 - generation * 0.1 * (tribe == "scrambled") - 4 * (tribe == "real"),
                                                           3, POPULATION)), 2)
            frame["tribes"][tribe] = {
                "survived": int((~eliminated).sum()), "eliminated": int(eliminated.sum()),
                "equity": {"best": float(equity.max()), "median": float(np.median(equity)),
                           "mean": float(np.round(equity.mean(), 2)), "worst": float(equity.min())},
                "fitness": {"best": round(float(fitness.max()), 5), "median": round(float(np.median(fitness)), 5)},
                "trades": {"median_per_day": float(np.median(per_day)), "max_per_day": float(per_day.max()),
                           "total": int(per_day.sum() * len(days))},
                "flies": [{"equity": float(e), "eliminated": bool(x), "trades_per_day": float(d)}
                          for e, x, d in zip(equity, eliminated, per_day)]}
            book = lineage[tribe]
            if generation and rng.random() < 0.35:
                book["ancestors"] = (book["ancestors"] + [book["id"]])[-8:]
                book["id"] = f"{tribe}-f{book['minted']:05d}"
                book["minted"] += 1
                book["born"], book["origin"] = generation, "child"
            best = int(order[0])
            frame["heroes"][tribe] = {"id": book["id"], "born": book["born"], "origin": book["origin"],
                                      "generations_lived": generation - book["born"] + 1,
                                      "ancestors": list(book["ancestors"]), "equity": float(equity[best]),
                                      "fitness": round(float(fitness[best]), 5),
                                      "trades_per_day": float(per_day[best])}
        frames.append(frame)

    competitor_results = {}
    for name, drift in (("momentum", -0.012), ("random", -0.02), ("buy_and_hold", 0.0)):
        by_day = [round(START_CASH * float(np.exp(drift + d["price_move_pct"] / 100 * (name == "buy_and_hold"))), 2)
                  for d in days]
        score = float(np.log(np.array(by_day) / START_CASH).mean())
        competitor_results[name] = {"final_equity": round(START_CASH * np.exp(score), 2), "fitness": round(score, 5),
                                    "final_equity_by_window": by_day,
                                    "trades_per_day": {"momentum": 30.0, "random": 60.0, "buy_and_hold": 1.0}[name]}

    out = {"contract_version": CONTRACT_VERSION, "run_id": "fake", "fake": True,
           "generated": datetime.now(timezone.utc).isoformat(),
           "generations": GENERATIONS, "population": POPULATION, "survive_share": SURVIVE,
           "bars_per_window": cfg.bars, "bar_minutes": 5, "candle_minutes": 5 * BARS_PER_CANDLE,
           "start_cash": START_CASH, "fee_bps": cfg.fee_bps, "min_hold_bars": cfg.min_hold_bars,
           "tribes": list(TRIBES), "competitors": list(COMPETITORS),
           "windows": [{k: d[k] for k in ("first_time", "last_time", "price_move_pct")} | {"candles": candles_for(evolve, d)}
                       for d in days],
           "competitor_results": competitor_results, "frames": frames}
    path = HERE / "runs.fake.json"
    path.write_text(json.dumps(out) + "\n")
    print(f"{path} : {GENERATIONS} generations, {len(days)} real fixed days, "
          f"{path.stat().st_size / 1024:.0f} KB (fake flies)")


if __name__ == "__main__":
    main()
