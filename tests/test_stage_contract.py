"""F-029 and F-030 — what a stage may do, and how often it may pay for it.

The audit filed these as architecture, and they were the two items I left for
last because "make the model immutable" is a refactor of the whole program
rather than a defect with a book behind it. That framing is right about the
refactor and wrong about the risk, and this file is the part that can be built
and checked today.

**F-029 — a mutable `Book` through large stages means any stage can change
anything and nothing notices.** The concrete danger is not that the model is
mutable; it is that a stage's *claim* about itself is unenforced. `ProfileStage`
says it measures the book and writes findings. Nothing checked that, and a
measuring stage that quietly edits a document is the worst kind of defect this
program can have: every other claim in the same run rests on the same sort of
promise.

So a stage declares `mutates`, and the pipeline takes a fingerprint of the book
before a stage that says `False` and compares it after. A stage that breaks its
word does not produce a book — the run is blocked, because the output was
produced under an assumption that turned out false.

**F-030 — the same files are parsed several times.** Measured before:
15 documents, 22 parses on one real book. After: 15 and 15.

The cache is keyed on a digest of the bytes, which is what makes it safe, and it
has two doors. A reader gets a shared tree; a stage that is going to *edit* one
takes it, and taking removes it from the cache — because two documents in one
book can be byte-identical, and a shared mutated tree would be one document
silently overwriting another.
"""

from __future__ import annotations

import hashlib
import zipfile

import pytest

from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy
from epubforge.stages import DEFAULT_STAGES
from epubforge.stages.base import Context, Stage
from tests.factory import make_modern_epub


class TestF029AStageIsHeldToWhatItSaysAboutItself:
    def test_a_stage_that_only_measures_says_so(self):
        from epubforge.stages.profile import ProfileStage

        assert ProfileStage.mutates is False

    def test_and_everything_else_admits_that_it_changes_things(self):
        """The default is the unflattering one: a stage that has not thought
        about the question is assumed to change the book."""
        assert Stage.mutates is True
        changing = [s for s in DEFAULT_STAGES if s.mutates]
        assert len(changing) == len(DEFAULT_STAGES) - 1

    def test_a_stage_that_breaks_its_word_stops_the_rebuild(self, tmp_path):
        """The whole point. Written as a liar rather than found in the wild,
        because the enforcement is what is being tested and a real stage that
        did this would be a bug to fix rather than a fixture."""

        class Liar(Stage):
            name = "liar"
            mutates = False

            def run(self, ctx: Context) -> None:
                first = next(iter(sorted(ctx.book.resources)))
                ctx.book.resources[first].data += b"<!-- ktos tu byl -->"

        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"), [Liar])
        assert result.status is Status.BLOCKED
        assert result.output_path is None
        assert "package.stage-broke-its-word" in {
            f.rule for f in result.report.findings if f.rule
        }

    @pytest.mark.parametrize(
        "damage",
        [
            # Not `spine.reverse()`: the fixture has one spine item and
            # reversing one item is not a change. A test whose damage does no
            # damage passes for the wrong reason.
            pytest.param(lambda book: book.spine.pop(), id="reading-order"),
            pytest.param(lambda book: book.metadata.identifiers.clear(), id="identity"),
            # `linear` decides whether page-turning ever reaches a document.
            # Nothing about the file changes; where the reader ends up does.
            pytest.param(
                lambda book: setattr(book.spine[0], "linear", not book.spine[0].linear),
                id="out-of-the-flow",
            ),
            pytest.param(lambda book: book.toc.clear(), id="contents"),
            pytest.param(
                lambda book: book.resources.pop(sorted(book.resources)[0]), id="a-file"
            ),
        ],
    )
    def test_the_fingerprint_sees_more_than_the_bytes(self, tmp_path, damage):
        """A stage can change a book without touching a single document — by
        reordering the spine, renaming it, emptying the contents. Each of those
        is something a reader meets on the first page."""

        class Liar(Stage):
            name = "liar"
            mutates = False

            def run(self, ctx: Context) -> None:
                damage(ctx.book)

        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"), [Liar])
        assert result.status is Status.BLOCKED

    def test_an_honest_measuring_stage_passes(self, tmp_path):
        """The guard on the guard: a check that fails for everybody is a check
        nobody can use."""

        from epubforge.report import Level

        class Honest(Stage):
            name = "honest"
            mutates = False

            def run(self, ctx: Context) -> None:
                # Reads the book, writes a finding, changes nothing — which is
                # what a measuring stage is.
                ctx.report.add(
                    "honest",
                    Level.INFO,
                    "package.regenerated",
                    values={"version": ctx.book.source_version},
                )

        source = make_modern_epub(str(tmp_path / "in2.epub"))
        result = rebuild(source, str(tmp_path / "out2.epub"), Policy.preset("preserve"), [Honest])
        assert result.status.wrote_a_file

    def test_a_real_rebuild_is_not_blocked_by_this(self, tmp_path):
        """Every stage in the pipeline, on a real book, against its own claim."""
        source = make_modern_epub(str(tmp_path / "real.epub"))
        result = rebuild(source, str(tmp_path / "real-out.epub"), Policy.preset("preserve"))
        assert result.status.wrote_a_file


