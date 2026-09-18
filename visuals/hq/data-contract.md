# HQ data contract

One file, `visuals/hq/runs.json`, is everything the HQ knows. The world replays it; it never
runs the simulation and never reads `runs/*/gen_*.json` directly (PLAN.md rule 7). Every number
on screen comes from this file, which comes from the logs (rule 8).

Written by `scripts/export_for_visuals.py`. A fake one, for building against before a run
finishes, comes from `visuals/hq/fake_runs.py`.

## Top level

| key | type | meaning |
|---|---|---|
| `run_id` | string | the run directory this came from, e.g. `day4_full` |
| `generations` | int | how many entries `frames` has |
| `population` | int | flies per tribe, per generation |
| `bars_per_generation` | int | decision bars in a generation's window |
| `bar_minutes` | int | minutes per bar (5) |
| `candle_minutes` | int | minutes per candle in `window.candles` (15: three bars each) |
| `start_cash` | number | every trader's opening bankroll (1000) |
| `broke_below` | number | the equity a fly dies at (500) |
| `fee_bps` | number | fee per side, basis points |
| `min_hold_bars` | int | bars a position must be held |
| `tribes` | string[] | `["real", "scrambled"]`, in wing order |
| `competitors` | string[] | `["momentum", "random", "buy_and_hold"]` |
| `generated` | string | ISO timestamp of the export |
| `frames` | Frame[] | one per generation, generation ascending |

## Frame

```json
{
  "generation": 0,
  "window": {"first_time": "2024-12-01T22:20:00+00:00",
             "last_time": "2024-12-02T22:20:00+00:00",
             "price_move_pct": -1.4,
             "candles": [[95718.24, 95790.0, 95601.5, 95655.1], "... 96 of them ..."]},
  "tribes": {
    "real": {
      "alive": 97, "broke": 3,
      "equity": {"best": 1031.1, "median": 973.46, "mean": 971.2, "worst": 872.03},
      "fitness": {"best": 0.0306, "median": -0.0269},
      "trades": {"total": 2104, "median": 18, "max": 192},
      "flies": [{"equity": 1002.3, "broke": false, "trades": 12}]
    },
    "scrambled": { "... same shape ..." }
  },
  "competitors": {"momentum": 959.73, "random": 951.37, "buy_and_hold": 985.48},
  "heroes": {
    "real": {"id": "real-f00038", "born": 0, "origin": "founder",
             "generations_lived": 3, "ancestors": ["real-f00011"],
             "equity": 1031.1, "fitness": 0.0306, "trades": 18},
    "scrambled": { "... same shape ..." }
  }
}
```

### Rules the rooms rely on

- `tribes.<name>.flies` has exactly `population` entries, in a stable order: **index `k` is the
  same desk on The Trading Floor in every generation.** A desk goes dark when its fly's `broke`
  is true. Flies are not the same individual from generation to generation - selection replaces
  them - so a desk is a seat, not a fly.
- `alive + broke == population`.
- `equity` figures are dollars, already rounded to cents. `worst` is the lowest final equity of
  a living or dead fly; a dead fly's equity is frozen at its death.
- `fitness` is `log(final equity / start_cash)`, the number selection actually used.
- `competitors.<name>` is that competitor's final equity on the same window, same rules.
- `heroes.<name>.ancestors` is the chain from the founder down to the hero's parent, oldest
  first. It is empty when the hero is itself a founder. `heroes.<name>.id` is never in its own
  `ancestors`.
- A hero's `equity` and `fitness` are that generation's, so the Hero's Desk can draw a curve by
  reading `frames[g].heroes.real.equity` across `g`. The hero may change from generation to
  generation; `id` says who is being watched.
- Times are ISO 8601 with an offset. `price_move_pct` is a percentage, already multiplied by
  100, signed.
- `window.candles` are the real BTC-USD bars that generation traded, `[open, high, low, close]`
  in dollars, oldest first, each one `candle_minutes` wide: the window's 288 five-minute
  decision bars grouped in threes, so 96 candles. They come from the evolve set at the row
  indices the run logged, and the exporter refuses to write them unless the bar after the first
  opens at the entry price the run logged - a data file whose rows have shifted cannot chart the
  wrong day. Every candle's high and low contain its open and close. A visual that has no
  candles draws none; it never invents a shape.

### What is deliberately not here

Equity curves within a generation, genomes, per-bar actions and connectome data, and
five-minute prices (the candles are fifteen-minute). They are in `runs/<run_id>/gen_XXX.json`
and the evolve set, and they are large; the HQ animates generation by generation, so per-bar
detail would be a hundred megabytes it never draws. Add them to the contract before
adding a room that needs them.
