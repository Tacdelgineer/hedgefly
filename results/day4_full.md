# day4_full: 40 generations, real vs scrambled

100 flies per tribe, 288 five-minute bars per generation (one day), 5 bps a side, 3-bar
minimum hold, $1,000 start. Both tribes trade the **same window** every generation, so every
comparison below is paired by generation. Every figure here is computed from
`runs/day4_full/gen_XXX_summary.json` (PLAN.md rule 8).

## Verdict: noise

The real tribe did not beat the scrambled one. On the median fly it came out ahead in 23 of
40 generations by an average of $1.12, with a 95% confidence interval of -$3.14 to +$3.83
that sits squarely across zero (sign-flip permutation p = 0.47). On the best fly it came out
*behind* in 22 of 40. Neither tribe improved against buy-and-hold over the run.

Intervals use a moving-block bootstrap (blocks of 5 generations), because survivors carry
over from one generation to the next and make the generations less independent than they look.

## Per generation (final equity, dollars)

| gen | move | real best | real med | scr best | scr med | dead r/s | trades r/s | mom | rand | B&H |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | -1.20% | 1,015 | 983 | 1,006 | 977 | 0/0 | 7/32 | 971 | 960 | 987 |
| 1 | +0.34% | 1,014 | 999 | 1,005 | 992 | 0/0 | 4/8 | 968 | 980 | 1,003 |
| 2 | -1.53% | 1,007 | 999 | 996 | 984 | 0/0 | 3/8 | 967 | 972 | 984 |
| 3 | +1.55% | 1,017 | 1,008 | 1,011 | 1,001 | 0/0 | 3/8 | 987 | 989 | 1,015 |
| 4 | -0.07% | 1,015 | 1,000 | 1,022 | 988 | 0/0 | 3/9 | 973 | 944 | 999 |
| 5 | -1.52% | 998 | 993 | 999 | 990 | 0/0 | 3/8 | 971 | 966 | 984 |
| 6 | +0.95% | 1,015 | 1,008 | 1,011 | 998 | 0/0 | 3/7 | 982 | 969 | 1,009 |
| 7 | +0.74% | 1,012 | 993 | 1,023 | 999 | 0/0 | 2/7 | 974 | 975 | 1,007 |
| 8 | +0.50% | 1,011 | 1,000 | 1,017 | 993 | 0/0 | 3/7 | 978 | 972 | 1,004 |
| 9 | +1.51% | 1,014 | 1,008 | 1,018 | 1,015 | 0/0 | 3/6 | 990 | 981 | 1,015 |
| 10 | -1.02% | 999 | 991 | 992 | 988 | 0/0 | 4/6 | 970 | 964 | 989 |
| 11 | -2.10% | 1,019 | 973 | 1,027 | 989 | 0/0 | 4/6 | 953 | 972 | 978 |
| 12 | -4.59% | 998 | 963 | 1,005 | 972 | 0/0 | 4/7 | 969 | 931 | 954 |
| 13 | -0.01% | 1,003 | 997 | 1,004 | 998 | 0/0 | 4/6 | 975 | 970 | 999 |
| 14 | -1.93% | 1,000 | 984 | 996 | 983 | 0/0 | 4/5 | 959 | 950 | 980 |
| 15 | +1.08% | 1,024 | 1,011 | 1,026 | 1,012 | 0/0 | 5/6 | 988 | 971 | 1,010 |
| 16 | -1.65% | 1,007 | 984 | 1,007 | 993 | 0/0 | 5/6 | 966 | 967 | 983 |
| 17 | +0.89% | 1,028 | 1,012 | 1,035 | 1,022 | 0/0 | 4/6 | 987 | 969 | 1,008 |
| 18 | +0.54% | 1,006 | 1,000 | 1,005 | 997 | 0/0 | 4/6 | 975 | 974 | 1,005 |
| 19 | -1.91% | 994 | 976 | 1,001 | 992 | 0/0 | 4/6 | 960 | 941 | 980 |
| 20 | +0.16% | 1,003 | 999 | 1,003 | 998 | 0/0 | 4/6 | 971 | 973 | 1,001 |
| 21 | -2.44% | 1,004 | 987 | 1,001 | 990 | 0/0 | 4/6 | 967 | 962 | 975 |
| 22 | -1.59% | 1,027 | 1,000 | 1,016 | 997 | 0/0 | 4/6 | 1,008 | 965 | 984 |
| 23 | +3.88% | 1,041 | 1,014 | 1,054 | 1,021 | 0/0 | 4/6 | 993 | 991 | 1,038 |
| 24 | -0.77% | 1,003 | 1,000 | 1,005 | 993 | 0/0 | 4/6 | 974 | 964 | 992 |
| 25 | +0.92% | 1,020 | 1,006 | 1,026 | 993 | 0/0 | 4/6 | 977 | 987 | 1,009 |
| 26 | +0.03% | 1,010 | 999 | 1,012 | 1,004 | 0/0 | 4/6 | 964 | 967 | 1,000 |
| 27 | -3.48% | 1,004 | 971 | 1,015 | 991 | 0/0 | 4/7 | 966 | 966 | 965 |
| 28 | +5.17% | 1,067 | 1,051 | 1,072 | 1,038 | 0/0 | 4/7 | 1,019 | 1,010 | 1,051 |
| 29 | -0.08% | 1,022 | 955 | 1,027 | 965 | 0/0 | 4/5 | 1,017 | 988 | 999 |
| 30 | +1.12% | 1,012 | 1,002 | 1,013 | 1,002 | 0/0 | 4/5 | 982 | 962 | 1,011 |
| 31 | -0.93% | 1,008 | 994 | 1,005 | 997 | 0/0 | 4/5 | 961 | 971 | 990 |
| 32 | +0.18% | 1,002 | 996 | 999 | 995 | 0/0 | 4/5 | 983 | 969 | 1,001 |
| 33 | +0.92% | 1,050 | 1,005 | 1,056 | 995 | 0/0 | 5/5 | 1,009 | 957 | 1,009 |
| 34 | +0.02% | 1,005 | 998 | 1,002 | 994 | 0/0 | 4/5 | 968 | 976 | 1,000 |
| 35 | +1.40% | 1,015 | 1,001 | 1,014 | 1,004 | 0/0 | 3/4 | 982 | 983 | 1,013 |
| 36 | -1.50% | 1,003 | 991 | 1,003 | 990 | 0/0 | 4/5 | 973 | 964 | 985 |
| 37 | -3.62% | 1,007 | 996 | 1,005 | 969 | 0/0 | 4/5 | 986 | 940 | 963 |
| 38 | -2.78% | 1,010 | 987 | 1,013 | 968 | 0/0 | 4/4 | 977 | 960 | 972 |
| 39 | +0.52% | 1,010 | 999 | 1,002 | 999 | 0/0 | 4/5 | 980 | 977 | 1,005 |


