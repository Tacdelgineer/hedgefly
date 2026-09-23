"""B-roll: the two final champions' logged training day, replayed bar by bar in the terminal.

    uv run --no-sync python -m scripts.broll_replay                  # both champions, about 60 s
    uv run --no-sync python -m scripts.broll_replay --tribe real --seconds 45

Reads `runs/<run>/replay_champions.json`, which `scripts/replay_champions.py` (on the visuals
branch) wrote by running the run's final champions over its first fixed training day and checking
every action against the generation log. Each bar prints its time, the BTC close the fly decided on, the fly's decision
(BUY, SELL or HOLD) and its equity once that decision has filled. A decision that changes the position fills at the next bar's
open (PLAN.md rule 4) and is marked; a BUY while already long, or a SELL while flat, changes
nothing. Cyan is the real champion and magenta the scrambled one (visuals/style.md).

Reads that one file and prints. It writes nothing and runs no brain.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INK = {"real": (39, 242, 210), "scrambled": (255, 61, 154)}      # visuals/style.md
GHOST = (216, 220, 255)


def rgb(colour: tuple[int, int, int], text: str, bold: bool = False, dim: bool = False) -> str:
    style = ("1;" if bold else "") + ("2;" if dim else "")
    return f"\033[{style}38;2;{colour[0]};{colour[1]};{colour[2]}m{text}\033[0m"


def cell(tribe: str, bar: dict, following: dict | None) -> str:
    """One champion's column for one bar: its decision, its position, its equity."""
    ink, action = INK[tribe], bar["action"].upper()
    before = bar["position_before"]
    after = following["position_before"] if following else before
    filled = after != before
    word = rgb(ink, f"{action:<4}", bold=action != "HOLD", dim=action == "HOLD")
    held = rgb(ink, "LONG" if before else "flat", dim=not before)
    mark = rgb(ink, f"◆ {'BOUGHT' if after else 'SOLD'} @ next open".ljust(20), bold=True) if filled else " " * 20
    equity = f"${bar['equity']:,.2f}"
    return f"{word}  {held}  {rgb(ink, f'{equity:>9}')}  {mark}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, default=REPO / "runs" / "day7_validation")
    p.add_argument("--tribe", choices=("both", "real", "scrambled"), default="both")
    p.add_argument("--seconds", type=float, default=60.0, help="how long the whole day takes to print")
    args = p.parse_args()

    log = json.loads((args.run / "replay_champions.json").read_text())
    tribes = ("real", "scrambled") if args.tribe == "both" else (args.tribe,)
    champs = {t: log["champions"][t] for t in tribes}
    day, rules = log["window"], log["rules"]
    bars = len(next(iter(champs.values()))["bars"])
    pause = args.seconds / bars

    print(rgb(GHOST, f"HEDGEFLY · champion replay · run {log['run']}, generation {log['generation']}", bold=True))
    print(rgb(GHOST, f"training day {day['first_time'][:16].replace('T', ' ')} UTC → {day['last_time'][11:16]}"
                     f" · BTC {day['price_move_pct']:+.2f}% · {bars} five-minute bars"
                     f" · ${rules['start_cash']:,.0f} to start · {rules['fee_bps']:g} bps a side", dim=True))
    for t, c in champs.items():
        print(rgb(INK[t], f"  {t:<9} {c['id']}  born generation {c['born']}", bold=True))
    print()
    head = "time    BTC close  "
    for t in tribes:
        head += f"│ {t.upper() + ' · decision · position · equity':<44}"
    print(rgb(GHOST, head.rstrip(), dim=True))

    for k in range(bars):
        row = champs[tribes[0]]["bars"][k]
        price = f"${row['close']:,.2f}"
        line = f"{row['decided_at'][11:16]}  {price:>10}  "
        for t in tribes:
            b = champs[t]["bars"]
            line += f"│ {cell(t, b[k], b[k + 1] if k + 1 < bars else None)} "
        print(line, flush=True)
        time.sleep(pause)

    print()
    for t, c in champs.items():
        agree = c["against_the_log"]
        print(rgb(INK[t], f"  {t:<9} ends the day at ${c['final_equity']:,.2f} after {c['trades']} trades"
                          f" · {agree['same_action']} of {agree['bars']} decisions match the generation log",
                  bold=True))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
