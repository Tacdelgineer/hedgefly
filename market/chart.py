"""The picture the flies see: 64 candles as a 64 x 64 image, exactly as brain/interface.md says.

One column per candle, oldest on the left, the candle that just closed on the right. Row 0 is
the highest price of the window. Each column is inked from the candle's low to its high, and
more strongly between its open and close, so the body and the wicks are distinguishable. The
image is scaled to its own 64 candles, so the flies see shape, never an absolute price.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CHART_SHAPE = (64, 64)
WINDOW = CHART_SHAPE[1]        # candles per chart, one per column
WICK_INK = 0.45
BODY_INK = 1.0


def render(candles: pd.DataFrame) -> np.ndarray:
    """The last WINDOW candles (oldest first) as a (64, 64) float32 image in [0, 1]."""
    if len(candles) != WINDOW:
        raise ValueError(f"a chart needs exactly {WINDOW} candles, got {len(candles)}")
    height = CHART_SHAPE[0]
    low, high = candles["low"].to_numpy(np.float32), candles["high"].to_numpy(np.float32)
    open_, close = candles["open"].to_numpy(np.float32), candles["close"].to_numpy(np.float32)
    floor, ceiling = low.min(), high.max()
    scale = (height - 1) / max(ceiling - floor, 1e-9)

    def row_of(price: np.ndarray) -> np.ndarray:            # row 0 is the top of the window
        return np.rint((ceiling - price) * scale)

    rows = np.arange(height, dtype=np.float32)[:, None]
    chart = np.where((rows >= row_of(high)) & (rows <= row_of(low)), WICK_INK, 0.0)
    body_top, body_bottom = row_of(np.maximum(open_, close)), row_of(np.minimum(open_, close))
    return np.where((rows >= body_top) & (rows <= body_bottom), BODY_INK, chart).astype(np.float32)


def render_range(candles: pd.DataFrame, first: int, last: int) -> np.ndarray:
    """Charts for the decision candles `first` .. `last` (positions in `candles`), one per
    candle: (last - first + 1, 64, 64). Each chart ends at its own candle, so nothing after it
    can reach the flies (PLAN.md rule 4)."""
    if first < WINDOW - 1:
        raise ValueError(f"the first chart needs {WINDOW - 1} candles before it, so `first` must be >= {WINDOW - 1}")
    if last >= len(candles):
        raise ValueError(f"`last` is {last} but there are only {len(candles)} candles")
    return np.stack([render(candles.iloc[t - WINDOW + 1:t + 1]) for t in range(first, last + 1)])
