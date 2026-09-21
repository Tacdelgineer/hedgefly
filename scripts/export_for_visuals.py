"""Turn a run's logs into the one file the visuals read (visuals/hq/data-contract.md, v2).

    uv run python -m scripts.export_for_visuals --run runs/day6_full
    uv run python -m scripts.export_for_visuals --run runs/day6_full --out visuals/hq/runs.json

The visuals replay logs and never re-run the simulation (PLAN.md rule 7), and every number
they show comes out of those logs (rule 8). This is the only bridge between the two: it reads
the run's manifest for the four fixed days and the competitors, `gen_XXX_summary.json` for the
tribe figures, and `gen_XXX.json` for each fly's equity and whether it was eliminated.

The candlesticks are the real bars of each fixed day: the manifest logs each day's first and
last bar index, and the evolve set is read at exactly those rows. Before trusting the indices
it checks that the bar after the first one opens at the entry price the run logged, so a
re-fetched data file whose rows have moved is caught here instead of charting the wrong day.

It never opens the locked test set; the finale writes its own file.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from market import Wallet, load_evolve

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "visuals" / "hq" / "runs.json"
CONTRACT_VERSION = 4        # v4 = v3 + lineage, the trade tape, the champion replay and the eye
TRIBES = ("real", "scrambled")
COMPETITORS = ("momentum", "random", "buy_and_hold")
BARS_PER_CANDLE = 6         # 288 five-minute bars -> 48 thirty-minute candles a day
PRICE_TOLERANCE = 0.01      # dollars: the logged entry price is rounded to cents


def candles_for(evolve: pd.DataFrame, window: dict, per: int = BARS_PER_CANDLE) -> list[list[float]]:
    """A day's decision bars as [open, high, low, close] candles of `per` bars each.

    Checks the indices against the price the run logged first: the bar after the day's first
    one is where the flies' first trade filled, so its open must be the logged entry price."""
    first, last = int(window["first_index"]), int(window["last_index"])
    filled = float(evolve["open"].iloc[first + 1])
    if abs(filled - float(window["entry_price"])) > PRICE_TOLERANCE:
        raise SystemExit(f"bar {first + 1} opens at {filled}, but the run logged an entry price of "
                         f"{window['entry_price']}: the evolve file is not the one this run traded")
    bars = evolve.iloc[first:last + 1]
    group = np.arange(len(bars)) // per
    agg = bars.groupby(group).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
    return [[round(float(r.o), 2), round(float(r.h), 2), round(float(r.l), 2), round(float(r.c), 2)]
            for r in agg.itertuples()]


def generations(run_dir: Path) -> list[tuple[Path, Path]]:
    """(summary, full log) per generation, in order. A generation without both is skipped."""
    pairs = []
    for summary in sorted(run_dir.glob("gen_[0-9][0-9][0-9]_summary.json")):
        full = run_dir / summary.name.replace("_summary", "")
        if full.exists():
            pairs.append((summary, full))
    if not pairs:
        raise SystemExit(f"no finished generations in {run_dir}")
    return pairs


def seats(log: dict, tribe: str) -> list[dict]:
    """One entry per fly, in log order. A run with validation days adds each fly's validation
    equity, so a visual can show a fly that is good on the days it was selected on and poor on
    the days it never saw."""
    out = []
    for fly in log["tribes"][tribe]["flies"]:
        seat = {"equity": round(float(fly["final_equity"]), 2), "eliminated": bool(fly["eliminated"]),
                "trades_per_day": round(float(fly["trades_per_day"]), 2),
                "fitness": round(float(fly["fitness"]), 6)}
        if "validation_final_equity" in fly:
            seat["validation_equity"] = round(float(fly["validation_final_equity"]), 2)
        out.append(seat)
    return out


def tribe_frame(summary: dict, log: dict, tribe: str) -> dict:
    digest = summary["tribes"][tribe]
    return {"survived": digest["survived"], "eliminated": digest["eliminated"],
            "equity": {k: digest["final_equity"][k] for k in ("best", "median", "mean", "worst")},
            "fitness": {k: digest["fitness"][k] for k in ("best", "median")},
            "trades": {k: digest["trades"][k] for k in ("median_per_day", "max_per_day", "total")},
            "flies": seats(log, tribe)} | side_blocks(digest)


