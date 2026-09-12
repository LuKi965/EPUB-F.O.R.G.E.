"""A10 of the 0.4.4 recovery audit: the converter's analysis read the file's
size and called the "reading" step done. The preflight now measures what a
person decides on before converting — pages, a text layer on a sample of
pages, encryption, the renderer, links and bookmarks — and the window's row
says those numbers rather than "not checked" beside a finished step.
"""

from __future__ import annotations

import pathlib

import pytest

from epubforge.pdfconv import draw, service
from tests.test_pdf import THREE_PARAGRAPHS, _spiral, column, make_pdf

pytest.importorskip("pdfminer.high_level")


def manual(tmp_path: pathlib.Path, pages: int = 5) -> pathlib.Path:
    return make_pdf(
        tmp_path / "manual.pdf", [column(THREE_PARAGRAPHS)] * pages,
        links={0: [(72, 690, 200, 712, 1)]}, outline=[("One", 0), ("Two", 1)],
    )


def plain_manual(tmp_path: pathlib.Path, pages: int = 5) -> pathlib.Path:
    """Prose that differs from page to page: nothing repeats in a margin,
    nothing stands in columns, nothing is drawn."""
    return make_pdf(
        tmp_path / "plain.pdf",
        [column([f"Page {number} opens with its own first sentence."] + THREE_PARAGRAPHS[1:], top=650)
         for number in range(pages)],
    )


def complex_manual(tmp_path: pathlib.Path, pages: int = 5) -> pathlib.Path:
    """The shapes the conversion has to decide about, on every page: a running
    head and a page number in the margins, two columns of prose, a vector
    drawing on the first page and a grid of cells on the second."""
    left = ["Left column line one of the page,", "left column line two,", "left column line three,",
            "left column line four,", "left column line five,", "left column line six."]
    right = ["Right column line one of the page,", "right column line two,", "right column line three,",
             "right column line four,", "right column line five,", "right column line six."]
    sheets = []
    for number in range(1, pages + 1):
        lines = [(72, 760, 10.0, "THE COMPLEX MANUAL")]
        if number == 2:
            # The grid page: the same shape `test_a_grid_of_cells_comes_back_a_table`
            # reads as a table, between two lines of prose, in one column.
            lines += column(["A sentence of prose standing over the table."], top=700)
            for index, (name, hot, cold) in enumerate(
                (("Americano", "tak", "tak"), ("Cappuccino", "tak", "nie"), ("Cold Brew", "nie", "tak"))
            ):
                y = 660.0 - index * 16
                lines += [(72.0, y, 10.0, name), (220.0, y, 10.0, hot), (300.0, y, 10.0, cold)]
            lines += column(["And a sentence of prose standing under it."], top=580)
        else:
            lines += column(left, top=650, left=72)
            lines += column(right, top=650, left=320)
        lines += [(300, 30, 10.0, str(number))]
        sheets.append(lines)
    # The drawing: strokes piled on one another, the way artwork is drawn,
    # standing under the columns of the first page.
    return make_pdf(tmp_path / "complex.pdf", sheets, strokes={0: _spiral(150, 250, 60)})


class TestThePreflightMeasuresTheFile:
    def test_pages_text_links_and_bookmarks_are_the_files_own(self, tmp_path):
        info = service.look_at(manual(tmp_path))
        assert info.pages == 5
        assert info.has_text is True and info.checked
        assert info.sampled_pages == service.PREFLIGHT_PAGES
        assert info.characters > 0
        assert info.links == 1
        assert info.outline_entries == 2
        assert info.encrypted is False
        assert info.renderer == draw.available()
        assert not info.refusal

    def test_a_scan_is_refused_as_needing_ocr_not_converted_to_nothing(self, tmp_path):
        """Pages that draw no text: `has_text` is measured `False`, which is
        the one fact this program will not guess, and the refusal says OCR."""
        from tests.factory import png_bytes  # noqa: F401 — the fixture below draws its own pixels

        blank = make_pdf(tmp_path / "scan.pdf", [[], []],
                         images={0: [(72, 400, 400, 300, 4, 3, bytes((90, 90, 90)) * 12)]})
        info = service.look_at(blank)
        assert info.pages == 2
        assert info.has_text is False and info.needs_ocr
        assert info.refusal_code == "no-text"

    def test_a_file_that_is_not_a_pdf_is_refused_and_nothing_is_guessed(self, tmp_path):
        junk = tmp_path / "junk.pdf"
        junk.write_bytes(b"%PDF-1.4 not really a document")
        info = service.look_at(junk)
        assert info.refusal_code == "unreadable" and info.refusal
        assert info.has_text is None and not info.checked
        assert info.pages == 0

    def test_a_missing_file_is_refused_before_anything_is_read(self, tmp_path):
        info = service.look_at(tmp_path / "missing.pdf")
        assert info.refusal_code == "not-a-file"
        assert info.has_text is None

    def test_the_sample_is_a_budget_and_a_short_file_is_read_whole(self, tmp_path):
        info = service.look_at(manual(tmp_path, pages=2))
        assert info.pages == 2 and info.sampled_pages == 2


