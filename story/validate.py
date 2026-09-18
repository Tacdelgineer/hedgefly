"""The Fact Guard (PLAN.md rule 8): the narrator never invents a number.

Every number a viewer sees - on screen, in narration, on a poster - comes out of the logs. So
a story is checked against the summary it was written from: every number in the narration must
be a number in that summary, every fly or lineage it names must exist, and every tribe it
names must be one of the two that ran.

Numbers are matched with a rounding tolerance, because "$1,031.10" may fairly be told as
"$1,031", and a figure written as a percentage may fairly be scaled by 100. A number that
matches nothing is a hallucination and the story is rejected and regenerated.
"""

from __future__ import annotations

import dataclasses
import re

ROOMS = ("lab", "brain_room", "trading_floor", "heros_desk", "vault", "archive", "print_shop")
HEADLINE_WORDS = 8
NARRATION_SENTENCES = 3
REL_TOLERANCE = 0.005        # "about $1,031" for $1,031.10

NUMBER = re.compile(r"[-+]?\$?\d[\d,]*(?:\.\d+)?%?")
FLY_ID = re.compile(r"\b[a-z]+-f\d+\b", re.IGNORECASE)
TRIBE_CLAIM = re.compile(r"\b(\w+)\s+tribe\b|\btribe\s+of\s+(\w+)\b", re.IGNORECASE)
# A sentence ends at .!? followed by space or end of text. The period inside "$1,031.10" is
# followed by a digit, so it never counts as the end of a sentence.
SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")


class FactGuardError(ValueError):
    """Raised when a story says something the summary does not."""


@dataclasses.dataclass(frozen=True)
class Verdict:
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems

    def raise_if_bad(self) -> None:
        if self.problems:
            raise FactGuardError("; ".join(self.problems))


def walk(node):
    """Every leaf of a nested summary."""
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from walk(value)
    else:
        yield node


def summary_numbers(summary: dict) -> set[float]:
    """Every number in the summary, including the ones inside strings: timestamps carry the
    year and the day, and fly ids carry their own digits."""
    found: set[float] = set()
    for leaf in walk(summary):
        if isinstance(leaf, bool):
            continue
        if isinstance(leaf, (int, float)):
            found.add(float(leaf))
        elif isinstance(leaf, str):
            found.update(float(n) for n in re.findall(r"\d+(?:\.\d+)?", leaf))
    return found


def summary_ids(summary: dict) -> set[str]:
    return {leaf.lower() for leaf in walk(summary) if isinstance(leaf, str) and FLY_ID.fullmatch(leaf)}


def summary_tribes(summary: dict) -> set[str]:
    return {name.lower() for name in summary.get("tribes", {})}


def text_numbers(text: str) -> list[tuple[float, str]]:
    """(value, as written) for every number in the text."""
    out = []
    for raw in NUMBER.findall(text):
        cleaned = raw.replace("$", "").replace(",", "").rstrip("%")
        try:
            out.append((float(cleaned), raw))
        except ValueError:
            continue
    return out


def matches(value: float, written: str, known: set[float], rel: float = REL_TOLERANCE) -> bool:
    """Is this number in the summary, allowing for honest rounding?"""
    decimals = len(written.split(".")[1].rstrip("%")) if "." in written else 0
    candidates = [value]
    if written.endswith("%"):                       # 1.4% may be the summary's 1.4 or its 0.014
        candidates += [value / 100, value * 100]
    for candidate in candidates:
        for number in known:
            if candidate == number:
                return True
            if abs(candidate - number) <= 0.5 * 10 ** (-decimals):
                return True
            if abs(candidate - number) <= rel * max(1.0, abs(number)):
                return True
    return False


def resolve(summary: dict, path: str):
    """A dotted stat key, the way a poster asks for one: tribes.real.final_equity.best."""
    node = summary
    for part in path.split("."):
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                raise KeyError(path)
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise KeyError(path)
    return node


def check(story: dict, summary: dict, rel: float = REL_TOLERANCE) -> Verdict:
    """Everything wrong with this story, as a list. Empty means it may be published."""
    problems: list[str] = []
    for field in ("headline", "narration", "poster"):
        if field not in story:
            problems.append(f"missing {field}")
    if problems:
        return Verdict(problems)

    headline, narration = str(story["headline"]), str(story["narration"])
    poster = story["poster"] if isinstance(story["poster"], dict) else {}

    if len(headline.split()) > HEADLINE_WORDS:
        problems.append(f"headline is {len(headline.split())} words, at most {HEADLINE_WORDS}")
    sentences = [s for s in SENTENCE_END.split(narration) if s.strip()]
    if not 1 <= len(sentences) <= NARRATION_SENTENCES:
        problems.append(f"narration is {len(sentences)} sentences, wanted 1 to {NARRATION_SENTENCES}")

    known = summary_numbers(summary)
    for text in (headline, narration, str(poster.get("title", "")), str(poster.get("subtitle", ""))):
        for value, written in text_numbers(text):
            if not matches(value, written, known, rel):
                problems.append(f"{written} is in the story but not in the summary")

    ids, tribes = summary_ids(summary), summary_tribes(summary)
    for text in (headline, narration):
        for name in FLY_ID.findall(text):
            if name.lower() not in ids:
                problems.append(f"no such fly: {name}")
        for claim in TRIBE_CLAIM.findall(text):
            word = (claim[0] or claim[1]).lower()
            if word not in tribes and word not in ("the", "a", "one", "other", "same", "each", "its", "this"):
                problems.append(f"no such tribe: {word}")

    for field in ("title", "subtitle", "featured_room"):
        if field not in poster:
            problems.append(f"poster is missing {field}")
    if poster.get("featured_room") not in ROOMS and "featured_room" in poster:
        problems.append(f"no such room: {poster['featured_room']}")
    for key in poster.get("stat_keys", []):
        try:
            resolve(summary, str(key))
        except KeyError:
            problems.append(f"stat key does not resolve: {key}")
    return Verdict(problems)


def validate(story: dict, summary: dict, rel: float = REL_TOLERANCE) -> dict:
    """The story, or an exception naming everything wrong with it."""
    check(story, summary, rel).raise_if_bad()
    return story
