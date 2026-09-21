"""Re-run the two final champions on ONE training day, writing down what a generation never does.

    uv run python -m scripts.replay_champions --run runs/day7_validation --window 0

A generation log (PLAN.md rule 7) keeps every fly's actions and equity, bar by bar, but not the
numbers the decision was made ON: the margin each vote cleared, and which readout groups were
loud when it did. Those live for one line inside `FlyRun.decide` and are thrown away. The
Replay Room needs them, and rule 8 says a viewer may only see numbers that were written down -
so this script writes them down.

It re-simulates the last generation's best real fly and best scrambled fly, one at a time, on
one of the run's four fixed training days, out of the EVOLVE set. It never touches the six
months the finale is for, and it never selects, breeds or scores anything: it replays one day
and records it.

The genomes come out of the generation log, where they are rounded to five decimals
(evolve/logs.py). That is a real difference from the tensors the run held, so this script
checks its own replay against the actions the log recorded for the same fly on the same day and
writes the agreement into the output. A room may then say how closely the replay matched.

Output: `<run>/replay_champions.json`
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from nfly import load_malecns

from brain import Genome, TribeAgent, build_eye, scramble
from brain.agent import MIN_CALIBRATION_CHARTS, MOTOR_SUPERCLASSES
from market import Wallet, load_evolve, render_range, trade_window
from market.chart import WINDOW

REPO = Path(__file__).resolve().parents[1]
TRIBES = ("real", "scrambled")
TOP_GROUPS = 6            # readout groups named per bar: the loudest few, not a wall of 498
EYE_BARS = 16             # bars whose photoreceptor drive is kept, for the fly's-eye room
ACTION_NAMES = ("hold", "buy", "sell")


# ---- the run being replayed ----------------------------------------------------------------

def last_generation(run_dir: Path) -> tuple[int, dict]:
    logs = sorted(run_dir.glob("gen_[0-9][0-9][0-9].json"))
    if not logs:
        raise SystemExit(f"no generation logs in {run_dir}")
    return int(logs[-1].stem.split("_")[1]), json.loads(logs[-1].read_text())


def champion(log: dict, tribe: str) -> tuple[int, dict]:
    """The fly the log says won this tribe's generation, and where it sits in the population."""
    flies = log["tribes"][tribe]["flies"]
    best = max(range(len(flies)), key=lambda k: flies[k]["fitness"])
    return best, flies[best]


def genome_of(log: dict, tribe: str, seat: int) -> Genome:
    """One fly's genome, as a population of one, exactly as the log rounded it."""
    g = log["tribes"][tribe]["genomes"]
    return Genome(chart_gain=torch.tensor([g["chart_gain"][seat]], dtype=torch.float32),
                  position_gain=torch.tensor([g["position_gain"][seat]], dtype=torch.float32),
                  readout_w=torch.tensor([g["readout_w"][seat]], dtype=torch.float32))


def group_names(conn, readout_idx: torch.Tensor) -> list[str]:
    """The name of each readout group, in the order `brain.agent.readout_groups` numbers them.

    That function returns the grouping but not its labels, and it builds them with
    `np.unique(..., return_inverse=True)`, whose inverse indexes the SORTED unique keys. The same
    keys sorted the same way are therefore the group names, in group order."""
    rows = conn.neurons.iloc[readout_idx.cpu().numpy()]

    def column(name: str) -> np.ndarray:
        if name not in rows.columns:
            return np.full(len(rows), "", dtype=object)
        return rows[name].fillna("").astype(str).to_numpy()

    motor = rows["super_class"].isin(MOTOR_SUPERCLASSES).to_numpy()
    cell_type, sub_class = column("cell_type"), column("sub_class")
    key = np.where(motor & (sub_class != ""), "muscle:" + sub_class, "type:" + cell_type)
    key = np.where(key == "type:", "untyped:" + rows["root_id"].astype(str).to_numpy(), key)
    return [str(k) for k in np.unique(key)]


# ---- one champion, one day -----------------------------------------------------------------

