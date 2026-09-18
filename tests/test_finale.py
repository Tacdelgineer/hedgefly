"""The finale's rigging: the right champions, and a language model that cannot see the future.

The finale itself is not run here - it opens the locked test set, and it runs once, on camera
(PLAN.md rule 3 and FINALE). The merge step that joins its two halves is tested too."""

import json

import numpy as np
import pytest
import torch

from brain import Genome
from finale_shared import champions_of, last_generation
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


def test_the_merge_refuses_halves_that_traded_different_bars():
    """Two traders judged on different data are not a race."""
    from finale_merge import agree, merge
    flies = {"run": "r", "bars": 100, "first_time": "a", "last_time": "b", "data": "locked test set",
             "rehearsal": False, "generation": 3, "champions_per_tribe": 10,
             "entry_price": 1.0, "exit_price": 2.0,
             "passes": {"with_fees": {"fee_bps": 5.0, "min_hold_bars": 3, "tribes": {"real": {}},
                                      "competitors": {"momentum": {"final_equity": 900.0}}},
                        "no_fees": {"fee_bps": 0.0, "min_hold_bars": 3, "tribes": {"real": {}},
                                    "competitors": {"momentum": {"final_equity": 910.0}}}}}
    llm = {"run": "r", "bars": 100, "first_time": "a", "last_time": "b", "data": "locked test set",
           "rehearsal": False, "model": "Qwen3.8-27B", "bars_between_decisions": 12,
           "passes": {"with_fees": {"competitors": {"llm": {"final_equity": 1010.0}}},
                      "no_fees": {"competitors": {"llm": {"final_equity": 1020.0}}}}}
    agree(flies, llm)
    joined = merge(flies, llm)
    assert joined["parts"] == ["flies", "llm"]
    assert set(joined["passes"]["with_fees"]["competitors"]) == {"momentum", "llm"}
    assert joined["passes"]["no_fees"]["competitors"]["llm"]["final_equity"] == 1020.0

    with pytest.raises(SystemExit, match="did not trade the same thing"):
        agree(flies, {**llm, "bars": 99})


def test_the_chart_can_be_drawn_without_the_language_model():
    from finale_merge import merge
    flies = {"run": "r", "bars": 100, "first_time": "a", "last_time": "b", "data": "d",
             "rehearsal": False, "generation": 3, "champions_per_tribe": 10,
             "entry_price": 1.0, "exit_price": 2.0,
             "passes": {"with_fees": {"fee_bps": 5.0, "min_hold_bars": 3, "tribes": {}, "competitors": {}},
                        "no_fees": {"fee_bps": 0.0, "min_hold_bars": 3, "tribes": {}, "competitors": {}}}}
    joined = merge(flies, None)
    assert joined["parts"] == ["flies"] and "llm" not in joined


def test_an_hourly_fly_sees_every_bar_but_acts_only_on_the_hour():
    """The cadence pass limits how often a champion may act, not what its brain sees: the
    brain must be called on every bar, and only every 12th decision may be a trade."""
    import numpy as np
    from finale_shared import HOURLY, acting_every
    seen = []

    def brain(chart, positions):
        seen.append(chart)
        return np.array([1, 2], np.int8)                  # it would buy and sell on every bar

    first = 63
    hourly = acting_every(brain, first, HOURLY)
    acted = [hourly(bar, np.zeros(2, np.int8)) for bar in range(36)]
    assert len(seen) == 36, "the brain must see every bar"
    for k, actions in enumerate(acted):
        expected = [1, 2] if k % HOURLY == 0 else [0, 0]
        assert actions.tolist() == expected, f"bar {k}"


def test_acting_every_bar_is_the_brain_itself():
    from finale_shared import acting_every

    def brain(chart, positions):
        return chart
    assert acting_every(brain, 0, 1) is brain


def test_the_merge_carries_the_hourly_pass_and_lines_up_the_cadence_chart():
    from finale_merge import merge
    tribe = {"mean_equity": [1000.0, 1001.0], "final_equity": [1001.0]}
    flies = {"run": "r", "bars": 2, "first_time": "a", "last_time": "b", "data": "d",
             "rehearsal": False, "generation": 3, "champions_per_tribe": 10,
             "entry_price": 1.0, "exit_price": 2.0,
             "passes": {"with_fees": {"fee_bps": 5.0, "min_hold_bars": 3,
                                      "tribes": {"real": tribe, "scrambled": tribe}, "competitors": {}},
                        "no_fees": {"fee_bps": 0.0, "min_hold_bars": 3,
                                    "tribes": {"real": tribe, "scrambled": tribe}, "competitors": {}},
                        "hourly_with_fees": {"fee_bps": 5.0, "min_hold_bars": 3, "bars_between_decisions": 12,
                                             "tribes": {"real": tribe, "scrambled": tribe}}}}
    llm = {"run": "r", "bars": 2, "first_time": "a", "last_time": "b", "data": "d", "rehearsal": False,
           "model": "Qwen3.8-27B", "bars_between_decisions": 12,
           "passes": {"with_fees": {"competitors": {"llm": {"final_equity": 990.0, "equity": [1000.0, 990.0]}}},
                      "no_fees": {"competitors": {"llm": {"final_equity": 995.0, "equity": [1000.0, 995.0]}}}}}
    joined = merge(flies, llm)
    assert "hourly_with_fees" in joined["passes"]
    assert set(joined["cadence"]["lines"]) == {"real_every_bar", "real_hourly", "scrambled_every_bar",
                                               "scrambled_hourly", "llm_hourly"}
    assert joined["cadence"]["fee_bps"] == 5.0


def test_a_fee_free_champion_pass_is_a_replay_checked_fly_by_fly():
    """The finale's two fee-free passes are the brains' actions replayed, not a second run of
    the brains. The replay must refuse to report a fly whose fills changed."""
    import numpy as np
    from finale_shared import Champions, replay_champions
    from market import BUY, HOLD, SELL
    frame = candles(400)
    first, last = 63, 200
    genome = Genome.random(2, GROUPS, torch.Generator().manual_seed(0))
    champs = Champions("real", genome, [{"id": "real-f00001"}, {"id": "real-f00002"}])
    acts = np.full((last - first + 1, 2), HOLD, np.int8)
    acts[0], acts[10], acts[20] = [BUY, BUY], [SELL, HOLD], [BUY, SELL]
    free = replay_champions(champs, acts, frame, first, last, 0.0, 3, [3, 2])
    assert free["trades"] == [3, 2] and free["ids"] == ["real-f00001", "real-f00002"]
    with pytest.raises(RuntimeError, match="filled differently"):
        replay_champions(champs, acts, frame, first, last, 0.0, 3, [1, 2])


def test_the_merge_carries_both_hourly_passes():
    from finale_merge import merge
    tribe = {"mean_equity": [1000.0], "final_equity": [1000.0]}
    blank = {"fee_bps": 5.0, "min_hold_bars": 3, "tribes": {"real": tribe, "scrambled": tribe}, "competitors": {}}
    flies = {"run": "r", "bars": 1, "first_time": "a", "last_time": "b", "data": "d", "rehearsal": False,
             "generation": 1, "champions_per_tribe": 10, "entry_price": 1.0, "exit_price": 1.0,
             "passes": {"with_fees": blank, "no_fees": blank, "hourly_with_fees": blank, "hourly_no_fees": blank}}
    assert {"hourly_with_fees", "hourly_no_fees"} <= set(merge(flies, None)["passes"])