class TestF030ADocumentIsParsedOncePerVersionOfItself:
    @staticmethod
    def parse_counts(source: str, destination: str) -> dict[str, int]:
        """How many times each distinct set of bytes was handed to the parser."""
        import collections

        from epubforge import xhtml
        from epubforge.stages import content as content_stage

        counts: collections.Counter = collections.Counter()
        original = xhtml.parse_document

        def counting(data):
            counts[hashlib.sha256(data).hexdigest()] += 1
            return original(data)

        xhtml.parse_document = counting
        content_stage.xhtml.parse_document = counting
        try:
            rebuild(source, destination, Policy.preset("preserve"))
        finally:
            xhtml.parse_document = original
            content_stage.xhtml.parse_document = original
        return dict(counts)

    def test_nothing_is_parsed_twice_from_the_same_bytes(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        counts = self.parse_counts(source, str(tmp_path / "out.epub"))
        repeated = {digest[:8]: n for digest, n in counts.items() if n > 1}
        assert not repeated, f"parsed more than once: {repeated}"

    def test_and_the_book_still_comes_out_right(self, tmp_path):
        """A cache that breaks the output is not an optimisation."""
        source = make_modern_epub(str(tmp_path / "in2.epub"))
        result = rebuild(source, str(tmp_path / "out2.epub"), Policy.preset("preserve"))
        assert result.status.wrote_a_file
        with zipfile.ZipFile(result.output_path) as archive:
            assert any(name.endswith(".opf") for name in archive.namelist())


class TestF030TakingIsNotSharing:
    """The hazard the second door exists for, written as a test because it is
    the kind of thing that would otherwise be found by a reader."""

    def _context(self, tmp_path):
        from epubforge.model import Book, Resource
        from epubforge.report import Report

        book = Book()
        page = (
            b'<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
            b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
            b"<body><p>Ten sam tekst.</p></body></html>"
        )
        for path in ("a.xhtml", "b.xhtml"):
            book.add(Resource(path=path, media_type="application/xhtml+xml", data=page))
        return Context(book=book, policy=Policy.preset("preserve"), report=Report())

    def test_two_identical_documents_share_a_read(self, tmp_path):
        ctx = self._context(tmp_path)
        first = ctx.parsed(ctx.book.resources["a.xhtml"])
        second = ctx.parsed(ctx.book.resources["b.xhtml"])
        assert first is second, "identical bytes, one parse — that is the saving"

    def test_but_never_share_an_edit(self, tmp_path):
        """Byte-identical documents are real: two blank pages, two colophons.
        Handing the second one the first one's edited tree is one document
        overwriting another, silently."""
        ctx = self._context(tmp_path)
        taken = ctx.take(ctx.book.resources["a.xhtml"])
        marker = taken.root.find(".//{http://www.w3.org/1999/xhtml}p")
        marker.text = "Zmienione w pierwszym dokumencie."
        second = ctx.parsed(ctx.book.resources["b.xhtml"])
        assert second is not taken
        assert "Zmienione" not in "".join(second.root.itertext())

    def test_taking_a_document_nobody_read_still_works(self, tmp_path):
        ctx = self._context(tmp_path)
        assert ctx.take(ctx.book.resources["a.xhtml"]).root is not None
