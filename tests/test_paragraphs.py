"""Runs of empty paragraphs behind `empty_paragraph_runs` (D-054, DROGA 3.4).

Measured on the owner's shelf before a line of this was written: 20 213
empty paragraphs in 102 books. A single one between two paragraphs of text
is a break between scenes and is nobody's business; two or more in a row,
one at a document edge, one beside a heading is a converter carrying
somebody's page pushing. The default leaves everything and counts; `ask`
puts one question per book with the neighbourhood shown; `remove` is the
standing answer for a batch — and what it takes is `KEEP_HEIGHT`: a run of
up to three between paragraphs keeps its height, a taller one comes down to
one blank line, and an edge or heading run goes whole.
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

#: Every shape at once, and both sides of `KEEP_HEIGHT`: an edge run, a run
#: beside a heading, a caesura of three between paragraphs (kept), a single
#: break (never in question), a run of five between paragraphs (down to one)
#: and an edge run at the end.
EVERY_SHAPE = (
    EMPTY * 3
    + "<h1>Rozdział pierwszy</h1>"
    + EMPTY * 2
    + "<p>Pierwszy akapit tekstu, dość długi, żeby było co pokazać w podglądzie.</p>"
    + EMPTY * 3
    + "<p>Drugi akapit po cezurze trzech linii.</p>"
    + EMPTY
    + "<p>Trzeci akapit po przerwie między scenami.</p>"
    + EMPTY * 5
    + "<p>Czwarty akapit po przepchnięciu na nową stronę.</p>"
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
        assert [run.shape for run in found.runs] == [
            "edge", "heading", "between", "between", "edge",
        ]
        assert [len(run.paragraphs) for run in found.runs] == [3, 2, 3, 5, 4]
        assert found.breaks == 1
        assert found.pieces == 17
        # All of an edge or heading run; nothing from a caesura of three;
        # all but one of the run of five.
        assert found.removable == 3 + 2 + 0 + 4 + 4

    def test_a_paragraph_with_a_picture_is_not_empty(self):
        root, _ = xhtml.parse(book_body('<p><img src="a.png" alt=""/></p><p></p><p></p><p>x</p>'))
        found = paragraphs.find_runs(root)
        assert [len(run.paragraphs) for run in found.runs] == [2]
        assert found.runs[0].before is not None  # the picture paragraph stands before it

    def test_a_no_break_space_is_still_empty(self):
        """A converter writes `&#160;` where somebody pressed Enter twice;
        it draws nothing, so the paragraph is empty and the two of them are
        a run — a caesura of two, which keeps its height."""
        root, _ = xhtml.parse(book_body("<p>a</p><p> </p><p>   </p><p>b</p>"))
        found = paragraphs.find_runs(root)
        assert [len(run.paragraphs) for run in found.runs] == [2]
        assert found.pieces == 2

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
        assert empties_in(chapter_of(result)) == 18
        kept = next(f for f in result.report.findings if f.rule == "paragraphs.empty-runs-kept")
        assert kept.values == {
            "count": 17, "runs": 5, "breaks": 1, "removable": 13, "height": 3,
        }
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
        assert "17" in question.summary
        assert "[3 × pusty akapit]" in question.detail
        assert "Drugi akapit" in question.detail
        # What an answer of "remove" would actually take, and the boundary.
        assert "zabierze z nich 13" in question.detail
        assert "ciąg do 3 pustych linii między akapitami zachowuje" in question.detail
        assert [o.id for o in question.options] == [KEEP, "remove"]
        assert question.recommended == "remove"
        assert not question.reversible

    def test_no_answer_changes_nothing_and_says_so(self, tmp_path):
        result = rebuilt(
            book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, asker=Recorder(), empty_paragraph_runs="ask",
        )
        assert empties_in(chapter_of(result)) == 18
        assert "paragraphs.empty-runs-unanswered" in rules_of(result)
        assert "paragraphs.empty-runs-removed" not in rules_of(result)

    def test_an_answer_of_remove_removes(self, tmp_path):
        result = rebuilt(
            book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, asker=Removes(), empty_paragraph_runs="ask",
        )
        assert "paragraphs.empty-runs-removed" in rules_of(result)
        assert empties_in(chapter_of(result)) == 5

    def test_a_standing_answer_settles_a_batch(self, tmp_path):
        result = rebuilt(
            book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, empty_paragraph_runs="ask",
            standing={"paragraphs:empty-runs": Answer(option="remove")},
        )
        assert "paragraphs.empty-runs-removed" in rules_of(result)


class TestRemoving:
    @pytest.mark.parametrize(
        "height, stays",
        [(2, 2), (3, 3), (4, 1), (9, 1), (53, 1)],
        ids=["dwie-zostaja-dwiema", "trzy-zostaja-trzema", "cztery", "dziewiec", "piecdziesiat-trzy"],
    )
    def test_a_caesura_keeps_its_height_and_a_pushed_run_comes_down(self, tmp_path, height, stays):
        """Both sides of `KEEP_HEIGHT`, and the owner's own words for the
        near side: *„przy `remove` przerwy liczone tak, żeby dwie puste
        linie zostały dwiema"*. A run of two or three in mid-chapter may be
        a caesura somebody set — a jump in time, the edge of a part — and
        bringing it down to one would make it look like an ordinary scene
        break. A run of dozens is a page pushed in a word processor (one on
        the owner's shelf is 53 high), and that comes down to one."""
        body = "<p>Koniec sceny.</p>" + EMPTY * height + "<p>Początek następnej.</p>"
        result = rebuilt(book(tmp_path / "in.epub", body), tmp_path, empty_paragraph_runs="remove")
        assert empties_in(chapter_of(result)) == stays

    def test_a_break_stays_a_break_and_the_pushing_goes(self, tmp_path):
        result = rebuilt(book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, empty_paragraph_runs="remove")
        text = chapter_of(result)
        # The caesura of three, the single break, and one blank line left of
        # the run of five — nothing else.
        assert empties_in(text) == 5
        assert text.index("<h1") < text.index("Pierwszy akapit")
        root, _ = xhtml.parse(text.encode("utf-8"))
        blocks = [e for e in xhtml.iter_elements(root) if xhtml.local_name(e) in ("p", "h1")]
        assert [paragraphs.is_empty(e) for e in blocks] == [
            False,              # <h1>
            False,              # pierwszy akapit
            True, True, True,   # cezura trzech linii, nietknięta
            False,              # drugi akapit
            True,               # pojedyncza przerwa między scenami
            False,              # trzeci akapit
            True,               # to, co zostało z ciągu pięciu
            False,              # czwarty akapit
        ]

    def test_the_text_is_the_same_to_the_character(self, tmp_path):
        source = book(tmp_path / "in.epub", EVERY_SHAPE)
        result = rebuilt(source, tmp_path, empty_paragraph_runs="remove")
        with zipfile.ZipFile(source) as archive:
            before = fidelity.document_text(archive.read("OEBPS/chapter.xhtml"))
        assert fidelity.document_text(chapter_of(result).encode("utf-8")) == before
        assert "package.text-lost" not in rules_of(result)
        assert "package.prose-changed" not in rules_of(result)

    def test_the_report_says_how_many_runs_and_from_how_many_to_how_many(self, tmp_path):
        """The owner's rule for this entry: numbers, not the bare fact.
        A visible change made on somebody's word has to be nameable (K6),
        and "a run of fifty-three came down to one" is a different fact
        from "181 paragraphs were removed"."""
        result = rebuilt(book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, empty_paragraph_runs="remove")
        removed = next(f for f in result.report.findings if f.rule == "paragraphs.empty-runs-removed")
        assert removed.values == {
            "count": 13, "documents": 1, "breaks": 1,
            # The run of five came down to one; the two edge runs and the one
            # beside the heading went whole; the caesura of three was left.
            "shortened": 1, "longest": 5, "left": 1, "dropped": 3, "untouched": 1,
        }
        assert "1 run(s) between paragraphs were shortened" in removed.message
        assert "from 5 to 1" in removed.message
        assert "1 were left at their height" in removed.message

    def test_the_ledger_carries_the_same_numbers(self, tmp_path):
        result = rebuilt(book(tmp_path / "in.epub", EVERY_SHAPE), tmp_path, empty_paragraph_runs="remove")
        entry = [c for c in result.report.changes if c.rule == "paragraphs.empty-runs-removed"]
        assert len(entry) == 1 and not entry[0].reversible
        assert "najdłuższy 5" in entry[0].before and "3 na brzegu" in entry[0].before
        assert "→ 1 pusta linia" in entry[0].after
        assert "1 ciąg(ów) zostawionych bez zmiany wysokości" in entry[0].after
        assert result.report.stats["space_removed"] == {"EPUB/text/0000-chapter.xhtml": 13}

    def test_the_tallest_run_is_named_even_among_many(self, tmp_path):
        """One book on the owner's shelf holds a run of fifty-three. The
        entry names the tallest that was shortened, not the average."""
        body = (
            "<p>a</p>" + EMPTY * 2 + "<p>b</p>" + EMPTY * 9 + "<p>c</p>"
            + EMPTY * 4 + "<p>d</p>"
        )
        result = rebuilt(book(tmp_path / "in.epub", body), tmp_path, empty_paragraph_runs="remove")
        removed = next(f for f in result.report.findings if f.rule == "paragraphs.empty-runs-removed")
        # The nine and the four came down to one each; the caesura of two was
        # left where it stood.
        assert removed.values["shortened"] == 2
        assert removed.values["longest"] == 9
        assert removed.values["left"] == 1
        assert removed.values["untouched"] == 1
        assert removed.values["dropped"] == 0

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
            assert empties_in(archive.read(name).decode("utf-8")) == 5

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
