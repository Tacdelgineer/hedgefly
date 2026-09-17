# Brain interface

The contract between the market side (`market/`, the wallet) and the fly brains (`brain/`).
Both sides build against this file. Change it only by agreement, in its own commit.

## Every candle, the brain receives

| Input | Type | Shape | Values |
| --- | --- | --- | --- |
| `chart` | numpy `float32` | `(64, 64)` | 0 = paper, 1 = ink. One image, shared by every fly in the tribe. |
| `position` | numpy `int8` or `bool` | `(P,)` | One flag per fly: 0 = flat, 1 = long. |

`P` is the population size of the run.

**Chart**
- Shows the last 64 closed candles: candle `t`, which just closed, and the 63 before it.
  Nothing after the close of `t` (PLAN.md rule 4).
- Time runs left to right: column 0 is candle `t-63`, column 63 is candle `t`.
  Row 0 is the top (highest price).
- Prices are scaled per image, from the lowest low to the highest high of those 64 candles.
- What is drawn (bars, line, volume) is up to `market/`, but one renderer is used for every
  tribe, every window, the calibration charts and the finale.

**Position**
- The position each fly holds at the close of candle `t`, i.e. after the order it decided at
  candle `t-1` filled at the open of `t`.

## Every candle, the brain returns

numpy `int8`, shape `(P,)`, one action per fly, in the same fly order as `position`:

| Code | Action |
| --- | --- |
| 0 | HOLD |
| 1 | BUY |
| 2 | SELL |

- Decided at the close of candle `t`. The wallet executes it at the open of `t+1` (rule 4).
- Deterministic (argmax over three logits). Ties resolve to HOLD.
- The brain does not know the trading rules: it can say BUY while long or SELL while flat.
  What those mean is the wallet's decision.

## Calling sequence

```python
from brain import Genome, TribeAgent

agent = TribeAgent.build(connectome, calibration_charts)   # once per tribe (real, scrambled)
run = agent.start(genome)                                   # once per window; P = genome.population
for t in window:                                            # every candle, in order
    actions = run.decide(charts[t], positions)              # (P,) int8
```

- `calibration_charts`: numpy `float32`, shape `(T, 64, 64)`, `T >= 256` consecutive charts
  from `data/btc_evolve.parquet` only, never from the locked test set (rule 3). Both tribes get
  the same calibration charts.
- A run keeps each fly's brain state from candle to candle. Feed every candle of the window
  once, in order; skipping or repeating a candle changes what the flies see. A new window
  needs a new `start`.
- `P` is fixed for the whole run. A broke fly still gets decisions; the wallet ignores them.
- Genomes come from `evolve/`; the market side never builds or changes one.
