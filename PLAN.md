# Hedgefly - Natural Selection Capital

100 real fruit-fly brains (MaleCNS v1.0 connectome) trade Bitcoin.
The brains never change. Only the small "cables" that connect market data to the
brain, and brain output to trades, evolve. A real-brain tribe races a
scrambled-brain tribe. The finale is a test on data no fly has ever seen.

The story is told as a risograph-style isometric world, "Natural Selection
Capital HQ", drawn entirely in code, with a local AI narrator that writes each
generation's story and prints a poster for it.

Video: "I Evolved 100 Fly Brains Into Crypto Traders"
Deadline: published within 7 days.

---

## NON-NEGOTIABLE RULES (every agent reads this first)

1. **Brain weights are frozen.** No backprop, no gradient training, no RL on the
   connectome. If using nfly, learnable edge gains, biases and leaks stay at init.
2. **Only the genome evolves.** Genome = encoder gains + decoder (readout) weights.
   Nothing else.
3. **The test set is locked.** The last 6 months of candles live in a separate file
   that is loaded ONLY by `finale.py`. No other code may import or read it.
4. **No lookahead.** A decision made at candle close t executes at candle t+1 open.
   There must be a unit test for this.
5. **Fees on every trade.** Default 10 bps per side, configurable. Same rules for
   every fly and every tribe.
