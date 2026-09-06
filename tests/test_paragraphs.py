"""Runs of empty paragraphs behind `empty_paragraph_runs` (D-054, DROGA 3.4).

Measured on the owner's shelf before a line of this was written: 20 213
empty paragraphs in 102 books. A single one between two paragraphs of text
is a break between scenes and is nobody's business; two or more in a row,
one at a document edge, one beside a heading is a converter carrying
somebody's page pushing. The default leaves everything and counts; `ask`
puts one question per book with the neighbourhood shown; `remove` is the
standing answer for a batch — and it leaves one blank line of a run
between paragraphs, so a break stays a break.
"""

from __future__ import annotations

import os
import pathlib
import zipfile

import pytest

from epubforge import fidelity, render, render_fidelity, xhtml
from epubforge.cli import main
from epubforge.decisions import KEEP, Answer
from epubforge.pipeline import rebuild
from epubforge.policy import EMPTY_PARAGRAPH_RUNS, Policy
from epubforge.stages import paragraphs
from tests.factory import MODERN_NAV, write_zip
from tests.test_hyphen_stage import CONTAINER, PACKAGE


def book(path, body: str) -> str:
    page = (
        '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
        f'<meta charset="utf-8"/><title>Rozdział</title></head><body>{body}</body></html>'
    )
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": PACKAGE.encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": page.encode(),
        },
    )


EMPTY = "<p></p>"
NBSP = "<p> </p>"

#: Every shape at once: an edge run, a run beside a heading, a run of three
#: between paragraphs, a single break between paragraphs, and an edge run at
#: the end.
EVERY_SHAPE = (
    EMPTY * 3
    + "<h1>Rozdział pierwszy</h1>"
    + EMPTY * 2
    + "<p>Pierwszy akapit tekstu, dość długi, żeby było co pokazać w podglądzie.</p>"
    + EMPTY * 3
    + "<p>Drugi akapit po przepchnięciu.</p>"
    + EMPTY
    + "<p>Trzeci akapit po przerwie między scenami.</p>"
    + NBSP * 4
)


class Recorder:
    def __init__(self):
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return None


class Removes:
    def ask(self, question):
        return Answer(option="remove")


def rebuilt(source, tmp_path, *, asker=None, standing=None, **policy):
    return rebuild(
        source, str(tmp_path / "out.epub"),
        Policy.preset("preserve", validate_before_publish="off", render_gate="off", **policy),
        asker=asker, standing=standing,
    )


def chapter_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("chapter.xhtml"))
        return archive.read(name).decode("utf-8")


def rules_of(result) -> set:
    return {f.rule for f in result.report.findings if f.rule}


def empties_in(document: str) -> int:
    root, _ = xhtml.parse(document.encode("utf-8"))
    return sum(1 for e in xhtml.iter_elements(root) if paragraphs.is_empty(e))


class TestWhatIsCountedAndWhatIsNot:
    def test_a_single_blank_line_between_paragraphs_is_a_break_not_a_run(self):
        root, _ = xhtml.parse(book_body("<p>a</p><p></p><p>b</p>"))
        found = paragraphs.find_runs(root)
        assert found.runs == [] and found.breaks == 1

    def test_the_shapes_from_the_measurement(self):
        root, _ = xhtml.parse(book_body(EVERY_SHAPE))
        found = paragraphs.find_runs(root)
        assert [run.shape for run in found.runs] == ["edge", "heading", "between", "edge"]
        assert [len(run.paragraphs) for run in found.runs] == [3, 2, 3, 4]
        assert found.breaks == 1
        assert found.pieces == 12
        # All of an edge or heading run; all but one of a run between text.
        assert found.removable == 3 + 2 + 2 + 4

    def test_a_paragraph_with_a_picture_is_not_empty(self):
        root, _ = xhtml.parse(book_body('<p><img src="a.png" alt=""/></p><p></p><p></p><p>x</p>'))
        found = paragraphs.find_runs(root)
        assert [len(run.paragraphs) for run in found.runs] == [2]
        assert found.runs[0].before is not None  # the picture paragraph stands before it

    def test_a_no_break_space_is_still_empty(self):
        root, _ = xhtml.parse(book_body("<p>a</p><p> </p><p>   </p><p>b</p>"))
        assert paragraphs.find_runs(root).removable == 1

    def test_runs_inside_a_div_are_read_in_their_own_sequence(self):
        root, _ = xhtml.parse(book_body("<div><p></p><p></p><p>a</p></div><p>b</p>"))
        found = paragraphs.find_runs(root)
        assert [run.shape for run in found.runs] == ["edge"]

    def test_the_preview_shows_the_neighbourhood(self):
        root, _ = xhtml.parse(book_body(EVERY_SHAPE))
        found = paragraphs.find_runs(root)
        shown = paragraphs.preview(found.runs[2])
        assert "w podglądzie." in shown and "[3 × pusty akapit]" in shown and "Drugi akapit" in shown
        assert paragraphs.preview(found.runs[0]).startswith("⟨początek⟩")


