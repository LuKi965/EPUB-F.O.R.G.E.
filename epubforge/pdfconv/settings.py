"""What the PDF converter offers a person to decide, and nothing else.

A leaf: it imports nothing, so the core's `Policy` can hold one of these
without importing the converter (D-056). The settings are the module's, live
under `Policy.pdf`, and read `policy.pdf.layout` rather than
`policy.pdf_layout` — which is the difference between a converter's settings
being *in* the repair tool and being *beside* it.
"""

from __future__ import annotations

from dataclasses import dataclass

#: What becomes of the running heads and page numbers a PDF brought along:
#: asked once per book, kept, or removed for all of them (0.5, D-052).
RUNNING_HEADS = ("ask", "keep", "remove")

#: What a PDF becomes: a book that reflows (the default, and what every mode
#: does unless it is told otherwise) or the pages it had, kept as pages.
LAYOUTS = ("reflowable", "fixed")


@dataclass
class PdfSettings:
    """The converter's own settings, carried by `Policy.pdf`."""

    #: A PDF source carries running heads and page numbers in its text layer;
    #: the reader keeps them as marked paragraphs and the PDF stage asks once
    #: per book whether to remove them (`ask`), or does what a batch has
    #: already decided (`keep`, `remove`). Nothing leaves without an answer.
    running_heads: str = "ask"

    #: What a PDF is turned into: a book that reflows, or the pages it had.
    #:
    #: `reflowable` — the default in every mode — reads the geometry back into
    #: paragraphs, headings, tables and lists, so the text can be set at any
    #: size on any screen. `fixed` keeps the page: every line where the
    #: typesetter put it, on a page of the source's own measurements, and the
    #: publication declared `pre-paginated`.
    #:
    #: A separate mode and never a default, decided with the owner 2026-09-08.
    #: A fixed page keeps the look and takes the reader's font size away from
    #: them, which is the one thing an EPUB gives that paper does not; for a
    #: novel that is a bad trade and for a form, a score or a diagram with
    #: words in it it is the only right one. Nobody but the person holding the
    #: document can tell which of the two they have, so the program does not
    #: decide it for them — it offers both and says in the report what the
    #: chosen one costs.
    layout: str = "reflowable"
