"""A06 of the 0.4.4 recovery audit: the appearance gate for a book that came
out of a PDF measured only that the pages drew *something*. For a fixed book
every page has a source page to compare with, and it is now compared — the
source drawn by PDFium, the book by the browser, ink counted per block — with
a limit measured on faithful and damaged pages rather than chosen.

The unit tests need no browser; the gate tests run on the pinned engine, as
every render test does.
"""

from __future__ import annotations

import io
import os
import re

import pytest
from PIL import Image

from epubforge import render
from epubforge.pdfconv import draw, gate
from epubforge.report import FAILED, PASSED, Report
from tests.test_pdf import THREE_PARAGRAPHS, column, make_pdf, rebuilt

pytest.importorskip("pdfminer.high_level")

engine = pytest.mark.renders


def _needs_the_engines():
    if os.environ.get("EPUBFORGE_RENDER_TESTS") != "1" or render.find_renderer() is None:
        pytest.skip("set EPUBFORGE_RENDER_TESTS=1 and name a Chromium")
    if not draw.available():
        pytest.skip("pypdfium2 is not installed")


class TestTheInkArithmetic:
    def test_the_same_image_loses_nothing(self):
        image = Image.new("L", (240, 320), 255)
        for y in range(40, 60):
            for x in range(20, 200):
                image.putpixel((x, y), 0)
        blocks = gate.ink_blocks(image)
        assert gate.missing_share(blocks, blocks) == 0.0

    def test_ink_the_output_lacks_is_counted_against_the_source(self):
        source = Image.new("L", (240, 320), 255)
        for y in range(40, 60):
            for x in range(20, 200):
                source.putpixel((x, y), 0)
        blank = Image.new("L", (240, 320), 255)
        assert gate.missing_share(gate.ink_blocks(source), gate.ink_blocks(blank)) == pytest.approx(1.0)

    def test_ink_the_output_adds_is_not_a_loss(self):
        """A heavier face is not missing ink."""
        source = Image.new("L", (240, 320), 255)
        heavier = Image.new("L", (240, 320), 255)
        for y in range(40, 60):
            for x in range(20, 200):
                source.putpixel((x, y), 0)
                heavier.putpixel((x, y), 0)
                heavier.putpixel((x, y + 40), 0)
        assert gate.missing_share(gate.ink_blocks(source), gate.ink_blocks(heavier)) == 0.0

    def test_a_blank_source_has_nothing_to_lose(self):
        blank = gate.ink_blocks(Image.new("L", (240, 320), 255))
        assert gate.missing_share(blank, blank) == 0.0


class TestOnlyAFixedBookIsCompared:
    def test_a_reflowable_book_is_not_paired_with_pages(self, tmp_path):
        source = make_pdf(tmp_path / "one.pdf", [column(THREE_PARAGRAPHS)])
        result = rebuilt(source, tmp_path)
        assert result.output_path
        assert not gate._fixed_layout(result.output_path)

    def test_a_fixed_book_is(self, tmp_path):
        source = make_pdf(tmp_path / "one.pdf", [column(THREE_PARAGRAPHS)])
        result = rebuilt(source, tmp_path, pdf_layout="fixed")
        assert result.output_path
        assert gate._fixed_layout(result.output_path)

    def test_a_pages_document_names_its_source_page(self):
        assert gate._page_number_of("page-0012.xhtml", 3) == 12
        assert gate._page_number_of("0011-page-0012.xhtml", 3) == 12
        assert gate._page_number_of("section-0002.xhtml", 3) == 4


@engine
class TestTheGateComparesWithTheSource:
    """Q07, on the pinned engine. The book is damaged after the conversion
    built it, the way the consent-scope tests damage theirs, and the gate
    is the thing being asked."""

    @staticmethod
    def _damaged(path, lines: int):
        """The published fixed book with *lines* lines removed from page 1."""
        import shutil
        import zipfile

        damaged = path.with_name("damaged.epub")
        with zipfile.ZipFile(path) as before, zipfile.ZipFile(damaged, "w") as after:
            for item in before.infolist():
                data = before.read(item.filename)
                if item.filename.endswith("page-0001.xhtml"):
                    text = data.decode("utf-8")
                    text = re.sub(r'<div class="ef-pdf-line[^>]*>.*?</div>', "", text, count=lines, flags=re.S)
                    data = text.encode("utf-8")
                after.writestr(item, data)
        return damaged

    def test_a_faithful_page_passes_and_the_report_names_the_engine(self, tmp_path):
        _needs_the_engines()
        source = make_pdf(tmp_path / "one.pdf", [column(THREE_PARAGRAPHS)])
        result = rebuilt(source, tmp_path, pdf_layout="fixed")
        assert result.output_path
        measured = gate.compare_fixed(str(source), result.output_path, sample=0)
        assert measured.available and measured.completed, measured.reason
        assert measured.ok, [str(p) for p in measured.pages]
        assert all(p.difference < gate.LOST_SHARE for p in measured.pages)

    def test_a_page_that_lost_a_line_is_refused(self, tmp_path):
        _needs_the_engines()
        source = make_pdf(tmp_path / "one.pdf", [column(THREE_PARAGRAPHS)])
        result = rebuilt(source, tmp_path, pdf_layout="fixed")
        assert result.output_path
        damaged = self._damaged(tmp_path / "out.epub", 1)
        measured = gate.compare_fixed(str(source), str(damaged), sample=0)
        assert measured.completed
        assert not measured.ok, [str(p) for p in measured.pages]
        assert measured.pages[0].difference > gate.LOST_SHARE

    def test_the_whole_gate_refuses_and_records_the_check(self, tmp_path):
        _needs_the_engines()
        from epubforge.policy import Policy

        source = make_pdf(tmp_path / "one.pdf", [column(THREE_PARAGRAPHS)])
        good = rebuilt(source, tmp_path, pdf_layout="fixed")
        report = Report()
        policy = Policy.preset("preserve", render_gate="stop", render_sample=0)
        refusal = gate.render_gate(str(good.output_path), policy, report, None,
                                   lambda *a, **k: "cannot", source=str(source))
        assert refusal == "", report.to_text("pl")
        assert report.checks["render"] == PASSED
        assert "render.pdf-compared" in {f.rule for f in report.findings}
        damaged = self._damaged(tmp_path / "out.epub", 1)
        report = Report()
        refusal = gate.render_gate(str(damaged), policy, report, None,
                                   lambda *a, **k: "cannot", source=str(source))
        assert refusal, "brama przepuscila strone bez wiersza"
        assert report.checks["render"] == FAILED
        assert "render.pdf-page-differs" in {f.rule for f in report.findings}
