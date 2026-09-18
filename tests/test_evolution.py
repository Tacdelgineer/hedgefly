"""Selection, mutation and lineage (PLAN.md EVOLUTION). No brain and no market: pure breeding."""

import numpy as np
import pytest
import torch

from brain import Genome
from brain.genome import GAIN_GRID, N_VOTES
from evolve.population import Lineage, breed, concat, fitness, mutate, replace, select

POPULATION, GROUPS = 100, 20


@pytest.fixture
def genome():
    return Genome.random(POPULATION, GROUPS, torch.Generator().manual_seed(0))


@pytest.fixture
def founded():
    lineage = Lineage("real")
    return lineage, lineage.found(POPULATION)


def test_fitness_is_the_log_ratio_of_the_bankroll():
    equity = np.array([1000.0, 2000.0, 500.0])
    scores = fitness(equity, np.zeros(3, bool), 1000.0)
    assert scores[0] == pytest.approx(0.0)
    assert scores[1] == pytest.approx(np.log(2))
    assert scores[2] == pytest.approx(np.log(0.5))


def test_the_bankroll_is_only_a_scale_factor():
    """Why $1,000 was left alone: a log ratio does not care what the flies started with."""
    equity = np.array([1100.0, 900.0])
    assert np.allclose(fitness(equity, np.zeros(2, bool), 1000.0),
                       fitness(10 * equity, np.zeros(2, bool), 10_000.0))


def test_broke_flies_all_share_the_worst_fitness():
    equity = np.array([1500.0, 400.0, 450.0])
    broke = np.array([False, True, True])
    scores = fitness(equity, broke, 1000.0)
    assert scores[1] == scores[2] == scores.min()
    assert scores[0] > scores[1]


def test_selection_keeps_the_top_fifth_and_fills_the_rest(genome, founded):
    lineage, roster = founded
    scores = np.arange(POPULATION, dtype=float)                 # fly 99 is the best
    offspring = breed(genome, roster, scores, lineage, 0, np.random.default_rng(0),
                      torch.Generator().manual_seed(0))
    assert (offspring.n_survive, offspring.n_child, offspring.n_newcomer) == (20, 70, 10)
    assert offspring.genome.population == POPULATION
    assert len(offspring.roster) == POPULATION
    assert offspring.roster[0] == roster[99], "the fittest fly must be the first survivor"
    assert set(offspring.survivors) == {roster[i] for i in range(POPULATION - 20, POPULATION)}


def test_survivors_carry_their_genome_through_unchanged(genome, founded):
    lineage, roster = founded
    scores = np.arange(POPULATION, dtype=float)
    offspring = breed(genome, roster, scores, lineage, 0, np.random.default_rng(0),
                      torch.Generator().manual_seed(0))
    assert torch.equal(offspring.genome.readout_w[0], genome.readout_w[99])


def test_children_record_a_surviving_parent_and_newcomers_none(genome, founded):
    lineage, roster = founded
    scores = np.arange(POPULATION, dtype=float)
    offspring = breed(genome, roster, scores, lineage, 0, np.random.default_rng(0),
                      torch.Generator().manual_seed(0))
    children = [lineage.flies[i] for i in offspring.roster[20:90]]
    newcomers = [lineage.flies[i] for i in offspring.roster[90:]]
    assert all(c.parent in offspring.survivors and c.origin == "child" and c.born == 1 for c in children)
    assert all(n.parent is None and n.origin == "newcomer" for n in newcomers)


def test_a_lineage_can_be_walked_back_to_its_founder(genome, founded):
    """What the summary's hero lineage is made of."""
    lineage, roster = founded
    scores = np.arange(POPULATION, dtype=float)
    current, generation = genome, 0
    for generation in range(3):
        offspring = breed(current, roster, scores, lineage, generation, np.random.default_rng(generation),
                          torch.Generator().manual_seed(generation))
        current, roster = offspring.genome, offspring.roster
    child = roster[-1 - 10]                                     # a child, not a newcomer
    chain = lineage.ancestors(child)
    assert len(chain) == 3 and lineage.flies[chain[0]].origin == "founder"
    assert lineage.flies[chain[0]].born == 0
    assert lineage.ancestors(roster[0]) == []                   # a founder that has survived


def test_mutation_moves_every_gene_by_its_own_spread(genome):
    child = mutate(genome, rate=0.5, generator=torch.Generator().manual_seed(0))
    spreads = Genome.spreads(GROUPS)
    for name, spread in spreads.items():
        delta = (getattr(child, name) - getattr(genome, name)).flatten()
        assert (delta != 0).all(), f"{name} was not mutated"
        assert float(delta.std()) == pytest.approx(0.5 * spread, rel=0.15)


def test_genome_arithmetic_keeps_the_shapes(genome):
    picked = select(genome, [3, 3, 7])
    assert picked.population == 3
    assert torch.equal(picked.readout_w[0], picked.readout_w[1])
    joined = concat(picked, Genome.random(2, GROUPS))
    assert joined.population == 5
    swapped = replace(genome, [0], Genome.neutral(1, GROUPS))
    assert torch.equal(swapped.readout_w[0], torch.zeros(GROUPS, N_VOTES))
    assert torch.equal(swapped.readout_w[1], genome.readout_w[1])
    assert swapped.chart_gain.shape == (POPULATION, GAIN_GRID, GAIN_GRID)


def test_fitness_over_fixed_windows_is_the_mean_log_return():
    from evolve.population import fitness_over_windows
    finals = np.array([[1100.0, 1000.0], [900.0, 1000.0], [1000.0, 1000.0], [1000.0, 1000.0]])
    scores = fitness_over_windows(finals, 1000.0)
    assert scores[0] == pytest.approx((np.log(1.1) + np.log(0.9)) / 4)
    assert scores[1] == 0.0
    assert scores[0] < scores[1], "a good day and a bad day of the same size is a loss, not a wash"


def test_the_logs_and_breeding_eliminate_the_same_flies(genome, founded):
    from evolve.population import survivors_of
    lineage, roster = founded
    scores = np.random.default_rng(3).normal(size=POPULATION)
    keep = survivors_of(scores)
    offspring = breed(genome, roster, scores, lineage, 0, np.random.default_rng(0),
                      torch.Generator().manual_seed(0))
    assert offspring.survivors == [roster[i] for i in keep]
    assert len(keep) == 20
