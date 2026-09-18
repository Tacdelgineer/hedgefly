"""The finale's rigging: the right champions, and a language model that cannot see the future.

The finale itself is not run here - it opens the locked test set, and it runs once, on camera
(PLAN.md rule 3 and FINALE)."""

import json

import numpy as np
import pytest
import torch

from finale import champions_of, last_generation
from story.llm import describe_window, parse_action
from tests.test_no_lookahead import candles, rewrite_future

POPULATION, GROUPS, TOP = 12, 5, 3


def fake_run(tmp_path, fitness):
    """A generation log shaped like the real thing, with known fitness and genomes."""
    genomes = {"chart_gain": [[[float(i)] * 8] * 8 for i in range(POPULATION)],
               "position_gain": [float(i) for i in range(POPULATION)],
               "readout_w": [[[float(i), float(i)]] * GROUPS for i in range(POPULATION)]}
    log = {"tribes": {"real": {"flies": [{"id": f"real-f{i:05d}", "fitness": f} for i, f in enumerate(fitness)],
                               "genomes": genomes}}}
    (tmp_path / "gen_000.json").write_text(json.dumps(log))
    (tmp_path / "gen_007.json").write_text(json.dumps(log))
    return tmp_path


def test_the_last_generation_is_the_one_that_runs(tmp_path):
    generation, _ = last_generation(fake_run(tmp_path, np.zeros(POPULATION)))
    assert generation == 7


def test_a_run_with_no_generations_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="no generation logs"):
        last_generation(tmp_path)


def test_the_champions_are_the_fittest_flies_in_order(tmp_path):
    fitness = [0.1, -0.5, 0.9, 0.3, 0.0, -0.2, 0.7, 0.2, -0.9, 0.4, 0.5, -0.1]
    champs = champions_of(json.loads((fake_run(tmp_path, fitness) / "gen_007.json").read_text()), "real", TOP)
    assert champs.ids == ["real-f00002", "real-f00006", "real-f00010"]          # 0.9, 0.7, 0.5
    assert champs.genome.population == TOP
    # each fake fly's genes are its own index, so the genome must have been sliced in that order
    assert torch.equal(champs.genome.position_gain, torch.tensor([2.0, 6.0, 10.0]))
    assert champs.genome.readout_w.shape == (TOP, GROUPS, 2)
    assert [f["fitness"] for f in champs.flies] == [0.9, 0.7, 0.5]


def test_the_language_model_is_told_nothing_after_its_own_bar():
    """Rule 4 for the finale's LLM trader: rewriting the future may not change the prompt."""
    frame = candles(300)
    for t in (100, 180, 250):
        assert describe_window(frame, t, 0) == describe_window(rewrite_future(frame, t), t, 0)


def test_the_window_is_described_on_its_own_scale():
    """Same as the chart: the low of the 64 bars is 0 and the high is 100, never a real price."""
    frame = candles(300)
    text = describe_window(frame, 120, 1)
    assert "0-100 scale" in text and "LONG" in text
    numbers = [int(n) for n in text.split("]")[0].split("[")[1].split(",")]
    assert len(numbers) == 64 and min(numbers) >= 0 and max(numbers) <= 100
    assert str(round(float(frame["close"].iloc[120]), 2)) not in text


def test_an_unreadable_reply_is_a_hold_not_a_guess():
    assert parse_action("BUY") == 1 and parse_action("sell it all") == 2
    assert parse_action("HOLD") == 0
    assert parse_action("I am not sure") is None