## Paired analysis and trends

```
PAIRED, same window each generation (real minus scrambled):
         median equity: real ahead in 23/40 gens (0 ties), mean diff $+1.12, block-bootstrap 95% CI [$-3.14, $+3.83], sign-flip p=0.468
           best equity: real ahead in 18/40 gens (0 ties), mean diff $-0.80, block-bootstrap 95% CI [$-3.37, $+0.38], sign-flip p=0.421
median excess over B&H: real ahead in 23/40 gens (0 ties), mean diff $+1.12, block-bootstrap 95% CI [$-3.13, $+3.82], sign-flip p=0.467
 median, 2nd half only: real ahead in 12/20 gens (0 ties), mean diff $+2.31, block-bootstrap 95% CI [$-2.02, $+5.64], sign-flip p=0.332

DID EITHER TRIBE IMPROVE? median minus buy-and-hold, first vs last quarter:
       real: first 10 gens $-1.64, last 10 gens $+2.08, corr with generation +0.04
  scrambled: first 10 gens $-7.08, last 10 gens $-3.45, corr with generation +0.01

TRADING, median trades per fly, first vs last quarter:
       real: first 10 gens 3.4, last 10 gens 4.0, corr with generation +0.16
  scrambled: first 10 gens 10.0, last 10 gens 4.8, corr with generation -0.47

TOTALS: deaths real 0, scrambled 0; median trades real 4, scrambled 6
competitor means: momentum $978.00, random $968.66, B&H $996.42; tribe medians: real $995.77, scrambled $994.65
best fly beat B&H in: real 39/40, scrambled 37/40; median fly beat B&H in: real 17/40, scrambled 17/40

real hero (gen 39): real-f03216, born gen 39 (newcomer), alive 1 gens, $1,009.77
  ancestors: (founder)
  longest-lived hero in the run: real-f01314 (3 gens)

scrambled hero (gen 39): scrambled-f03204, born gen 39 (child), alive 1 gens, $1,002.34
  ancestors: scrambled-f03130
  longest-lived hero in the run: scrambled-f00284 (2 gens)
```

## What the numbers do say

- **Nobody died.** Zero broke flies in 8,000 fly-generations. At one day per window and a
  $500 broke line, no strategy loses half its money, so the Trading Floor's dark desks and
  the terminal's pile never fill on real data.
- **Selection taught the scrambled tribe to trade less.** Its median fly went from 10.0 trades
  a day in the first 10 generations to 4.8 in the last 10 (correlation with generation -0.47).
  The real tribe started at 3.4 and stayed there. Under 5 bps fees, trading less is what gets
  rewarded, and the scrambled flies converged on where the real wiring began. This is the one
  clear evolutionary effect in the run.
- **The best fly beating buy-and-hold is not skill.** It happened in 39/40 generations for the
  real tribe and 37/40 for the scrambled one, but that is the maximum of 100 draws. The median
  fly beat buy-and-hold in 17/40 for both tribes.
- **The last hero came off the street.** The real tribe's top fly in generation 39 is a
  newcomer - a random genome with no ancestors. The longest any fly held the top spot was 3
  generations.
