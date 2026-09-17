"""The flies' brains: a frozen MaleCNS connectome per tribe, driven by a chart and read out as
trading actions. Contract with the market side: brain/interface.md."""

from .agent import BUY, CHART_SHAPE, HOLD, SELL, FlyRun, TribeAgent, build_eye
from .genome import N_VOTES, GAIN_GRID, Genome
from .scramble import scramble

__all__ = ["BUY", "CHART_SHAPE", "HOLD", "SELL", "FlyRun", "TribeAgent", "build_eye",
           "GAIN_GRID", "N_VOTES", "Genome", "scramble"]