6. **Fair scrambled tribe.** Degree-preserving edge swaps on the same edge list:
   swap targets (a->b, c->d) => (a->d, c->b). Each neuron keeps its in-degree and
   out-degree; sign and synapse count travel with the presynaptic neuron (Dale's law).
   Recompute any per-neuron input normalization after swapping. Same population
   size, same windows, same mutation settings as the real tribe.
7. **Everything is logged.** Every generation writes to `runs/<run_id>/gen_XXX.json`
   (genomes, equity curves, trades, fitness, clan tags). Visuals replay logs; they
   never re-run the simulation.
8. **Every number viewers see comes from the logs.** On screen, in narration, on
   posters. The narrator never invents numbers (see Fact Guard).
9. **The simulation always has priority on the GPU.** The narrator never runs
   while a generation is simulating.
10. **Credits.** README cites MaleCNS (Berg et al., Cell 2026,
    doi:10.1016/j.cell.2026.08.015, data CC BY 4.0), nfly (MIT), and the
    creative-skills repo (MIT). Visual style inspired by Kevin Ngo's
    "a small light, room by room".

---

## SETUP

- Hardware: DGX Spark (ARM64 / aarch64, 128 GB unified memory). Repo lives on the
  Spark; work over SSH.
- **ARM check:** verify `torch.cuda.is_available()` is True inside the project env.
  Never silently fall back to CPU. If a package resolves a CPU-only wheel, fix it.
- Brain base: `zhengxuyu/nfly` pinned to a specific commit (young repo; pin it).
  Fallback if it breaks: reimplement its published rate dynamics directly:
  `h[t+1] = (1 - alpha) * h[t] + alpha * min(ReLU(W h[t] + b + u[t]), h_max)`
- Connectome: the 3 MaleCNS v1.0 flat-connectome feather files (~1.2 GB) into `data/`.
- Market: BTC-USD 1h candles from a public source.
  - `data/btc_evolve.parquet`: everything except the last 6 months
  - `data/btc_locked_test.parquet`: last 6 months (see rule 3)
- Narrator model: Qwen3.8-27B, served locally with an OpenAI-compatible endpoint
  (vLLM or Ollama).
- Visual skills (Claude Code): `riso-rooms` and `hand-drawn-canvas-animation` from
  github.com/IshaanKalra2103/creative-skills. MP4 rendering needs Node 18+,
  Chrome and ffmpeg. If headless Chrome is a problem on ARM Linux, render on the
  Windows workstation instead.

---

## SIMULATION ARCHITECTURE

- **Brain:** one shared sparse W on GPU. Batch dimension = flies.
  State shape `[population, N_neurons]`. The real tribe and the scrambled tribe
  each have their own W.
- **Senses:** the last 64 candles rendered as a small chart image and fed through
  the retina encoder ("the fly sees the chart"), plus one input for current
  position (flat or long). Per-fly encoder gains are part of the genome.
- **Actions:** readout from descending + motor neurons -> 3 logits: BUY / SELL / HOLD.
  Argmax, deterministic. Per-fly readout weights are part of the genome.
- **Portfolio:** long or flat only. Starts at $1,000 (paper). A fly that drops
  below $500 is "broke" and dies for that generation.
- **Brain steps per candle:** configurable (start with 2).

## EVOLUTION

- Each generation, every fly in both tribes trades the SAME randomly chosen window
  of the evolve set (start: 2 weeks = 336 hourly candles).
- Fitness = log(final equity / 1000). Broke flies get the minimum fitness.
- Top 20% survive. Children = parent genome + Gaussian noise. 10% random newcomers.
- Baselines logged every generation on the same window: Random trader, Buy-and-hold.
- Lineage: every fly records its parent id (for the family tree).
- Clan tags (for the story): cluster flies by behavior (trade frequency, time in
  market, reaction to drops). Tag only; clans do not affect selection.
- After each generation, write a compact summary `runs/<run_id>/gen_XXX_summary.json`
  (tribe stats, deaths, top flies, clan sizes, baselines). Narrator and visuals
  read summaries, not raw logs.

## FINALE (`finale.py`)

- Load the top 10 flies from each tribe from the last generation.
- Trade the entire locked test set once. Same fees and rules.
- Output: equity curves for real champions, scrambled champions, Random, Buy-and-hold.
- Run once, on camera. Whatever happens is the ending.

---

## VISUAL DIRECTION

**Look:** risograph-printed isometric cutaway rooms. Warm paper background,
navy / salmon / teal / yellow inks, halftone dots, slightly misaligned color plates,
wobbly lines. Every mark drawn in code (canvas). No stock images, no AI images.
Inspiration only; do not copy anyone's artwork or scenes.

**The world: Natural Selection Capital HQ.** A diorama of rooms. The camera moves
room to room like chapters of the story. Rooms are driven by exported log data.

| Room | What it shows | Driven by |
|------|---------------|-----------|
| The Lab | DGX Spark on a desk, cables, a jar of fruit flies | static |
| The Brain Room | a connectome sculpture that pulses | activity summary per generation |
| The Trading Floor | rows of tiny desks, one per fly; two wings: Real / Scrambled; desks go dark when a fly goes broke | equity + deaths |
| The Hall of Clans | a banner per clan; banners fall when a clan goes extinct | clan sizes |
| The Archive | bookcases of generation logs; one spine per generation | generation count |
| The Print Shop | a riso printer printing that generation's poster | narrator poster |
| The Vault | a locked vault door holding the test data; opens only in the finale | finale results |

**Films** (hand-drawn-canvas-animation skill), 10-30 s each, maximum 3:
1. Cold open: the life of a fly trader
2. Extinction event: a clan wiped out by a crash
3. The Vault opens: finale

**Exports:** 16:9 for the main video, 9:16 crops for Shorts.

## NARRATOR + POSTER (local, on the Spark)

- Runs after each generation (or in batch after the run). Never during simulation.
- Input: `gen_XXX_summary.json` only.
- Output: `story/gen_XXX.json`:
  ```json
  {
    "headline": "max 8 words",
    "narration": "1-3 sentences, nature-documentary tone",
    "new_clan_names": {"clan_id": "name"},
    "poster": {
      "title": "short",
      "subtitle": "short",
      "featured_room": "trading_floor | hall_of_clans | vault | ...",
      "stat_keys": ["keys from the summary to print on the poster"]
    }
  }
  ```
- Clan names persist once given.
- **Posters are rendered by a riso poster template** (canvas JS, same look as HQ).
  The model chooses words and which stat keys to show; the template reads the
  real numbers from the summary. The model never types numbers onto posters.
- **Fact Guard** (`story/validate.py`): rejects narration that contains a number
  not present in the summary (small rounding tolerance) or names a fly, clan or
  tribe that doesn't exist. Rejected output is regenerated.
- Voice: narration text goes to the existing TTS narration pipeline.

---

## SPEED BUDGET (measure on Day 1)

Reference point: nfly reports whole-CNS inference around 8 ms/step on an RTX 5090.
The Spark will differ, so measure it.

- Measure ms/step at population 1, 100, 200 for subsets: all, brain, visual_small.
- Target: <= 10 minutes per generation for both tribes combined.
- If too slow, cut in this order:
  1. fewer brain steps per candle (1 instead of 2)
  2. shorter window
  3. population 50
  4. smaller subset (last resort, because it removes motor readout neurons)
- **Never cut:** the scrambled tribe, the locked test set, fees, the Fact Guard.

## VISUAL CUT ORDER (if behind schedule)

1. Films 2 and 3 (keep the cold open)
2. The Print Shop room (posters still exported as images)
3. The Hall of Clans and The Archive
4. Minimum HQ: The Lab, The Brain Room, The Trading Floor, The Vault

---

## SCHEDULE

| Day | Simulation | Visuals + Story | Done when |
|-----|-----------|-----------------|-----------|
| 1 | Env, connectome + BTC data, speed benchmark | Install skills; Qwen3.8-27B endpoint up | Benchmark table; data split test passes; model answers a test prompt |
| 2 | Senses, actions, portfolio, batched population | Block out HQ rooms (static, no data) | 100 random-genome flies trade one window; fee + no-lookahead tests pass |
| 3 | Evolution loop, scrambled W, baselines, logging, summaries | Export script; wire Trading Floor to a fake summary | 3 generations run end to end and write logs |
| 4 | Overnight run (film the Spark) | Narrator + Fact Guard + poster template | 30-50 generations logged; narration + posters for each |
| 5 | Buffer / fixes | Wire all rooms to real logs; record HQ fly-through; cold open film | Screen recordings exist |
| 6 | Finale on camera | Vault film; voiceover | Finale chart + narration recorded |
| 7 | - | Edit, thumbnail, upload, 2-3 Shorts | Published |

---

## LANES

- **Claude Code, session A:** `brain/`, `evolve/`, `finale.py`, `tests/`
- **Claude Code, session B (from Day 2, with the riso skills):** `visuals/`
- **Codex:** `market/`, `story/`, `scripts/export_for_visuals.py`
- One git worktree per lane. After each task, a different agent reviews the change
  against the NON-NEGOTIABLE RULES before merging.

---

## REPO LAYOUT

```
hedgefly/
  PLAN.md
  AGENTS.md
  CLAUDE.md
  README.md                 # credits
  data/                     # connectome + candles (gitignored)
  brain/                    # load connectome, batched sim, scramble
  market/                   # fetch, split, render chart, portfolio, fees
  evolve/                   # genome, mutation, selection, lineage, clans, logging
  finale.py
  story/                    # narrator.py, validate.py, prompts/
  visuals/
    hq/                     # riso HQ world (reads exported JSON)
    posters/                # riso poster template
    films/                  # canvas films + renders
  scripts/                  # bench.py, run_evolution.py, export_for_visuals.py
  runs/                     # generation logs (gitignored except final run)
  tests/
```
