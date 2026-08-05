"""Where every book in a run is going, decided before any of them moves.

A batch used to work this out one book at a time, from the basename of the
source. Two books called `ksiazka.epub` in different folders therefore resolved
to one destination: the second overwrote the first, both were announced as
written, and the run exited 0. In a library filed by author — which is how
libraries are filed — that is the ordinary case, not an edge one.

Deciding all of it up front is what makes the collision visible while it is
still a question rather than a loss.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Job:
    source: str
    destination: str


@dataclass
class Collision:
    """Several sources that would land on one destination."""

    destination: str
    sources: list[str]


@dataclass
class Plan:
    jobs: list[Job] = field(default_factory=list)
    collisions: list[Collision] = field(default_factory=list)
    #: Destinations that already hold a file. Not an error by itself — the
    #: caller decides whether that needs a `--force`.
    occupied: list[str] = field(default_factory=list)
    #: Sources whose destination would be the source itself.
    self_targets: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.collisions and not self.self_targets


def destination_for(source: str, output: str | None) -> str:
    """Where one book goes, given the ``-o`` the user passed.

    Three shapes, and they are not interchangeable: no output at all writes
    beside the source; a directory takes the basename; a file path is used
    verbatim, which only makes sense for a single input.
    """
    if not output:
        stem = os.path.splitext(source)[0]
        return f"{stem}.forged.epub"
    if os.path.isdir(output):
        stem = os.path.splitext(os.path.basename(source))[0]
        return os.path.join(output, f"{stem}.epub")
    return output


def plan_batch(sources: list[str], output: str | None) -> Plan:
    """Resolve every destination and report what is wrong with the set.

    Nothing here touches the filesystem beyond asking what exists. The point is
    to be able to answer "what would this run do" without doing it.
    """
    plan = Plan()
    by_destination: dict[str, list[str]] = {}

    for source in sources:
        destination = destination_for(source, output)
        plan.jobs.append(Job(source, destination))
        by_destination.setdefault(os.path.abspath(destination), []).append(source)

    for destination, claimants in by_destination.items():
        if len(claimants) > 1:
            plan.collisions.append(Collision(destination, claimants))
        elif os.path.exists(destination):
            plan.occupied.append(destination)

    for job in plan.jobs:
        if os.path.abspath(job.destination) == os.path.abspath(job.source):
            plan.self_targets.append(job.source)

    return plan


def describe(plan: Plan) -> list[str]:
    """The plan as lines a person can read before agreeing to it."""
    lines = [f"{len(plan.jobs)} book(s):"]
    for job in plan.jobs:
        marker = "!" if os.path.exists(job.destination) else " "
        lines.append(f"  {marker} {job.source}")
        lines.append(f"      -> {job.destination}")
    if plan.occupied:
        lines.append("")
        lines.append(f"{len(plan.occupied)} destination(s) already exist (marked !)")
    return lines
