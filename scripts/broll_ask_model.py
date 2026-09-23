"""B-roll: ask the local model, live, a question the finale's trader was asked - in its own words.

    uv run --no-sync python -m scripts.broll_ask_model
    uv run --no-sync python -m scripts.broll_ask_model --at 2026-03-17T18:35:00+00:00 --position long

The prompt is the finale's exactly: the trader's system prompt and the chart in words from
`story/llm.py` (`TRADER_SYSTEM`, `describe_window`), sent through the same client with the same
settings - temperature 0, reasoning off, an 8-token answer - that `finale_llm.py` uses.

The question is one the finale rehearsal asked (`finale_llm.py --rehearse`, the last bars of the
evolve set). A question from the six locked months would have to read that data here, and only
the two finale scripts may (PLAN.md rule 3). The rehearsal logged what the model answered at each
of its last hourly questions, so that answer is printed beside the live one. The default is its
last SELL: 20:35 UTC on 17 March 2026, asked while it was long - its logged equity moves with the
price up to that bar and stays flat from the next fill on.

Reads the evolve set and the rehearsal log, calls the model once, and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import threading
import time
from pathlib import Path

import pandas as pd

from market import load_evolve
from story.llm import ACTION_WORDS, LOCAL_URL, TRADER_SYSTEM, LocalModel, describe_window, parse_action
from story.narrator import simulation_running

REPO = Path(__file__).resolve().parents[1]
REHEARSAL = REPO / "runs" / "day6_full" / "finale_llm_rehearsal.json"
GHOST, DIM, BOLD, RESET = "\033[38;2;216;220;255m", "\033[2m", "\033[1m", "\033[0m"


def say(text: str, style: str = GHOST, pause: float = 0.0) -> None:
    print(f"{style}{text}{RESET}", flush=True)
    time.sleep(pause)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--at", default="2026-03-17T20:35:00+00:00",
                   help="a decision bar the rehearsal asked about (UTC, ISO format)")
    p.add_argument("--position", choices=("flat", "long"), default="long",
                   help="the position the model held at that bar")
    p.add_argument("--llm-url", default=LOCAL_URL)
    p.add_argument("--llm-model", default="qwen3.6:35b-a3b")
    args = p.parse_args()

    if simulation_running():
        raise SystemExit("a generation is simulating; the simulation owns the GPU (PLAN.md rule 9)")
    rehearsal = json.loads(REHEARSAL.read_text())
    logged = dict(rehearsal["passes"]["with_fees"]["competitors"]["llm"]["replies"]["last"])
    at = pd.Timestamp(args.at)
    if at.isoformat() not in logged:
        raise SystemExit(f"the rehearsal logged no answer at {at.isoformat()}; it has "
                         f"{', '.join(k[5:16] for k in logged)}")

    candles = load_evolve()
    t = int((pd.to_datetime(candles["timestamp"]) == at).to_numpy().argmax())
    if pd.Timestamp(candles["timestamp"].iloc[t]) != at:
        raise SystemExit(f"no bar at {at} in the evolve set")
    question = describe_window(candles, t, 1 if args.position == "long" else 0)
    model = LocalModel(args.llm_url, args.llm_model).check()

    say(f"HEDGEFLY · the finale's trader prompt · {args.llm_model} · temperature 0 · reasoning off",
        BOLD + GHOST, 0.8)
    say(f"bar {at:%Y-%m-%d %H:%M} UTC · BTC close ${candles['close'].iloc[t]:,.2f} · "
        f"a question from the finale rehearsal", DIM + GHOST, 1.2)
    say("\nSYSTEM", BOLD + GHOST)
    for line in TRADER_SYSTEM.splitlines():
        say(line, DIM + GHOST, 0.06)
    say("\nUSER", BOLD + GHOST)
    for line in question.splitlines():
        for part in textwrap.wrap(line, 100) or [""]:
            say(part, GHOST, 0.25)

    reply: dict = {}
    thread = threading.Thread(target=lambda: reply.update(text=model.chat(TRADER_SYSTEM, question)))
    started = time.time()
    thread.start()
    while thread.is_alive():
        print(f"\r{DIM}{GHOST}asking {args.llm_model} ... {time.time() - started:4.1f} s{RESET}", end="", flush=True)
        time.sleep(0.1)
    thread.join()
    if "text" not in reply:
        raise SystemExit("\nthe model did not answer")
    seconds = time.time() - started
    print(f"\r{' ' * 60}\r", end="")
    action = parse_action(reply["text"])
    word = {code: w for w, code in ACTION_WORDS.items()}.get(action, reply["text"])
    say(f"\n{args.llm_model} answers in {seconds:.1f} s:", GHOST, 0.3)
    say(f"    {reply['text']}", BOLD + GHOST, 1.0)
    say(f"\nthe finale rehearsal, same bar: {logged[at.isoformat()]}   "
        f"({REHEARSAL.relative_to(REPO)})", DIM + GHOST)
    if word != logged[at.isoformat()]:
        say("the live answer differs from the logged one", DIM + GHOST)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
