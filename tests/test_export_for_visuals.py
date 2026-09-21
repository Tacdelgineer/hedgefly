"""The bridge from logs to the visuals (visuals/hq/data-contract.md, version 2).

The visuals replay this file and nothing else, so what it promises has to be true: one seat per
fly, the elimination count matching the seats, real candles for the real days, and a hero who
is not its own ancestor."""

import json

import pandas as pd
import pytest

import scripts.export_for_visuals as exporter
from scripts.export_for_visuals import (brain_block, candles_for, check, frame_of, generations,
                                          locked_block, seats, traded_moments)

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


def log(eliminated=4, generation=0, survivors=0):
    """POPULATION flies as a generation's own log holds them.

    Every fly records the generation it was `born` in and its `origin` at birth, which is what
    the Nursery counts. At generation 0 the whole population are founders. Later, the first
    `survivors` flies were born a generation earlier and carry the origin they were born with;
    the rest were born into this generation, the last of them a random newcomer."""
    flies = []
    for i in range(POPULATION):
        if generation == 0:
            born, origin = 0, "founder"
        elif i < survivors:
            born, origin = generation - 1, "child"
        else:
            born, origin = generation, "newcomer" if i == POPULATION - 1 else "child"
        flies.append({"id": f"real-f{i:05d}", "final_equity": 900.0 + i, "eliminated": i < eliminated,
                      "trades_per_day": i / 2, "born": born, "origin": origin})
    return {"tribes": {"real": {"flies": flies},
                       "scrambled": {"flies": json.loads(json.dumps(flies))}}}


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


def test_at_generation_zero_the_whole_population_are_founders():
    f = frame_of(summary(), log())
    assert f["tribes"]["real"]["born"] == {"founder": POPULATION, "child": 0, "newcomer": 0,
                                           "survivor": 0}


def test_the_nursery_counts_who_was_born_this_generation():
    """A fly born in an earlier generation is a survivor whatever it was born as, so the four
    counts are a partition of the population and the Nursery's arithmetic always closes."""
    f = frame_of(summary(generation=3), log(generation=3, survivors=2))
    born = f["tribes"]["real"]["born"]
    assert born == {"founder": 0, "child": 3, "newcomer": 1, "survivor": 2}
    assert sum(born.values()) == POPULATION


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


def test_the_brain_room_reads_its_figures_from_the_run(tmp_path):
    (tmp_path / "run_summary.json").write_text(json.dumps({"brain": {"neurons": 166700,
                                                                     "readout_groups": 498}}))
    assert brain_block(tmp_path)["neurons"] == 166700
    assert brain_block(tmp_path / "nowhere") is None


def test_the_vault_reads_the_locked_set_from_the_split_and_never_from_the_parquet(tmp_path,
                                                                                 monkeypatch):
    """PLAN.md rule 3: the locked candles are for the two finale scripts alone. split.json holds
    the counts precisely so the vault's wall can be filled without opening the parquet."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "split.json").write_text(json.dumps(
        {"locked": {"file": "the-candles.parquet", "rows": 52915,
                    "first": "2026-03-17T22:00:00+00:00", "last": "2026-09-17T22:00:00+00:00"}}))
    monkeypatch.setattr(exporter, "REPO", tmp_path)

    # split.json is the only file in data/, so a block at all proves nothing else was opened
    block = locked_block()
    assert block["rows"] == 52915 and block["source"] == "data/split.json"
    assert "file" not in block                 # the candles are not even named on the vault wall


def test_a_project_without_a_split_file_simply_has_no_vault_figures(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "REPO", tmp_path)
    assert locked_block() is None


FEE = 5.0 / 1e4


def a_finale(fills=(3, 7, 11, 15), bars=40, every=4, logged_trades=None):
    """A finale where the model's fills are known, so what is recovered can be compared.

    The fee-free wallet is a flat line; the with-fees one is the same line with one fee taken
    out at each fill. That is exactly the relationship the real passes have, which is what makes
    the fills recoverable at all."""
    free = [1000.0] * bars
    fee, taken = [], 1.0
    for k in range(bars):
        if k in fills:
            taken *= 1 - FEE
        fee.append(free[k] * taken)
    llm = lambda equity: {"equity": equity, "trades": len(fills) if logged_trades is None else logged_trades,
                          "decisions": bars // every, "bars_between_decisions": every,
                          "replies": {"asked": bars // every, "counts": {"BUY": 2, "SELL": 2, "HOLD": 6},
                                      # the last decision sits at bar (bars//every - 1) * every,
                                      # which on this five-minute grid is 03:00
                                      "last": [["2026-01-01T03:00:00+00:00", "HOLD"]]}}
    return {"first_time": "2026-01-01T00:00:00+00:00", "last_time": "2026-01-01T03:15:00+00:00",
            "bars": bars,
            "passes": {"with_fees": {"fee_bps": 5.0, "competitors": {"llm": llm(fee)}},
                       "no_fees": {"fee_bps": 0.0, "competitors": {"llm": llm(free)}}}}


def test_the_model_s_fills_are_recovered_from_the_fee_step():
    """Nothing but a fill can move the ratio between the two passes, so every step is one."""
    out = traded_moments(a_finale(fills=(3, 7, 11, 15)))
    assert out["count"] == 4 and out["buys"] == 2 and out["sells"] == 2
    assert [side for _stamp, side in out["moments"]] == ["BUY", "SELL", "BUY", "SELL"]


def test_fills_that_disagree_with_the_logged_trade_count_are_refused():
    """The wall must never show a trade the logs do not contain (PLAN.md rule 8), so a
    reconstruction that does not match the count the run logged is not exported at all."""
    with pytest.raises(SystemExit, match="logged 9 trades"):
        traded_moments(a_finale(fills=(3, 7, 11, 15), logged_trades=9))


def test_a_clock_too_coarse_to_print_is_refused():
    """The times are interpolated, then checked against the timestamps the run really logged."""
    raw = a_finale(fills=(3, 7))
    raw["passes"]["with_fees"]["competitors"]["llm"]["replies"]["last"] = [["2026-01-01T00:00:00+00:00", "HOLD"]]
    with pytest.raises(SystemExit, match="interpolated clock"):
        traded_moments(raw)


def test_a_finale_with_no_fee_free_twin_recovers_nothing_rather_than_guessing():
    raw = a_finale(fills=(3, 7))
    del raw["passes"]["no_fees"]
    assert traded_moments(raw) is None
