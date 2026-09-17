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

Brain speed benchmark (ms per brain step by population and subset, GPU only):

```bash
uv run scripts/bench.py
```

## Dependencies

- `nfly` is pinned to commit `82d227eed4a35cd261f81d202e0d30458c9e4e73` in `pyproject.toml`
  (`[tool.uv.sources]`). Change the pin on purpose, never by accident.
- `gymnasium` is a direct dependency because `import nfly` imports it (`nfly/agent.py`),
  even though nfly only declares it in its `games` extra.

## Credits

- **MaleCNS v1.0 connectome.** Berg, S., Beckett, I. R., Costa, M., Schlegel, P., Januszewski, M.,
  Marin, E. C., Nern, A., et al. *Sexual dimorphism in the complete connectome of the Drosophila
  male central nervous system.* Cell (2026).
  [doi:10.1016/j.cell.2026.08.015](https://doi.org/10.1016/j.cell.2026.08.015).
  Data from FlyEM (HHMI Janelia Research Campus) and collaborators, released under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): <https://male-cns.janelia.org/>.
- **nfly** by Zhengxu Yu, <https://github.com/zhengxuyu/nfly>, MIT License. Connectome loader and
  rate-based brain dynamics.
- **creative-skills** by Ishaan Kalra, <https://github.com/IshaanKalra2103/creative-skills>,
  MIT License. The `riso-rooms` and `hand-drawn-canvas-animation` skills used for the visuals.
- The visual style is inspired by Kevin Ngo's "a small light, room by room". Inspiration only;
  no artwork or scenes are copied.
