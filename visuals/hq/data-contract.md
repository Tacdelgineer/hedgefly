# Visuals data contract — version 4

One file, `visuals/hq/runs.json`, is everything the visuals know. They replay it; they never
run the simulation and never read `runs/*/gen_*.json` directly (PLAN.md rule 7). Every number
on screen comes from this file, which comes from the logs (rule 8).

Written by `scripts/export_for_visuals.py`. A fake one for building against -
`visuals/hq/runs.fake.json`, real market days with invented flies - comes from
`python -m visuals.hq.fake_runs`; open it with `visuals/terminal/?data=../hq/runs.fake.json`.
Read by `visuals/terminal/`.

**Version 2** follows the switch to four fixed days and to death by elimination. Version 1
(one random day per generation, death by bankruptcy) is what the riso HQ on branch
`session-a/day4` reads; it is B-roll and stays on that version. **Version 3** adds the
validation days, the fee-free scores and the finale. **Version 4** adds the four blocks the
Tree of Life, the Barcode Wall, the Ticker Tape Hall, the Replay Room and the Fly's-Eye View
need: `lineage`, `tape`, `replay` and `eye`. All four are optional; a page must check for them.

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
- `story` (optional) is `{"headline": "..."}`, the narrator's headline for the generation from
  `story/<run_id>/gen_XXX.json`, re-checked by the Fact Guard when exported. Pages show it
  through `headlineFor`, which drops a leading "Generation N:" and falls back to the rule-based
  headline if a digit is left, so no number on screen is one a model typed.

## Version 3 additions

All optional: a page must render against a file that has none of them.

| key | meaning |
|---|---|
| `brain` | the run's `run_summary.json` brain block: `neurons`, `edges`, `photoreceptors`, `readout_groups`, `shared_eye_from`, `steps_per_candle`. The Brain Room's and Eye Room's walls |
| `run` | `genome_size`, `minutes_per_generation`, `minutes_total`, from the same summary. The Switchboard's dial count and the Server Room's clock |
| `locked` | the locked test set as `data/split.json` records it: `rows`, `first`, `last`, `source`. The vault's wall before a finale exists. Read from split.json and never from the parquet, which only the finale scripts may open (rule 3) |
| `finale` | every trader's final equity and thinned curve, per pass; `llm.replies`; `llm.traded` |

### finale.passes.<pass>.traders.llm.traded

When the model was actually in the market. The finale logs how many times it traded and what it
said in its last 24 calls, but **not a trade log**, so nothing in it says when it bought. Two
logged curves together do: the fee-free pass replays the with-fees pass decision for decision,
so the ratio between the two equity curves is flat except at a fill, where the fee knocks the
with-fees wallet down by exactly one `fee_bps`. Every step in that ratio is one fill, and
nothing else can produce one.

```json
{"count": 292, "buys": 146, "sells": 146,
 "recovered_from": "the fee step between the with-fees and fee-free passes",
 "clock": "interpolated across the run's span, rounded to the five-minute bar grid",
 "clock_drift_minutes": 5.0,
 "moments": [["2026-03-18T18:15:00+00:00", "BUY"], ["2026-03-18T19:15:00+00:00", "SELL"]]}
```

Two things the exporter checks before writing any of it, and refuses on:

- **`count` must equal the trades the run logged.** It does: 292, and the final fee ratio equals
  `(1 - 5bps)^292`. The 146 BUY fills also equal the 146 BUY replies the run logged, which is
  what confirms fills alternate from flat.
- **The clock must be close enough to be worth printing.** The finale carries no per-bar
  timestamp, and the candles that do are the locked set, so bar-to-clock is interpolated across
  `first_time..last_time`. That interpolation is then measured against the real timestamps the
  run *did* log, on its last replies: `clock_drift_minutes` is the worst disagreement, 5.0 min,
  which is one bar against a 60-minute decision grid. Beyond half a decision apart the exporter
  refuses to export times at all.

`moments` is a sample - buy/sell pairs spread evenly across the run, not all 292 - because it
feeds a wall that cycles them. `count`, `buys` and `sells` are the whole run.

