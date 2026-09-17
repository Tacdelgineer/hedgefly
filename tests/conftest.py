from pathlib import Path

import numpy as np
import pytest
import torch
from nfly import load_malecns
from nfly.connectome import write_synthetic

from brain import CHART_SHAPE
from brain.agent import POSITION_CLASS

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="session")
def device() -> str:
    if not torch.cuda.is_available():
        pytest.fail("CUDA is not available; brain tests never fall back to CPU")
    return "cuda"


@pytest.fixture(scope="session")
def synthetic_connectome(tmp_path_factory):
    """nfly's toy MaleCNS-format connectome. It has no proprioceptors, so 20 central neurons
    stand in for them."""
    conn = load_malecns(write_synthetic(tmp_path_factory.mktemp("synthetic")), min_syn=1, cache=False)
    stand_ins = conn.neurons.index[conn.neurons["super_class"] == "cb_intrinsic"][:20]
    conn.neurons.loc[stand_ins, "class"] = POSITION_CLASS
    return conn


@pytest.fixture(scope="session")
def malecns():
    """The whole MaleCNS v1.0 CNS (subset `all`), from the cache in data/."""
    if not (DATA / "connectome-weights.feather").exists():
        pytest.skip("MaleCNS v1.0 files are not in data/ (see README)")
    return load_malecns(DATA)


def fake_charts(n: int, seed: int) -> np.ndarray:
    """(n, 64, 64) consecutive charts of a random-walk price, drawn by the interface rules:
    one column per candle, newest on the right, row 0 the highest price, each column inked
    from the candle's low to its high. Test data only; the real renderer lives in market/."""
    height, width = CHART_SHAPE
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n + width - 1)))
    spread = close * np.abs(rng.normal(0, 0.005, close.shape))
    low, high = close - spread, close + spread
    rows = np.arange(height)[:, None]
    charts = np.empty((n, height, width), np.float32)
    for t in range(n):
        lo, hi = low[t:t + width], high[t:t + width]
        scale = (height - 1) / max(hi.max() - lo.min(), 1e-9)
        top = (height - 1) - np.round((hi - lo.min()) * scale)
        bottom = (height - 1) - np.round((lo - lo.min()) * scale)
        charts[t] = (rows >= top) & (rows <= bottom)
    return charts


@pytest.fixture(scope="session")
def charts():
    return fake_charts
