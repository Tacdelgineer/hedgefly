"""The local language model, and the trader that reads a chart in words.

One small OpenAI-compatible client, shared by the narrator (`story/narrator.py`) and by the
finale's language-model trader. Qwen3.8-27B served locally by vLLM or Ollama; nothing here
ever calls out to the internet, and PLAN.md rule 9 says the narrator never runs while a
generation is simulating.

The trader is given exactly what the flies are given: the last 64 bars, scaled to their own
high and low, plus the position it is holding. The flies get that as a 64 x 64 picture; the
model gets the same numbers written out, because it cannot see. It then trades through the
same wallet as everyone else, so it pays the same fees, waits out the same minimum hold, and
fills at the next bar's open.
"""

from __future__ import annotations

import dataclasses
import os
import re

import numpy as np
import pandas as pd
import requests

from market import BUY, HOLD, SELL, Wallet, trade_window
from market.chart import WINDOW

# Ollama on this Spark listens on its Tailscale address, not on localhost. Override with the
# environment variable when the model is served elsewhere.
LOCAL_URL = os.environ.get("HEDGEFLY_LLM_URL", "http://100.103.129.82:11434/v1")
LOCAL_MODEL = os.environ.get("HEDGEFLY_LLM_MODEL", "Qwen3.8-27B")
TIMEOUT = 120
SCALE = 100                 # the window's low is 0 and its high is 100

ACTION_WORDS = {"BUY": BUY, "SELL": SELL, "HOLD": HOLD}

TRADER_SYSTEM = """You are trading BTC-USD against a population of fruit flies.

Rules, the same for every trader:
- You are either LONG or FLAT. No shorting, no leverage.
- BUY goes long with everything, SELL goes flat. Either costs 5 basis points.
- A position cannot be changed until 3 bars after the one that opened it.
- Your decision at the close of this bar is filled at the OPEN of the next one.

You see the last 64 five-minute bars, scaled to their own high and low: 0 is the lowest low of
those 64 bars and 100 is the highest high. You are told nothing else - no absolute price, no
news, no indicator. Exactly what the flies see, written out.

Answer with one word: BUY, SELL or HOLD. No explanation."""


class LocalModel:
    """A chat call to the local endpoint. Deterministic: temperature 0, no sampling.

    Reasoning is switched off. Qwen3-family models think before they answer, and Ollama puts
    that thinking in a separate "reasoning" field that still counts against max_tokens: with the
    trader's 8-token budget the whole budget went on thinking, the answer came back empty, and an
    empty answer parses as HOLD - a trader that silently never trades. reasoning_effort "none"
    makes the model answer directly."""

    def __init__(self, url: str = LOCAL_URL, model: str = LOCAL_MODEL, timeout: int = TIMEOUT,
                 reasoning: str | None = "none"):
        self.url, self.model, self.timeout, self.reasoning = url.rstrip("/"), model, timeout, reasoning
        self.session = requests.Session()
        self.calls = 0

    def check(self):
        """Fail now, loudly, rather than in the middle of a six-month run."""
        try:
            response = self.session.get(f"{self.url}/models", timeout=10)
            response.raise_for_status()
        except requests.RequestException as error:
            raise SystemExit(f"no local model at {self.url}: {error}\n"
                             f"start it (vLLM or Ollama) or pass --no-llm") from error
        served = [m.get("id") for m in response.json().get("data", [])]
        if served and self.model not in served:
            raise SystemExit(f"{self.url} serves {served}, not {self.model!r}")
        return self

    def chat(self, system: str, user: str, max_tokens: int = 8, temperature: float = 0.0) -> str:
        payload = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.reasoning is not None:
            payload["reasoning_effort"] = self.reasoning
        response = self.session.post(f"{self.url}/chat/completions", json=payload, timeout=self.timeout)
        response.raise_for_status()
        self.calls += 1
        return response.json()["choices"][0]["message"]["content"].strip()


@dataclasses.dataclass(frozen=True)
class LLMRun:
    name: str
    final_equity: float
    trades: int
    broke: bool
    equity: np.ndarray
    decisions: int
    unparsed: int
    actions: np.ndarray | None = None     # (T,) every action it took, for an exact fee-free replay

    def summary(self, start_cash: float) -> dict:
        return {"final_equity": round(self.final_equity, 2),
                "fitness": round(float(np.log(max(self.final_equity, 1e-9) / start_cash)), 6),
                "trades": int(self.trades), "broke": bool(self.broke),
                "decisions": self.decisions, "unparsed_replies": self.unparsed}


def describe_window(candles: pd.DataFrame, t: int, position: int) -> str:
    """The last 64 bars in words: the same shape the chart draws, on the same 0-100 scale.

    Reads candles[t-63 .. t] and nothing after t, which is PLAN.md rule 4 for this trader."""
    bars = candles.iloc[t - WINDOW + 1:t + 1]
    low, high = float(bars["low"].min()), float(bars["high"].max())
    span = max(high - low, 1e-9)

    def scaled(values) -> list[int]:
        return [int(round(SCALE * (v - low) / span)) for v in values]

    closes = scaled(bars["close"].to_numpy())
    last = bars.iloc[-1]
    move = 100 * (float(last["close"]) / float(bars["close"].iloc[0]) - 1)
    return (f"64 bars, oldest first, closing prices on the 0-100 scale of this window:\n"
            f"{closes}\n"
            f"The newest bar: open {scaled([last['open']])[0]}, high {scaled([last['high']])[0]}, "
            f"low {scaled([last['low']])[0]}, close {closes[-1]}.\n"
            f"Over these 64 bars the close moved {move:+.2f}%.\n"
            f"You are currently {'LONG' if position else 'FLAT'}.\n"
            f"BUY, SELL or HOLD?")


def parse_action(reply: str) -> int | None:
    """The first of BUY / SELL / HOLD the model says. None if it says none of them."""
    found = re.search(r"\b(BUY|SELL|HOLD)\b", reply.upper())
    return ACTION_WORDS[found.group(1)] if found else None


class LLMTrader:
    """The local model as one more competitor in the finale."""

    def __init__(self, url: str = LOCAL_URL, model: str = LOCAL_MODEL):
        self.client = LocalModel(url, model)
        self.model = model

    def check(self) -> "LLMTrader":
        self.client.check()
        return self

    def trade(self, candles: pd.DataFrame, first: int, last: int, every: int = 12,
              **wallet: object) -> LLMRun:
        """Trade bars `first`..`last`, asking the model every `every` bars and holding between.

        A call per five-minute bar would be 52,915 calls over the locked test set, which is
        days of wall time; asking hourly and holding in between is the concession. It changes
        how often this trader may act, never the rules it acts under - it still pays the same
        fees, waits out the same minimum hold and fills at the next bar's open."""
        state = {"decisions": 0, "unparsed": 0, "bar": first}

        def decide(chart: np.ndarray, positions: np.ndarray) -> np.ndarray:
            t = state["bar"]
            state["bar"] += 1
            if (t - first) % every:
                return np.array([HOLD], np.int8)
            reply = self.client.chat(TRADER_SYSTEM, describe_window(candles, t, int(positions[0])))
            action = parse_action(reply)
            state["decisions"] += 1
            state["unparsed"] += action is None
            return np.array([HOLD if action is None else action], np.int8)

        purse = Wallet(1, **wallet)
        result = trade_window(decide, candles, first, last, purse)
        return LLMRun("llm", float(result.final_equity[0]), int(result.trades[0]),
                      bool(result.broke[0]), result.equity[:, 0], state["decisions"], state["unparsed"],
                      result.actions[:, 0].copy())
