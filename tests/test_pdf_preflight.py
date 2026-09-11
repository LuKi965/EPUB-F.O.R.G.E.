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
from tests.test_pdf import THREE_PARAGRAPHS, column, make_pdf

pytest.importorskip("pdfminer.high_level")


def manual(tmp_path: pathlib.Path, pages: int = 5) -> pathlib.Path:
    return make_pdf(
        tmp_path / "manual.pdf", [column(THREE_PARAGRAPHS)] * pages,
        links={0: [(72, 690, 200, 712, 1)]}, outline=[("One", 0), ("Two", 1)],
    )


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
        assert tr("pdf.analysis.text.yes", sampled=3) in item.summary

    def test_a_refused_document_says_why_in_the_persons_language(self, tmp_path):
        from epubforge.gui.shell.models import BookStatus
        from epubforge.gui.shell.pdf_backend import PdfBackend
        from epubforge.gui.strings import tr

        junk = tmp_path / "junk.pdf"
        junk.write_bytes(b"not a pdf at all")
        (item,) = PdfBackend("pl").analyse([junk])
        assert item.status is BookStatus.FAILED
        assert item.error.startswith(tr("pdf.analysis.unreadable", detail="").rstrip())