class TestThePreflightMeasuresTheSample:
    """W10 pt 2 of the 0.4.4 recovery plan: *the plan holds real candidates*.

    The preflight reads its sample of pages the way the conversion reads a
    page — the reader's own scan, running-head detector, column test and
    grids — and counts what the conversion will meet. Four pages rather than
    three, because the head detector says nothing below four.
    """

    def test_columns_drawings_tables_and_running_heads_are_counted(self, tmp_path):
        info = service.look_at(complex_manual(tmp_path))
        assert info.sampled_pages == service.PREFLIGHT_PAGES == 4
        # Every sampled page — the grid page too: three cells across three
        # rows are two stacks of left edges to the reader's own column test,
        # which is the test the conversion applies (the cut then keeps the
        # grid whole, `_regions`). The preflight counts what the reader counts.
        assert info.columns_pages == 4, info
        assert info.drawings == 1, info
        assert info.tables == 1, info
        assert info.running_heads == 8 and info.running_head_pages == 4, info
        assert info.pictures == 0

    def test_plain_prose_counts_nothing(self, tmp_path):
        info = service.look_at(plain_manual(tmp_path))
        assert info.has_text
        assert (info.columns_pages, info.drawings, info.tables, info.pictures) == (0, 0, 0, 0)
        assert info.running_heads == 0 and info.running_head_pages == 0

    def test_the_sample_is_counted_by_the_readers_own_functions(self, tmp_path):
        """The same file through the reader itself: what the conversion's
        layout says about the first four pages is what the sample said."""
        from epubforge.pdfconv import reader
        from epubforge.report import Report

        source = complex_manual(tmp_path, pages=4)
        sample = reader.sample_layout(str(source), 4)
        report = Report()
        reader.read_pdf(str(source), report)
        layout = report.stats["pdf_layout"]
        assert sample.column_pages == layout["column_pages"]
        assert sample.running_heads == layout["running_heads"]
        assert sample.drawings == layout["drawings_detected"]


class TestTheRowSaysWhatWasMeasured:
    """The adapter, without Qt: the row's line carries the numbers."""

    def test_a_measured_document_says_its_numbers(self, tmp_path):
        from epubforge.gui.shell.models import BookStatus
        from epubforge.gui.shell.pdf_backend import PdfBackend
        from epubforge.gui.strings import tr

        (item,) = PdfBackend("pl").analyse([manual(tmp_path)])
        assert item.status is BookStatus.READY
        assert item.summary != tr("pdf.analysis.unchecked")
        assert "5 stron" in item.summary and "1 odsyłacz" in item.summary
        assert tr("pdf.analysis.text.yes", sampled=service.PREFLIGHT_PAGES) in item.summary

    def test_the_row_says_what_the_sample_looks_like_and_the_plan_has_candidates(self, tmp_path):
        from epubforge.gui.shell.pdf_backend import PdfBackend
        from epubforge.gui.strings import tr

        (item,) = PdfBackend("pl").analyse([complex_manual(tmp_path)])
        assert "w kolumnach" in item.summary and "pagina na 4 z 4" in item.summary, item.summary
        assert tr("pdf.candidate.heads", pages=4, sampled=4) in item.candidates
        assert tr("pdf.candidate.columns", pages=4, sampled=4) in item.candidates
        assert tr("pdf.candidate.tables", count=1) in item.candidates
        key = "pdf.candidate.drawings" if draw.available() else "pdf.candidate.drawings.no-renderer"
        assert tr(key, count=1) in item.candidates, item.candidates
        (plain,) = PdfBackend("pl").analyse([plain_manual(tmp_path)])
        assert plain.candidates == ()

    def test_a_refused_document_says_why_in_the_persons_language(self, tmp_path):
        from epubforge.gui.shell.models import BookStatus
        from epubforge.gui.shell.pdf_backend import PdfBackend
        from epubforge.gui.strings import tr

        junk = tmp_path / "junk.pdf"
        junk.write_bytes(b"not a pdf at all")
        (item,) = PdfBackend("pl").analyse([junk])
        assert item.status is BookStatus.FAILED
        assert item.error.startswith(tr("pdf.analysis.unreadable", detail="").rstrip())
