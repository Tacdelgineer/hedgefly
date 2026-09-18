"""The bridge from logs to the visuals (visuals/hq/data-contract.md, version 2).

The visuals replay this file and nothing else, so what it promises has to be true: one seat per
fly, the elimination count matching the seats, real candles for the real days, and a hero who
is not its own ancestor."""

import json

import pandas as pd
import pytest

from scripts.export_for_visuals import candles_for, check, frame_of, generations, seats

POPULATION = 6


def summary(generation=0, eliminated=4):
    top = [{"id": "real-f00001", "trades_per_day": 2.5}]
    tribe = {"survived": POPULATION - eliminated, "eliminated": eliminated,
             "final_equity": {"best": 1031.1, "median": 997.46, "mean": 995.2, "worst": 962.03},
             "fitness": {"best": 0.0306, "median": -0.0025},
             "trades": {"total": 104, "median_per_day": 4.0, "max_per_day": 22.5},
             "top": top,
             "hero_lineage": {"id": "real-f00001", "parent": None, "born": 0, "origin": "founder",
                              "ancestors": [], "generations_lived": 1,
                              "fitness": 0.0306, "final_equity": 1031.1}}
    return {"generation": generation,
            "tribes": {"real": tribe, "scrambled": json.loads(json.dumps(tribe))}}


def log(eliminated=4):
    flies = [{"id": f"real-f{i:05d}", "final_equity": 900.0 + i, "eliminated": i < eliminated,
              "trades_per_day": i / 2} for i in range(POPULATION)]
    return {"tribes": {"real": {"flies": flies}, "scrambled": {"flies": list(flies)}}}


def payload(**changes):
    base = {"population": POPULATION, "windows": [], "frames": [frame_of(summary(), log())]}
    return {**base, **changes}


def test_a_frame_carries_one_seat_per_fly_in_log_order():
    f = frame_of(summary(), log())
    rows = f["tribes"]["real"]
    assert len(rows["flies"]) == POPULATION
    assert [s["trades_per_day"] for s in rows["flies"]] == [i / 2 for i in range(POPULATION)]
    assert rows["flies"][0]["eliminated"] is True and rows["flies"][-1]["eliminated"] is False
    assert rows["survived"] == 2 and rows["eliminated"] == 4
    assert f["heroes"]["real"]["id"] == "real-f00001" and f["heroes"]["real"]["trades_per_day"] == 2.5


def test_a_good_export_passes_its_own_checks():
    check(payload())


def test_a_seat_count_that_does_not_match_the_population_is_caught():
    with pytest.raises(SystemExit, match="expected"):
        check(payload(population=POPULATION + 1))


def test_an_elimination_count_that_disagrees_with_the_seats_is_caught():
    bad = frame_of(summary(eliminated=5), log(eliminated=4))      # the summary says 5, the seats 4
    with pytest.raises(SystemExit, match="marked eliminated"):
        check({"population": POPULATION, "windows": [], "frames": [bad]})


def test_a_hero_cannot_be_its_own_ancestor():
    f = frame_of(summary(), log())
    f["heroes"]["real"]["ancestors"] = ["real-f00001"]
    with pytest.raises(SystemExit, match="own ancestor"):
        check({"population": POPULATION, "windows": [], "frames": [f]})


def test_a_run_with_no_finished_generations_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="no finished generations"):
        generations(tmp_path)


def test_a_generation_without_its_full_log_is_skipped(tmp_path):
    (tmp_path / "gen_000_summary.json").write_text("{}")
    (tmp_path / "gen_001_summary.json").write_text("{}")
    (tmp_path / "gen_001.json").write_text("{}")
    assert [s.name for s, _ in generations(tmp_path)] == ["gen_001_summary.json"]


def test_seats_are_rounded_to_cents():
    rows = seats({"tribes": {"real": {"flies": [{"final_equity": 1000.12345, "eliminated": False,
                                                  "trades_per_day": 1.234}]}}}, "real")
    assert rows == [{"equity": 1000.12, "eliminated": False, "trades_per_day": 1.23}]


def evolve_bars(n=12):
    """Twelve known bars: opens 100, 101, ..., each bar 3 dollars high to low."""
    opens = [100.0 + i for i in range(n)]
    return pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=n, freq="5min", tz="UTC"),
                         "open": opens, "high": [o + 2 for o in opens], "low": [o - 1 for o in opens],
                         "close": [o + 0.5 for o in opens], "volume": 1.0})


def test_candles_are_the_real_bars_grouped():
    bars = candles_for(evolve_bars(), {"first_index": 0, "last_index": 11, "entry_price": 101.0}, per=6)
    assert len(bars) == 2
    assert bars[0] == [100.0, 107.0, 99.0, 105.5]      # open of bar 0, highest high, lowest low, close of bar 5
    assert bars[1] == [106.0, 113.0, 105.0, 111.5]


def test_a_data_file_whose_rows_have_moved_is_refused():
    """If the evolve set is re-fetched and its rows move, the logged indices point at another
    day. The entry price the run logged catches it before a wrong chart is drawn."""
    with pytest.raises(SystemExit, match="not the one this run traded"):
        candles_for(evolve_bars(), {"first_index": 0, "last_index": 11, "entry_price": 250.0})


def test_a_candle_that_does_not_contain_its_own_body_is_caught():
    with pytest.raises(SystemExit, match="do not contain"):
        check(payload(windows=[{"candles": [[100.0, 99.0, 98.0, 100.5]]}]))    # high below the close
