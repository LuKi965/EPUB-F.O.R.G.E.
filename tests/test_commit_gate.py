"""F-006, second half — what has to be true before a book becomes a file.

0.2.20 closed the read side: a source that cannot be read in full stops the
rebuild before any stage runs. The write side had nothing. The archive verifier
reads entry order, the mimetype and CRCs — properties of a *ZIP* — and had no
opinion about whether the *book* made sense, so a spine entry naming a document
that no longer exists produced a technically perfect archive, published
atomically.

The audit put it plainly: *a stage repairs part of a book but leaves a dangling
manifest fallback or a missing spine target; the ZIP is valid, so it is
published.* These tests are that sentence, one fixture at a time.

**What is deliberately not fatal** is worth as much as what is. A dangling link
*inside a content document* is usually the source's own, `preserve` keeps it on
purpose, and the report says so by name. Making it fatal would refuse a large
fraction of real books for a defect they arrived with — the failure mode of the
read-side gate's first draft, repeated. The last class here pins that line.
"""

from __future__ import annotations

import pytest

from epubforge import invariants
from epubforge.model import Book, Landmark, NavPoint, Resource, SpineItem
from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy

from .factory import make_modern_epub


def book_with(*resources: str) -> Book:
    """A model in the shape the invariants see, after every stage has run."""
    book = Book()
    for path in resources:
        book.add(Resource(path=path, media_type="application/xhtml+xml", data=b"<html/>"))
    book.spine = [SpineItem(path) for path in resources]
    return book


class TestTheReadingOrder:
    def test_a_spine_entry_naming_a_document_that_is_gone_is_fatal(self):
        book = book_with("a.xhtml")
        book.spine.append(SpineItem("removed.xhtml"))
        broken = invariants.check(book)
        assert [v.rule for v in broken] == ["invariant.spine-target-missing"]
        assert "removed.xhtml" in str(broken[0])

    def test_the_same_document_twice_in_the_reading_order_is_fatal(self):
        """A reading system paginates it twice and one page has two positions."""
        book = book_with("a.xhtml")
        book.spine.append(SpineItem("a.xhtml"))
        assert [v.rule for v in invariants.check(book)] == ["invariant.spine-duplicated"]

    def test_an_empty_reading_order_is_fatal(self):
        book = book_with()
        assert "invariant.spine-empty" in {v.rule for v in invariants.check(book)}

    def test_an_ordinary_reading_order_passes(self):
        assert invariants.check(book_with("a.xhtml", "b.xhtml")) == []


class TestTheNavigation:
    def test_a_contents_entry_leading_nowhere_is_fatal(self):
        """Generated rather than carried, which is what makes it ours to be
        right about — and it is the defect a reader meets first."""
        book = book_with("a.xhtml")
        book.toc = [NavPoint(label="Gone", target="gone.xhtml")]
        assert [v.rule for v in invariants.check(book)] == ["invariant.nav-target-missing"]

    def test_a_landmark_leading_nowhere_is_fatal(self):
        book = book_with("a.xhtml")
        book.landmarks = [Landmark("bodymatter", "Start", "gone.xhtml#x")]
        assert [v.rule for v in invariants.check(book)] == ["invariant.landmark-target-missing"]

    def test_a_navigation_document_that_is_not_in_the_book_is_fatal(self):
        book = book_with("a.xhtml")
        book.nav_path = "nav.xhtml"
        assert [v.rule for v in invariants.check(book)] == ["invariant.nav-missing"]

    def test_a_fragment_on_a_target_that_exists_is_fine(self):
        book = book_with("a.xhtml")
        book.toc = [NavPoint(label="Chapter", target="a.xhtml#middle")]
        assert invariants.check(book) == []


class TestFallbacks:
    def test_a_fallback_to_nothing_is_fatal(self):
        book = book_with("a.xhtml")
        book.resources["a.xhtml"].fallback = "gone.xhtml"
        assert [v.rule for v in invariants.check(book)] == ["invariant.fallback-missing"]

    def test_a_fallback_cycle_is_fatal(self):
        """`a` falls back to `b` and `b` to `a` is a manifest a reading system
        follows until it stops being a reading system."""
        book = book_with("a.xhtml", "b.xhtml")
        book.resources["a.xhtml"].fallback = "b.xhtml"
        book.resources["b.xhtml"].fallback = "a.xhtml"
        assert "invariant.fallback-cycle" in {v.rule for v in invariants.check(book)}

    def test_a_chain_that_ends_somewhere_real_is_fine(self):
        book = book_with("a.xhtml", "b.xhtml", "c.xhtml")
        book.resources["a.xhtml"].fallback = "b.xhtml"
        book.resources["b.xhtml"].fallback = "c.xhtml"
        assert invariants.check(book) == []


class TestTheGateItself:
    """The invariants are one thing; refusing to publish is the other, and the
    audit's finding is about the second."""

    def test_nothing_reaches_the_disk(self, tmp_path, monkeypatch):
        source = make_modern_epub(str(tmp_path / "in.epub"), title="T")
        out = tmp_path / "out.epub"

        def wreck(book):
            book.spine.append(SpineItem("nie-ma-mnie.xhtml"))
            return original(book)

        original = invariants.check
        monkeypatch.setattr(
            "epubforge.pipeline.invariants.check",
            lambda book: wreck(book),
        )
        result = rebuild(source, str(out), Policy.preset("preserve"))
        assert result.status is Status.BLOCKED
        assert result.output_path is None
        assert not out.exists()

    def test_the_report_says_which_thing_was_untrue(self, tmp_path, monkeypatch):
        source = make_modern_epub(str(tmp_path / "in.epub"), title="T")
        monkeypatch.setattr(
            "epubforge.pipeline.invariants.check",
            lambda book: [invariants.Violation("invariant.spine-target-missing",
                                               "the reading order names nie-ma-mnie.xhtml")],
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        finding = next(
            f for f in result.report.findings if f.rule == "package.invariant-failed"
        )
        assert "nie-ma-mnie.xhtml" in finding.values["detail"]

    @pytest.mark.parametrize("preset", ["preserve", "strict", "minimal"])
    def test_an_ordinary_book_is_not_refused_by_any_of_this(self, tmp_path, preset):
        source = make_modern_epub(str(tmp_path / "in.epub"), title="T")
        result = rebuild(source, str(tmp_path / f"out-{preset}.epub"), Policy.preset(preset))
        assert result.status is Status.SUCCEEDED, result.report.to_text()


class TestWhatIsDeliberatelyNotFatal:
    """The line, drawn on purpose and pinned so it cannot drift.

    Everything the rebuild is responsible for must be true. Everything the book
    arrived with is reported rather than refused.
    """

    def test_a_dead_link_inside_a_document_does_not_refuse_the_book(self, tmp_path):
        """`preserve` keeps it and says so. Refusing here would turn a defect
        the book walked in with into a book nobody can rebuild."""
        import zipfile

        source = make_modern_epub(str(tmp_path / "in.epub"), title="T")
        with zipfile.ZipFile(source) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        chapter = next(n for n in entries if n.endswith(".xhtml") and "nav" not in n)
        entries[chapter] = entries[chapter].replace(
            b"</body>", b'<p><a href="nie-ma.xhtml">tam</a></p></body>')

        broken = tmp_path / "broken.epub"
        with zipfile.ZipFile(broken, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            for name, data in entries.items():
                if name != "mimetype":
                    archive.writestr(name, data)

        result = rebuild(str(broken), str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status.wrote_a_file
        assert "xhtml.dead-reference-kept" in {f.rule for f in result.report.findings if f.rule}
