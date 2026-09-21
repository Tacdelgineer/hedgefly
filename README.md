# Hedgefly: Natural Selection Capital

100 real fruit-fly brains (the MaleCNS v1.0 connectome) trade Bitcoin. The brains stay frozen;
only the genome that connects market data to the brain, and brain output to trades, evolves.
See [PLAN.md](PLAN.md). Its non-negotiable rules apply to every change.

## Setup

Built for a DGX Spark (ARM64, GB10, CUDA 13). Environments are managed with uv only.

```bash
uv sync
uv run python -c "import torch; assert torch.cuda.is_available(), 'CPU-only torch'"
```

Download the connectome (CC BY 4.0, about 1.1 GB) into `data/` (gitignored):

```bash
B=https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome
curl -o data/body-annotations.feather       $B/body-annotations-male-cns-v1.0-minconf-0.5.feather
curl -o data/body-neurotransmitters.feather $B/body-neurotransmitters-male-cns-v1.0.feather
curl -o data/connectome-weights.feather     $B/connectome-weights-male-cns-v1.0-minconf-0.5.feather
```

The first load filters the weights table and caches it in `data/cache/` (about 25 s).

Download the candles. BTC-USD 5-minute bars; the last 6 months are split into a separate file
that only `finale.py` ever opens (PLAN.md rule 3):

```bash
uv run python -m market.fetch_btc --start 2022-09-01
```

Brain speed benchmark (ms per brain step by population and subset, GPU only):

```bash
uv run scripts/bench.py
```

Evolve (writes `runs/<run_id>/`, one log and one summary per generation):

```bash
uv run python -m scripts.run_evolution --generations 3
uv run python -m scripts.check_sensitivity        # do enough flies react to the chart?
```

## A deliberate fairness choice: both tribes use the real fly's eye

The scrambled tribe is the control that says whether the fruit fly's actual wiring matters, so
the two tribes must differ in the wiring and in nothing else (PLAN.md rule 6).

One thing that looks like wiring but is not: the **eye layout**. Photoreceptors carry no
coordinate in the MaleCNS release, so nfly places each one at the synapse-weighted mean hex
coordinate of its columnar targets - that is, it computes where a photoreceptor looks *from the
edges*. Scrambling the edges scatters the photoreceptors at random across the chart.

Handing the scrambled tribe an eye built from its own scrambled edges would therefore not test
its wiring, it would blindfold it, and the real tribe would win a race against an opponent that
cannot see. **Both tribes are built with the photoreceptor layout computed from the real
connectome** (`brain.build_eye`, passed to `TribeAgent.build(..., eye=...)`), and the readout
groups both tribes vote through come from the release's annotations rather than from the edges
for the same reason. What the scrambled tribe loses is the circuit between the eye and the
readout - which is the thing under test.

Tested in `tests/test_fairness.py`: an eye built from scrambled edges really does land
somewhere else, and the two tribes really are built with the same one.

## Dependencies

- `nfly` is pinned to commit `82d227eed4a35cd261f81d202e0d30458c9e4e73` in `pyproject.toml`
  (`[tool.uv.sources]`). Change the pin on purpose, never by accident.
- `gymnasium` is a direct dependency because `import nfly` imports it (`nfly/agent.py`),
  even though nfly only declares it in its `games` extra.

## The world

**Natural Selection Capital HQ** is the run as a place: isometric cutaway rooms in a neon
risograph look, drawn entirely in code on one canvas, replaying `runs/<run_id>/` room by room.
Published from `gh-pages`: <https://tacdelgineer.github.io/hedgefly/>

- Source: `visuals/hq2/index.html`, over the shared core in `visuals/lib/neon-riso.js`.
- Data: `visuals/hq/runs.json`, written only by `scripts/export_for_visuals.py`
  (`visuals/hq/data-contract.md`, v4). The page replays it and never re-runs anything.
- One file: `node scripts/build_standalone.mjs` inlines the core and the data into
  `visuals/dist/hedgefly.html`, which opens by double-click with no server.
- 23 rooms, and three ways to look at the whole building: **K** the blueprint plan, **O** the
  dollhouse section, **N** night-to-day light tied to the generation. **I** opens the About
  panel; the full key list is in the legend and in that panel.
- Film: `node scripts/record_hq.mjs`, `record_extra.mjs`, `record_rooms.mjs` and
  `record_new.mjs` write PNG frames plus mp4, wide and vertical, into `results/film*`.
  `results/final_footage/{wide,vertical}` collects all 40 of those mp4s under names that put
  them in script order; `ORDER.txt` there says which reel each one came from. Both cuts run
  7:10.8. Untracked, like the reels it is copied from.
- Checks: `node scripts/smoke_rooms.mjs` draws every room and view once and fails on anything
  that throws; `node scripts/test_director.mjs` presses every director key in the built file.

One script re-runs the simulation for the visuals rather than replaying it, and it is the only
one: `scripts/replay_champions.py`, for the Replay Room. The margins a fly decides on and the
readout groups behind them are never written to a generation log, so it re-runs the two final
champions on one day of the **evolve** set and writes them down, which is what keeps rule 8
true for that room. It checks itself against the actions the run logged.

## Credits

- **MaleCNS v1.0 connectome.** Berg, S., Beckett, I. R., Costa, M., Schlegel, P., Januszewski, M.,
  Marin, E. C., Nern, A., et al. *Sexual dimorphism in the complete connectome of the Drosophila
  male central nervous system.* Cell (2026).
  [doi:10.1016/j.cell.2026.08.015](https://doi.org/10.1016/j.cell.2026.08.015).
  Data from FlyEM (HHMI Janelia Research Campus) and collaborators, released under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): <https://male-cns.janelia.org/>.
- **nfly** by Zhengxu Yu, <https://github.com/zhengxuyu/nfly>, MIT License. Connectome loader and
  rate-based brain dynamics.
- **creative-skills** by IshaanKalra2103, <https://github.com/IshaanKalra2103/creative-skills>,
  MIT License. The `riso-rooms` and `hand-drawn-canvas-animation` skills used for the visuals.
- The visual style is inspired by Kevin Ngo's "a small light, room by room" and his "life of a
  fruit fly" animation ([@kevin_t_ngo](https://twitter.com/kevin_t_ngo)). Inspiration only; no
  artwork, scenes or frames are copied, and every mark in this repo is drawn in code.

The short form, as it appears in the world's About panel and in `skills/neon-riso-fly/SKILL.md`:

> Visual style inspired by Kevin Ngo's "a small light, room by room" and his "life of a fruit fly" animation (@kevin_t_ngo). Built with the riso-rooms and hand-drawn-canvas-animation skills by IshaanKalra2103 (MIT). Connectome: MaleCNS v1.0 (Berg et al., Cell 2026). Brain simulator: nfly (MIT).
