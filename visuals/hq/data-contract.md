# Visuals data contract — version 2

One file, `visuals/hq/runs.json`, is everything the visuals know. They replay it; they never
run the simulation and never read `runs/*/gen_*.json` directly (PLAN.md rule 7). Every number
on screen comes from this file, which comes from the logs (rule 8).

Written by `scripts/export_for_visuals.py`. A fake one for building against -
`visuals/hq/runs.fake.json`, real market days with invented flies - comes from
`python -m visuals.hq.fake_runs`; open it with `visuals/terminal/?data=../hq/runs.fake.json`.
Read by `visuals/terminal/`.

**Version 2** follows the switch to four fixed days and to death by elimination. Version 1
(one random day per generation, death by bankruptcy) is what the riso HQ on branch
`session-a/day4` reads; it is B-roll and stays on that version.

## Top level

| key | type | meaning |
|---|---|---|
| `contract_version` | int | `2` |
| `run_id` | string | the run directory this came from |
| `generated` | string | ISO timestamp of the export |
| `generations` | int | how many entries `frames` has |
| `population` | int | flies per tribe, per generation |
| `survive_share` | number | share of each tribe that reproduces (0.2); the rest are eliminated |
| `bars_per_window` | int | five-minute decision bars in one fixed day (288) |
| `bar_minutes` | int | 5 |
| `candle_minutes` | int | minutes per candle in `windows[].candles` (30: six bars each) |
| `start_cash` | number | every trader's opening bankroll, every day (1000) |
| `fee_bps`, `min_hold_bars` | number, int | the trading rules |
| `tribes` | string[] | `["real", "scrambled"]` |
| `competitors` | string[] | `["momentum", "random", "buy_and_hold"]` |
| `windows` | Window[] | the fixed days, oldest first. The SAME for every generation |
| `competitor_results` | object | each competitor on the fixed days; also the same every generation |
| `frames` | Frame[] | one per generation, ascending |

### Window

```json
{"first_time": "2024-03-04T09:00:00+00:00", "last_time": "2024-03-05T09:00:00+00:00",
 "price_move_pct": -1.2, "candles": [[95718.24, 95790.0, 95601.5, 95655.1], "... 48 of them"]}
```

`candles` are the real BTC-USD bars of that day, `[open, high, low, close]` in dollars, oldest
first, six five-minute bars to a candle. They come from the evolve set at the row indices the
run logged, and the exporter refuses to write them unless the bar after the first opens at the
entry price the run logged, so a data file whose rows have moved cannot chart the wrong day.

### competitor_results

```json
{"buy_and_hold": {"final_equity": 996.61, "fitness": -0.00339,
                  "final_equity_by_window": [987.1, 1004.2, 999.0, 996.3], "trades_per_day": 1.0}}
```

## Frame

```json
{
  "generation": 0,
  "tribes": {
    "real": {
      "survived": 20, "eliminated": 80,
      "equity": {"best": 1031.1, "median": 997.46, "mean": 995.2, "worst": 962.03},
      "fitness": {"best": 0.0306, "median": -0.0025},
      "trades": {"median_per_day": 4.0, "max_per_day": 61.5, "total": 2104},
      "flies": [{"equity": 1002.3, "eliminated": false, "trades_per_day": 3.25}]
    },
    "scrambled": { "... same shape ..." }
  },
  "heroes": {
    "real": {"id": "real-f00038", "born": 0, "origin": "founder", "generations_lived": 3,
             "ancestors": ["real-f00011"], "equity": 1031.1, "fitness": 0.0306,
             "trades_per_day": 4.5},
    "scrambled": { "... same shape ..." }
  }
}
```

### Rules the visuals rely on

- **A fly's `equity` is its geometric-mean final equity over the four days**,
  `start_cash * exp(fitness)`, so ordering flies by it is ordering them by fitness.
- **Death is elimination.** A fly is `eliminated` when it is not among the `survive_share`
  fittest of its tribe that generation, i.e. it does not reproduce. `survived + eliminated ==
  population`, and exactly `eliminated` flies are marked. There is no bankruptcy.
- `tribes.<name>.flies` has exactly `population` entries in log order. Index `k` is a seat,
  not an individual: selection replaces who sits there.
- `trades` are fills per fixed day, averaged over the four days for a fly.
- `heroes.<name>` is the fittest fly of the generation. `ancestors` runs from the founder to its
  parent, oldest first; it is empty for a founder or a newcomer, and never contains `id`.

### What is deliberately not here

Equity curves within a day, per-bar actions, genomes, connectome data and five-minute prices.
They are in `runs/<run_id>/gen_XXX.json` and the evolve set, and they are large; add them to
the contract before adding a visual that needs them.
