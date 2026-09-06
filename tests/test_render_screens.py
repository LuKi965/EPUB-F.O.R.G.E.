"""EF-089: the full appearance check looks past the first screen, and the
report says how far it looked.

The independent audit of 2026-09-05 hid a paragraph 1 800 px down a page —
`visibility: hidden` in the candidate, untouched in the source — and the
check compared two screenshots of the first 800 px, found them identical, and
called the book unchanged. One screenshot per document is one screen. The
full check (`sample=0`, which is `strict` and a release) now takes one tall
shot of `SCREENS` viewport heights and judges it band by band; the sampled
check does not, and the report says `1 screen` so that nobody reads
"checked" as "whole".
"""

from __future__ import annotations

import os
import pathlib
import zipfile

import pytest

from epubforge import render, render_fidelity

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _png(path: pathlib.Path, width: int, height: int, inked: "list[tuple[int, int]]") -> pathlib.Path:
    """A white PNG with black rectangles at the (top, bottom) rows given."""
    from PIL import Image, ImageDraw

    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    for top, bottom in inked:
        draw.rectangle((20, top, width - 20, bottom), fill=0)
    image.save(path)
    return path


class TestBands:
    def test_ink_is_measured_per_screen(self, tmp_path):
        page = _png(tmp_path / "a.png", 600, 2400, [(100, 200), (1700, 1800)])
        inks = render.ink_bands(page, 800)
        assert len(inks) == 3
        assert not inks[0].blank and inks[1].blank and not inks[2].blank

    def test_a_difference_is_located_in_its_screen(self, tmp_path):
        one = _png(tmp_path / "a.png", 600, 2400, [(100, 200), (1700, 1722)])
        two = _png(tmp_path / "b.png", 600, 2400, [(100, 200)])
        whole = render.difference(one, two)
        bands = render.difference_bands(one, two, 800)
        assert whole < render_fidelity.DIFFERENT, "over the whole page the loss is under the threshold — that is the defect"
        assert bands[2] > render_fidelity.DIFFERENT and bands[0] == 0.0

    def test_a_screen_that_went_blank_is_a_loss(self, tmp_path):
        one = _png(tmp_path / "a.png", 600, 2400, [(100, 200), (1700, 1800)])
        two = _png(tmp_path / "b.png", 600, 2400, [(100, 200)])
        before, after = render.ink_bands(one, 800), render.ink_bands(two, 800)
        check = render_fidelity.PageCheck(document="x", viewport=(600, 800))
        check.source_ink, check.output_ink = before[2], after[2]
        check.difference = render.difference_bands(one, two, 800)[2]
        render_fidelity._judge(check)
        assert check.problems, check


class TestTheReportSaysHowFarItLooked:
    def test_the_sampled_check_says_one_screen(self):
        # The stand-in the suite uses for the browser reports one comparison;
        # what matters here is the shape of the values the gate hands on.
        measured = render_fidelity.RenderFidelity(
            available=True, engine="x", pages=[], completed=True, documents=12, total=40
        )
        assert measured.screens == 1
        assert render_fidelity.SCREENS > 1


# ------------------------------------------------------------- the real thing
def _book(path: pathlib.Path, hidden: bool) -> str:
    container = (
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
        '<rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    opf = (
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:x</dc:identifier>'
        "<dc:title>T</dc:title><dc:language>en</dc:language>"
        '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>'
        '<manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="n" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest>'
        '<spine><itemref idref="c"/></spine></package>'
    )
    style = "margin-top:1800px;" + ("visibility:hidden;" if hidden else "")
    chapter = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title></head><body>'
        f'<p>VISIBLE FIRST PARAGRAPH</p><p style="{style}">LOWER PARAGRAPH MUST STAY VISIBLE</p>'
        "</body></html>"
    )
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        '<head><title>N</title></head><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">C</a></li></ol></nav></body></html>'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("EPUB/package.opf", opf)
        z.writestr("EPUB/chapter.xhtml", chapter)
        z.writestr("EPUB/nav.xhtml", nav)
    return str(path)


@pytest.mark.renders
def test_a_paragraph_hidden_on_the_third_screen_is_caught_by_the_full_check(tmp_path):
    if not os.environ.get("EPUBFORGE_RENDER_TESTS") or render.find_renderer() is None:
        pytest.skip("set EPUBFORGE_RENDER_TESTS=1 and name a Chromium")
    source = _book(tmp_path / "source.epub", hidden=False)
    damaged = _book(tmp_path / "damaged.epub", hidden=True)
    full = render_fidelity.compare(source, damaged, sample=0)
    assert not full.ok, [str(page) for page in full.pages]
    assert full.screens == render_fidelity.SCREENS
    sampled = render_fidelity.compare(source, damaged, sample=12)
    assert sampled.screens == 1, "the sampled check says what it looked at"