def side_blocks(digest: dict) -> dict:
    """The fee-free and validation scores a run logged beside the one selection used."""
    out = {}
    if "fee_free" in digest:
        out["fee_free"] = {"fitness": {k: digest["fee_free"]["fitness"][k] for k in ("best", "median")},
                           "equity": {k: digest["fee_free"]["final_equity"][k] for k in ("best", "median")}}
    if "validation" in digest:
        v = digest["validation"]
        out["validation"] = {"fitness": {k: v["fitness"][k] for k in ("best", "median", "mean")},
                             "equity": {k: v["final_equity"][k] for k in ("best", "median")},
                             "survivors_median_fitness": v["survivors_median_fitness"],
                             "trades": {"median_per_day": v["trades"]["median_per_day"]}}
    return out


def hero_frame(summary: dict, tribe: str) -> dict:
    hero = summary["tribes"][tribe]["hero_lineage"]
    per_day = next((f["trades_per_day"] for f in summary["tribes"][tribe]["top"] if f["id"] == hero["id"]), 0)
    return {"id": hero["id"], "born": hero["born"], "origin": hero["origin"],
            "generations_lived": hero["generations_lived"], "ancestors": list(hero["ancestors"]),
            "equity": hero["final_equity"], "fitness": hero["fitness"], "trades_per_day": per_day} | (
            {"validation_fitness": hero["validation_fitness"], "validation_equity": hero["validation_final_equity"]}
            if "validation_fitness" in hero else {})


def newborn(log: dict, tribe: str, generation: int) -> dict:
    """How this generation's flies came to be: founders, children of last generation's
    survivors, and newcomers - counted from each fly's own record, for the Nursery."""
    counts = {"founder": 0, "child": 0, "newcomer": 0, "survivor": 0}
    for fly in log["tribes"][tribe]["flies"]:
        counts[fly["origin"] if fly["born"] == generation else "survivor"] += 1
    return counts


def frame_of(summary: dict, log: dict) -> dict:
    g = summary["generation"]
    tribes = {t: tribe_frame(summary, log, t) | {"born": newborn(log, t, g)} for t in TRIBES}
    return {"generation": summary["generation"],
            "tribes": tribes,
            "heroes": {t: hero_frame(summary, t) for t in TRIBES}}


def window_of(day: dict, evolve: pd.DataFrame | None) -> dict:
    out = {k: day[k] for k in ("first_time", "last_time", "price_move_pct")}
    if evolve is not None:
        out["candles"] = candles_for(evolve, day)
    return out


FINALE_POINTS = 480          # the finale's equity curves, thinned to this many points each


