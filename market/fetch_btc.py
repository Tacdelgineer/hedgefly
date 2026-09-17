"""Download BTC-USD hourly candles and split off the locked test set.

    uv run python -m market.fetch_btc --start 2022-09-01

Source: the public Coinbase Exchange candles endpoint (no key, real BTC-USD spot, 300 candles
per request). The last `--locked-months` months go to data/btc_locked_test.parquet and are
never touched again outside finale.py (PLAN.md rule 3); everything before them goes to
data/btc_evolve.parquet. data/split.json records both ranges so the split can be checked
without opening the locked file.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from market.data import CANDLE_COLUMNS, EVOLVE_PATH, LOCKED_PATH, SPLIT_PATH

URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
GRANULARITY = 3600
MAX_CANDLES = 300               # the endpoint's limit per request
PAUSE = 0.12                    # polite spacing between requests
RETRIES = 5


def fetch_chunk(start: datetime, end: datetime, session: requests.Session) -> list[list[float]]:
    params = {"granularity": GRANULARITY, "start": start.isoformat(), "end": end.isoformat()}
    for attempt in range(RETRIES):
        response = session.get(URL, params=params, timeout=30)
        if response.ok:
            return response.json()
        time.sleep(2 ** attempt * PAUSE)
    raise RuntimeError(f"Coinbase refused {start} - {end}: {response.status_code} {response.text[:200]}")


def fetch(start: datetime, end: datetime) -> pd.DataFrame:
    """Hourly candles in [start, end), oldest first, one row per traded hour."""
    session, rows = requests.Session(), []
    window = timedelta(seconds=GRANULARITY * MAX_CANDLES)
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + window, end)
        rows += fetch_chunk(chunk_start, chunk_end, session)
        print(f"\r{chunk_start:%Y-%m-%d} ... {len(rows):,} candles", end="", flush=True)
        chunk_start = chunk_end
        time.sleep(PAUSE)
    print()
    candles = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    candles["timestamp"] = pd.to_datetime(candles["time"], unit="s", utc=True)
    candles = candles[list(CANDLE_COLUMNS)].drop_duplicates("timestamp").sort_values("timestamp")
    return candles.reset_index(drop=True)


def describe(name: str, candles: pd.DataFrame) -> dict:
    hours = (candles["timestamp"].iloc[-1] - candles["timestamp"].iloc[0]) / pd.Timedelta(hours=1) + 1
    return {"file": name, "rows": len(candles), "first": candles["timestamp"].iloc[0].isoformat(),
            "last": candles["timestamp"].iloc[-1].isoformat(), "missing_hours": int(hours) - len(candles)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--start", default="2022-09-01", help="first candle (UTC date)")
    p.add_argument("--end", default=None, help="last candle (UTC date); default now")
    p.add_argument("--locked-months", type=int, default=6, help="months of candles reserved for the finale")
    args = p.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = (datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) if args.end
           else datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0))
    candles = fetch(start, end)

    boundary = candles["timestamp"].iloc[-1] - pd.DateOffset(months=args.locked_months)
    evolve, locked = candles[candles["timestamp"] < boundary], candles[candles["timestamp"] >= boundary]
    if evolve.empty or locked.empty:
        raise SystemExit(f"split at {boundary} leaves {len(evolve)} evolve and {len(locked)} locked candles")
    evolve.to_parquet(EVOLVE_PATH, index=False)
    locked.to_parquet(LOCKED_PATH, index=False)

    split = {"source": URL, "granularity_seconds": GRANULARITY, "boundary": boundary.isoformat(),
             "fetched_at": datetime.now(timezone.utc).isoformat(),
             "evolve": describe(EVOLVE_PATH.name, evolve), "locked": describe(LOCKED_PATH.name, locked)}
    SPLIT_PATH.write_text(json.dumps(split, indent=2) + "\n")
    print(json.dumps(split, indent=2))


if __name__ == "__main__":
    main()
