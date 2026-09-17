"""The flies' brains: a frozen MaleCNS connectome per tribe, driven by a chart and read out as
trading actions. Contract with the market side: brain/interface.md."""

from .agent import BUY, CHART_SHAPE, HOLD, SELL, FlyRun, TribeAgent
from .genome import GAIN_GRID, N_ACTIONS, Genome

__all__ = ["BUY", "CHART_SHAPE", "HOLD", "SELL", "FlyRun", "TribeAgent", "GAIN_GRID", "N_ACTIONS", "Genome"]
