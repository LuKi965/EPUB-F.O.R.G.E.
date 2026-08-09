"""The repository's own half of "is this released", held to by the suite.

A version was once bumped, given a changelog entry, committed, pushed — and
then called released. It was not: no build, no tag, nothing anybody could
download. The milestone it closed went unfrozen too, and `frozen/*` quietly
stopped covering the roadmap.

`packaging/release_check.py` is the whole answer and it needs the network,
because the fact that settles the question lives on the remote. What is checked
*here* is everything that does not: the version, the changelog and the READMEs
agreeing with each other. Those are what the release step reads, and every one
of them has been wrong at least once.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "packaging"))

from release_check import RELEASED, heading_for, milestone_points, version  # noqa: E402

import epubforge  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def changelog() -> str:
    return (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_the_version_is_the_one_the_package_reports():
    assert version() == epubforge.__version__


class TestTheChangelogKeepsUp:
    def test_the_current_version_has_a_section(self):
        """Bumping the number without writing the entry is how a release goes
        out with empty notes — the workflow reads the changelog for them."""
        assert heading_for(epubforge.__version__), (
            f"CHANGELOG.md has no dated section for {epubforge.__version__}"
        )

    def test_the_section_says_which_stage_and_when(self):
        heading = heading_for(epubforge.__version__)
        assert heading.group("stage") == epubforge.__stage__
        assert heading.group("date")

    def test_no_version_is_written_twice(self):
        """Two sections for one number means one of them is what shipped and
        nobody can tell which."""
        numbers = [m.group("version") for m in RELEASED.finditer(changelog())]
        assert len(numbers) == len(set(numbers)), sorted(
            n for n in numbers if numbers.count(n) > 1
        )

    def test_the_sections_run_newest_first(self):
        def key(number: str) -> tuple[int, ...]:
            return tuple(int(part) for part in number.split("."))

        numbers = [m.group("version") for m in RELEASED.finditer(changelog())]
        assert numbers == sorted(numbers, key=key, reverse=True)

    def test_unreleased_is_where_work_waits(self):
        """The heading has to survive, because renaming it is the handover that
        turns work into a release, and there is nowhere else for the next
        entry to go."""
        assert "\n## Unreleased\n" in changelog()


class TestTheReadmesAreStepZero:
    """Step 0 of the milestone cycle, and it is step *zero* because the README
    ships with the release and is what a first-time visitor reads."""

    @pytest.mark.parametrize("name", ["README.md", "README.en.md"])
    def test_it_names_the_current_version(self, name):
        assert f"`{epubforge.__version__}`" in (ROOT / name).read_text(encoding="utf-8")

    @pytest.mark.parametrize("name", ["README.md", "README.en.md"])
    def test_it_names_only_one_version(self, name):
        """A stale number left beside a fresh one is worse than a stale number
        on its own: it reads as a deliberate distinction."""
        text = (ROOT / name).read_text(encoding="utf-8")
        found = set(re.findall(r"`(\d+\.\d+\.\d+)`", text))
        assert found == {epubforge.__version__}, found


class TestAMilestoneSaysSoInItsHeading:
    """The marker lives in the changelog heading because that is the one line
    nobody forgets to write. Anywhere else it would be the second thing
    forgotten, right after the freeze it exists to remind about."""

    def test_the_marker_parses_when_it_is_there(self):
        heading = heading_for(epubforge.__version__)
        for point in milestone_points(heading.group("rest")):
            assert point.strip()

    def test_a_milestone_marker_is_not_silently_reused(self):
        """Two releases claiming to close the same roadmap point means one of
        them did not, and the frozen branch for it points at the wrong thing."""
        points = [
            point
            for match in RELEASED.finditer(changelog())
            for point in milestone_points(match.group("rest"))
        ]
        assert len(points) == len(set(points)), sorted(
            p for p in points if points.count(p) > 1
        )
