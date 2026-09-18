"""The bridge from logs to the HQ (visuals/hq/data-contract.md).

The visuals replay this file and nothing else, so what it promises has to be true: one seat
per fly, the death count matching the seats, and a hero who is not its own ancestor."""

import json

import pytest

from scripts.export_for_visuals import check, frame_of, generations, seats

POPULATION = 6


def summary(generation=0, broke=2):
    top = [{"id": "real-f00001", "trades": 9}]
    tribe = {"alive": POPULATION - broke, "broke": broke,
             "final_equity": {"best": 1031.1, "median": 973.46, "mean": 971.2, "worst": 402.03},
             "fitness": {"best": 0.0306, "median": -0.0269},
             "trades": {"total": 104, "median": 18, "max": 92},
             "top": top,
             "hero_lineage": {"id": "real-f00001", "parent": None, "born": 0, "origin": "founder",
                              "ancestors": [], "generations_lived": 1,
                              "fitness": 0.0306, "final_equity": 1031.1}}
    return {"generation": generation,
            "window": {"first_time": "2025-01-01T00:00:00+00:00", "last_time": "2025-01-02T00:00:00+00:00",
                       "price_move_pct": -1.4, "bars": 288},
            "tribes": {"real": tribe, "scrambled": json.loads(json.dumps(tribe))},
            "competitors": {name: {"final_equity": 950.0} for name in ("momentum", "random", "buy_and_hold")}}


def log(broke=2):
    flies = [{"id": f"real-f{i:05d}", "final_equity": 900.0 + i, "broke": i < broke, "trades": i}
             for i in range(POPULATION)]
    return {"tribes": {"real": {"flies": flies}, "scrambled": {"flies": list(flies)}}}


def payload(**changes):
    base = {"population": POPULATION, "frames": [frame_of(summary(), log())]}
    return {**base, **changes}


def test_a_frame_carries_one_seat_per_fly_in_log_order():
    f = frame_of(summary(), log())
    assert len(f["tribes"]["real"]["flies"]) == POPULATION
    assert [s["trades"] for s in f["tribes"]["real"]["flies"]] == list(range(POPULATION))
    assert f["tribes"]["real"]["flies"][0]["broke"] is True
    assert f["competitors"] == {"momentum": 950.0, "random": 950.0, "buy_and_hold": 950.0}
    assert f["heroes"]["real"]["id"] == "real-f00001" and f["heroes"]["real"]["trades"] == 9


def test_a_good_export_passes_its_own_checks():
    check(payload())


def test_a_seat_count_that_does_not_match_the_population_is_caught():
    with pytest.raises(SystemExit, match="expected"):
        check(payload(population=POPULATION + 1))


def test_a_death_count_that_disagrees_with_the_seats_is_caught():
    bad = frame_of(summary(broke=3), log(broke=2))      # the summary says 3, the seats say 2
    with pytest.raises(SystemExit, match="marked broke"):
        check({"population": POPULATION, "frames": [bad]})


def test_a_hero_cannot_be_its_own_ancestor():
    f = frame_of(summary(), log())
    f["heroes"]["real"]["ancestors"] = ["real-f00001"]
    with pytest.raises(SystemExit, match="own ancestor"):
        check({"population": POPULATION, "frames": [f]})


def test_a_run_with_no_finished_generations_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="no finished generations"):
        generations(tmp_path)


def test_a_generation_without_its_full_log_is_skipped(tmp_path):
    (tmp_path / "gen_000_summary.json").write_text("{}")
    (tmp_path / "gen_001_summary.json").write_text("{}")
    (tmp_path / "gen_001.json").write_text("{}")
    assert [s.name for s, _ in generations(tmp_path)] == ["gen_001_summary.json"]


def test_seats_are_rounded_to_cents():
    rows = seats({"tribes": {"real": {"flies": [{"final_equity": 1000.12345, "broke": False, "trades": 1}]}}}, "real")
    assert rows == [{"equity": 1000.12, "broke": False, "trades": 1}]
