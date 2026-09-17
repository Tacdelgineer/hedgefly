"""Where the candle files live and who may open them.

`data/btc_locked_test.parquet` is the last six months; PLAN.md rule 3 says only `finale.py`
may load it, so `load_locked` refuses every other caller instead of trusting convention.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
EVOLVE_PATH = DATA / "btc_evolve.parquet"
LOCKED_PATH = DATA / "btc_locked_test.parquet"     # rule 3: finale.py only
SPLIT_PATH = DATA / "split.json"                   # ranges and counts of both files, safe to read

CANDLE_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
LOCKED_READER = "finale.py"


def load_evolve() -> pd.DataFrame:
    """Every candle except the last six months."""
    return read_candles(EVOLVE_PATH)


def load_locked() -> pd.DataFrame:
    """The locked test set. Only finale.py may call this (rule 3)."""
    caller = Path(inspect.stack()[1].filename).name
    if caller != LOCKED_READER:
        raise PermissionError(f"the locked test set is loaded only by {LOCKED_READER}, not by {caller} (PLAN.md rule 3)")
    return read_candles(LOCKED_PATH)


def read_candles(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run `uv run python -m market.fetch_btc` first")
    candles = pd.read_parquet(path)
    missing = [c for c in CANDLE_COLUMNS if c not in candles.columns]
    if missing:
        raise ValueError(f"{path.name} lacks columns {missing}")
    return candles


def load_split() -> dict:
    """The split description written by fetch_btc.py: first and last timestamp and row count of
    each file. Reading it tells you where the boundary is without opening the locked candles."""
    if not SPLIT_PATH.exists():
        raise FileNotFoundError(f"{SPLIT_PATH} is missing; run `uv run python -m market.fetch_btc` first")
    return json.loads(SPLIT_PATH.read_text())
