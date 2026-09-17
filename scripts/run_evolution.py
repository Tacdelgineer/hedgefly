"""Run the evolution loop and write a run's logs (PLAN.md EVOLUTION, rule 7).

    uv run python -m scripts.run_evolution --generations 3
    uv run python -m scripts.run_evolution --generations 50 --run-id overnight

Each generation draws one window of the evolve set and gives it to both tribes and to all three
competitors, then writes runs/<run_id>/gen_XXX.json and gen_XXX_summary.json. Nothing here
touches the locked test set (rule 3); that is finale.py's alone.
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
    p.add_argument("--bars", type=int, default=default.bars, help="decision bars per generation window")
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
    print("\n| gen | real best | scrambled best | momentum | random | buy & hold | window move |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for s in report["summaries"]:
        t, c = s["tribes"], s["competitors"]
        print(f"| {s['generation']} | ${t['real']['final_equity']['best']:,.2f} "
              f"| ${t['scrambled']['final_equity']['best']:,.2f} "
              f"| ${c['momentum']['final_equity']:,.2f} | ${c['random']['final_equity']:,.2f} "
              f"| ${c['buy_and_hold']['final_equity']:,.2f} | {s['window']['price_move_pct']:+.2f}% |")
    for name in ("real", "scrambled"):
        hero = report["summaries"][-1]["tribes"][name]["hero_lineage"]
        print(f"\n{name} hero lineage: {hero['id']} (born gen {hero['born']}, {hero['origin']}, "
              f"{hero['generations_lived']} generation(s) alive), fitness {hero['fitness']:+.4f}")
        print(f"  ancestors: {' -> '.join(hero['ancestors']) or '(a founder)'}")


if __name__ == "__main__":
    main()
