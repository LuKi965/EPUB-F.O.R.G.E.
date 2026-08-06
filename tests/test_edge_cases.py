"""The corpus family that has to be built, and who can build it.

`docs/ROADMAP.md` point [1] asks for three books at the limits, and unlike every
other family these are not files anyone owns. They were built by
`tools/make_edge_cases.py`, which imported from `tests/public_corpus.py` — so
filling the family required a checkout, a Python and a command line.

The one person who can fill it runs Windows and the installer. "Just run the
script" was, to him, an instruction to do nothing, and the family sat at zero
across four releases while being reported as the thing standing in the way.
These tests hold the builders in the package, where the window can reach them.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.edge_cases import EDGES, build_edges
from epubforge.inventory import families, measure
from epubforge.reader import read_epub
from epubforge.report import Report


class TestTheEdgesCanBeBuiltWithoutACheckout:
    def test_the_builders_live_in_the_package_not_in_the_tests(self):
        """A window cannot import from a test suite: the installer does not
        ship one. This is the whole reason the module moved."""
        import epubforge.edge_cases as module

        assert module.__name__.startswith("epubforge.")
        assert callable(build_edges)

    def test_all_four_are_written(self, tmp_path):
        written = build_edges(tmp_path)
        assert len(written) == len(EDGES) == 4
        assert {p.stem for p in written} == set(EDGES)
        assert all(p.stat().st_size > 0 for p in written)

    def test_running_twice_leaves_four_files_not_eight(self, tmp_path):
        """The corpus counts books. A duplicate would inflate the very family
        somebody is pressing the button to fill."""
        build_edges(tmp_path)
        build_edges(tmp_path)
        assert len(list(tmp_path.glob("*.epub"))) == 4

    def test_each_one_is_a_readable_epub(self, tmp_path):
        """Broken in the one way it is built to be broken, and valid otherwise.
        A file broken in six ways tells you nothing when it fails."""
        for path in build_edges(tmp_path):
            parsed = read_epub(str(path), Report(source=str(path)))
            assert parsed.spine, path.name

    def test_every_edge_is_described_in_both_languages(self):
        for name, (builder, polish, english) in EDGES.items():
            assert callable(builder)
            assert polish and english and polish != english, name


class TestTheEdgesAreTheFamilyTheyWereBuiltFor:
    def test_each_lands_in_pathological(self, tmp_path):
        for path in build_edges(tmp_path):
            assert "pathological" in families(measure(path).fields), path.name

    def test_four_of_them_close_the_family(self, tmp_path):
        from epubforge.inventory import coverage

        rows = coverage([measure(path) for path in build_edges(tmp_path)])
        assert rows["pathological"]["have"] == 4
        assert rows["pathological"]["short"] == 0


class TestTheyAreTheSameFileEverywhere:
    """A signature is worth keeping only if two machines produce one book."""

    @pytest.mark.parametrize(
        "name", ["brzeg-bez-okladki", "brzeg-400-sekcji", "brzeg-jeden-plik"]
    )
    def test_two_runs_produce_identical_bytes(self, name, tmp_path):
        builder = EDGES[name][0]
        first = builder(tmp_path / "a" / f"{name}.epub").read_bytes()
        second = builder(tmp_path / "b" / f"{name}.epub").read_bytes()
        assert first == second

    def test_the_huge_one_is_deliberately_not_deterministic(self, tmp_path):
        """Its payload is noise, because the point is a file that cannot be
        compressed. Determinism and incompressibility cannot both hold, and
        this book is about memory rather than about a recorded signature."""
        builder = EDGES["brzeg-wielka-grafika"][0]
        first = builder(tmp_path / "a" / "x.epub", megabytes=1).read_bytes()
        second = builder(tmp_path / "b" / "x.epub", megabytes=1).read_bytes()
        assert first != second

    def test_the_host_system_byte_is_pinned(self, tmp_path):
        """`zipfile` stamps the platform it ran on — 0 for Windows, 3 for
        everything else. Unpinned, a corpus generated on Windows hashed
        differently from one generated in CI and every book came back "new"."""
        path = EDGES["brzeg-bez-okladki"][0](tmp_path / "e.epub")
        with zipfile.ZipFile(path) as archive:
            assert {info.create_system for info in archive.infolist()} == {3}
            assert {info.date_time for info in archive.infolist()} == {
                (1980, 1, 1, 0, 0, 0)
            }