def book_body(body: str) -> bytes:
    return (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
        f"<body>{body}</body></html>"
    ).encode("utf-8")


class TestTheDefaultLeavesEverythingAndCounts:
    def test_keep_is_the_default(self):
        assert EMPTY_PARAGRAPH_RUNS == ("ask", "keep", "remove")
        assert Policy().empty_paragraph_runs == "keep"

    def test_nothing_moves_and_the_report_counts(self, tmp_path):
        recorder = Recorder()
        result = rebuilt(book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, asker=recorder)
        assert result.output_path
        assert empties_in(chapter_of(result)) == 13
        kept = next(f for f in result.report.findings if f.rule == "paragraphs.empty-runs-kept")
        assert kept.values == {"count": 12, "runs": 4, "breaks": 1}
        assert not [q for q in recorder.asked if q.group == "paragraphs:empty-runs"]

    def test_a_clean_book_says_nothing(self, tmp_path):
        result = rebuilt(book(tmp_path / "in.epub", "<p>a</p><p></p><p>b</p>"), tmp_path)
        assert not {r for r in rules_of(result) if r.startswith("paragraphs.")}


class TestAskingOncePerBook:
    def test_one_question_with_the_neighbourhood(self, tmp_path):
        recorder = Recorder()
        rebuilt(book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, asker=recorder, empty_paragraph_runs="ask")
        asked = [q for q in recorder.asked if q.group == "paragraphs:empty-runs"]
        assert len(asked) == 1
        question = asked[0]
        assert "12" in question.summary
        assert "[3 × pusty akapit]" in question.detail
        assert "Drugi akapit" in question.detail
        assert [o.id for o in question.options] == [KEEP, "remove"]
        assert question.recommended == "remove"
        assert not question.reversible

    def test_no_answer_changes_nothing_and_says_so(self, tmp_path):
        result = rebuilt(
            book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, asker=Recorder(), empty_paragraph_runs="ask",
        )
        assert empties_in(chapter_of(result)) == 13
        assert "paragraphs.empty-runs-unanswered" in rules_of(result)
        assert "paragraphs.empty-runs-removed" not in rules_of(result)

    def test_an_answer_of_remove_removes(self, tmp_path):
        result = rebuilt(
            book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, asker=Removes(), empty_paragraph_runs="ask",
        )
        assert "paragraphs.empty-runs-removed" in rules_of(result)
        assert empties_in(chapter_of(result)) == 2

    def test_a_standing_answer_settles_a_batch(self, tmp_path):
        result = rebuilt(
            book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, empty_paragraph_runs="ask",
            standing={"paragraphs:empty-runs": Answer(option="remove")},
        )
        assert "paragraphs.empty-runs-removed" in rules_of(result)


class TestRemoving:
    def test_a_break_stays_a_break_and_the_pushing_goes(self, tmp_path):
        result = rebuilt(book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, empty_paragraph_runs="remove")
        text = chapter_of(result)
        # One blank line of the run of three, the single break, nothing else.
        assert empties_in(text) == 2
        assert text.index("<h1") < text.index("Pierwszy akapit")
        root, _ = xhtml.parse(text.encode("utf-8"))
        blocks = [e for e in xhtml.iter_elements(root) if xhtml.local_name(e) in ("p", "h1")]
        assert [paragraphs.is_empty(e) for e in blocks] == [False, False, True, False, True, False]

    def test_the_text_is_the_same_to_the_character(self, tmp_path):
        source = book(tmp_path / "in.epub", EVERY_SHAPE)
        result = rebuilt(source, tmp_path, empty_paragraph_runs="remove")
        with zipfile.ZipFile(source) as archive:
            before = fidelity.document_text(archive.read("OEBPS/chapter.xhtml"))
        assert fidelity.document_text(chapter_of(result).encode("utf-8")) == before
        assert "package.text-lost" not in rules_of(result)
        assert "package.prose-changed" not in rules_of(result)

    def test_the_report_and_the_ledger_say_how_many(self, tmp_path):
        result = rebuilt(book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, empty_paragraph_runs="remove")
        removed = next(f for f in result.report.findings if f.rule == "paragraphs.empty-runs-removed")
        assert removed.values == {"count": 11, "documents": 1, "breaks": 1}
        entry = [c for c in result.report.changes if c.rule == "paragraphs.empty-runs-removed"]
        assert len(entry) == 1 and not entry[0].reversible
        assert result.report.stats["space_removed"] == {"EPUB/text/0000-chapter.xhtml": 11}

    def test_text_in_a_tail_is_not_lost(self, tmp_path):
        """A converter's empty paragraph with words after it, outside any
        element — the words are the book's and stay where they were read."""
        body = "<p>a</p><p></p><p></p>luźne słowa<p>b</p>"
        result = rebuilt(book(tmp_path / "in.epub", body), tmp_path, empty_paragraph_runs="remove")
        text = chapter_of(result)
        assert "luźne słowa" in text
        assert text.index("<p>a</p>") < text.index("luźne słowa") < text.index("<p>b</p>")

    def test_the_second_rebuild_finds_nothing_to_do(self, tmp_path):
        first = rebuilt(book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, empty_paragraph_runs="remove")
        second = rebuild(
            first.output_path, str(tmp_path / "again.epub"),
            Policy.preset("preserve", validate_before_publish="off", render_gate="off",
                          empty_paragraph_runs="remove"),
        )
        assert "paragraphs.empty-runs-removed" not in rules_of(second)
        assert chapter_of(second) == chapter_of(first)

    def test_the_single_break_is_never_touched_by_remove(self, tmp_path):
        result = rebuilt(book(tmp_path / "in.epub", "<p>a</p><p></p><p>b</p>"), tmp_path, empty_paragraph_runs="remove")
        assert empties_in(chapter_of(result)) == 1
        assert not {r for r in rules_of(result) if r.startswith("paragraphs.")}