def replay_one(agent: TribeAgent, genome: Genome, candles, first: int, last: int,
               wallet_rules: dict, log_actions: np.ndarray | None) -> dict:
    """Trade the day, recording every bar's decision and the numbers behind it.

    The action is whatever `FlyRun.decide` returns - the real decision code, not a copy of it.
    The margins are rebuilt around that call: `decide` compares each logit with the fly's own
    running average, so the average read BEFORE the call and the votes recomputed from the state
    the call left behind give back exactly the two numbers it decided on. `vote_inputs` is a pure
    function of that state, so recomputing it changes nothing and re-runs no brain step."""
    run = agent.start(genome)
    body, stats = agent.body, agent.stats
    bars, held = [], []

    def decide(chart: np.ndarray, position: np.ndarray) -> np.ndarray:
        before = None if run.vote_average is None else run.vote_average.clone()
        action = run.decide(chart, position)
        votes = body.vote_inputs(run.h, stats)                            # (1, G) as decide saw it
        logits = torch.bmm(votes.unsqueeze(1), run.genome.readout_w).squeeze(1)      # (1, 2)
        change = torch.zeros_like(logits) if before is None else logits - before
        held.append({"position": int(position[0]), "votes": votes[0].cpu().numpy(),
                     "change": change[0].cpu().numpy()})
        return action

    started = time.perf_counter()
    result = trade_window(decide, candles, first, last, Wallet(1, **wallet_rules))
    elapsed = time.perf_counter() - started

    readout_w = genome.readout_w[0].cpu().numpy()                          # (G, 2)
    opens = candles["open"].to_numpy()
    closes = candles["close"].to_numpy()
    stamps = candles["timestamp"]
    loudness = np.zeros(readout_w.shape[0])

    for i, (record, action) in enumerate(zip(held, result.actions[:, 0])):
        t = first + i
        votes, change = record["votes"], record["change"]
        lead = int(np.argmax(change))                                      # the vote that came closest
        contribution = votes * readout_w[:, lead]
        order = np.argsort(-np.abs(contribution))[:TOP_GROUPS]
        loudness += np.abs(votes)
        bars.append({
            "bar": i,
            "decided_at": stamps.iloc[t].isoformat(),
            "filled_at": stamps.iloc[t + 1].isoformat(),
            "close": round(float(closes[t]), 2),
            "fill_price": round(float(opens[t + 1]), 2),
            "position_before": record["position"],
            "action": ACTION_NAMES[int(action)],
            "margin_buy": round(float(change[0]), 6),
            "margin_sell": round(float(change[1]), 6),
            "leading_vote": ("buy", "sell")[lead],
            "equity": round(float(result.equity[i, 0]), 2),
            "top_groups": [{"group": int(g), "activity": round(float(votes[g]), 4),
                            "contribution": round(float(contribution[g]), 6)} for g in order],
        })

    counts = np.bincount(result.actions[:, 0].astype(int), minlength=3)
    out = {
        "final_equity": round(float(result.final_equity[0]), 2),
        "trades": int(result.trades[0]),
        "actions": {ACTION_NAMES[k]: int(counts[k]) for k in range(3)},
        "seconds": round(elapsed, 1),
        "ms_per_bar": round(1000 * elapsed / len(bars), 1),
        "busiest_groups": [int(g) for g in np.argsort(-loudness)[:12]],
        "bars": bars,
    }
    if log_actions is not None:
        same = int((result.actions[:, 0] == log_actions).sum())
        out["against_the_log"] = {
            "bars": int(len(log_actions)), "same_action": same,
            "agreement": round(same / len(log_actions), 4),
            "note": "the genome was reloaded from the log at five decimals, so this is how "
                    "closely the replay reproduced the run's own decisions",
        }
    return out


# ---- the fly's eye -------------------------------------------------------------------------

def eye_block(agent: TribeAgent, genome: Genome, charts: np.ndarray, bars: list[int]) -> dict | None:
    """Where each photoreceptor looks at the chart, and what it drew from a few of the day's bars.

    nfly's retina samples the 64x64 chart at one point per photoreceptor; `grid` is that point in
    [-1, 1]. Those points ARE the compound eye's layout, computed from the real connectome's edges
    (PLAN.md), so a room can draw the chart the way the eye actually carves it up."""
    eye = agent.body.eye
    grid = eye.retina.grid.detach().cpu().numpy().reshape(-1, 2)          # (K, 2) in [-1, 1]
    if grid.shape[0] != int(eye.idx.numel()):
        return None
    frames = []
    for b in bars:
        chart = torch.as_tensor(charts[b], dtype=torch.float32, device=agent.body.device)
        drive = eye.encode(torch.stack([chart, torch.zeros_like(chart)]).unsqueeze(0))
        frames.append({"bar": int(b), "drive": [round(float(v), 3) for v in drive.flatten().cpu().numpy()]})
    return {"photoreceptors": int(grid.shape[0]),
            "layout": [[round(float(u), 4), round(float(v), 4)] for u, v in grid],
            "built_from": "real",
            "note": "drive from the frame channel alone; in a trading bar the second channel "
                    "carries the chart's change since the previous bar",
            "frames": frames}


