"""Selection, mutation and lineage: how one generation of flies becomes the next.

PLAN.md EVOLUTION: fitness is log(final equity / start cash), broke flies get the minimum
fitness, the top 20% survive, children are a survivor's genome plus Gaussian noise, 10% of
every generation are random newcomers, and every fly records the parent it came from.

Nothing here touches the brain (rule 1): a fly is its genome and its ancestry.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import torch

from brain import Genome

SURVIVE_SHARE = 0.20
NEWCOMER_SHARE = 0.10
MUTATION_RATE = 0.15       # in units of each gene's own starting spread (Genome.spreads)


# ---- genome arithmetic ----------------------------------------------------------------------

def _fields(genome: Genome) -> tuple[str, ...]:
    return tuple(f.name for f in dataclasses.fields(genome))


def select(genome: Genome, rows) -> Genome:
    """The flies at `rows`, in that order (a survivor can be picked more than once)."""
    rows = torch.as_tensor(np.asarray(rows), dtype=torch.long)
    return Genome(**{name: getattr(genome, name)[rows] for name in _fields(genome)})


def concat(*genomes: Genome) -> Genome:
    parts = [g for g in genomes if g.population]
    return Genome(**{name: torch.cat([getattr(g, name) for g in parts]) for name in _fields(parts[0])})


def replace(genome: Genome, rows, other: Genome) -> Genome:
    """The same population with the flies at `rows` swapped for `other`."""
    rows = torch.as_tensor(np.asarray(rows), dtype=torch.long)
    out = {}
    for name in _fields(genome):
        tensor = getattr(genome, name).clone()
        tensor[rows] = getattr(other, name)
        out[name] = tensor
    return Genome(**out)


def mutate(genome: Genome, rate: float = MUTATION_RATE, generator: torch.Generator | None = None) -> Genome:
    """Gaussian noise on every gene, scaled by that gene's own starting spread, so one rate
    means the same thing to a chart gain around 1 and to a vote around 0.04."""
    spreads = Genome.spreads(genome.n_groups)
    out = {}
    for name in _fields(genome):
        tensor = getattr(genome, name)
        noise = torch.randn(tensor.shape, generator=generator, dtype=tensor.dtype)
        out[name] = tensor + rate * spreads[name] * noise
    return Genome(**out)


# ---- fitness --------------------------------------------------------------------------------

def fitness(final_equity: np.ndarray, broke: np.ndarray, start_cash: float) -> np.ndarray:
    """log(final equity / start cash). Broke flies all share the tribe's worst fitness, so
    selection never prefers one bankruptcy to another (PLAN.md EVOLUTION)."""
    scores = np.log(np.maximum(final_equity, 1e-9) / start_cash)
    return np.where(broke, scores.min(), scores) if broke.any() else scores


# ---- lineage --------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Fly:
    id: str
    parent: str | None
    born: int               # the generation this fly was bred in
    origin: str             # founder | child | newcomer

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


class Lineage:
    """Every fly a tribe has ever bred, by id, so a family tree can be walked backwards.

    A survivor keeps its id and its ancestry: it is the same individual living another
    generation, not a copy of itself."""

    def __init__(self, tribe: str):
        self.tribe = tribe
        self.flies: dict[str, Fly] = {}
        self._minted = 0

    def mint(self, parent: str | None, born: int, origin: str) -> str:
        fly = Fly(f"{self.tribe}-f{self._minted:05d}", parent, born, origin)
        self._minted += 1
        self.flies[fly.id] = fly
        return fly.id

    def found(self, population: int) -> list[str]:
        return [self.mint(None, 0, "founder") for _ in range(population)]

    def ancestors(self, fly_id: str) -> list[str]:
        """The chain from this fly's parent back to the founder, oldest first."""
        chain: list[str] = []
        current = self.flies[fly_id].parent
        while current is not None:
            chain.append(current)
            current = self.flies[current].parent
        return list(reversed(chain))

    def record(self, fly_id: str, generation: int) -> dict:
        """A fly's papers: who it is, where it came from, and how long it has been alive."""
        fly = self.flies[fly_id]
        return {**fly.as_dict(), "ancestors": self.ancestors(fly_id),
                "generations_lived": generation - fly.born + 1}


# ---- breeding -------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Breeding:
    genome: Genome
    roster: list[str]          # fly id per row of the genome
    survivors: list[str]
    n_survive: int
    n_child: int
    n_newcomer: int


def breed(genome: Genome, roster: list[str], scores: np.ndarray, lineage: Lineage, generation: int,
          rng: np.random.Generator, generator: torch.Generator,
          survive_share: float = SURVIVE_SHARE, newcomer_share: float = NEWCOMER_SHARE,
          rate: float = MUTATION_RATE) -> Breeding:
    """The next generation: survivors unchanged, children of survivors, and random newcomers."""
    population = genome.population
    n_survive = max(1, round(survive_share * population))
    n_newcomer = round(newcomer_share * population)
    n_child = population - n_survive - n_newcomer
    if n_child < 0:
        raise ValueError(f"survivors ({n_survive}) and newcomers ({n_newcomer}) exceed the population ({population})")

    ranked = np.argsort(-scores, kind="stable")                      # deterministic ties
    survivors = ranked[:n_survive]
    parents = rng.choice(survivors, n_child) if n_child else np.empty(0, int)

    children = mutate(select(genome, parents), rate, generator) if n_child else None
    newcomers = Genome.random(n_newcomer, genome.n_groups, generator) if n_newcomer else None
    parts = [select(genome, survivors)] + [g for g in (children, newcomers) if g is not None]

    roster_next = [roster[i] for i in survivors]
    roster_next += [lineage.mint(roster[i], generation + 1, "child") for i in parents]
    roster_next += [lineage.mint(None, generation + 1, "newcomer") for _ in range(n_newcomer)]
    return Breeding(concat(*parts), roster_next, [roster[i] for i in survivors],
                    n_survive, n_child, n_newcomer)
