"""PLAN.md rule 8: the narrator never invents a number.

Tested against fake summaries, so no GPU and no language model are needed."""

import json

import pytest

from story.narrator import digest, narrate, parse_json
from story.validate import FactGuardError, check, resolve, validate

SUMMARY = {
    "run_id": "test", "generation": 7,
    "window": {"bars": 288, "first_time": "2025-03-04T09:00:00+00:00", "price_move_pct": -1.4},
    "tribes": {
        "real": {"population": 100, "alive": 97, "broke": 3,
                 "fitness": {"best": 0.0135, "median": -0.0085},
                 "final_equity": {"best": 1031.1, "median": 973.46, "worst": 872.03},
                 "trades": {"median": 18, "max": 192},
                 "hero_lineage": {"id": "real-f00038", "ancestors": ["real-f00011"], "born": 0}},
        "scrambled": {"population": 100, "alive": 100, "broke": 0,
                      "fitness": {"best": 0.006, "median": -0.0438},
                      "final_equity": {"best": 1005.97, "median": 957.14, "worst": 869.57},
                      "trades": {"median": 65, "max": 192},
                      "hero_lineage": {"id": "scrambled-f00043", "ancestors": [], "born": 0}},
    },
    "competitors": {"momentum": {"final_equity": 959.73}, "buy_and_hold": {"final_equity": 985.48}},
}

GOOD = {"headline": "The real tribe pulls ahead",
        "narration": "The best real fly finished at $1,031.10 while the scrambled tribe's best "
                     "managed $1,005.97. Three flies went broke.",
        "poster": {"title": "Generation 7", "subtitle": "A day in the market",
                   "featured_room": "trading_floor",
                   "stat_keys": ["tribes.real.final_equity.best", "tribes.real.broke"]}}


def story(**changes):
    return {**GOOD, **changes}


def test_a_true_story_passes():
    assert check(GOOD, SUMMARY).ok
    assert validate(GOOD, SUMMARY) is GOOD


def test_an_invented_number_is_caught():
    bad = story(narration="The best real fly finished at $1,212.44, a fine day.")
    problems = check(bad, SUMMARY).problems
    assert any("1,212.44" in p for p in problems)
    with pytest.raises(FactGuardError, match="1,212.44"):
        validate(bad, SUMMARY)


def test_an_invented_number_in_the_headline_is_caught():
    assert any("44" in p for p in check(story(headline="44 flies went broke today"), SUMMARY).problems)


def test_honest_rounding_is_allowed():
    """$1,031.10 may be told as $1,031, and -1.4 as 1.4% of a move."""
    assert check(story(narration="The best real fly reached $1,031 on a day that moved 1.4%."),
                 SUMMARY).ok


def test_a_fly_that_does_not_exist_is_caught():
    bad = story(narration="The lineage of real-f09999 endured another generation.")
    assert any("real-f09999" in p for p in check(bad, SUMMARY).problems)


def test_a_real_fly_is_allowed():
    assert check(story(narration="The lineage of real-f00038 endured, child of real-f00011."), SUMMARY).ok


def test_a_tribe_that_does_not_exist_is_caught():
    bad = story(narration="The mutant tribe collapsed entirely.")
    assert any("mutant" in p for p in check(bad, SUMMARY).problems)


def test_a_headline_over_eight_words_is_caught():
    bad = story(headline="This headline goes on and on and on and on for far too long")
    assert any("at most 8" in p for p in check(bad, SUMMARY).problems)


def test_narration_must_be_one_to_three_sentences():
    bad = story(narration="One. Two. Three. Four.")
    assert any("sentences" in p for p in check(bad, SUMMARY).problems)


def test_a_poster_stat_key_must_resolve():
    bad = story(poster={**GOOD["poster"], "stat_keys": ["tribes.real.final_equity.invented"]})
    assert any("does not resolve" in p for p in check(bad, SUMMARY).problems)
    assert resolve(SUMMARY, "tribes.real.final_equity.best") == 1031.1


def test_a_poster_room_must_exist():
    bad = story(poster={**GOOD["poster"], "featured_room": "the_pub"})
    assert any("no such room" in p for p in check(bad, SUMMARY).problems)


def test_missing_fields_are_caught():
    assert "missing narration" in check({"headline": "x", "poster": {}}, SUMMARY).problems


class FakeModel:
    """Replays scripted replies instead of calling the local endpoint."""

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def chat(self, system, user, max_tokens=400, temperature=0.0):
        self.prompts.append(user)
        return self.replies.pop(0)


def test_the_narrator_accepts_a_good_story_first_time():
    model = FakeModel([json.dumps(GOOD)])
    out = narrate(SUMMARY, model)
    assert out["headline"] == GOOD["headline"] and out["attempts"] == 1 and out["generation"] == 7


def test_the_narrator_rewrites_what_the_fact_guard_rejects():
    liar = story(narration="The best real fly finished at $9,999.99 and retired.")
    model = FakeModel([json.dumps(liar), json.dumps(GOOD)])
    out = narrate(SUMMARY, model)
    assert out["attempts"] == 2
    assert "9,999.99" in model.prompts[1], "the model must be told what was wrong"


def test_the_narrator_gives_up_rather_than_publish_a_lie():
    liar = story(narration="The best real fly finished at $9,999.99 and retired.")
    model = FakeModel([json.dumps(liar)] * 3)
    with pytest.raises(ValueError, match="rejected 3 attempts"):
        narrate(SUMMARY, model, attempts=3)


def test_a_fenced_reply_is_still_json():
    assert parse_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert parse_json('Sure! {"a": 2}') == {"a": 2}


def test_the_digest_keeps_what_the_story_needs_and_drops_the_bulk():
    """A summary carries curves and a hundred flies; a prompt gets the headline figures."""
    fat = {**SUMMARY, "tribes": {**SUMMARY["tribes"],
                                 "real": {**SUMMARY["tribes"]["real"],
                                          "top": [{"id": f"real-f{i:05d}"} for i in range(10)],
                                          "equity_curve": list(range(288))}}}
    small = digest(fat)
    assert small["generation"] == 7 and "hero_lineage" in small["tribes"]["real"]
    assert small["tribes"]["real"]["final_equity"]["best"] == 1031.1
    assert len(small["tribes"]["real"]["top"]) == 3
    assert "equity_curve" not in small["tribes"]["real"]
    assert "run_id" not in small
