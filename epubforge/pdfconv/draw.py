"""Drawing a region of the source page, because this program cannot draw.

Q01 of the quality roadmap: a diagram made of vector strokes is not a picture
to carry, so a page whose whole content was a drawing arrived as a row of
callout labels with nothing to label. The reader has always *known* where the
drawing is — `reader._drawings` boxes it, in order to gather the text standing
on it — and had nothing to put there.

What it puts there now is a picture of that box, rendered from the source PDF
at a stated scale. Not an export of the vectors: an export needs fonts,
clipping, transforms and effects to survive a second engine, and the roadmap
warns in as many words not to assume SVG solves the problem by itself. A
raster of the region is the honest first answer — it is what the page looks
like — and its costs are stated where they are paid: a fixed resolution, and
no text inside the image (the callouts stay text, beside it).

**PDFium, and why.** The check is licence and distribution, not price: PDFium
is BSD-style and `pypdfium2` ships prebuilt binaries for Windows in a 3.9 MB
wheel with no copyleft. MuPDF is AGPL or commercial; the Chromium this program
already requires for the appearance gate embeds PDFium but will not render a
PDF to a screenshot in headless — measured, three ways, all of them a blank
viewer background.

**Optional, and honest when absent.** Without the library the drawings are not
carried and the report says so exactly as it did before. A conversion does not
fail for want of it, and nothing pretends the drawing arrived.
"""

from __future__ import annotations

import functools
import io

#: How many pixels per PDF point. 2.0 is the same ratio the cover thumbnails
#: use for a high-DPI screen, and a drawing of line art at twice its printed
#: size stays sharp on a phone without turning a page into a megabyte.
SCALE = 2.0

#: A region has to be worth carrying. Below this, in points, it is a rule, a
#: box round a paragraph or a table border — the reader's own drawing detector
#: already refuses most of those, and this is the second sieve.
SMALLEST = 40.0

#: What one region may cost. A page of dense line art at scale 2 is a few
#: hundred kilobytes; a whole-page photograph rendered by accident is not, and
#: a book of those is a book nobody can send anywhere.
MOST_BYTES = 4 * 1024 * 1024


@functools.lru_cache(maxsize=1)
def _renderer():
    """The renderer's document class, or `None` when it is not installed.

    One place, asked once, so that "is there a renderer" and "give me the
    renderer" cannot disagree — and so the import is written down exactly
    once, with the narrow `ImportError` the rest of this package uses for an
    optional library rather than a handler that swallows everything.
    """
    try:
        from pypdfium2 import PdfDocument
    except ImportError:
        return None
    return PdfDocument


@functools.lru_cache(maxsize=1)
def _refusals() -> tuple:
    """What the renderer throws at a file it will not open or draw.

    Named rather than caught wholesale: `PdfiumError` is its own class for a
    document PDFium rejects, and `OSError` is the file not being there. Both
    mean the same thing here — no picture — and anything else is a defect in
    this program that ought to come out, not be filed under "not carried".
    Empty when there is no renderer, in which case nothing calls into one.
    """
    renderer = _renderer()
    if renderer is None:
        return ()
    from pypdfium2 import PdfiumError

    return (OSError, PdfiumError)


def available() -> bool:
    """Whether a renderer is installed. Asked once."""
    return _renderer() is not None


def why_not() -> str:
    """The sentence for a report when there is no renderer."""
    return "pypdfium2"


class Sheet:
    """One opened PDF, so a document of a hundred pages is opened once.

    The reader walks pages in order and asks for regions as it goes; opening
    the file per region turned a 105-page manual into 105 opens in the first
    measurement of this.
    """

    def __init__(self, source: str) -> None:
        self._source = source
        self._document = None
        self._tried = False

    def _opened(self):
        """The document, opened on first use and only if there is a renderer."""
        if self._tried:
            return self._document
        self._tried = True
        renderer = _renderer()
        if renderer is not None:
            try:
                self._document = renderer(self._source)
            except _refusals():
                self._document = None
        return self._document

    def close(self) -> None:
        document, self._document = self._document, None
        if document is None:
            return
        try:
            document.close()
        except _refusals():
            # Closing is best effort: the pictures are already bytes in the
            # book by now, and a renderer that will not let go of a file is
            # not a reason to lose a conversion that finished.
            pass

    def region(self, page: int, box, height: float, scale: float = SCALE) -> "bytes | None":
        """A PNG of *box* on *page*, or `None` when it cannot be drawn.

        *box* is `(x0, y0, x1, y1)` in PDF points with y measured from the
        bottom of the page, which is how `pdfminer` reports it and therefore
        how the reader holds it. The renderer draws from the top, so the two
        y coordinates are turned over here — in one place, next to the sentence
        that says why.
        """
        document = self._opened()
        if document is None:
            return None
        x0, y0, x1, y1 = box
        if (x1 - x0) < SMALLEST or (y1 - y0) < SMALLEST:
            return None
        try:
            drawn = document[page - 1].render(scale=scale)
            image = drawn.to_pil()
        except (IndexError, *_refusals()):
            # A page number past the end, or a page PDFium refuses to draw.
            # Either way there is no picture of this region, which the caller
            # reports; it is not a reason to lose the rest of the book.
            return None
        left, right = int(x0 * scale), int(x1 * scale)
        # y from the bottom becomes y from the top.
        top, bottom = int((height - y1) * scale), int((height - y0) * scale)
        left, top = max(0, left), max(0, top)
        right, bottom = min(image.width, right), min(image.height, bottom)
        if right - left < 1 or bottom - top < 1:
            return None
        out = io.BytesIO()
        image.crop((left, top, right, bottom)).convert("RGB").save(
            out, format="PNG", optimize=True
        )
        data = out.getvalue()
        if len(data) > MOST_BYTES:
            return None
        return data
