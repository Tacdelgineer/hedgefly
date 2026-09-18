# day6_full: 20 generations on four fixed days

100 flies per tribe. Every generation, every fly of both tribes trades the same four days of
the evolve set (288 five-minute bars each, $1,000 a day, 5 bps a side, 3-bar minimum hold).
Fitness is the mean log return over the four; the top 20% survive unchanged and the other 80%
are eliminated. 25.56 min per generation on the GB10, 8.5 hours in all. Every figure here is
computed from `runs/day6_full/` (PLAN.md rule 8).

## What the run shows

**Fitness on the fixed days improves, in both tribes.** The median real fly went from $989.35
to $1,028.39 a day (fitness -0.0107 to +0.0280), the median scrambled fly from $985.31 to
$1,021.61. Both finish above buy-and-hold on these days ($1,005.49). The best fly of each tribe
climbed early and then stopped: the real one last improved at generation 14, the scrambled one
at 16. Fixed days did what they were for - selection accumulates now.

**The real tribe's median fly was ahead in all 20 generations, by $4 at generation 0 and about
$7 over the last ten. Their best flies finished level** ($1,030.88 against $1,030.57).

Read that carefully:

- It is **one run per tribe**, so the 20 generations are one lineage each, not 20 trials.
- **The gap was there before selection started** (+$4.04 at generation 0), so it is at least
  partly the wiring's effect on random genomes, not something evolution found.
- **About half of it is fees** (rough estimate). The median scrambled fly trades 9.75 times a
  day against 2.5, which at 5 bps a fill is roughly 0.36% a day, about $3.60 of the ~$7 gap.
- To say the real wiring *reads the chart* better needs several seeds per tribe, or the finale.

**This is overfitting to four days.** Both final heroes make most of their money on day 4, a
day BTC fell 0.99%: the real hero ends that day at $1,082.55 and the scrambled hero at
$1,098.19, against $1,000.95-$1,025.86 on the other three. They have learned that day. How
much of it survives unseen data is what the finale's six locked months will say.

**Trading collapsed early and stayed down.** Median trades a day: real 7.75 -> 2.5, scrambled
31.25 -> 9.75, most of it in the first generation.

## Per generation and the numbers behind the text

```
fixed days: ['2022-12-31 +0.26%', '2023-02-26 +1.20%', '2024-03-13 +1.95%', '2025-01-19 -0.99%']
competitors (geo mean over the 4 days): {'momentum': 985.99, 'random': 971.12, 'buy_and_hold': 1005.49}

| gen | real best | real median | scr best | scr median | trades/day r | trades/day s |
|---|---|---|---|---|---|---|
| 0 | 1,021.14 | 989.35 | 1,019.96 | 985.31 | 7.75 | 31.25 |
| 1 | 1,022.37 | 1,004.12 | 1,019.96 | 1,001.94 | 3 | 10.5 |
| 2 | 1,024.55 | 1,016.54 | 1,022.03 | 1,006.31 | 2.75 | 10.88 |
| 3 | 1,025.18 | 1,020.72 | 1,022.03 | 1,009.91 | 2.5 | 11.5 |
| 4 | 1,025.18 | 1,021.68 | 1,022.69 | 1,010.86 | 2.5 | 10.25 |
| 5 | 1,028.75 | 1,022.55 | 1,025.67 | 1,010.53 | 2.38 | 10.5 |
| 6 | 1,028.75 | 1,023.08 | 1,025.67 | 1,014.52 | 2.25 | 10.5 |
| 7 | 1,028.75 | 1,024.63 | 1,025.67 | 1,016.52 | 2.25 | 10.5 |
| 8 | 1,028.75 | 1,024.40 | 1,025.67 | 1,015.13 | 2.25 | 10.75 |
| 9 | 1,029.58 | 1,024.76 | 1,025.67 | 1,016.16 | 2.25 | 10.5 |
| 10 | 1,029.79 | 1,025.57 | 1,028.06 | 1,018.92 | 2.25 | 9.5 |
| 11 | 1,030.02 | 1,026.01 | 1,028.06 | 1,016.97 | 2.25 | 9.38 |
| 12 | 1,030.41 | 1,025.76 | 1,028.06 | 1,018.00 | 2.75 | 9.5 |
| 13 | 1,030.69 | 1,025.99 | 1,028.06 | 1,018.98 | 2.5 | 9.25 |
| 14 | 1,030.88 | 1,026.24 | 1,028.06 | 1,019.42 | 2.5 | 9.38 |
| 15 | 1,030.88 | 1,025.31 | 1,028.06 | 1,019.65 | 2.5 | 9.5 |
| 16 | 1,030.88 | 1,025.13 | 1,030.57 | 1,018.71 | 2.5 | 9.12 |
| 17 | 1,030.88 | 1,027.29 | 1,030.57 | 1,019.99 | 2.25 | 9.5 |
| 18 | 1,030.88 | 1,027.88 | 1,030.57 | 1,021.24 | 2.25 | 9.5 |
| 19 | 1,030.88 | 1,028.39 | 1,030.57 | 1,021.61 | 2.5 | 9.75 |

IMPROVEMENT ON THE FIXED DAYS
       real: best $1,021.14 -> $1,030.88 (last improved at gen 14); median $989.35 -> $1,028.39; median fitness -0.01070 -> +0.02800; median vs B&H $+22.90
  scrambled: best $1,019.96 -> $1,030.57 (last improved at gen 16); median $985.31 -> $1,021.61; median fitness -0.01480 -> +0.02138; median vs B&H $+16.12

REAL vs SCRAMBLED, same four days
  median: real ahead in 20/20 generations; gen 0 +4.04, last +6.78, mean over last 10 +7.01
  best:   real ahead in 20/20; last gen +0.31 (fitness +0.03042 vs +0.03011)

TRADES PER DAY (median fly)
       real: gen 0 7.75, gen 10 2.25, gen 19 2.5; first 5 mean 3.70, last 5 mean 2.40
  scrambled: gen 0 31.25, gen 10 9.5, gen 19 9.75; first 5 mean 14.88, last 5 mean 9.47

FINAL HEROES, day by day (vs buy & hold) [1002.12, 1011.47, 1018.96, 989.63]
       real real-f01157: [1000.95, 1017.12, 1024.73, 1082.55]  trades/day 2.25  origin child born 14
  scrambled scrambled-f01342: [997.34, 1003.93, 1025.86, 1098.19]  trades/day 8.0  origin child born 16
  real hero lineage depth 7, alive 6 gens
  scrambled hero lineage depth 7, alive 4 gens
```