# ---- main --------------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", default="runs/day7_validation", help="the run whose champions to replay")
    p.add_argument("--window", type=int, default=0, help="which fixed TRAINING day (0-based)")
    p.add_argument("--device", default="cuda")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    run_dir = (REPO / args.run).resolve()
    generation, log = last_generation(run_dir)
    cfg = log["config"]
    if not (0 <= args.window < len(log["windows"])):
        raise SystemExit(f"this run has {len(log['windows'])} training days; --window {args.window} is not one")
    day = log["windows"][args.window]
    first, last = int(day["first_index"]), int(day["last_index"])

    candles = load_evolve()
    print(f"{run_dir.name}: generation {generation}, training day {args.window} "
          f"({day['first_time']} .. {day['last_time']}, {day['price_move_pct']:+.2f}%)")
    if abs(float(candles["open"].iloc[first + 1]) - float(day["entry_price"])) > 0.01:
        raise SystemExit("the evolve file is not the one this run traded: the first fill price differs")

    calibration = render_range(candles, WINDOW - 1, WINDOW - 2 + MIN_CALIBRATION_CHARTS)
    charts = render_range(candles, first, last)
    conn = load_malecns(cfg["data_dir"])
    eye = build_eye(conn)
    print(f"connectome: {conn.n_neurons:,} neurons, {conn.n_edges:,} edges; "
          f"{int(eye.idx.numel()):,} photoreceptors")

    wallet_rules = {"start_cash": cfg["start_cash"], "fee_bps": cfg["fee_bps"],
                    "min_hold_bars": cfg["min_hold_bars"]}
    payload = {
        "run": run_dir.name, "generation": generation,
        "recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data": "evolve set", "window_index": args.window,
        "window": {k: day[k] for k in ("first_time", "last_time", "bars", "entry_price",
                                       "exit_price", "price_move_pct")},
        "bar_minutes": 5,
        "rules": {k: cfg[k] for k in ("start_cash", "fee_bps", "min_hold_bars",
                                      "steps_per_candle", "vote_memory")},
        "champions": {},
    }

    for tribe in TRIBES:
        wiring = conn if tribe == "real" else scramble(conn, seed=cfg["scramble_seed"])
        built = time.perf_counter()
        agent = TribeAgent.build(wiring, calibration, device=args.device, eye=eye,
                                 steps_per_candle=cfg["steps_per_candle"], vote_memory=cfg["vote_memory"])
        seat, fly = champion(log, tribe)
        genome = genome_of(log, tribe, seat)
        print(f"{tribe}: {agent.n_groups} readout groups, built in {time.perf_counter() - built:.0f} s; "
              f"champion {fly['id']} (seat {seat}, fitness {fly['fitness']:+.6f})")

        logged = np.asarray(log["tribes"][tribe]["actions_by_window"][args.window][seat], dtype=np.int8)
        block = replay_one(agent, genome, candles, first, last, wallet_rules, logged)
        block |= {
            "id": fly["id"], "parent": fly["parent"], "born": fly["born"], "seat": seat,
            "logged": {"fitness": fly["fitness"], "final_equity": fly["final_equity"],
                       "equity_this_day": fly["final_equity_by_window"][args.window],
                       "trades_all_days": fly["trades"]},
            "group_names": group_names(wiring, agent.body.readout_idx),
            "group_sizes": [int(v) for v in agent.body.group_size.cpu().numpy()],
        }
        if tribe == "real":
            step = max(1, len(charts) // EYE_BARS)
            payload["eye"] = eye_block(agent, genome, charts, list(range(0, len(charts), step))[:EYE_BARS])
        payload["champions"][tribe] = block
        print(f"   replayed: ${block['final_equity']:,.2f}, {block['trades']} trades, "
              f"{block['ms_per_bar']:.0f} ms/bar, agreement with the log "
              f"{block['against_the_log']['agreement']:.1%}")
        del agent, wiring
        torch.cuda.empty_cache()

    out = Path(args.out) if args.out else run_dir / "replay_champions.json"
    out.write_text(json.dumps(payload, indent=1, allow_nan=False) + "\n")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