class TestTheSettingIsReachableEverywhere:
    def test_the_flag(self, tmp_path):
        source = book(tmp_path / "in.epub", EVERY_SHAPE)
        out = tmp_path / "out"
        code = main([
            "build", source, "-o", str(out / "book.epub"), "--gate", "off", "--render-gate", "off",
            "--empty-paragraph-runs", "remove",
        ])
        assert code == 0
        written = list(out.glob("*.epub"))
        assert len(written) == 1
        with zipfile.ZipFile(written[0]) as archive:
            name = next(n for n in archive.namelist() if n.endswith("chapter.xhtml"))
            assert empties_in(archive.read(name).decode("utf-8")) == 2

    def test_the_window_offers_all_three_and_defaults_to_keep(self):
        pytest.importorskip("PySide6")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from epubforge.gui.app import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        try:
            combo = window.empty_runs_combo
            offered = [combo.itemData(i) for i in range(combo.count())]
            assert offered == list(EMPTY_PARAGRAPH_RUNS)
            assert combo.currentData() == "keep"
            for i in range(combo.count()):
                assert combo.itemData(i, Qt.ToolTipRole)
            combo.setCurrentIndex(offered.index("remove"))
            assert window._policy().empty_paragraph_runs == "remove"
        finally:
            window.close()
            app.processEvents()


# --------------------------------------------------------------------------
# The render gate on a document made shorter on purpose.

def _needs_a_browser():
    if not os.environ.get("EPUBFORGE_RENDER_TESTS") or render.find_renderer() is None:
        pytest.skip("set EPUBFORGE_RENDER_TESTS=1 and name a Chromium")


LONG_TEXT = (
    "<p>Zdanie, które ciągnie się przez wiersz i jeszcze kawałek, żeby akapit miał "
    "wysokość, a strona treść do zmierzenia tuszem. " * 4 + "</p>"
)


class TestTheRenderGateHoldsAShortenedDocumentToItsInk:
    """Removing sixty empty paragraphs from the top of a chapter moves every
    line up by more than a screen. Screen by screen that reads as the last
    screen going blank — a loss — and it is not one: the ink is all there,
    a screen higher. The gate is told which documents were shortened on
    somebody's word and holds those to their ink."""

    @pytest.mark.renders
    def test_the_removal_passes_the_full_gate(self, tmp_path):
        _needs_a_browser()
        body = EMPTY * 60 + LONG_TEXT * 12
        result = rebuild(
            book(tmp_path / "in.epub", body), str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off", render_gate="stop",
                          render_sample=0, empty_paragraph_runs="remove"),
        )
        assert result.output_path, result.report.to_text()
        rules = rules_of(result)
        assert "paragraphs.empty-runs-removed" in rules
        assert "render.page-lost-content" not in rules
        assert "render.checked-whole" in rules

    @pytest.mark.renders
    def test_a_real_loss_in_a_shortened_document_is_still_a_loss(self, tmp_path):
        """The allowance is by ink, not by name: a shortened document that
        also lost a third of its text fails on the sum."""
        _needs_a_browser()
        source = pathlib.Path(book(tmp_path / "a.epub", EMPTY * 60 + LONG_TEXT * 12))
        shorter = pathlib.Path(book(tmp_path / "b.epub", LONG_TEXT * 12))
        lost = pathlib.Path(book(tmp_path / "c.epub", LONG_TEXT * 7))
        name = "OEBPS/chapter.xhtml"
        fine = render_fidelity.compare(source, shorter, sample=0, shortened={name})
        assert fine.ok, [str(p) for p in fine.pages if p.problems]
        assert any("sądzony po tuszu" in note for page in fine.pages for note in page.notes)
        bad = render_fidelity.compare(source, lost, sample=0, shortened={name})
        assert not bad.ok
        assert any("stracił treść" in problem for page in bad.pages for problem in page.problems)
