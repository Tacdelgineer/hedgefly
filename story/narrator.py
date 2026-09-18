"""The narrator: one generation summary in, one story out (PLAN.md NARRATOR + POSTER).

    uv run python -m story.narrator --run runs/day4_full
    uv run python -m story.narrator --run runs/day4_full --generation 12

Reads `runs/<run_id>/gen_XXX_summary.json` and nothing else - never the raw logs, never the
simulation - and writes `story/<run_id>/gen_XXX.json`. The model picks words and which stats
the poster should print; the poster template reads the numbers themselves out of the summary,
so the model never types a number onto a poster.

Everything it writes goes through the Fact Guard (`story/validate.py`) before it is kept. A
rejected story is sent back with the complaints attached and rewritten, up to `--attempts`
times; a story that never passes is not written at all.

Rule 9: the simulation owns the GPU. This refuses to start while a run is simulating.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from .llm import LOCAL_MODEL, LOCAL_URL, LocalModel
from .validate import ROOMS, check

REPO = Path(__file__).resolve().parents[1]
STORIES = REPO / "story"
ATTEMPTS = 4

SYSTEM = """You narrate a nature documentary about fruit-fly brains trading Bitcoin.

100 flies with a real fruit fly's connectome race 100 flies whose wiring has been shuffled.
The brains are frozen; only the little genome connecting the chart to the brain evolves. Each
generation both tribes trade the same day of the market, the top fifth survive, and the rest
are their children and a few newcomers.

Write about what the numbers in front of you actually say. Tone: calm, precise, a little awed
by the flies. Never sentimental, never hyped.

THE ONE UNBREAKABLE RULE: every number you write must appear in the summary you were given.
Do not compute, round beyond the obvious, average, or estimate anything. If you are not sure a
number is in the summary, write no number - the sentence is always better without it.

Answer with JSON only, no code fence, no commentary:
{"headline": "at most 8 words",
 "narration": "1 to 3 sentences",
 "poster": {"title": "short", "subtitle": "short",
            "featured_room": "one of: %s",
            "stat_keys": ["dotted keys from the summary, e.g. tribes.real.final_equity.best"]}}""" % " | ".join(ROOMS)


def digest(summary: dict) -> dict:
    """The parts of a summary worth a paragraph. The whole thing is mostly curves."""
    out = {"generation": summary.get("generation"), "window": summary.get("window"),
           "competitors": summary.get("competitors"), "tribes": {}}
    for name, tribe in summary.get("tribes", {}).items():
        out["tribes"][name] = {k: tribe[k] for k in
                               ("population", "alive", "broke", "fitness", "final_equity", "trades",
                                "action_share", "held_back_by_minimum_hold", "hero_lineage")
                               if k in tribe}
        if "top" in tribe:
            out["tribes"][name]["top"] = tribe["top"][:3]
    return out


def simulation_running() -> bool:
    """Rule 9: the narrator never runs while a generation is simulating."""
    found = subprocess.run(["pgrep", "-f", "scripts.run_evolution"], capture_output=True, text=True)
    return found.returncode == 0 and bool(found.stdout.strip())


def parse_json(reply: str) -> dict:
    """The model's JSON, with or without the code fence it was asked not to use."""
    fenced = re.search(r"```(?:json)?\s*(.+?)```", reply, re.S)
    text = fenced.group(1) if fenced else reply
    brace = text.find("{")
    if brace < 0:
        raise ValueError(f"no JSON in the reply: {reply[:120]!r}")
    return json.loads(text[brace:text.rfind("}") + 1])


def narrate(summary: dict, model: LocalModel, attempts: int = ATTEMPTS) -> dict:
    """A story the Fact Guard accepts, or an exception carrying the last complaints."""
    prompt = json.dumps(digest(summary), indent=1)
    complaints: list[str] = []
    for attempt in range(attempts):
        ask = prompt if not complaints else (
            f"{prompt}\n\nYour previous answer was rejected by the fact checker:\n"
            + "\n".join(f"- {c}" for c in complaints)
            + "\nWrite it again. Remove any number you cannot find in the summary above.")
        try:
            story = parse_json(model.chat(SYSTEM, ask, max_tokens=400))
        except (ValueError, json.JSONDecodeError) as error:
            complaints = [f"that was not valid JSON ({error})"]
            continue
        verdict = check(story, summary)
        if verdict.ok:
            return {**story, "generation": summary.get("generation"), "attempts": attempt + 1}
        complaints = verdict.problems
    raise ValueError(f"the fact guard rejected {attempts} attempts: {'; '.join(complaints)}")


def summaries_of(run_dir: Path, generation: int | None) -> list[Path]:
    if generation is not None:
        path = run_dir / f"gen_{generation:03d}_summary.json"
        if not path.exists():
            raise SystemExit(f"{path} does not exist")
        return [path]
    found = sorted(run_dir.glob("gen_[0-9][0-9][0-9]_summary.json"))
    if not found:
        raise SystemExit(f"no generation summaries in {run_dir}")
    return found


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, required=True, help="a run directory under runs/")
    p.add_argument("--generation", type=int, default=None, help="just this one")
    p.add_argument("--attempts", type=int, default=ATTEMPTS, help="rewrites before giving up")
    p.add_argument("--llm-url", default=LOCAL_URL)
    p.add_argument("--llm-model", default=LOCAL_MODEL)
    p.add_argument("--out", type=Path, default=None, help="default story/<run_id>/")
    p.add_argument("--force", action="store_true", help="narrate even while a run is simulating")
    args = p.parse_args()

    if simulation_running() and not args.force:
        raise SystemExit("a generation is simulating; the simulation owns the GPU (PLAN.md rule 9). "
                         "Narrate afterwards, or pass --force if you know the run has the GPU to spare.")

    model = LocalModel(args.llm_url, args.llm_model).check()
    out_dir = args.out or STORIES / args.run.name
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in summaries_of(args.run, args.generation):
        summary = json.loads(path.read_text())
        generation = summary.get("generation", 0)
        try:
            story = narrate(summary, model, args.attempts)
        except ValueError as error:
            print(f"gen {generation:3d}: NOT WRITTEN - {error}")
            continue
        target = out_dir / f"gen_{generation:03d}.json"
        target.write_text(json.dumps(story, indent=1) + "\n")
        print(f"gen {generation:3d}: {story['headline']}  ({story['attempts']} attempt(s)) -> {target}")


if __name__ == "__main__":
    main()