def thin(curve: list[float], points: int = FINALE_POINTS) -> list[float]:
    step = max(1, len(curve) // points)
    out = curve[::step]
    if out[-1] != curve[-1]:
        out = out + [curve[-1]]
    return [round(float(v), 2) for v in out]


def brain_block(run_dir: Path) -> dict | None:
    """The brain's shape, from the run's own run_summary.json, for the Brain Room's wall."""
    path = run_dir / "run_summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("brain")


def run_block(run_dir: Path) -> dict | None:
    """What the run cost and how big a genome is: the Switchboard's dial count and the Server
    Room's clock, both out of the run's own run_summary.json."""
    path = run_dir / "run_summary.json"
    if not path.exists():
        return None
    summary = json.loads(path.read_text())
    keep = ("genome_size", "minutes_per_generation", "minutes_total")
    out = {k: summary[k] for k in keep if k in summary}
    return out or None


def locked_block() -> dict | None:
    """What the vault holds, from `data/split.json`.

    The vault's wall needs the size of the locked test set before any finale exists. split.json
    carries both ranges and bar counts precisely so it can be read without opening the locked
    file (PLAN.md SETUP), so this stays clear of rule 3: no one here touches the parquet."""
    path = REPO / "data" / "split.json"
    if not path.exists():
        return None
    locked = json.loads(path.read_text())["locked"]
    return {"rows": locked["rows"], "first": locked["first"], "last": locked["last"],
            "source": "data/split.json"}


def traded_moments(raw: dict, name: str = "llm", want_pairs: int = 24) -> dict | None:
    """When a trader was actually in the market, recovered exactly from two logged curves.

    The finale logs how many times the model traded (292) and what it replied in the last 24
    calls, but not a trade log, so nothing says *when* it bought. Two logged series together do:
    the fee-free pass replays the with-fees pass decision for decision, so the ratio between the
    two equity curves is flat except at a fill, where the fee knocks the with-fees wallet down by
    exactly one fee_bps. Every step in that ratio is one fill and nothing else can make one.

    Starting flat, fills alternate BUY, SELL, BUY. The count is checked against the trades the
    run logged and this refuses to guess if they disagree, so a wall can never show a moment the
    logs do not contain (PLAN.md rule 8)."""
    passes = raw.get("passes", {})
    fee_block = passes.get("with_fees", {}).get("competitors", {}).get(name)
    free_block = passes.get("no_fees", {}).get("competitors", {}).get(name)
    if not fee_block or not free_block or "equity" not in fee_block:
        return None
    fee = float(passes["with_fees"]["fee_bps"]) / 1e4
    if fee <= 0:
        return None

    ratio = [w / n for w, n in zip(fee_block["equity"], free_block["equity"]) if n]
    bars = [k for k in range(1, len(ratio)) if ratio[k] < ratio[k - 1] * (1 - fee / 2)]
    logged = fee_block.get("trades")
    if logged is not None and len(bars) != logged:
        raise SystemExit(f"{name}: recovered {len(bars)} fills from the fee ratio but the run "
                         f"logged {logged} trades; not exporting a trade the logs do not show")

    # Bar -> clock. The finale logs no per-bar timestamp, and the candles that carry one are the
    # locked set, which only the finale scripts may open (rule 3). So the clock is interpolated
    # across the run's own first_time..last_time - and then checked against the real timestamps
    # the run did log, on its last replies, before any of it is allowed out.
    first = datetime.fromisoformat(raw["first_time"])
    minutes = (datetime.fromisoformat(raw["last_time"]) - first).total_seconds() / 60 / max(1, raw["bars"] - 1)
    every = int(fee_block.get("bars_between_decisions", 1))
    raw_at = lambda bar: first + timedelta(minutes=minutes * bar)

    replies = (fee_block.get("replies") or {}).get("last") or []
    drift = 0.0
    if replies:
        n = int(fee_block["decisions"])
        for i, (stamp, _word) in enumerate(replies):
            bar = (n - len(replies) + i) * every
            drift = max(drift, abs((raw_at(bar) - datetime.fromisoformat(stamp)).total_seconds() / 60))
        if drift > every * minutes / 2:
            raise SystemExit(f"{name}: the interpolated clock is {drift:.0f} min out against the "
                             f"timestamps the run logged, more than half a decision apart; "
                             f"not exporting times this coarse")

    # Bars sit on real five-minute marks of the clock, so the interpolated time is rounded onto
    # that grid: within the measured drift the result is the bar's own timestamp, and at worst
    # it names the neighbouring bar.
    grid = round(minutes)                                  # 5, for five-minute candles
    def at(bar):
        t = raw_at(bar).replace(second=0, microsecond=0, tzinfo=raw_at(bar).tzinfo)
        t += timedelta(minutes=round(raw_at(bar).second / 60))
        return (t - timedelta(minutes=t.minute % grid)
                + timedelta(minutes=grid if t.minute % grid >= grid / 2 else 0)).isoformat()

    # every other fill is a BUY; take pairs spread evenly, so the wall shows a buy and its sell
    buys = list(range(0, len(bars) - 1, 2))
    take = buys if len(buys) <= want_pairs else [buys[round(k * (len(buys) - 1) / (want_pairs - 1))]
                                                 for k in range(want_pairs)]
    moments = []
    for i in sorted(set(take)):
        moments.append([at(bars[i]), "BUY"])
        moments.append([at(bars[i + 1]), "SELL"])
    return {"count": len(bars), "buys": (len(bars) + 1) // 2, "sells": len(bars) // 2,
            "recovered_from": "the fee step between the with-fees and fee-free passes",
            "clock": "interpolated across the run's span, rounded to the five-minute bar grid",
            "clock_drift_minutes": round(drift, 1),   # worst disagreement with a logged reply time
            "moments": moments}


def finale_block(path: Path, rehearsal: bool = False) -> dict | None:
    """The finale as the visuals need it: every trader's final equity and its equity curve,
    thinned, in each pass. Reads the merged finale.json, or the flies' half alone if the merge
    has not happened. The run it came from is recorded, because it need not be the run the rest
    of the file replays."""
    tag = "_rehearsal" if rehearsal else ""
    merged = path / f"finale{tag}.json"
    half = path / f"finale_flies{tag}.json"
    source = merged if merged.exists() else half if half.exists() else None
    if source is None:
        return None
    raw = json.loads(source.read_text())
    passes = {}
    for label, block in raw["passes"].items():
        out = {"fee_bps": block["fee_bps"], "bars_between_decisions": block.get("bars_between_decisions", 1),
               "traders": {}}
        for tribe, rows in block.get("tribes", {}).items():
            out["traders"][f"{tribe}_champions"] = {
                "final_equity": round(float(np.mean(rows["final_equity"])), 2),
                "each": rows["final_equity"], "trades": rows["trades"], "ids": rows["ids"],
                "curve": thin(rows["mean_equity"])}
        for name, row in block.get("competitors", {}).items():
            out["traders"][name] = {"final_equity": row["final_equity"], "trades": row.get("trades"),
                                    "curve": thin(row["equity"])}
            if "replies" in row:                       # what the model actually said
                out["traders"][name]["replies"] = row["replies"]
                traded = traded_moments(raw, name)      # and when it actually acted
                if traded:
                    out["traders"][name]["traded"] = traded
        passes[label] = out
    return {"run": raw["run"], "generation": raw["generation"], "rehearsal": raw.get("rehearsal", False),
            "data": raw["data"], "bars": raw["bars"], "first_time": raw["first_time"],
            "last_time": raw["last_time"], "parts": raw.get("parts", ["flies"]),
            "llm": raw.get("llm"), "passes": passes, "source": source.name}


# ---- the family tree (the Tree of Life and the Barcode Wall) -------------------------------

ORIGIN_CODE = {"survivor": "s", "child": "c", "newcomer": "n", "founder": "f"}


def lineage_row(log: dict, tribe: str) -> list[dict]:
    """One generation's flies, with just the fields the tree is built from."""
    return [{"id": f["id"], "parent": f["parent"], "origin": f["origin"], "born": f["born"],
             "fitness": float(f["fitness"]), "eliminated": bool(f["eliminated"])}
            for f in log["tribes"][tribe]["flies"]]


def lineage_of(rows: list[list[dict]]) -> list[list[dict]]:
    """Every fly of every generation, linked to the seat it came from one generation earlier.

    A branch of the tree is a seat number per generation, so the page never has to match a
    string: `p` is the seat this fly continues from, or -1 where the branch starts. A fly that
    survived is its own parent a generation on - the same id in both - and a child links to the
    parent it was made from. `o` is how it got there (survivor / child / newcomer / founder) and
    `e` marks the flies selection dropped, which is where a branch stops."""
    by_id = [{f["id"]: k for k, f in enumerate(gen)} for gen in rows]
    out = []
    for g, gen in enumerate(rows):
        previous = by_id[g - 1] if g else {}
        row = []
        for fly in gen:
            link, kind = previous.get(fly["id"], -1), "survivor"
            if link < 0:
                link, kind = previous.get(fly["parent"], -1), fly["origin"]
            row.append({"p": link, "o": ORIGIN_CODE.get(kind, "n"),
                        "f": round(fly["fitness"], 6), "e": int(fly["eliminated"])})
        out.append(row)
    return out


def champion_branch(tree: list[list[dict]], rows: list[list[dict]]) -> dict:
    """The winning fly of the last generation, and the seat its line held in every generation
    before that: the branch the Tree of Life draws in gold. -1 where the line did not yet exist."""
    last = len(tree) - 1
    seat = max(range(len(tree[last])), key=lambda k: tree[last][k]["f"])
    seats = [-1] * len(tree)
    g, s = last, seat
    seats[g] = s
    while g > 0 and tree[g][s]["p"] >= 0:
        s, g = tree[g][s]["p"], g - 1
        seats[g] = s
    return {"id": rows[last][seat]["id"], "seat": seat, "seats": seats,
            "born": rows[last][seat]["born"], "fitness": round(rows[last][seat]["fitness"], 6)}


def lineage_block(rows: dict[str, list[list[dict]]]) -> dict:
    out = {}
    for tribe, per_gen in rows.items():
        tree = lineage_of(per_gen)
        out[tribe] = {"flies": tree, "champion": champion_branch(tree, per_gen)}
    return out


# ---- the trade tape ------------------------------------------------------------------------

TAPE_FLIES = 8               # the best flies of the last generation, per tribe, on all four days


def fills_of(actions: list[int], evolve: pd.DataFrame, day: dict, rules: dict) -> tuple[list[dict], float, int]:
    """The fills a logged run of decisions produced, and the equity they ended on.

    The generation logs keep every decision but no trade blotter (PLAN.md rule 7 logs actions
    and equity). A fill is not the same thing as a decision - a BUY while already long does
    nothing, and the minimum hold refuses a flip - so the fills are recovered by putting the
    LOGGED decisions back through the same `market.wallet` in the same rule-4 order, on the same
    bars of the evolve set the run traded. Nothing is guessed: the caller checks the equity this
    returns against the equity the run logged, fly by fly, and refuses to export a tape that
    does not land on the same number."""
    wallet = Wallet(1, **rules)
    opens, closes, stamps = evolve["open"].to_numpy(), evolve["close"].to_numpy(), evolve["timestamp"]
    first, last = int(day["first_index"]), int(day["last_index"])
    out, equity = [], 0.0
    for i, t in enumerate(range(first, last + 1)):
        before = int(wallet.positions[0])
        wallet.fill(np.asarray([actions[i]], dtype=np.int8), float(opens[t + 1]))
        after = int(wallet.positions[0])
        equity = float(wallet.settle(float(closes[t + 1]))[0])
        if after != before:
            out.append({"t": stamps.iloc[t + 1].isoformat(), "side": "buy" if after else "sell",
                        "price": round(float(opens[t + 1]), 2), "equity": round(equity, 2), "bar": i})
    return out, equity, int(wallet.trades[0])


def tape_block(log: dict, manifest: dict, evolve: pd.DataFrame, config: dict,
               per_tribe: int = TAPE_FLIES) -> dict:
    """Every fill the last generation's best flies made, in time order, for the Ticker Tape Hall."""
    rules = {k: config[k] for k in ("start_cash", "fee_bps", "min_hold_bars")}
    fills, checked = [], 0
    for tribe in TRIBES:
        flies = log["tribes"][tribe]["flies"]
        actions = log["tribes"][tribe]["actions_by_window"]
        curves = log["tribes"][tribe]["equity_by_window"]
        best = sorted(range(len(flies)), key=lambda k: -flies[k]["fitness"])[:per_tribe]
        for seat in best:
            for w, day in enumerate(manifest["windows"]):
                got, equity, trades = fills_of(actions[w][seat], evolve, day, rules)
                logged = float(curves[w][-1][seat])
                if abs(equity - logged) > 0.01:
                    raise SystemExit(f"tape: {flies[seat]['id']} on day {w} replays to ${equity:,.2f} "
                                     f"but the run logged ${logged:,.2f}; not exporting a trade the "
                                     f"logs do not back")
                if trades != len(got):
                    raise SystemExit(f"tape: {flies[seat]['id']} on day {w}: the wallet counted "
                                     f"{trades} trades but {len(got)} fills were seen")
                checked += 1
                for fill in got:
                    fills.append(fill | {"tribe": tribe, "fly": flies[seat]["id"], "day": w})
    fills.sort(key=lambda f: (f["t"], f["fly"]))
    return {"generation": log["generation"], "flies_per_tribe": per_tribe,
            "days_checked": checked, "fills": fills,
            "source": "the generation log's own decisions, put back through market.wallet on the "
                      "evolve bars the run traded; every fly's replayed equity matched its logged equity"}


# ---- the champion replay and the fly's eye --------------------------------------------------

REPLAY_GROUPS = 4            # readout groups named per bar on the Replay Room's board
EYE_CELLS = 420              # photoreceptors binned to about this many ommatidia to draw


def replay_block(run_dir: Path) -> dict | None:
    """One training day, decision by decision, from `scripts.replay_champions`.

    Vote margins and readout-group activity are not in any generation log - they live for one
    line inside the brain and are dropped - so that script re-runs the two champions on one day
    of the EVOLVE set and writes them down. It also records how closely its replay reproduced
    the actions the run logged; that number rides along so a room can show it."""
    path = run_dir / "replay_champions.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    out = {k: raw[k] for k in ("run", "generation", "recorded", "data", "window_index", "window", "rules")}
    out["bar_minutes"] = raw["bar_minutes"]
    out["champions"] = {}
    for tribe, champ in raw["champions"].items():
        names, index = champ["group_names"], {}
        bars = []
        for bar in champ["bars"]:
            top = bar["top_groups"][:REPLAY_GROUPS]
            for g in top:
                index.setdefault(g["group"], names[g["group"]])
            bars.append({"b": bar["bar"], "t": bar["decided_at"], "a": bar["action"],
                         "p": bar["fill_price"], "c": bar["close"], "pos": bar["position_before"],
                         "mb": bar["margin_buy"], "ms": bar["margin_sell"], "eq": bar["equity"],
                         "g": [[g["group"], g["activity"], g["contribution"]] for g in top]})
        out["champions"][tribe] = {
            "id": champ["id"], "parent": champ["parent"], "born": champ["born"],
            "final_equity": champ["final_equity"], "trades": champ["trades"],
            "actions": champ["actions"], "ms_per_bar": champ["ms_per_bar"],
            "agreement": champ["against_the_log"]["agreement"],
            "bars_same": champ["against_the_log"]["same_action"],
            "logged_equity_this_day": champ["logged"]["equity_this_day"],
            "groups": {str(k): v for k, v in sorted(index.items())},
            "group_count": len(names),
            "busiest": [[int(g), names[int(g)]] for g in champ["busiest_groups"][:8]],
            "bars": bars}
    return out


def eye_block(run_dir: Path, cells: int = EYE_CELLS) -> dict | None:
    """The chart as the compound eye samples it, binned down to something drawable.

    `scripts.replay_champions` records where every one of the eye's photoreceptors looks at the
    64x64 chart and what it drew from a handful of the day's bars. 5,494 of them is far too many
    marks for a 12fps canvas, so neighbours are pooled onto a coarse lattice and each cell keeps
    the MEAN drive of the photoreceptors in it - a real average of logged values, not a redrawn
    picture. The cell's position is the mean position of its own photoreceptors."""
    path = run_dir / "replay_champions.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text()).get("eye")
    if not raw:
        return None
    layout = np.asarray(raw["layout"], dtype=float)
    side = max(4, int(round(np.sqrt(cells * 4 / np.pi))))
    key = np.floor((layout + 1) / 2 * side).clip(0, side - 1).astype(int)
    flat = key[:, 0] * side + key[:, 1]
    bins, inverse, counts = np.unique(flat, return_inverse=True, return_counts=True)
    centre = np.zeros((len(bins), 2))
    np.add.at(centre, inverse, layout)
    centre /= counts[:, None]
    frames = []
    for frame in raw["frames"]:
        drive = np.asarray(frame["drive"], dtype=float)
        pooled = np.zeros(len(bins))
        np.add.at(pooled, inverse, drive)
        pooled /= counts
        frames.append({"bar": frame["bar"], "v": [round(float(v), 3) for v in pooled]})
    return {"photoreceptors": int(raw["photoreceptors"]), "built_from": raw["built_from"],
            "note": raw["note"], "cells": len(bins),
            "layout": [[round(float(u), 4), round(float(v), 4)] for u, v in centre],
            "per_cell": [int(c) for c in counts], "frames": frames}


def check(payload: dict) -> None:
    """The contract's invariants, verified here rather than discovered in the browser."""
    population = payload["population"]
    for frame in payload["frames"]:
        for tribe, rows in frame["tribes"].items():
            where = f"generation {frame['generation']} / {tribe}"
            if len(rows["flies"]) != population:
                raise SystemExit(f"{where}: {len(rows['flies'])} flies, expected {population}")
            if rows["survived"] + rows["eliminated"] != population:
                raise SystemExit(f"{where}: survived {rows['survived']} + eliminated {rows['eliminated']} "
                                 f"!= {population}")
            marked = sum(1 for f in rows["flies"] if f["eliminated"])
            if marked != rows["eliminated"]:
                raise SystemExit(f"{where}: {marked} flies marked eliminated but the summary says "
                                 f"{rows['eliminated']}")
            hero = frame["heroes"][tribe]
            if hero["id"] in hero["ancestors"]:
                raise SystemExit(f"{where}: {hero['id']} is its own ancestor")
    for k, window in enumerate(payload["windows"]):
        for o, h, l, c in window.get("candles", []):
            if not (h >= max(o, c) and l <= min(o, c)):
                raise SystemExit(f"day {k}: a candle whose high and low do not contain its open and "
                                 f"close ({o}, {h}, {l}, {c})")
    tree = payload.get("lineage", {})
    for tribe, block in tree.items():
        if len(block["flies"]) != len(payload["frames"]):
            raise SystemExit(f"lineage/{tribe}: {len(block['flies'])} generations, "
                             f"{len(payload['frames'])} frames")
        for g, row in enumerate(block["flies"]):
            if len(row) != population:
                raise SystemExit(f"lineage/{tribe} generation {g}: {len(row)} flies, expected {population}")
            for fly in row:
                if fly["p"] >= 0 and (g == 0 or fly["p"] >= population):
                    raise SystemExit(f"lineage/{tribe} generation {g}: a branch coming from seat "
                                     f"{fly['p']} of a generation that has no such seat")
        seats, champion = block["champion"]["seats"], block["champion"]
        if seats[-1] != champion["seat"]:
            raise SystemExit(f"lineage/{tribe}: the champion branch does not end on the champion")
        for g in range(1, len(seats)):
            here, back = seats[g], seats[g - 1]
            if here >= 0 and back >= 0 and block["flies"][g][here]["p"] != back:
                raise SystemExit(f"lineage/{tribe}: the champion branch skips from generation "
                                 f"{g - 1} to {g}")
    tape = payload.get("tape")
    if tape:
        for fill in tape["fills"]:
            if fill["side"] not in ("buy", "sell") or fill["price"] <= 0:
                raise SystemExit(f"tape: a fill that is neither a buy nor a sell, or has no price: {fill}")
        times = [f["t"] for f in tape["fills"]]
        if times != sorted(times):
            raise SystemExit("tape: the fills are not in time order")
    replay = payload.get("replay")
    if replay:
        for tribe, champ in replay["champions"].items():
            if not champ["bars"]:
                raise SystemExit(f"replay/{tribe}: no bars")
            if not 0 <= champ["agreement"] <= 1:
                raise SystemExit(f"replay/{tribe}: agreement {champ['agreement']} is not a share")
            for bar in champ["bars"]:
                if bar["a"] not in ("hold", "buy", "sell"):
                    raise SystemExit(f"replay/{tribe}: bar {bar['b']} has action {bar['a']!r}")
                for g, _activity, _contribution in bar["g"]:
                    if str(g) not in champ["groups"]:
                        raise SystemExit(f"replay/{tribe}: bar {bar['b']} names group {g}, which "
                                         f"has no name in the export")
    eye = payload.get("eye")
    if eye:
        if len(eye["layout"]) != eye["cells"] or len(eye["per_cell"]) != eye["cells"]:
            raise SystemExit("eye: the layout and the cell counts disagree")
        if sum(eye["per_cell"]) != eye["photoreceptors"]:
            raise SystemExit(f"eye: {sum(eye['per_cell'])} photoreceptors binned, "
                             f"{eye['photoreceptors']} recorded")
        for frame in eye["frames"]:
            if len(frame["v"]) != eye["cells"]:
                raise SystemExit(f"eye: bar {frame['bar']} has {len(frame['v'])} cells, "
                                 f"expected {eye['cells']}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, required=True, help="a run directory under runs/")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--finale", type=Path, default=None,
                   help="a run directory holding finale.json (default: --run's own, if it has one)")
    p.add_argument("--finale-rehearsal", action="store_true",
                   help="use the finale's rehearsal files, to build the finale visuals before the real one exists")
    args = p.parse_args()

    manifest = json.loads((args.run / "manifest.json").read_text())
    if "windows" not in manifest:
        raise SystemExit(f"{args.run} predates the fixed days (contract v1); this exporter writes v2")
    config = manifest["config"]
    evolve = load_evolve()
    # One pass over the logs: each generation's 13 MB is parsed once and the frame, the family
    # tree's row and (on the last one) the trade tape are all taken off it before it is dropped.
    frames, tree_rows, last_log = [], {t: [] for t in TRIBES}, None
    for summary_path, log_path in generations(args.run):
        summary, log = json.loads(summary_path.read_text()), json.loads(log_path.read_text())
        frames.append(frame_of(summary, log))
        for tribe in TRIBES:
            tree_rows[tribe].append(lineage_row(log, tribe))
        last_log = log
    minutes = manifest["data"]["granularity_seconds"] // 60

    payload = {"contract_version": CONTRACT_VERSION, "run_id": manifest["run_id"],
               "generated": datetime.now(timezone.utc).isoformat(),
               "generations": len(frames), "population": config["population"],
               "survive_share": config["survive_share"], "bars_per_window": config["bars"],
               "bar_minutes": minutes, "candle_minutes": minutes * BARS_PER_CANDLE,
               "start_cash": config["start_cash"], "fee_bps": config["fee_bps"],
               "min_hold_bars": config["min_hold_bars"],
               "tribes": list(TRIBES), "competitors": list(COMPETITORS),
               "windows": [window_of(day, evolve) for day in manifest["windows"]],
               "competitor_results": {n: manifest["competitors"][n] for n in COMPETITORS},
               "frames": frames}
    if manifest.get("validation_windows"):
        payload["validation_windows"] = [window_of(day, evolve) for day in manifest["validation_windows"]]
        payload["validation_competitor_results"] = manifest.get("validation_competitors", {})
    brain = brain_block(args.run)
    if brain:
        payload["brain"] = brain
    run_meta = run_block(args.run)
    if run_meta:
        payload["run"] = run_meta
    locked = locked_block()
    if locked:
        payload["locked"] = locked
    payload["lineage"] = lineage_block(tree_rows)
    payload["tape"] = tape_block(last_log, manifest, evolve, config)
    replay = replay_block(args.run)
    if replay:
        payload["replay"] = replay
    eye = eye_block(args.run)
    if eye:
        payload["eye"] = eye
    finale = finale_block(args.finale or args.run, args.finale_rehearsal)
    if finale:
        payload["finale"] = finale
    check(payload)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload) + "\n")
    last = frames[-1]
    print(f"{args.out} : {len(frames)} generations, {len(payload['windows'])} fixed days, "
          f"{payload['population']} flies a tribe, {args.out.stat().st_size / 1024:.0f} KB")
    extras = [k for k in ("validation_windows", "brain", "run", "locked", "finale",
                          "lineage", "tape", "replay", "eye") if k in payload]
    if extras:
        print(f"with {', '.join(extras)}" + (f" (finale from {payload['finale']['run']}, "
              f"{payload['finale']['source']})" if "finale" in payload else ""))
    print(f"last generation {last['generation']}: real best ${last['tribes']['real']['equity']['best']:,.2f}, "
          f"scrambled best ${last['tribes']['scrambled']['equity']['best']:,.2f}, "
          f"hero {last['heroes']['real']['id']} with {len(last['heroes']['real']['ancestors'])} ancestors")
    print(f"tape: {len(payload['tape']['fills'])} fills rebuilt from logged decisions over "
          f"{payload['tape']['days_checked']} fly-days, every one landing on the logged equity")
    if "replay" in payload:
        agree = {t: c["agreement"] for t, c in payload["replay"]["champions"].items()}
        print(f"replay: one training day, {', '.join(f'{t} {a:.1%} of bars matched the log' for t, a in agree.items())}")


if __name__ == "__main__":
    main()