## v4 blocks

### `lineage`

The family tree, per tribe. `flies[generation][seat]` is one fly, compacted to four fields,
because it is 2,400 of them:

```json
{"p": 74, "o": "s", "f": 0.029359, "e": 0}
```

- `p` — the seat this fly continues from in the **previous** generation, or `-1` where the
  branch starts. That is the whole tree: a page never has to match an id string.
- `o` — how it got there: `s` survivor, `c` child, `n` newcomer, `f` founder.
- `f` — its fitness, the mean log return over the four fixed days.
- `e` — 1 if selection eliminated it this generation, which is where its branch stops.

`champion` is the last generation's best fly and the seat its line held in every generation
before it: `{"id", "seat", "born", "fitness", "seats": [2, 60, 88, ...]}`, `-1` before the line
existed. That array is the gold branch, and the export refuses to write one whose steps do not
join up.

### `tape`

Every fill the last generation's best `flies_per_tribe` flies made, over all four fixed days,
in time order:

```json
{"t": "2022-12-31T20:30:00+00:00", "side": "buy", "price": 16558.13,
 "equity": 999.56, "bar": 3, "tribe": "scrambled", "fly": "scrambled-f00839", "day": 0}
```

A generation log holds every **decision** and no trade blotter, and a decision is not a fill: a
BUY while already long does nothing and the minimum hold refuses a flip. So the exporter puts
the logged decisions back through `market.wallet` in the same rule-4 order on the same evolve
bars, and takes the fills off that. It is not a guess, and it is not allowed to be: for every
fly-day it compares the replayed equity with the equity the run already logged and refuses the
whole block if any of them differ by more than a cent. `days_checked` is how many it checked.

### `replay`

One training day of the EVOLVE set, decision by decision, for the final champion of each tribe.
**This is the one block that is not in any generation log.** Vote margins and readout-group
activity live for a single line inside `brain/agent.py` and are dropped, so
`scripts/replay_champions.py` re-runs the two champions and writes them down; the exporter
reads its output. Per bar:

```json
{"b": 8, "t": "2022-12-31T20:50:00+00:00", "a": "sell", "p": 16553.32, "c": 16553.18,
 "pos": 0, "mb": -0.043186, "ms": 0.001434, "eq": 1000.0,
 "g": [[224, -1.0164, 0.13412], [238, 1.005, -0.132666]]}
```

`mb` / `ms` are the BUY and SELL margins — each logit **minus that fly's own running average of
it**, which is what the decision is actually made on. `g` is the loudest readout groups, as
`[group, activity, contribution]`; `groups` maps those numbers to the names the release's
annotations give them (`type:DNp65`, `muscle:...`). `agreement` and `bars_same` say how closely
the replay reproduced the actions the run logged for the same fly on the same day — the genome
is reloaded from the log at five decimals, so this is a measurement, not an assumption.

### `eye`

Where the compound eye looks at the chart, and what it drew from a handful of bars:

```json
{"photoreceptors": 5494, "cells": 520, "built_from": "real",
 "layout": [[-0.9231, 0.5551], ...], "per_cell": [7, 12, ...],
 "frames": [{"bar": 0, "v": [0.412, 0.0, ...]}]}
```

`layout` is each drawable ommatidium's position in chart space, `[-1, 1]` on both axes.
5,494 photoreceptors is far too many marks for a 12fps canvas, so neighbours are pooled onto a
coarse lattice: a cell's position is the mean position of its own photoreceptors and its value
the mean of their drive. `per_cell` must sum to `photoreceptors`, and the export checks it.
The layout is computed from the REAL connectome's edges and both tribes share it (PLAN.md).

### What is deliberately not here

Equity curves within a day for every fly, per-bar actions for every fly, genomes, connectome
data and five-minute prices. They are in `runs/<run_id>/gen_XXX.json` and the evolve set, and
they are large; add them to the contract before adding a visual that needs them. The `replay`
block is the narrow exception, and it covers two flies on one day.
