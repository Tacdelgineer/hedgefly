"""Run the evolution loop and write a run's logs (PLAN.md EVOLUTION, rule 7).

    uv run python -m scripts.run_evolution --generations 3
    uv run python -m scripts.run_evolution --generations 50 --run-id overnight

Once per run it draws four fixed days of the evolve set; every generation, every fly of both
tribes trades all four, and fitness is the mean log return over them. Writes
runs/<run_id>/gen_XXX.json and gen_XXX_summary.json. Nothing here touches the locked test set
(rule 3); that belongs to the two finale scripts alone.
"""

from __future__ import annotations

import argparse
import dataclasses

import torch

from evolve import Config, run


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default = Config()
    p.add_argument("--generations", type=int, default=default.generations)
    p.add_argument("--population", type=int, default=default.population)
    p.add_argument("--bars", type=int, default=default.bars, help="decision bars per fixed day")
    p.add_argument("--windows", type=int, default=default.windows, help="fixed days every fly trades")
    p.add_argument("--fee-bps", type=float, default=default.fee_bps, help="per side")
    p.add_argument("--min-hold-bars", type=int, default=default.min_hold_bars)
    p.add_argument("--mutation-rate", type=float, default=default.mutation_rate)
    p.add_argument("--seed", type=int, default=default.seed)
    p.add_argument("--device", default=default.device)
    p.add_argument("--run-id", default=None, help="name of the directory under runs/")
    args = p.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA is not available in this env; refusing to evolve on CPU (PLAN.md SETUP)")

    cfg = dataclasses.replace(Config(), **{k: v for k, v in vars(args).items()
                                           if k != "run_id" and v is not None})
    report = run(cfg, run_id=args.run_id)

    print(f"\n{report['generations']} generations in {report['minutes_total']:.2f} min "
          f"({report['minutes_per_generation']:.2f} min per generation, both tribes)")
    print(f"genome: {report['genome_size']:,} numbers per fly "
          f"({report['brain']['readout_groups']} readout groups)")
    print(f"logs: {report['run_dir']}")
    c = report["competitors"]
    print(f"competitors on the fixed days (geometric mean): momentum ${c['momentum']['final_equity']:,.2f}, "
          f"random ${c['random']['final_equity']:,.2f}, buy & hold ${c['buy_and_hold']['final_equity']:,.2f}")
    print("\n| gen | real best | real median | scrambled best | scrambled median | trades/day real | trades/day scr |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for s in report["summaries"]:
        t = s["tribes"]
        print(f"| {s['generation']} | ${t['real']['final_equity']['best']:,.2f} "
              f"| ${t['real']['final_equity']['median']:,.2f} "
              f"| ${t['scrambled']['final_equity']['best']:,.2f} "
              f"| ${t['scrambled']['final_equity']['median']:,.2f} "
              f"| {t['real']['trades']['median_per_day']:g} | {t['scrambled']['trades']['median_per_day']:g} |")
    for name in ("real", "scrambled"):
        hero = report["summaries"][-1]["tribes"][name]["hero_lineage"]
        print(f"\n{name} hero lineage: {hero['id']} (born gen {hero['born']}, {hero['origin']}, "
              f"{hero['generations_lived']} generation(s) alive), fitness {hero['fitness']:+.4f}")
        print(f"  ancestors: {' -> '.join(hero['ancestors']) or '(a founder)'}")


if __name__ == "__main__":
    main()
