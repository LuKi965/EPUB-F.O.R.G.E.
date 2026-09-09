"""A PDF with a text layer, read into the same model as an EPUB (0.5, D-052).

What a PDF is, for this program: characters with a position, a font and a
size, laid out on pages by somebody's typesetter; images; and, when the
publisher bothered, an outline. What an EPUB is: paragraphs, headings and a
reading order. The gap between the two is geometry, and this module reads
the geometry back into structure using named thresholds rather than guesses,
so that the report can say what it decided and from what.

The promise is the same as for an EPUB: **no character of the text layer is
lost**. Lines are joined with spaces and nothing is dropped here — not the
line-end hyphen (the hyphen stage decides that, with its dictionary and its
question) and not the running head (a paragraph marked for the PDF stage to
ask about). A PDF with no text layer is refused: reading it would mean OCR,
which is a different program.
"""

from __future__ import annotations

import hashlib
import io
import os
import posixpath
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from ..model import Book, Creator, Identifier, NavPoint, PageTarget, Resource, SpineItem
from ..reader import EpubReadError
from . import draw
from ..report import Level, Report
from ..writer import escape

EXTENSION = ".pdf"
#: The class the PDF stage looks for: a line the reader took for a running
#: head or a page number, kept in the text until somebody answers.
RUNNING_HEAD_CLASS = "ef-pdf-running-head"
#: The class on a paragraph that continues the one before it across a page
#: break a running head sat in. The text stays in the page's order (K1-PDF is
#: a subsequence test, and the order is the source's); the PDF stage joins
#: the two halves back together when the head goes, and drops the mark when
#: it stays.
CONTINUED_CLASS = "ef-pdf-continued"
#: The class on the callout labels printed *on* a drawing — "A16" beside an
#: arrow — gathered under the drawing they belong to. Unlike the two above this
#: is not a mark for a later stage to remove: it says what the text is, and the
#: rebuilt book keeps it.
LABEL_CLASS = "ef-pdf-labels"

#: A heading is a line set larger than the body — these are the ratios, and
#: they are reported with every heading they produce.
BODY_RATIO_H1 = 1.6
BODY_RATIO_H2 = 1.25
#: A line that repeats at the same height on this share of the pages, digits
#: aside, is a running head or a page number. Under four pages nothing repeats
#: often enough to say.
RUNNING_HEAD_SHARE = 0.6
RUNNING_HEAD_MIN_PAGES = 4
#: Where running heads live: this share of the page height at the top or the
#: bottom.
MARGIN_SHARE = 0.12
#: A new paragraph starts after a gap wider than this many line pitches, at an
#: indent deeper than this many points, or after a line shorter than this share
#: of the block's width when the next begins a sentence.
PARAGRAPH_GAP_RATIO = 1.5
INDENT_POINTS = 8.0
SHORT_LINE_RATIO = 0.7
#: Fewer text characters than this per page, on average, is not a text layer.
MIN_CHARACTERS_PER_PAGE = 20
#: How the page is cut into areas that are read one after another. A gap wider
#: than this share of the page width is a gutter between columns; wider than
#: this share of the height, a band across it. The band is the larger of the
#: two on purpose: ordinary space between paragraphs runs to about three per
#: cent of a page's height (a line pitch and a half on a 595-point page), and a
#: threshold under that would cut a column into paragraphs and read them across
#: the gutter — which is the defect two-column detection was written for.
GUTTER_SHARE = 0.04
BAND_SHARE = 0.06
#: How many times the page may be cut. Six is far more than any page needs; it
#: is here so that a pathological page cannot recurse forever.
REGION_DEPTH = 6


def is_pdf(path: str) -> bool:
    return path.lower().endswith(EXTENSION)


@dataclass
class Line:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float
    size: float
    page: int
    bold: bool = False
    #: The line cut into runs of one face: `(text, style)`, style being "b",
    #: "i", "bi" or "". What the typesetter set apart is the only part of a
    #: page's look this reader can carry into a reflowable book, and it used to
    #: measure the line's face and then throw it away.
    runs: list = field(default_factory=list)
    running_head: bool = False
    #: Which area of the page this line belongs to. Lines of one area are read
    #: one after another; a paragraph never runs from one area into the next.
    region: int = 0
    #: The generic family the font's name claims — "serif", "sans-serif",
    #: "monospace" — or "" when it claims nothing. Empty is the ordinary case
    #: and is deliberately not a guess: a subset font called `UKJILE+ABCDEF`
    #: says nothing about its shape, and naming a family for it would be this
    #: reader inventing a face the file never named.
    family: str = ""


#: How far past a picture's own edges its name may reach and still be its name.
#: A caption is usually centred under the picture and narrower than it; a couple
#: of points of slack allow for the one that is set flush and rounds outwards.
CAPTION_SLACK = 4.0


@dataclass
class Picture:
    name: str
    data: bytes
    media_type: str
    page: int
    y1: float
    #: The rest of the box. Kept because a label printed *on* a drawing is
    #: text that belongs to the drawing, and the only way to know that is to
    #: know where the drawing is.
    x0: float = 0.0
    x1: float = 0.0
    y0: float = 0.0
    #: Short lines that stand inside this picture: callout labels, the "A16"
    #: beside an arrow. They are not paragraphs and they are not lost.
    #:
    #: The **lines**, not their text, and that is what the fixed-layout mode
    #: needs: a label whose position was thrown away can only be printed under
    #: the picture, and the one thing a label is for is standing beside the
    #: part of the drawing it names.
    labels: "list[Line]" = field(default_factory=list)
    #: The name written under the picture — "Americano" under the icon of it.
    caption: "Line | None" = None
    #: True when this is a *rendered region* rather than an image the PDF
    #: embedded: a diagram of vector strokes, drawn at a stated scale because
    #: this program cannot draw (Q01). Kept because the report must not say
    #: "carried an image" about a picture the program made of a page.
    drawn: bool = False

    def holds(self, line: "Line") -> bool:
        """Whether *line* stands inside this picture's box."""
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            return False
        middle_x = (line.x0 + line.x1) / 2
        middle_y = (line.y0 + line.y1) / 2
        return self.x0 <= middle_x <= self.x1 and self.y0 <= middle_y <= self.y1

    def is_named_by(self, line: "Line", pitch: float) -> bool:
        """Whether *line* stands under this picture as its name.

        Under it: the line's top is below the picture's foot by no more than
        one line of type, so the two are set as one thing. Within it: the line
        does not reach past either side of the picture.
        """
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            return False
        return (self.y0 - pitch <= line.y1 <= self.y0
                and line.x0 >= self.x0 - CAPTION_SLACK
                and line.x1 <= self.x1 + CAPTION_SLACK)


@dataclass
class Page:
    number: int
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    pictures: list[Picture] = field(default_factory=list)
    columns: bool = False
    #: The x that divides two columns, when there are two.
    split: "float | None" = None
    #: The page cut into the areas a person reads one after another, in that
    #: order. One region is an ordinary page of prose.
    regions: list = field(default_factory=list)
    #: Boxes of the vector drawings on the page. Not carried into the book —
    #: this reader has no way to draw them — but the text standing on them is.
    drawings: list = field(default_factory=list)
    #: The callouts printed on those drawings, taken out of the prose and
    #: printed together where the first of them stood.
    callouts: list = field(default_factory=list)


@dataclass
class Outline:
    """One outline entry that resolved to a page."""

    level: int
    title: str
    page: int


#: Above this share of paragraphs running into the next one mid-sentence, the
#: page was not read the way its layout intended. Measured rather than picked:
#: a 105-page appliance manual set in InDesign — the owner's first real PDF,
#: 2026-09-07 — came out at 24 %, while prose PDFs (the ones this suite writes,
#: and the Gutenberg books printed by Chromium) sit at nought to two. Ten per
#: cent stands between the two with room on either side.
TORN_SHARE_WARN = 0.10
#: A paragraph of this many words or fewer, ending without any sentence
#: punctuation, is a fragment rather than a paragraph: a caption torn from its
#: picture, a label lifted off a diagram, one cell of a table.
FRAGMENT_WORDS = 2


@dataclass
class Quality:
    """How much of the page's meaning survived being read as a line of text.

    The reader has always reported what it *did* — so many paragraphs, so many
    headings — and never how well it went. On prose the two are the same
    question. On a document laid out in blocks they are not: 1 964 paragraphs
    is a fine number and a bad sign when 481 of them are one sentence cut in
    half.
    """

    paragraphs: int = 0
    #: Paragraphs that end mid-sentence and are followed by one starting in
    #: lower case: two halves of one sentence, put in two paragraphs.
    torn: int = 0
    #: Paragraphs of a word or two with no sentence in them.
    fragments: int = 0
    median_characters: int = 0

    @property
    def torn_share(self) -> float:
        return self.torn / self.paragraphs if self.paragraphs else 0.0

    @property
    def fragment_share(self) -> float:
        return self.fragments / self.paragraphs if self.paragraphs else 0.0

    @property
    def poor(self) -> bool:
        return self.torn_share >= TORN_SHARE_WARN


def measure_quality(blocks: "list[Block]") -> Quality:
    """Read the blocks the way a person would and count what does not read.

    Deliberately about *text*, not about geometry: whatever the reader thought
    the page looked like, this is what came out of it.
    """
    paragraphs = [block.text.strip() for block in blocks if block.kind == "p"]
    paragraphs = [text for text in paragraphs if text]
    quality = Quality(paragraphs=len(paragraphs))
    if not paragraphs:
        return quality
    lengths = sorted(len(text) for text in paragraphs)
    quality.median_characters = lengths[len(lengths) // 2]
    for text, following in zip(paragraphs, paragraphs[1:]):
        if text[-1] not in SENTENCE_ENDS and following[:1].islower():
            quality.torn += 1
    quality.fragments = sum(
        1 for text in paragraphs
        if len(text.split()) <= FRAGMENT_WORDS and text[-1] not in SENTENCE_ENDS
    )
    return quality


#: What the end of a sentence looks like, closing quotes and brackets included.
SENTENCE_ENDS = ".!?:;…»”\"'’)]"


@dataclass
class Layout:
    """What the reader saw and decided — the numbers the report carries."""

    pages: int = 0
    lines: int = 0
    characters: int = 0
    paragraphs: int = 0
    headings: int = 0
    #: Grids rebuilt as tables, and the cells in them — cells that used to be
    #: one-or-two-word paragraphs.
    tables: int = 0
    table_cells: int = 0
    #: Runs of marked paragraphs marked up as lists.
    lists: int = 0
    #: The face the document is set in, and how much of it is set apart.
    body_face: str = ""
    emphasis: int = 0
    #: Pages carrying a vector drawing, and the drawings whose callouts were
    #: gathered out of the prose.
    drawing_pages: int = 0
    labelled_drawings: int = 0
    #: Drawings carried into the book as a rendered picture of their region
    #: (Q01). A page may hold several; this counts the pictures, not the pages.
    drawings_carried: int = 0
    images: int = 0
    images_skipped: int = 0
    running_heads: int = 0
    outline_entries: int = 0
    outline_unresolved: int = 0
    #: Entries in the table of contents the reader built. With an outline this
    #: is the whole of it, not only the entries that became documents.
    navigation_entries: int = 0
    #: Entries read off the book's own printed contents page, when it had no
    #: bookmarks to read instead.
    contents_entries: int = 0
    column_pages: int = 0
    body_size: float = 0.0
    torn_paragraphs: int = 0
    fragment_paragraphs: int = 0
    median_paragraph: int = 0
    #: How many areas the pages were cut into. One per page is prose.
    regions: int = 0


# ----------------------------------------------------------------- reading


def read_pdf(source: str, report: Report, budget=None, page_layout: str = "reflowable") -> Book:
    """Load *source* into a :class:`Book`, or refuse it with the reason said.

    *page_layout* is `reflowable` (the default, and what every mode does unless
    it is told otherwise) or `fixed` — see `PDF_LAYOUTS`. Everything up to the
    writing is the same either way: the same pages, the same areas, the same
    blocks in the same order. The two differ only in what is made of them.
    """
    pages, info, outline, layout = _read(source)
    _refuse_a_book_of_pictures(pages, layout, source, report)

    body_size = _lay_out_all(pages, layout)

    book = Book()
    book.source_version = "pdf"
    book.source_opf_path = None
    _read_metadata(book, source, info)

    if not outline:
        # No bookmarks — but the book very often prints its own contents on
        # page two, and `_tables` has already read it as rows ending in a page
        # number. That is the file saying where its parts begin, in the one
        # other place it says so.
        outline = contents_entries(pages)
        layout.contents_entries = len(outline)
    layout.outline_entries = len(outline)
    if page_layout == FIXED:
        # The same blocks the reflowable book is made of, and read in the same
        # order — `text_of` reads exactly these, with no chapter breaks, so
        # both modes carry the source's text in the source's order. What
        # differs is that here they are printed where they were drawn.
        blocks = _blocks(pages, body_size)
        sections = len(pages)
        _fill_the_pages(book, pages, blocks, layout, outline)
    else:
        parts = _sections(pages, outline, body_size)
        blocks = [block for _, blocks_of in parts for block in blocks_of]
        sections = len(parts)
        _fill_the_book(book, parts, layout, outline)
    quality = measure_quality(blocks)
    layout.torn_paragraphs = quality.torn
    layout.fragment_paragraphs = quality.fragments
    layout.median_paragraph = quality.median_characters
    layout.running_heads = sum(1 for page in pages for line in page.lines if line.running_head)

    _say_what_was_read(report, source, layout, sections, quality)
    if page_layout == FIXED:
        _say_the_page_was_kept(report, source, layout, pages)
    _say_what_was_noticed(report, source, layout)
    _say_what_was_not_placed(report, source, pages)
    report.stats["pdf_layout"] = layout.__dict__.copy()
    # The words the typesetter broke at a line end, joined as the hyphen
    # stage will meet them (`prze-konaniem`), and **how many times each was
    # broken there**: evidence that stage can use — a hyphen the reader put
    # at a line end is a converter's, not a writer's, and on typeset
    # material a third of them were otherwise left because their first half
    # happened to be a word (`nie-`, `po-`).
    #
    # The count is what tells the two apart the other way round (DROGA 6.12).
    # `to-day` is the author's spelling in a book from 1890; the typesetter
    # happening to break a line there does not make it a converter's hyphen.
    # A word this reader joined at a break appears in the text once per
    # break, so a hyphenated form the book carries **more often than it was
    # broken** stands somewhere nobody broke — and that is the author
    # writing it.
    report.stats["pdf_line_end_words"] = dict(sorted(_line_end_words(pages).items()))
    return book


def _lay_out_all(pages: list[Page], layout: "Layout") -> float:
    """Running heads, then the areas of each page, then the body size — the
    reader's whole view of the document, in the order the three must happen.

    Shared with `text_of`, which is the left side of K1-PDF: both sides have to
    mean the same thing by "the order the source is read in", and since pages
    are cut into areas that is no longer the order of the lines down the page.
    """
    _mark_running_heads(pages, layout)
    # The legend of one page names the callouts of another, so the whole
    # document is read for them before any page is laid out.
    names = callout_names(pages)
    # After the running heads, because a head at the top of the page is a band
    # of its own and would cut every page in two before anything else could.
    for page in pages:
        _lay_out(page, names)
    layout.column_pages = sum(1 for page in pages if page.columns)
    layout.regions = sum(len(page.regions) for page in pages)
    layout.drawing_pages = sum(1 for page in pages if page.drawings)
    layout.drawings_carried = sum(
        1 for page in pages for picture in page.pictures if picture.drawn
    )
    layout.body_size = _body_size(pages)
    layout.body_face = _body_face(pages)
    return layout.body_size


def _refuse_a_book_of_pictures(pages: list[Page], layout: "Layout", source: str, report: Report) -> None:
    """A PDF with no text layer is a stack of scans, and this reader cannot
    read a scan. Refused with the two numbers that say why."""
    layout.pages = len(pages)
    layout.lines = sum(len(page.lines) for page in pages)
    layout.characters = sum(
        len(line.text.replace(" ", "")) for page in pages for line in page.lines
    )
    if pages and layout.characters >= MIN_CHARACTERS_PER_PAGE * len(pages):
        return
    report.add(
        "pdf",
        Level.ERROR,
        "pdf.no-text-layer",
        values={"pages": len(pages), "characters": layout.characters},
        location=source,
    )
    # The finding above is the reason, with both numbers and in the reader's
    # language. This only stops the run; it does not restate it (`reported`).
    refusal = EpubReadError("the PDF has no text layer to read; scanning it would need OCR")
    refusal.reported = True
    raise refusal


def _fill_the_book(book: Book, sections: list, layout: "Layout",
                   outline: "list[Outline]") -> None:
    """One document and one spine entry per section, the pictures they stand
    on, and a table of contents made of the **whole** outline.

    The documents come from the outline's top level, because a document is a
    unit a reading system loads whole. The table of contents does not: an
    outline of 125 entries that gives 10 nav points has thrown away 115 of
    them, and they are the ones a person uses to find "6.6.4 Odkamienianie"
    without reading the chapter. Each entry points at an anchor on the page it
    named, which is the position the PDF itself recorded.
    """
    anchored = {entry.page for entry in outline}
    placed: dict[int, str] = {}
    spans: list = []
    for index, (title, blocks) in enumerate(sections, 1):
        path = f"text/section-{index:04d}.xhtml"
        # A section the outline did not name and no heading opened: the first
        # is the book's own front matter and takes the title; a later one is
        # named by its number, which is the one thing that is true of it.
        label = title or (book.metadata.title if index == 1 else f"{index}")
        spans.append((path, _add_section(book, path, label, blocks, layout, anchored, placed)))
        if not outline:
            book.toc.append(NavPoint(label=label, target=path))
    _place_the_pages_nothing_reaches(anchored, placed, spans)
    if layout.lists:
        book.add(Resource(path=STYLESHEET_PATH, media_type="text/css",
                          data=STYLESHEET.encode("utf-8")))
    if outline:
        book.toc.extend(_navigation(outline, placed))
    layout.navigation_entries = sum(len(list(node.walk())) for node in book.toc)


def _add_section(book: Book, path: str, label: str, blocks: list, layout: "Layout",
                 anchored: set, placed: dict) -> None:
    """One section as a document, a spine entry and the pictures it stands on,
    with the anchors it turned out to carry written into *placed*."""
    markup, counts = _render(blocks, label, anchored, layout.body_face)
    layout.paragraphs += counts["paragraphs"]
    layout.headings += counts["headings"]
    layout.tables += counts["tables"]
    layout.labelled_drawings += counts["labelled_drawings"]
    layout.lists += counts["lists"]
    layout.emphasis += counts["emphasis"]
    layout.table_cells += sum(len(row) for block in blocks
                              if block.kind == "table" for row in block.rows)
    for page, name in counts["anchored"]:
        placed.setdefault(page, f"{path}#{name}")
    anchors = sorted(counts["anchored"])
    for block in blocks:
        if block.kind == "image" and block.picture.name not in book.resources:
            picture = block.picture
            book.add(Resource(path=picture.name, media_type=picture.media_type, data=picture.data))
            layout.images += 1
    book.add(Resource(path=path, media_type="application/xhtml+xml", data=markup.encode("utf-8")))
    book.spine.append(SpineItem(path=path))
    pages = {page for block in blocks for page in _block_pages(block)}
    return min(pages) if pages else 0, anchors


def _place_the_pages_nothing_reaches(anchored: set, placed: dict, spans: list) -> None:
    """Where a table-of-contents entry goes when its page holds nothing.

    The outline names a page and no block reaches it: an empty page, or — 39 of
    the owner's manual's 105 — a page of nothing but a drawing made of curves,
    which this reader cannot carry. The entry still has to lead somewhere.

    It leads to **the last anchor before it in the document that page falls
    in**, which is the last thing a person would have read before that page
    began. Only a page with no anchor before it in its own document goes to the
    top of that document.

    Not to the document itself, and that is EPUBCheck on the owner's manual: a
    bare document link stands *before* every anchor in that document, so a
    table of contents that mixes the two runs backwards — twenty entries of a
    hundred and twenty-five, `NAV-011` on eight of ten documents. The entry was
    truthful about which document and wrong about where in it, and a person
    following "2.3 Ustaw twardość wody" landed at the head of the chapter.
    """
    starts = [start for _path, (start, _anchors) in spans]
    for index, (path, (_start, anchors)) in enumerate(spans):
        # Each section owns the pages from where it begins to where the next
        # one does, so a page nothing reaches still belongs somewhere.
        after = next((s for s in starts[index + 1:] if s), None)
        for page in sorted(p for p in anchored if p not in placed):
            if page < _start or (after is not None and page >= after):
                continue
            before = [name for at, name in anchors if at <= page]
            placed[page] = f"{path}#{before[-1]}" if before else path


def _anchor(page: int) -> str:
    return f"pdf-page-{page:04d}"


def _block_page(block: "Block") -> int:
    if block.picture is not None:
        return block.picture.page
    return block.lines[0].page if block.lines else 0


def _block_pages(block: "Block") -> list:
    """Every page this block has text on, in order. A paragraph that runs over
    the fold is on two."""
    if block.picture is not None:
        return [block.picture.page]
    seen: list = []
    for line in block.lines:
        if not seen or seen[-1] != line.page:
            seen.append(line.page)
    return seen


def _navigation(outline: "list[Outline]", placed: dict) -> "list[NavPoint]":
    """The outline as the tree it already is: an entry's level says whose child
    it is, and the entry after it at the same level is its sibling.

    An outline that skips a level — 1 then 3, which real files do — hangs the
    deeper entry off the nearest shallower one rather than inventing a parent
    nobody wrote.
    """
    roots: list[NavPoint] = []
    stack: list[tuple[int, NavPoint]] = []
    for entry in outline:
        node = NavPoint(label=entry.title or "—", target=placed.get(entry.page))
        while stack and stack[-1][0] >= entry.level:
            stack.pop()
        (stack[-1][1].children if stack else roots).append(node)
        stack.append((entry.level, node))
    return roots


def _say_what_was_read(report: Report, source: str, layout: "Layout",
                       sections: int, quality: "Quality") -> None:
    """What the reader did, and — the part it used not to say — how well."""
    report.add(
        "pdf",
        Level.FIX,
        "pdf.converted",
        values={
            "pages": layout.pages,
            "lines": layout.lines,
            "paragraphs": layout.paragraphs,
            "headings": layout.headings,
            "images": layout.images,
            "sections": sections,
        },
        location=source,
    )
    # How well it went, not only what was done. Always said, because a number
    # nobody can see is a number nobody can act on; raised to a warning when
    # the share says the layout was not read the way it was set.
    how_it_went = {
        "paragraphs": quality.paragraphs,
        "torn": quality.torn,
        "share": round(quality.torn_share * 100),
        "fragments": quality.fragments,
        "median": quality.median_characters,
    }
    # Two calls rather than one with a chosen identifier: a rule that cannot be
    # found by grepping for its name is a rule nobody can follow to its source.
    if quality.poor:
        report.add("pdf", Level.WARN, "pdf.reading-quality-poor",
                   values=how_it_went, location=source)
    else:
        report.add("pdf", Level.INFO, "pdf.reading-quality",
                   values=how_it_went, location=source)


def _say_what_was_noticed(report: Report, source: str, layout: "Layout") -> None:
    """The four things about the document that a reader of the report would
    want to know were there — each said only when it was."""
    if layout.contents_entries:
        report.add(
            "pdf",
            Level.FIX,
            "pdf.contents-page-read",
            values={"count": layout.contents_entries},
            location=source,
        )
    if layout.outline_entries:
        report.add(
            "pdf",
            Level.PRESERVED,
            "pdf.outline-used",
            values={"count": layout.outline_entries, "unresolved": layout.outline_unresolved},
            location=source,
        )
    if layout.tables:
        report.add(
            "pdf",
            Level.FIX,
            "pdf.tables-rebuilt",
            values={"count": layout.tables, "cells": layout.table_cells},
            location=source,
        )
    if layout.lists:
        report.add(
            "pdf",
            Level.FIX,
            "pdf.lists-rebuilt",
            values={"count": layout.lists},
            location=source,
        )
    if layout.drawings_carried:
        # Carried as a picture of the region, drawn from the source at a
        # stated scale (Q01). A separate sentence from the one below, because
        # "the diagram is in the book" and "the diagram is not in the book"
        # are not degrees of the same news.
        report.add(
            "pdf",
            Level.FIX,
            "pdf.drawing-carried",
            values={"count": layout.drawings_carried, "scale": draw.SCALE,
                    "labelled": layout.labelled_drawings},
            location=source,
        )
    if layout.drawing_pages and not layout.drawings_carried:
        # Said because the alternative is a book that quietly lacks every
        # diagram its source had. Two sentences and not one, because the two
        # reasons ask different things of the reader: a missing optional
        # library is something he can install, and a renderer that refused
        # the region is not. Telling him the first as though it were the
        # second would be telling him a fixable thing is impossible.
        if draw.available():
            report.add(
                "pdf",
                Level.WARN,
                "pdf.drawing-not-drawn",
                values={"pages": layout.drawing_pages,
                        "labelled": layout.labelled_drawings},
                location=source,
            )
        else:
            report.add(
                "pdf",
                Level.WARN,
                "pdf.drawing-not-carried",
                values={"pages": layout.drawing_pages,
                        "labelled": layout.labelled_drawings,
                        "missing": draw.why_not()},
                location=source,
            )
    if layout.images_skipped:
        report.add(
            "pdf",
            Level.WARN,
            "pdf.image-skipped",
            values={"count": layout.images_skipped},
            location=source,
        )
    if layout.column_pages:
        report.add(
            "pdf",
            Level.WARN,
            "pdf.columns",
            values={"pages": layout.column_pages},
            location=source,
        )
    if layout.running_heads:
        report.add(
            "pdf",
            Level.INFO,
            "pdf.running-heads-found",
            values={"count": layout.running_heads},
            location=source,
        )


def _say_what_was_not_placed(report: Report, source: str, pages: list[Page]) -> None:
    """The reader's own count against the raw one: a character the page draws
    and no line of this reader carries is a loss that has not happened yet and
    is about to. Said here, with the number, so the K1-PDF refusal that follows
    has its reason on record; the refusal itself is the gate's."""
    placed: Counter = Counter()
    for page in pages:
        # A label lifted onto its picture, or the name written under it, has
        # left `page.lines` and is printed with the picture instead. It is
        # placed; counting only the lines would call it lost.
        texts = [line.text for line in page.lines]
        texts += [line.text for line in page.callouts]
        for picture in page.pictures:
            texts += [line.text for line in picture.labels]
            if picture.caption is not None:
                texts.append(picture.caption.text)
        for text in texts:
            for character in text:
                if not character.isspace():
                    placed[character] += 1
    unplaced = character_inventory(source) - placed
    if unplaced:
        report.add(
            "pdf",
            Level.WARN,
            "pdf.characters-unplaced",
            values={"count": sum(unplaced.values()), "sample": "".join(sorted(unplaced)[:12])},
            location=source,
        )
    report.stats["pdf_characters_unplaced"] = sum(unplaced.values())


def _line_end_words(pages: list[Page]) -> "Counter[str]":
    words: "Counter[str]" = Counter()
    lines = [line.text.strip() for page in pages for line in page.lines if not line.running_head]
    for a, b in zip(lines, lines[1:]):
        if a.endswith("-") and len(a) > 1 and a[-2].isalnum() and b[:1].isalpha():
            left = re.split(r"[^\w-]", a)[-1] if re.split(r"[^\w-]", a) else ""
            right = re.match(r"\w+", b)
            if left and right and left != "-":
                words[f"{left}{right.group(0)}".casefold()] += 1
    return words


def drawn_text(source: str) -> str:
    """Every character the PDF draws, in the order the page tree holds them.

    Deliberately *not* the reader: no lines, no columns, no reading order —
    a walk over every `LTChar` the page tree holds, wherever it sits. It is
    the denominator K1-PDF needs and the reader cannot supply, because a
    construct the reader does not handle is exactly one it would leave out of
    its own count (EF-087). What this cannot say is where a character belongs;
    what it can say is that it existed, and a rebuild that lost it has to
    answer for it. A string rather than a bag so that the fold both sides of
    K1 go through — three dots into an ellipsis, among others — sees the
    dots next to each other.

    The walk is its own; the parse it walks need not be. pdfminer's layout
    analysis is most of what reading a PDF costs, and a rebuild asks for this
    text twice after the reader has parsed the same file (the reader's own
    count, then K1-PDF) — two parses more, for nothing the first had not
    seen. So `_read` walks the pages it parses and leaves the result here,
    keyed by the file's path, size and modification time; a file that changed
    underneath is parsed again.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams

    identity = _identity(source)
    if _DRAWN is not None and _DRAWN[0] == identity:
        return _DRAWN[1]
    pieces: list[str] = []
    for page in extract_pages(source, laparams=LAParams(all_texts=True)):
        _walk_characters(page, pieces)
    return _remember_drawn(identity, "".join(pieces))


#: The last parse's drawn text: (file identity, text). One slot — a rebuild
#: reads one source, and the gate that reads it again comes right after.
_DRAWN: "tuple[tuple, str] | None" = None


def _identity(source: str) -> tuple:
    status = os.stat(source)
    return (os.path.realpath(source), status.st_size, status.st_mtime_ns)


def _remember_drawn(identity: tuple, text: str) -> str:
    global _DRAWN
    _DRAWN = (identity, text)
    return text


def _walk_characters(element, pieces: list) -> None:
    from pdfminer.layout import LTChar

    if isinstance(element, LTChar):
        pieces.append(element.get_text())
        return
    try:
        children = list(element)
    except TypeError:
        return
    for child in children:
        _walk_characters(child, pieces)
    pieces.append(" ")


def character_inventory(source: str) -> "Counter[str]":
    """`drawn_text` as a bag, whitespace left out — the reader's own count is
    held against it in `read_pdf`."""
    return Counter(character for character in drawn_text(source) if not character.isspace())


def text_of(source: str) -> str:
    """Every character of the text layer, whitespace collapsed — the left side
    of K1 for a PDF source, read the way the conversion reads it.

    Not the lines down the page: the *blocks*, in the order the reader takes
    the areas of each page, with the labels lifted onto a drawing standing
    where the drawing stands. The two sides of K1 have to agree about the
    source's order or the subsequence test is asking a different question of
    each — and since pages are cut into areas the order down the page is not
    the reader's. They also agree about where a line break was a space and
    where it was not, because both go through `join_lines`.
    """
    pages, _, _, layout = _read(source)
    body_size = _lay_out_all(pages, layout)
    parts = [
        _picture_text(block.picture) if block.kind == "image"
        else block.text
        for block in _blocks(pages, body_size)
    ]
    return re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip()


def _picture_text(picture: Picture) -> str:
    """The words a picture carries: its name first, then the labels printed on
    it, in the order `_figure` prints them. One place, because both sides of K1
    read it — the source side here and the output side out of the markup."""
    return " ".join(
        line.text.strip()
        for line in ([picture.caption] if picture.caption is not None else []) + list(picture.labels)
    )


def join_lines(lines) -> str:
    """Lines of a paragraph made one string.

    A line break is a space — except after a hyphen-minus, where the
    typesetter broke a word and the break is not a space: `prze-` + `konaniem`
    is `prze-konaniem`, the shape a converter leaves in an EPUB and the one
    the hyphen stage knows how to ask about (a hyphen followed by a space is
    not a candidate there, so joined with a space the word would never have
    been put to anybody). Nothing is joined *into* a word here — the hyphen
    stays, and whether it goes is the hyphen stage's question, with its
    dictionary (D-052). A compound broken at its own hyphen comes back as
    the compound. An en dash or a minus at a line end is not a hyphen and
    gets its space.
    """
    out = ""
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if not out:
            out = text
        elif out.endswith("-") and len(out) > 1 and (out[-2].isalnum()) and text[:1].isalpha():
            out += text
        else:
            out += " " + text
    return out


def _read(source: str):
    """Pages with their lines and pictures, the document info, and the outline."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import (LAParams, LTChar, LTCurve, LTFigure, LTImage,
                                 LTTextContainer, LTTextLine)
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser

    skipped = 0
    pages: list[Page] = []
    pictures_seen = 0
    drawn: list[str] = []
    identity = _identity(source)
    # `all_texts`: text inside a Form XObject — a figure, to pdfminer — is
    # otherwise left as bare characters that no line groups, and this reader
    # walks lines. The independent audit of 2026-09-05 drew a page whose one
    # visible sentence sat in a form: the reader did not see it, the output
    # did not carry it, and K1 — reading through this same reader — said
    # nothing (EF-087). The inventory below is the second opinion — walked
    # here, over the same parse, so that it does not cost a second one.
    sheet = draw.Sheet(source)
    for number, lt_page in enumerate(extract_pages(source, laparams=LAParams(all_texts=True)), 1):
        _walk_characters(lt_page, drawn)
        page = Page(number=number, width=lt_page.width, height=lt_page.height)
        strokes: list = []
        stack = list(lt_page)
        while stack:
            element = stack.pop(0)
            if isinstance(element, LTCurve):
                # `LTLine` and `LTRect` are curves too. Kept as boxes only: what
                # this reader wants from them is where the drawing *is*.
                strokes.append((element.x0, element.y0, element.x1, element.y1))
            elif isinstance(element, LTTextContainer):
                for line in element:
                    if isinstance(line, LTTextLine):
                        chars = [c for c in line if isinstance(c, LTChar)]
                        text = line.get_text().replace("\n", "")
                        if not chars or not text.strip():
                            continue
                        common = Counter(c.fontname for c in chars).most_common(1)[0][0]
                        page.lines.append(Line(
                            text=text,
                            x0=line.x0, x1=line.x1, y0=line.y0, y1=line.y1,
                            size=round(sum(c.size for c in chars) / len(chars), 1),
                            page=number,
                            bold="bold" in common.lower(),
                            runs=_runs(line),
                            family=_family(common),
                        ))
            elif isinstance(element, LTFigure):
                stack[:0] = list(element)
            elif isinstance(element, LTImage):
                pictures_seen += 1
                picture = _picture(element, pictures_seen, number)
                if picture is None:
                    skipped += 1
                else:
                    page.pictures.append(picture)
        page.drawings = _drawings(strokes, page.width, page.height)
        # A drawing this reader cannot draw becomes a picture of itself (Q01).
        # Appended to `pictures` and not to some list of its own, because
        # everything a picture already gets is what a drawing needs: the
        # callouts standing on it are gathered into it, it is emitted as an
        # image block where it stood, and it is written as a resource. A
        # second channel would be a second set of all three.
        pictures_seen = _carry_the_drawings(sheet, page, pictures_seen)
        page.lines.sort(key=lambda line: (-round(line.y1), line.x0))
        split = _two_columns(page)
        page.columns = split is not None
        page.split = split
        _reading_order(page, split)
        pages.append(page)
    sheet.close()
    _remember_drawn(identity, "".join(drawn))

    info: dict = {}
    outline: list[Outline] = []
    unresolved = 0
    with open(source, "rb") as handle:
        parser = PDFParser(handle)
        document = PDFDocument(parser)
        for entry in document.info or ():
            for key, value in entry.items():
                info[key] = _decode(value)
        catalog_lang = document.catalog.get("Lang") if document.catalog else None
        if catalog_lang is not None:
            info.setdefault("Lang", _decode(catalog_lang))
        page_index = {page.pageid: index for index, page in enumerate(PDFPage.create_pages(document), 1)}
        try:
            for level, title, dest, action, _ in document.get_outlines():
                page = _outline_page(document, dest, action, page_index)
                if page is None:
                    unresolved += 1
                    continue
                outline.append(Outline(level=level, title=_decode(title), page=page))
        except Exception:  # noqa: BLE001 — no outline is not an error; a broken one is reported by count
            pass
    layout = Layout(outline_unresolved=unresolved, images_skipped=skipped)
    return pages, info, outline, layout


#: What the font's name says about the face it draws. A name like
#: `UKJILE+MyriadPro-BoldCondIt` carries both marks; `MyriadPro-Cond` neither.
BOLD_NAMES = ("bold", "black", "heavy", "semibold", "demi")
ITALIC_NAMES = ("italic", "oblique", "-it", "it+")


def _face(fontname: str) -> str:
    """"b", "i", "bi" or "" — what the font's name claims about its face."""
    name = (fontname or "").lower()
    style = "b" if any(mark in name for mark in BOLD_NAMES) else ""
    return style + ("i" if any(mark in name for mark in ITALIC_NAMES) else "")


#: Font names that say which of the three generic families the face belongs to.
#: The names of the base fourteen, the families every converter writes, and the
#: word itself — nothing further. A font this reader cannot place is left
#: unplaced (see `Line.family`); the fixed-layout mode then asks for no family
#: at all and the reading system's own is used, which is a smaller lie than a
#: guess. `sans` is looked for before `serif` because `DejaVuSans` is neither
#: `serif` nor a serif.
MONOSPACE_NAMES = ("mono", "courier", "consol")
SANS_NAMES = ("sans", "helvetica", "arial", "verdana", "tahoma", "calibri",
              "myriad", "futura", "frutiger", "gothic", "grotesk", "roboto",
              "segoe", "lato", "opensans")
SERIF_NAMES = ("serif", "times", "georgia", "garamond", "minion", "palatino",
               "cambria", "constantia", "baskerville", "caslon", "roman",
               "bookman", "century")


def _family(fontname: str) -> str:
    """"serif", "sans-serif", "monospace" — or "" when the name says nothing."""
    name = (fontname or "").lower()
    if any(mark in name for mark in MONOSPACE_NAMES):
        return "monospace"
    if any(mark in name for mark in SANS_NAMES):
        return "sans-serif"
    if any(mark in name for mark in SERIF_NAMES):
        return "serif"
    return ""


def _runs(line) -> list:
    """One line cut into runs of a single face, in order.

    Per character and not per line: a manual sets one word of a sentence in
    bold — the name of a button, a warning — and a line measured as a whole
    loses exactly that.
    """
    from pdfminer.layout import LTChar

    runs: list = []
    for char in line:
        text = char.get_text()
        if text == "\n":
            continue
        style = _face(char.fontname) if isinstance(char, LTChar) else (runs[-1][1] if runs else "")
        if runs and runs[-1][1] == style:
            runs[-1][0] += text
        else:
            runs.append([text, style])
    return [(text, style) for text, style in runs if text]


def _decode(value) -> str:
    from pdfminer.utils import decode_text

    try:
        from pdfminer.pdftypes import resolve1

        value = resolve1(value)
    except Exception:  # noqa: BLE001
        pass
    if isinstance(value, bytes):
        try:
            return decode_text(value).strip()
        except Exception:  # noqa: BLE001
            return value.decode("latin-1", "replace").strip()
    if hasattr(value, "name"):
        return str(value.name)
    return str(value).strip() if value is not None else ""


def _outline_page(document, dest, action, page_index: dict) -> int | None:
    from pdfminer.pdftypes import resolve1

    try:
        if dest is None and action is not None:
            action = resolve1(action)
            if isinstance(action, dict):
                dest = action.get("D")
        if isinstance(dest, (str, bytes)) or hasattr(dest, "name"):
            dest = document.get_dest(dest if isinstance(dest, bytes) else getattr(dest, "name", dest))
        dest = resolve1(dest)
        if isinstance(dest, dict):
            dest = resolve1(dest.get("D"))
        if isinstance(dest, list) and dest:
            first = dest[0]
            objid = getattr(first, "objid", None)
            if objid in page_index:
                return page_index[objid]
            if isinstance(first, int) and 0 <= first < len(page_index):
                return first + 1
    except Exception:  # noqa: BLE001
        return None
    return None


#: A printed contents page is at least this many rows. Fewer is a table that
#: happens to end in a number — a price, a capacity, a temperature.
ROWS_FOR_A_CONTENTS = 4
#: What a section number at the head of a contents entry looks like, and how
#: deep it goes: "1", "1.1", "3.2.1".
CONTENTS_NUMBER = re.compile(r"^(\d{1,3}(?:\.\d{1,3})*)[.)]?\s")


def printed_pages(pages: list[Page]) -> dict:
    """{the number printed on a page: the page it is printed on}.

    The page numbers are the ones `_mark_running_heads` already found — a line
    that repeats at the same height on most pages, holding nothing but digits.
    A contents page names the *printed* number, and the book has to be opened
    at the page that carries it; the two are the same in a file that starts its
    numbering at the first page and not otherwise.
    """
    seen: list = []
    for page in pages:
        for line in page.lines:
            text = line.text.strip()
            if line.running_head and text.isdigit():
                seen.append((int(text), page.number))
    if not seen:
        return {}
    # One offset, measured. A contents page carries its *own* page numbers
    # down the right margin, and the ones near the foot are marked as running
    # heads like any other bare number — so page three of the owner's manual
    # offered "60" and "24" as its number. What tells a page number from a
    # contents entry's number is that all the real ones stand the same
    # distance from the leaf they are printed on.
    offset = Counter(number - where for number, where in seen).most_common(1)[0][0]
    return {number: where for number, where in seen if number - where == offset}


def contents_entries(pages: list[Page]) -> "list[Outline]":
    """The book's own printed table of contents, read as an outline.

    A PDF with bookmarks says where its parts begin and this reader believes
    it. A PDF without them very often *prints* the same thing on page two:
    a title at the left, leader dots, and the page number at the right margin.
    Those are the two ends of one line of the page — `_reading_runs` already
    tells them apart — and the number is the one the book prints on the page
    it names, which `printed_pages` can look up.

    Read from the page's rows and not from the blocks, because half of such a
    line comes out a table row and half comes out joined into a paragraph,
    depending on how wide the leader is.

    Checked against a file that has both: on the owner's 105-page manual the
    printed contents gives 71 entries and **every one names the page the PDF's
    own bookmarks name**. Nothing here is guessed; the leader is the
    typesetter saying "this title, that page".
    """
    printed = printed_pages(pages)
    last = len(pages)
    best: list = []
    run: list = []
    where = 0
    for page in pages:
        body = [line for line in page.lines if not line.running_head]
        for row in _rows(_in_order(body)):
            entry = _contents_row(_reading_runs(row), printed, last)
            if entry is None:
                # A line that is not an entry — the words "Spis treści", a
                # rule, a stray — does not end the contents it stands in.
                continue
            # What ends it: a page named before the one named above it, or a
            # gap of more than a leaf. A printed contents runs on; two tables
            # forty pages apart are two tables.
            if run and (entry.page < run[-1].page or page.number > where + 1):
                if len(run) > len(best):
                    best = run
                run = []
            run.append(entry)
            where = page.number
    if len(run) > len(best):
        best = run
    return best if len(best) >= ROWS_FOR_A_CONTENTS else []


def _contents_row(runs: list, printed: dict, last: int) -> "Outline | None":
    """One line of a printed contents as an outline entry, or None.

    The line has to end in a bare number standing on its own — the leader put
    it there — and to begin with something that reads like a title.
    """
    if len(runs) < 2:
        return None
    number = "".join(line.text for line in runs[-1]).strip()
    title = " ".join(line.text.strip() for run in runs[:-1] for line in run).strip()
    if not number.isdigit() or not title or not _reads_like_a_heading(title):
        return None
    page = printed.get(int(number))
    if page is None or not 1 <= page <= last:
        return None
    found = CONTENTS_NUMBER.match(title)
    level = found.group(1).count(".") + 1 if found else 1
    return Outline(level=level, title=title, page=page)


def _picture(image, number: int, page: int) -> Picture | None:
    """The image's bytes as a file the reader can show: JPEG as it is, Flate
    through Pillow into PNG; anything else is skipped and counted."""
    # `get_filters()` yields `(name, parameters)` pairs, the name a PSLiteral.
    try:
        filters = [
            getattr(entry[0] if isinstance(entry, tuple) else entry, "name", str(entry))
            for entry in image.stream.get_filters()
        ]
    except Exception:  # noqa: BLE001
        filters = []
    filters = [f for f in filters if isinstance(f, str)]
    try:
        if "DCTDecode" in filters:
            return Picture(f"images/pdf-{number:04d}.jpg", image.stream.get_rawdata(), "image/jpeg",
                           page, image.y1, image.x0, image.x1, image.y0)
        if "JPXDecode" in filters:
            data = _png_via_pillow(io.BytesIO(image.stream.get_rawdata()))
            return Picture(f"images/pdf-{number:04d}.png", data, "image/png", page, image.y1,
                           image.x0, image.x1, image.y0) if data else None
        width, height = image.srcsize
        bits = image.bits or 8
        mode = _pillow_mode(image.colorspace)
        if mode is None or bits != 8:
            return None
        from PIL import Image

        raw = image.stream.get_data()
        picture = Image.frombytes(mode, (width, height), raw)
        out = io.BytesIO()
        picture.save(out, format="PNG")
        return Picture(f"images/pdf-{number:04d}.png", out.getvalue(), "image/png", page, image.y1,
                       image.x0, image.x1, image.y0)
    except Exception:  # noqa: BLE001 — an image this cannot decode is skipped and counted, never invented
        return None


def _pillow_mode(colorspace) -> str | None:
    """Pillow's name for the PDF's colour space, or None for one this will
    not guess at: the device spaces by name, an ICC-based space by its
    number of components (the profile itself is not applied — the pixels are
    carried as they are, which is what a reading system gets from any PNG)."""
    from pdfminer.pdftypes import resolve1

    spec = colorspace
    if isinstance(spec, list) and spec:
        family = _decode(spec[0])
        if family == "ICCBased" and len(spec) > 1:
            try:
                profile = resolve1(spec[1])
                components = resolve1(profile.get("N")) if hasattr(profile, "get") else None
            except Exception:  # noqa: BLE001
                components = None
            return {1: "L", 3: "RGB", 4: "CMYK"}.get(components)
        spec = spec[0]
    return {"DeviceRGB": "RGB", "DeviceGray": "L", "DeviceCMYK": "CMYK"}.get(_decode(spec))


def _png_via_pillow(handle) -> bytes | None:
    try:
        from PIL import Image

        out = io.BytesIO()
        Image.open(handle).save(out, format="PNG")
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


#: A drawing is where the page's vector strokes cluster, and the grid they are
#: counted on is coarse on purpose: a diagram is drawn as thousands of separate
#: curves, and what makes them one picture is that they touch.
DRAWING_CELL = 12.0
#: A stroke covering more than this share of the page is a background or a
#: border round the whole page, not part of a drawing.
DRAWING_STROKE_MAX = 0.5
#: A cluster smaller than this many cells, or thinner than this many cells
#: either way, is a rule under a heading or a box round a note. Measured on the
#: owner's manual: the band across the head of every page is 27 cells by 2, and
#: the drawing on page 6 — the one with eleven callouts on it — is 23 by 17.
CELLS_FOR_A_DRAWING = 20
CELLS_ACROSS_A_DRAWING = 3
#: And a drawing lays down more strokes than it covers cells: artwork piles
#: curve on curve, while the run of leader dots between a contents entry and
#: its page number lays exactly one stroke in each cell it crosses. Swept over
#: the manual, that difference is a cliff: at one stroke per cell 93 pages of
#: 105 hold a "drawing", at one and a half 43, at two 39, at three 33. The
#: leaders and the rules drop out at the cliff and nothing else moves.
DRAWING_DENSITY = 2.0


def _carry_the_drawings(sheet, page: "Page", seen: int) -> int:
    """Turn each of this page's drawings into a picture of itself (Q01).

    Returns the running picture count, because the names come off it and a
    drawing is numbered in the same sequence as a raster — one namespace for
    the images of one book.

    A region that overlaps a picture the page already carries is skipped: a
    photograph with a frame drawn round it is one illustration, and carrying
    both would put it in the book twice.
    """
    if not page.drawings:
        return seen
    for box in page.drawings:
        if any(_overlaps(box, (p.x0, p.y0, p.x1, p.y1)) for p in page.pictures):
            continue
        data = sheet.region(page.number, box, page.height)
        if data is None:
            continue
        seen += 1
        x0, y0, x1, y1 = box
        page.pictures.append(Picture(
            f"images/pdf-{seen:04d}.png", data, "image/png",
            page.number, y1, x0=x0, x1=x1, y0=y0, drawn=True,
        ))
    return seen


def _overlaps(one, other) -> bool:
    """Whether two boxes share any area."""
    ax0, ay0, ax1, ay1 = one
    bx0, by0, bx1, by1 = other
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def _drawings(strokes: list, width: float, height: float) -> list:
    """The boxes of the page's vector drawings, as `(x0, y0, x1, y1)`.

    This reader carries pictures and does not draw, so a diagram made of curves
    is not in the rebuilt book at all — but the text printed *on* it is, and
    without knowing where the drawing stands that text is a heap of one-word
    paragraphs. On the owner's manual page 6 the diagram of the machine is
    vector: no picture on the page, eleven callouts round it, `A1` to `A11`.
    """
    touched: Counter = Counter()
    for x0, y0, x1, y1 in strokes:
        if (x1 - x0) * (y1 - y0) > DRAWING_STROKE_MAX * width * height:
            continue
        for cx in range(int(x0 // DRAWING_CELL), int(x1 // DRAWING_CELL) + 1):
            for cy in range(int(y0 // DRAWING_CELL), int(y1 // DRAWING_CELL) + 1):
                touched[(cx, cy)] += 1
    found = []
    for group in _clusters(set(touched)):
        xs = [cell[0] for cell in group]
        ys = [cell[1] for cell in group]
        across, down = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        if (len(group) < CELLS_FOR_A_DRAWING
                or across < CELLS_ACROSS_A_DRAWING or down < CELLS_ACROSS_A_DRAWING
                or sum(touched[cell] for cell in group) < DRAWING_DENSITY * len(group)):
            continue
        found.append((min(xs) * DRAWING_CELL, min(ys) * DRAWING_CELL,
                      (max(xs) + 1) * DRAWING_CELL, (max(ys) + 1) * DRAWING_CELL))
    return found


def _clusters(cells: set) -> list:
    """Cells that touch, gathered — corners count, so a diagonal stroke does
    not split the drawing it is part of."""
    seen: set = set()
    groups = []
    for start in cells:
        if start in seen:
            continue
        seen.add(start)
        stack, group = [start], []
        while stack:
            cx, cy = stack.pop()
            group.append((cx, cy))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbour = (cx + dx, cy + dy)
                    if neighbour in cells and neighbour not in seen:
                        seen.add(neighbour)
                        stack.append(neighbour)
        groups.append(group)
    return groups


def _two_columns(page: Page) -> "float | None":
    """Two clusters of left edges, each narrower than half the page: columns.
    Returns the x that divides them, or None for a single column."""
    body = [line for line in page.lines if not line.running_head]
    if len(body) < 8:
        return None
    starts = Counter(round(line.x0 / 10) * 10 for line in body)
    common = [x for x, count in starts.most_common(2) if count >= 3]
    if len(common) < 2:
        return None
    left, right = sorted(common)
    if right - left <= page.width * 0.35:
        return None
    if any((line.x1 - line.x0) >= page.width * 0.55 for line in body):
        return None
    # Two columns are two *stacks*: most lines start at one edge or the
    # other, and none straddles the divide. A centred title page has many
    # short lines at many left edges and passed the two tests above — and
    # read column by column it came back in the wrong order (the Gutenberg
    # corpus printed by Chromium, one book, its title page).
    left_stack = [line for line in body if abs(line.x0 - left) <= 20]
    right_stack = [line for line in body if abs(line.x0 - right) <= 20]
    if len(left_stack) + len(right_stack) < 0.7 * len(body):
        return None
    # The divide is the gutter — between where the left stack ends and the
    # right one begins — not the midpoint of the two left edges: a left
    # column's lines reach well past that midpoint.
    rights = sorted(line.x1 for line in left_stack)
    left_edge_end = rights[int(0.9 * (len(rights) - 1))]
    if left_edge_end >= right:
        return None
    split = (left_edge_end + right) / 2
    straddling = sum(1 for line in body if line.x0 < split < line.x1)
    if straddling > 0.1 * len(body):
        return None
    return split


def _widest_gap(spans: "list[tuple[float, float]]") -> "tuple[float, float] | None":
    """The widest run with nothing over it: `(width, where it is cut)`.

    The spans are merged first, so a gap is a place *no* line reaches — not
    the space beside one short line with another line above it.
    """
    if len(spans) < 2:
        return None
    ordered = sorted(spans)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    if len(merged) < 2:
        return None
    best = max(
        ((merged[i + 1][0] - merged[i][1], (merged[i + 1][0] + merged[i][1]) / 2)
         for i in range(len(merged) - 1)),
        key=lambda pair: pair[0],
    )
    return best


def _regions(lines: "list[Line]", width: float, height: float,
             split: "float | None" = None, grouped: "list | None" = None,
             depth: int = 0) -> "list[list[Line]]":
    """The page cut into the areas a person reads one after another.

    The recursive XY cut, in the order that is safe for reading: a band across
    the page first, and — on a page set in columns — the columns within a band.
    Both are needed and neither alone is enough: a heading over two columns is
    a band, and the two columns under it are not.

    The band is what "one column, or two" could not do. The page that made it
    necessary is a manual whose legend stands at a fixed x while the drawing
    beside it carries the same labels; read straight down, a wrapped legend
    entry is cut in half by a label — 26 % of that book's paragraphs
    (`pdf.reading-quality-poor`), 2 % once the page is read by area.

    **The vertical cut may not go through a table.** Things standing side by
    side are sometimes read *across* — that is what a table is — and cutting on
    any wide vertical gap read one Gutenberg book's errata table (page number,
    misprint, correction) as three lists, every page number before every
    misprint, until K1 refused the rebuild. The gate was right. The answer is
    not to forbid the cut but to *know where the tables are*: `_grouped` holds
    the cells of every grid `_tables` found on the page, and no cut separates
    two cells of one grid. Everything else standing side by side is two areas
    and is read one after the other.

    *split* is what `_two_columns` measured on the whole page, and it overrules
    the grid: two columns of prose stand on shared baselines and look exactly
    like a table's rows, so on a page measured to be in columns the cut is what
    was wanted all along. Where the cut cannot be made at all — a column whose
    longest line reaches past the gutter leaves no gap to cut on — the lines are
    still ordered by it (`_in_order`).
    """
    if len(lines) <= 1 or depth >= REGION_DEPTH:
        return [_in_order(lines, split)] if lines else []
    # A band, when the gap is wider than any ordinary space between
    # paragraphs. Taken before a column split because top-to-bottom is always
    # the reading order and left-to-right is only ever true inside a band.
    across = _widest_gap([(line.y0, line.y1) for line in lines])
    if across and across[0] >= BAND_SHARE * height:
        cut = across[1]
        upper = [line for line in lines if (line.y0 + line.y1) / 2 > cut]
        lower = [line for line in lines if (line.y0 + line.y1) / 2 <= cut]
        if upper and lower:
            return (_regions(upper, width, height, split, grouped, depth + 1)
                    + _regions(lower, width, height, split, grouped, depth + 1))
    down = _widest_gap([(line.x0, line.x1) for line in lines])
    if down and down[0] >= GUTTER_SHARE * width:
        cut = down[1]
        left = [line for line in lines if (line.x0 + line.x1) / 2 < cut]
        right = [line for line in lines if (line.x0 + line.x1) / 2 >= cut]
        if left and right and (split is not None
                               or not _splits_a_grid(left, right, grouped)):
            return (_regions(left, width, height, split, grouped, depth + 1)
                    + _regions(right, width, height, split, grouped, depth + 1))
    return [_in_order(lines, split)]


def _grouped(lines: "list[Line]") -> list:
    """The cells of every grid on this page, one set of ids per grid.

    Read before the page is cut, because what a cut must not do is separate two
    cells of one row: a table is the one thing on a page that is read *across*.
    """
    return [{id(cell) for row in run for cell in row} for run in _tables(_in_order(lines))]


def _splits_a_grid(left: "list[Line]", right: "list[Line]", grouped: "list | None") -> bool:
    here = {id(line) for line in left}
    there = {id(line) for line in right}
    return any(cells & here and cells & there for cells in (grouped or ()))


def _in_order(lines: "list[Line]", split: "float | None" = None) -> "list[Line]":
    """The lines in the order a person takes them: down, then across.

    *split* is the x that divides a page set in two columns, and it is the
    answer of last resort. Normally the columns are areas of their own and each
    is sorted inside itself, so the split changes nothing. But a column whose
    longest line reaches past the gutter — a URL on a Gutenberg title page —
    leaves no gap for `_regions` to cut on, and then the whole page is one area
    and sorting it down-then-across reads the two columns line about. The page
    was measured to be in columns; that measurement is not thrown away because
    the cut could not be made.
    """
    if split is None:
        return sorted(lines, key=lambda line: (-round(line.y1), line.x0))
    return sorted(lines, key=lambda line: (0 if line.x0 < split else 1, -round(line.y1), line.x0))


def _lift_labels(page: Page) -> None:
    """Move short lines that stand on a drawing out of the text and onto it.

    A callout label — the "A16" beside an arrow — is text about the picture,
    not a paragraph of the book. Left in the flow it is a one-word paragraph
    at best and, when it falls between two lines of a legend, the thing that
    cuts a sentence in half. It goes with the picture, which is where a person
    reading the picture will look for it.
    """
    if not page.pictures:
        return
    pitch = _pitch(page)
    kept: list[Line] = []
    for line in page.lines:
        text = line.text.strip()
        if line.running_head or not _is_a_fragment(text):
            kept.append(line)
            continue
        inside = next((p for p in page.pictures if p.holds(line)), None)
        if inside is not None:
            inside.labels.append(line)
            continue
        # A name written under the picture — "Americano" under the icon of it.
        # Only one, and only if it reads as words: the bullet that opens a list
        # under a figure also stands under the figure, and is not its name.
        named = next(
            (p for p in page.pictures
             if not p.caption and p.is_named_by(line, pitch) and _reads_like_a_heading(text)),
            None,
        )
        if named is not None:
            named.caption = line
        else:
            kept.append(line)
    page.lines = kept


def _is_a_fragment(text: str) -> bool:
    """A word or two with no sentence in them: a label, not a paragraph."""
    return bool(text) and len(text.split()) <= FRAGMENT_WORDS and text[-1:] not in tuple(SENTENCE_ENDS)


#: What a callout looks like: the marker of a legend entry with its letter and
#: its number together — `A16`, `B1`, `E7`. Deliberately not a bare number:
#: `1.` and `2.` open the steps of a procedure, and a step is not a callout.
CALLOUT = re.compile(r"^[A-Z]{1,2}\d{1,3}$")


def callout_names(pages: list) -> set:
    """The markers that open a legend entry somewhere in this document.

    Evidence from the file rather than from its geometry. A legend reads
    "A16. Wskaźnik poziomu wody w tacce", so `A16` names a part of the machine;
    the same `A16` printed alone beside an arrow on the drawing is a *callout*,
    pointing back at that entry. Nothing else in a book looks like that, and no
    threshold is needed to say so.
    """
    names = set()
    for page in pages:
        # By the row, not by the line: a legend that sets its marker and its
        # entry as two lines on one baseline — "A6." and "Tacka na skropliny"
        # beside it — names `A6` just as plainly as one that sets them as one
        # line, and reading only whole lines missed exactly those.
        for row in _rows(_in_order(page.lines)):
            for run in _reading_runs(row):
                text = " ".join(line.text.strip() for line in run).strip()
                marker = _marker(text)
                if marker and text[len(marker):].strip() and CALLOUT.match(marker.strip(".)( ")):
                    names.add(marker.strip(".)( "))
    return names


def _is_a_callout(text: str, names: set) -> bool:
    """Whether this whole line is nothing but callouts — `A16`, or `B1 B4`."""
    tokens = text.split()
    return bool(tokens) and all(token.strip(".,)(") in names for token in tokens)


def _lift_callouts(page: Page, names: set) -> None:
    """Take the callouts printed on a drawing out of the prose.

    Where the drawing is a picture, `_lift_labels` puts the callout on it.
    Where the drawing is drawn — curves, which this reader cannot carry — there
    is no picture to put it on, and the callouts stayed in the flow: on the
    owner's manual, two hundred one-word paragraphs, and worse than that. A
    single `A15` standing between the two lines of a legend entry was read
    *into* it, so the entry came out "A16. Wskaźnik poziomu wody w tacce A15 na
    skropliny" — the exact damage the area model was built to undo, done by one
    stray word instead of by the reading order.

    So they leave the flow together and are printed where the first of them
    stood, which is where the drawing is.
    """
    if not names:
        return
    kept: list[Line] = []
    for row in _rows(_in_order(page.lines)):
        # By the *run*, not the baseline: a legend often sets its marker and
        # its entry as two lines on one line of the page — "B1." at the left
        # edge, "Zbiornik na wodę" a word's width away — and that run is the
        # entry, name and all. A callout is a run of its own, with a column of
        # white on either side of it.
        for run in _reading_runs(row):
            if all(not line.running_head and _is_a_callout(line.text.strip(), names)
                   for line in run):
                page.callouts.extend(run)
            else:
                kept.extend(run)
    page.lines = _in_order(kept)


def _lay_out(page: Page, names: "set | None" = None) -> None:
    """Give the page its regions, and its lines in the order they are read.

    Running heads take no part in the cutting. A head at the top of a page is
    a band of its own by any measure, and a page cut under it would lose the
    one thing the head's position tells us: that the paragraph it interrupts
    continues below it. So the areas are found among the body lines, and each
    head then joins the area it stands over.
    """
    _lift_labels(page)
    # After the pictures: a callout inside a picture's box has a home to go to,
    # and going there is better than being gathered with the loose ones.
    _lift_callouts(page, names or set())
    body = [line for line in page.lines if not line.running_head]
    heads = [line for line in page.lines if line.running_head]
    regions = _regions(body, page.width, page.height, page.split, _grouped(body))
    for index, region in enumerate(regions):
        for line in region:
            line.region = index
    for head in heads:
        below = [line for line in body if line.y1 < head.y1]
        head.region = (
            max(below, key=lambda line: line.y1).region if below
            else (len(regions) - 1 if regions else 0)
        )
    page.regions = [
        _in_order(list(region) + [h for h in heads if h.region == index], page.split)
        for index, region in enumerate(regions)
    ] or ([_in_order(heads, page.split)] if heads else [])
    page.lines = [line for region in page.regions for line in region]


def _reading_order(page: Page, split: "float | None") -> None:
    """Sort the page's lines the way a reader takes them: top to bottom, and
    on a two-column page the left column whole before the right one.

    Measured before this existed, on the corpus typeset in two columns by
    reportlab: lines taken in page order interleaved the columns, so a word
    broken at the end of a left-hand line was joined to the first word of
    the right-hand line beside it — 1 123 hyphenated words the source never
    had, 2 715 words missing, on one book. Two columns are still not
    re-flowed and still reported (`pdf.columns`); they are only read in
    order. A line that straddles the divide (a centred running head, a
    heading across both columns) goes with the column its left edge is in.
    """
    if split is None:
        page.lines.sort(key=lambda line: (-round(line.y1), line.x0))
        return
    page.lines.sort(key=lambda line: (0 if line.x0 < split else 1, -round(line.y1), line.x0))


# ------------------------------------------------------------ structure


def _mark_running_heads(pages: list[Page], layout: Layout) -> None:
    if len(pages) < RUNNING_HEAD_MIN_PAGES:
        return
    seen: Counter = Counter()
    keys: dict[int, list[tuple[Line, tuple]]] = {}
    for page in pages:
        for line in page.lines:
            top = line.y1 >= page.height * (1 - MARGIN_SHARE)
            bottom = line.y0 <= page.height * MARGIN_SHARE
            if not (top or bottom):
                continue
            # Keyed by the edge and the text, digits made equal; not by the
            # exact height, which a printer lets drift across pages — on a
            # 137-page print the footer sat in two height buckets and a
            # third of it went unrecognised.
            key = (top, re.sub(r"\d+", "#", line.text.strip()).lower())
            keys.setdefault(page.number, []).append((line, key))
        # Counted once per page, so a page that repeats its own header twice
        # does not count as two pages.
        for key in {k for _, k in keys.get(page.number, [])}:
            seen[key] += 1
    # A head that stands on every page, or on every left-hand or every
    # right-hand page: the author on the verso and the title on the recto is
    # the commonest arrangement in print, and each of those is on half the
    # pages. A head that changes with the chapter is not caught here; the
    # report says how many lines were found, and a person sees the rest.
    on_odd: Counter = Counter()
    for page in pages:
        for key in {k for _, k in keys.get(page.number, [])}:
            if page.number % 2:
                on_odd[key] += 1
    threshold = max(2, int(RUNNING_HEAD_SHARE * len(pages)))
    one_side = max(2, int(RUNNING_HEAD_SHARE * len(pages) / 2))
    for page in pages:
        for line, key in keys.get(page.number, []):
            count = seen[key]
            odd = on_odd[key]
            if count >= threshold or (count >= one_side and odd in (0, count)):
                line.running_head = True


def _body_face(pages: list[Page]) -> str:
    """The face the document is *set* in, by weight of characters.

    A manual set throughout in a bold condensed face is not one long shout, so
    what counts as a mark is a face that differs from this one.
    """
    weight: Counter = Counter()
    for page in pages:
        for line in page.lines:
            for text, style in line.runs:
                weight[style] += len(text)
    return weight.most_common(1)[0][0] if weight else ""


def _body_size(pages: list[Page]) -> float:
    weights: Counter = Counter()
    for page in pages:
        for line in page.lines:
            if not line.running_head:
                weights[line.size] += len(line.text)
    return weights.most_common(1)[0][0] if weights else 0.0


@dataclass
class Block:
    kind: str  # "p", "h1", "h2", "head" (running head), "image", "table"
    lines: list[Line] = field(default_factory=list)
    picture: Picture | None = None
    #: A paragraph a running head cut in two; this is the second half.
    continued: bool = False
    #: A table's cells, row by row. `lines` holds the same cells flat, so
    #: everything that counts lines counts a table's without knowing about it.
    rows: list = field(default_factory=list)

    @property
    def text(self) -> str:
        if self.kind == "table":
            # Cells are not one paragraph broken across lines: a hyphen at the
            # end of a cell is the cell's own word, so they join with a space.
            return " ".join(cell.text.strip() for row in self.rows for cell in row)
        if self.kind == "labels":
            return " ".join(line.text.strip() for line in self.lines)
        return join_lines(line.text for line in self.lines)


def _heading_level(line: Line, body_size: float) -> str | None:
    if body_size <= 0 or not _reads_like_a_heading(line.text):
        return None
    if line.size >= body_size * BODY_RATIO_H1:
        return "h1"
    if line.size >= body_size * BODY_RATIO_H2:
        return "h2"
    return None


def _reads_like_a_heading(text: str) -> bool:
    """Whether a line set larger than the body is a *title*.

    Size alone is not enough, and the owner's manual said so with numbers: on
    its 105 pages, "larger than the body" promoted **74 lines and not one of
    them was a heading** — tick marks from a table (`✓ ✕`), the figures in its
    cells (`3 1 4`), quantities (`0,5 L`, `2,0L`), arrows, and the markers of
    a legend (`A6.`, `B1.`, `E7.`). Body text there is 9 pt, so a great deal
    of small furniture clears 1.25 times it.

    What those have in common is what a title never does: **a title is mostly
    letters.** `A6` is half letters, `0,5 L` a quarter, `✓ ✕` none; `I`, `II`
    and the product's name over the page are all of them. Punctuation at the
    ends is not counted, or the roman numeral `I.` that opens a chapter would
    fail on its own full stop — eleven of those across the Gutenberg corpus,
    every one a real heading.

    Measured: the manual goes from 74 headings to 10 — and those ten are all
    the product's name standing over a page, which is at least a name — while
    the Gutenberg corpus keeps all 127 of the headings it had.
    """
    core = text.strip().strip(".,)(:;-–—[]")
    letters = sum(1 for character in core if character.isalpha())
    written = sum(1 for character in core if not character.isspace())
    return written > 0 and letters * 2 > written


def _blocks(pages: list[Page], body_size: float, breaks: set[int] = frozenset()) -> list[Block]:
    """Lines joined into paragraphs and headings, pictures in the flow.

    The unit is the **region**, not the page: a paragraph never runs from one
    area of the page into another, because those are two things a person reads
    one after the other rather than one thing that continues. That is what
    stops a legend beside a drawing from being cut in half by the drawing's
    own labels.

    A page in *breaks* is one the outline names as a chapter's first, and a
    paragraph does not run into a new chapter: the first line there starts a
    block whatever the geometry says.
    """
    flow = _Flow()
    for page in pages:
        _page_blocks(page, flow, body_size, breaks)
    return flow.blocks


@dataclass
class _Flow:
    """What the reader carries from one line to the next — across the areas of
    a page and across pages, because a paragraph crosses both."""

    blocks: "list[Block]" = field(default_factory=list)
    current: "Block | None" = None
    previous: "Line | None" = None
    #: The left edge and width of the area the *previous* line stood in, which
    #: is not always the area the current one stands in.
    left: float = 0.0
    width: float = 0.0
    #: A running head stands between the two halves of a paragraph; the half
    #: after it is marked so the stage that rejoins them can find it.
    interrupted: bool = False


@dataclass
class _Area:
    """One area of a page, measured on its own lines.

    Measured on the region rather than the page because against the page's
    left edge every line of a right-hand column looks indented and starts a
    paragraph — 5 552 paragraphs where the source had 2 036.
    """

    page: Page
    left: float
    width: float
    #: A list whose continuation lines are indented under a marker.
    hanging: bool
    #: The page's line pitch, which says how much space is more than a
    #: paragraph ever leaves.
    pitch: float
    #: Whether the line being placed is the area's first.
    first: bool = True


def _page_blocks(page: Page, flow: "_Flow", body_size: float, breaks: set[int]) -> None:
    """One page's areas, in reading order, with what stands beside them."""
    pitch = _pitch(page)
    regions = page.regions or ([page.lines] if page.lines else [])
    standing = [Block(kind="image", picture=picture) for picture in page.pictures]
    heights = {id(block): block.picture.y1 for block in standing}
    if page.callouts:
        block = Block(kind="labels", lines=list(page.callouts))
        heights[id(block)] = max(line.y1 for line in page.callouts)
        standing.append(block)
    standing.sort(key=lambda block: -heights[id(block)])
    placed = 0
    for region in regions:
        if not region:
            continue
        # A picture, or the callouts of a drawing, stand where they stand:
        # before the first area whose top is below them.
        top = max(line.y1 for line in region)
        while placed < len(standing) and heights[id(standing[placed])] > top:
            _stands_between(flow, standing[placed])
            placed += 1
        left, width = _region_geometry(region, page)
        area = _Area(page=page, left=left, width=width,
                     hanging=_hanging_indent(region, left), pitch=pitch)
        _area_blocks(region, area, flow, body_size, breaks)
    for block in standing[placed:]:
        _stands_between(flow, block)


def _stands_between(flow: "_Flow", block: "Block") -> None:
    """Put a picture, or the callouts of a drawing, into the flow — and end
    whatever paragraph stood above it, as `_tables` does for a grid.

    Nothing runs through a picture, and until this said so the order of the
    blocks was not the order the page is read in. A paragraph running from the
    foot of one page to the head of the next stays *open* while the picture
    below it is appended, so reading the blocks in order gave the next page's
    text before the picture that stands on this one. It cost nothing while one
    renderer read the blocks in the same wrong order as the check did; the
    fixed-layout mode cannot, because there each page is its own document, and
    K1 found it at once.
    """
    flow.blocks.append(block)
    flow.current = flow.previous = None


def _area_blocks(region: "list[Line]", area: "_Area", flow: "_Flow",
                 body_size: float, breaks: set[int]) -> None:
    """The lines of one area, joined into tables, paragraphs and headings."""
    grids = _tables(region)
    opens = {id(run[0][0]): run for run in grids}
    inside = {id(cell) for run in grids for row in run for cell in row}
    for line in region:
        run = opens.get(id(line))
        if run is not None:
            flow.blocks.append(Block(kind="table", rows=run,
                                     lines=[cell for row in run for cell in row]))
            # A table ends whatever stood before it and starts whatever comes
            # after: nothing runs through a grid.
            flow.current = flow.previous = None
            area.first = False
            continue
        if id(line) in inside:
            continue
        if line.running_head:
            flow.blocks.append(Block(kind="head", lines=[line]))
            # The head is furniture, not the area's first line: the body line
            # under it continues whatever the head cut in two, which is the
            # whole point of marking it.
            area.first = False
            flow.interrupted = flow.current is not None and flow.current.kind == "p"
            continue
        kind = _heading_level(line, body_size) or "p"
        if _starts_a_block(line, kind, flow, area, breaks):
            flow.current = Block(kind=kind)
            flow.blocks.append(flow.current)
        elif flow.interrupted:
            flow.current = Block(kind=kind, continued=True)
            flow.blocks.append(flow.current)
        flow.interrupted = False
        area.first = False
        flow.current.lines.append(line)
        flow.previous, flow.left, flow.width = line, area.left, area.width


def _starts_a_block(line: Line, kind: str, flow: "_Flow", area: "_Area",
                    breaks: set[int]) -> bool:
    """Whether *line* begins a block rather than continuing the one before it."""
    if flow.current is None or flow.current.kind != kind:
        return True
    previous = flow.previous
    if previous is None:
        return False
    # Two areas **of one page** are two things read one after the other —
    # except on a page set in two columns of one body, where the paragraph at
    # the foot of the left column is the one at the head of the right. That
    # page is recognised by `_two_columns`, which is measured.
    #
    # Of one page, and the words matter: the first area of a *new* page is not
    # a new area, it is the same reading carried over the fold. Cutting there
    # split every paragraph that runs from the foot of one page to the head of
    # the next — and with it every word the typesetter broke across that fold,
    # which came out as two words. Measured on the substitute corpus: it put
    # 78 paragraphs into *Pan Tadeusz* that the book does not have.
    if area.first and not area.page.columns and previous.page == line.page:
        return True
    # Text carrying on along one line of the page is one paragraph: "A6." at
    # the left edge and "Tacka na skropliny" a word's width away are a legend
    # entry, and read as two paragraphs the entry loses its name. Far apart on
    # the same baseline they are two columns instead — a table's row, which
    # `_tables` has already taken, or a callout beside a legend, which
    # `_lift_callouts` has.
    if _reads_on(previous, line):
        return False
    # A paragraph does not run into a new chapter.
    if line.page != previous.page and line.page in breaks:
        return True
    # More space above this line than a paragraph ever leaves.
    if previous.page == line.page and previous.y0 - line.y1 > PARAGRAPH_GAP_RATIO * area.pitch:
        return True
    return kind == "p" and _starts_a_paragraph(line, flow, area)


def _starts_a_paragraph(line: Line, flow: "_Flow", area: "_Area") -> bool:
    """The marks of a new paragraph in prose: an indent, a list marker, or a
    line before it that ended short of its own area's edge."""
    # An indent starts a paragraph in prose and continues one in a list; in a
    # list the *marker* is what starts it.
    #
    # And an indent is a line set in from the ones *around* it, not a whole
    # block set in from the page. A manual's list of teas stands forty points
    # inside the body's edge, every line of it, so every line looked indented
    # and eight lines came out as eight paragraphs — "Herbata Biała", then
    # "czas parzenia 1-3 minuty" under it as another. The line above has to be
    # at the block's own edge for the one below it to be indented from
    # anything.
    if (not area.hanging and line.x0 - area.left > INDENT_POINTS
            and flow.previous.x0 - flow.left <= INDENT_POINTS):
        return True
    if area.hanging and abs(line.x0 - area.left) <= INDENT_POINTS and _marker(line.text):
        return True
    # The short line is the *previous* line, so it is measured in the area *it*
    # stood in: the last line of a left-hand column fills its column and is not
    # short, though against the right-hand column's edge it looks shorter than
    # nothing.
    return ((flow.previous.x1 - flow.left) < SHORT_LINE_RATIO * flow.width
            and _starts_a_sentence(line.text))


#: Cells of one row sit on one baseline — this much of their own type size
#: apart at the most. They are not exactly level: on the owner's manual the
#: tick in a cell is set at 12 pt beside a word at 9, and their tops differ by
#: a point. Measured against the type and not the page's line pitch, which on
#: a page of few lines is not a line pitch at all: the synthetic page of the
#: test below has three rows 16 pt apart and a median gap of 42.
ROW_SLACK = 0.5
#: How far a cell may sit from the one above it and still be in its column.
#: Swept over the manual: 6 pt finds 72 tables and 453 cells, 12 pt finds 73
#: and 484, 24 pt finds 75 and 542 — a flat middle. What it has to tolerate is
#: a right-aligned column: the page numbers of a table of contents share their
#: right edge and stand 4.6 pt apart at the left.
COLUMN_SLACK = 12.0
#: Rows standing further apart than this many times their type size are two
#: tables, not one. Measured on the manual: its rows are 16.7 pt apart at 9 pt.
TABLE_ROW_GAP = 3.0
#: Two rows standing on one grid are a table. Measured on the Gutenberg corpus:
#: across four prose books and one verse play this finds **nothing at all**,
#: and in the other two it finds exactly what is there — an errata table of
#: page, misprint and correction, and a table of contents.
ROWS_FOR_A_TABLE = 2


def _tables(region: "list[Line]") -> "list[list[list[Line]]]":
    """The runs of rows in this area that stand on one grid.

    A table is the shape this reader used to be worst at: every cell became a
    paragraph of one or two words, so a page of them read as a heap. The manual
    has 73 of them — the beverage tables, the compatibility ticks, its own table
    of contents — and 484 cells that were 484 paragraphs.

    Rows have to be **consecutive**. A margin figure standing beside the table
    ends it and a new one starts under it, which splits one grid into two on
    the page where that happens. That is the price of not moving any text: the
    cells come out in the order they were already read in, so nothing about the
    reading order changes when a table is recognised — only the markup does.
    """
    body = [line for line in region if not line.running_head]
    found: list = []
    run: list = []
    for row in _rows(body):
        if _joins_the_grid(row, run):
            run.append(row)
            continue
        if len(run) >= ROWS_FOR_A_TABLE and not _is_a_list(run):
            found.append(run)
        run = [row] if _side_by_side(row) else []
    if len(run) >= ROWS_FOR_A_TABLE and not _is_a_list(run):
        found.append(run)
    return found


def _is_a_list(run: "list[list[Line]]") -> bool:
    """Whether this grid is really a list with its markers in a column.

    A note set as "•" at the left edge and the sentence beside it makes rows of
    two cells that line up as neatly as any table's, and read as a table it
    comes out as a column of bullets and a column of prose. What gives it away
    is the first column: nothing in it but markers.
    """
    return all(len(row) == 2 and not row[0].text.strip()[len(_marker(row[0].text.strip())):].strip()
               for row in run)


#: How wide the white between two pieces of text on one baseline may be for
#: them to still be one line of the page, in type sizes. Measured over the 964
#: such pairs in the owner's manual: a marker and the entry it names sit at
#: 0.8 to 1.4 ("8." and "Podnieś wieczko", "•" and "Nie wsypuj kawy"), and by
#: the middle of the distribution the pairs are 2.4 apart and are two columns
#: ("Nederlands" beside "4. Ustaw godzinę"). Two type sizes is the gap between
#: those two populations.
ONE_LINE_GAP = 2.0


def _same_row(one: Line, other: Line) -> bool:
    """Whether two lines stand on one baseline — the same line of the page."""
    return (one.page == other.page
            and abs(one.y1 - other.y1) <= ROW_SLACK * max(one.size, other.size))


def _reads_on(one: Line, other: Line) -> bool:
    """Whether *other* carries on from *one*: same baseline, and near enough
    that the white between them is a word space and not a column."""
    return (_same_row(one, other) and one.x1 <= other.x0
            and other.x0 - one.x1 <= ONE_LINE_GAP * max(one.size, other.size))


def _reading_runs(row: "list[Line]") -> "list[list[Line]]":
    """One baseline split into the pieces that read on from one another.

    A marker and the entry it names are one piece; two columns standing on the
    same baseline are two. Without this a callout that happens to sit level
    with a legend entry is read as part of it, and the entry loses its name to
    a word that belongs to the drawing.
    """
    runs: list = []
    for line in row:
        if runs and _reads_on(runs[-1][-1], line):
            runs[-1].append(line)
        else:
            runs.append([line])
    return runs


def _rows(lines: "list[Line]") -> "list[list[Line]]":
    """The area's lines grouped by the baseline they stand on."""
    rows: list = []
    for line in lines:
        if rows and _same_row(rows[-1][0], line):
            rows[-1].append(line)
        else:
            rows.append([line])
    return [sorted(row, key=lambda line: line.x0) for row in rows]


def _side_by_side(row: "list[Line]") -> bool:
    """Two or more cells on one baseline, none overlapping the next."""
    return len(row) >= 2 and all(a.x1 <= b.x0 for a, b in zip(row, row[1:]))


def _joins_the_grid(row: "list[Line]", run: "list[list[Line]]") -> bool:
    if not _side_by_side(row):
        return False
    if not run:
        return True
    above = run[-1]
    return (len(row) == len(above)
            and all(abs(a.x0 - b.x0) <= COLUMN_SLACK for a, b in zip(row, above))
            and above[0].y1 - row[0].y1 <= TABLE_ROW_GAP * max(above[0].size, row[0].size))


def _region_geometry(region: "list[Line]", page: Page) -> "tuple[float, float]":
    """The left edge and width of one area, measured on its own lines."""
    left = _block_left(region)
    return left, _block_width(region, left, page.width)


def _pitch(page: Page) -> float:
    ys = sorted({round(line.y1) for line in page.lines}, reverse=True)
    gaps = [a - b for a, b in zip(ys, ys[1:]) if 0 < a - b < 60]
    if not gaps:
        return 14.0
    gaps.sort()
    return float(gaps[len(gaps) // 2])


#: What share of an area's lines have to start at one edge for that edge to be
#: a stack rather than an accident. Swept over the owner's manual: 10 % gives
#: 192 lists and 15 torn paragraphs, 15 % gives 189 and 17, 25 % gives 168 and
#: 16 — and over the whole range the six books of the Gutenberg corpus do not
#: move by a single paragraph, because prose has one stack and no argument.
STACK_SHARE = 0.15


def _block_left(lines: list, fallback: float = 0.0) -> float:
    """The area's left edge: the leftmost stack of line starts, not the
    commonest one.

    A hanging-indent list has two stacks — the markers at the edge and the
    continuations set inside it — and the continuations can outnumber the
    markers. On page 48 of the owner's manual they do, by one line: 17 lines
    start at 178 pt and 16 at 163. Taking the commonest put the area's edge
    *inside* its own list, so no line was outdented, no marker opened anything,
    and forty-two lines of a numbered procedure came out as one paragraph.
    """
    starts = Counter(round(line.x0) for line in lines if not line.running_head)
    if not starts:
        return fallback
    enough = max(2, round(STACK_SHARE * sum(starts.values())))
    stacks = [x for x, count in starts.items() if count >= enough]
    return float(min(stacks)) if stacks else float(starts.most_common(1)[0][0])


def _block_width(lines: list, left: float, fallback: float) -> float:
    rights = sorted(line.x1 for line in lines if not line.running_head)
    if not rights:
        return fallback
    return max(1.0, rights[int(0.9 * (len(rights) - 1))] - left)


def _column_geometry(page: Page) -> dict:
    """{column: (left edge, width)} — one entry for a single column, two for
    a page set in two, each measured on its own lines."""
    if page.split is None:
        left = _block_left(page.lines)
        return {0: (left, _block_width(page.lines, left, page.width))}
    out = {}
    for column, lines in ((0, [l for l in page.lines if l.x0 < page.split]),
                          (1, [l for l in page.lines if l.x0 >= page.split])):
        left = _block_left(lines)
        out[column] = (left, _block_width(lines, left, page.width / 2))
    return out


#: What a list marker looks like at the start of a line: a bullet, or a short
#: run of letters and digits ending in a dot or a bracket — "1.", "4.2",
#: "A16.", "C11A.", "6.6.4.2". Long enough to catch a manual's numbering,
#: short enough not to catch a sentence that happens to start with a word and
#: a full stop.
MARKER = re.compile(r"^(?:[•·▪◦‣–—-]|\(?[A-Za-z]?\d{1,3}(?:\.\d{1,3}){0,3}[.)]?|[A-Z]{1,2}\d{0,3}[.)])(?=\s|$)")
#: A region is a hanging-indent list when at least this many of its lines start
#: at its left edge with a marker. Two is enough to be a list and too few to
#: happen by accident — a paragraph beginning "1939. " twice in one region.
MARKED_LINES_FOR_A_LIST = 2


def _marker(text: str) -> str:
    """The list marker this line starts with, or ""."""
    found = MARKER.match(text.strip())
    return found.group(0) if found else ""


def _hanging_indent(region: "list[Line]", left: float) -> bool:
    """Whether this area is a list whose continuations are indented.

    Prose indents the *first* line of a paragraph; a list indents everything
    *but* the first, so that the marker stands out on the left. The rule that
    starts a paragraph at an indent is right for the first and exactly wrong
    for the second: in a legend of forty entries it starts a new paragraph at
    every wrapped line, which is where a quarter of the manual's torn
    sentences came from.
    """
    marked = sum(
        1 for line in region
        if abs(line.x0 - left) <= INDENT_POINTS and _marker(line.text)
    )
    if marked < MARKED_LINES_FOR_A_LIST:
        return False
    return any(line.x0 - left > INDENT_POINTS for line in region)


def _starts_a_sentence(text: str) -> bool:
    stripped = text.lstrip("\"'„“‘«(—– ")
    return bool(stripped) and stripped[0].isupper()


def _sections(pages: list[Page], outline: list[Outline], body_size: float) -> list[tuple[str, list[Block]]]:
    """Documents: one per top-level outline entry when there is an outline,
    else one per `h1`, else one for the whole book."""
    top = [entry for entry in outline if entry.level == 1] or outline
    blocks = _blocks(pages, body_size, breaks={entry.page for entry in top})
    if top:
        starts = sorted({entry.page for entry in top})
        titles = {entry.page: entry.title for entry in top}
        sections: list[tuple[str, list[Block]]] = []
        current_title = ""
        current: list[Block] = []
        next_index = 0
        for block in blocks:
            page = block.picture.page if block.picture else block.lines[0].page
            while next_index < len(starts) and page >= starts[next_index]:
                if current:
                    sections.append((current_title, current))
                current_title = titles[starts[next_index]]
                current = []
                next_index += 1
            current.append(block)
        if current:
            sections.append((current_title, current))
        return sections or [("", blocks)]
    if any(block.kind == "h1" for block in blocks):
        sections = []
        current_title = ""
        current = []
        for block in blocks:
            if block.kind == "h1":
                if current:
                    sections.append((current_title, current))
                current_title = block.text
                current = []
            current.append(block)
        if current:
            sections.append((current_title, current))
        return sections
    return [("", blocks)]


def _figure(picture: Picture, mark: str = "") -> str:
    """The picture, with the labels printed on it gathered underneath.

    `_lift_labels` takes a callout — the "A16" beside an arrow — out of the
    flow, because on its own line in the middle of a legend it is not a
    paragraph and cuts one in half. Taking it out is only half the job: every
    character the PDF draws has to arrive somewhere, and a label moved and not
    printed is a character lost. On the owner's manual that was 1 097 of them.

    So they are printed under the picture they stand on, which is also where a
    reader looking at the drawing will look for them.
    """
    image = f'<img src="../{escape(picture.name)}" alt=""/>'
    labels = ""
    if picture.labels:
        printed = " ".join(escape(label.text.strip()) for label in picture.labels)
        labels = f'\n    <p class="{LABEL_CLASS}">{printed}</p>'
    if picture.caption is None:
        return f"    <p{mark}>{image}</p>{labels}"
    # `figcaption` may be a figure's **first or last** child and nothing else,
    # so the callouts stand after the figure rather than inside it — which is
    # also where they belong: the caption is the picture's name, the callouts
    # are text that stood *on* it. Found by EPUBCheck on the owner's manual,
    # on the one shape the substitute material does not have: a picture with a
    # name under it *and* callouts printed on it (`element "p" not allowed
    # here`, one document of ten). The order is unchanged — name, then the
    # callouts — because that is the order `_picture_text` reads them in, and
    # the two sides of K1 agree about it.
    caption = escape(picture.caption.text.strip())
    return (f"    <figure{mark}>\n      <p>{image}</p>\n"
            f"      <figcaption>{caption}</figcaption>\n    </figure>{labels}")


def _grid(rows: "list[list[Line]]", mark: str = "") -> str:
    """The rows as a table, cell for cell.

    Every cell is a `td`. Which row is the head is a question this reader has
    no answer to — the manual sets its header row in the same face and, on the
    page that started this, outside the grid altogether — and a `th` invented
    from nothing would be a claim the file never made.
    """
    out = [f"    <table{mark}>"]
    for row in rows:
        out.append("      <tr>")
        # One cell to a line, and the reason is not tidiness: the text of a
        # document is read with `itertext()`, which gives back what stands
        # *between* the elements too. Cells written end to end come back as
        # one word — "Opis ekspresu6" — and K1 refused the book for it.
        out += [f"        <td>{escape(cell.text.strip())}</td>" for cell in row]
        out.append("      </tr>")
    out.append("    </table>")
    return "\n".join(out)


#: Two paragraphs in a row, each opening with a marker, are a list. One is a
#: sentence that happens to begin "1939." — measured on the Gutenberg corpus,
#: where six books of prose and verse yield 2 to 16 items in all, against 550
#: in the owner's manual, which is a manual and is mostly procedures.
ITEMS_FOR_A_LIST = 2
#: The class on a list whose markers are printed in its own text.
LIST_CLASS = "ef-pdf-list"
STYLESHEET_PATH = "styles/pdf.css"
#: Written by the reader for its own markup, and as short as it can be: a PDF
#: has no design to carry across, so this says only the one thing the markup
#: would otherwise be lying about.
STYLESHEET = """\
/* A list whose markers stand in its own text. The source drew "1." and "•"
   as characters and this rebuild keeps every one of them, so the reading
   system must not set a second marker beside them. */
ul.ef-pdf-list { list-style: none; padding-left: 0; margin-left: 0; }
"""


def _list_runs(blocks: list) -> "list[tuple[int, int]]":
    """Runs of paragraphs that each open with a list marker, as index pairs.

    A manual is mostly procedures: 550 of this one's 1 421 blocks open with
    "1.", "•" or "6.6.4", and read as paragraphs they are a list a reading
    system cannot see. The markers are text the source drew, so they stay in
    the item and the list is told not to set its own beside them.
    """
    runs: list = []
    start: "int | None" = None
    for index in range(len(blocks) + 1):
        block = blocks[index] if index < len(blocks) else None
        marked = (block is not None and block.kind == "p" and not block.continued
                  and bool(_marker(block.text.strip())))
        if marked and start is None:
            start = index
        elif not marked and start is not None:
            if index - start >= ITEMS_FOR_A_LIST:
                runs.append((start, index - 1))
            start = None
    return runs


def _trimmed(runs: list) -> list:
    """The line's runs with the whitespace `join_lines` would strip removed."""
    runs = [[text, style] for text, style in runs]
    while runs and not runs[0][0].lstrip():
        runs.pop(0)
    if runs:
        runs[0][0] = runs[0][0].lstrip()
    while runs and not runs[-1][0].rstrip():
        runs.pop()
    if runs:
        runs[-1][0] = runs[-1][0].rstrip()
    return [(text, style) for text, style in runs if text]


def _marked(block: Block, body_face: str = "") -> str:
    """The block's text as markup, keeping what the typesetter set apart.

    A reflowable book cannot hold a page's layout, and should not try. What it
    can hold is the marks the typesetter *made*: the word set in bold because
    it names a button, the phrase in italic because it is quoted. This reader
    measured the face of every line and threw it away — 6 084 characters of it
    in the owner's manual, the legend's own numbers among them.

    Only a face that differs from the document's own body face is a mark. A
    manual set throughout in a bold condensed face is not one long shout.

    The plain text this produces is exactly `block.text`, character for
    character; `join_lines` is applied here to the runs instead of the lines.
    """
    pieces: list = []
    plain = ""
    for line in block.lines:
        runs = _trimmed(line.runs) if line.runs else _trimmed([(line.text, "")])
        text = "".join(run for run, _ in runs)
        if not text:
            continue
        if plain and not (plain.endswith("-") and len(plain) > 1
                          and plain[-2].isalnum() and text[:1].isalpha()):
            pieces.append((" ", ""))
            plain += " "
        pieces.extend(runs)
        plain += text
    return _faced_runs(pieces, body_face)


def _faced_runs(runs: list, body_face: str) -> str:
    """Runs of `(text, style)` as markup, with what the body is already set in
    left unmarked. Neighbours that mean the same thing are one element."""
    out: list = []
    for run, style in runs:
        mark = "".join(letter for letter in style if letter not in body_face)
        if out and out[-1][1] == mark:
            out[-1][0] += run
        else:
            out.append([run, mark])
    return "".join(_faced(escape(run), mark) for run, mark in out)


def _faced(text: str, mark: str) -> str:
    """*text* wrapped in what its face means, with the spaces left outside it:
    a legend's "A1.  " is set in bold, and the two spaces after it are not."""
    if not mark or not text.strip():
        return text
    body = text.strip()
    before = text[:len(text) - len(text.lstrip())]
    after = text[len(text.rstrip()):]
    if "b" in mark:
        body = f"<strong>{body}</strong>"
    if "i" in mark:
        body = f"<em>{body}</em>"
    return before + body + after


def _element(block: Block, mark: str, counts: dict, item: bool = False,
             body_face: str = "") -> str:
    """One block as its markup. *item* makes a paragraph a list item."""
    if block.kind == "image":
        return _figure(block.picture, mark)
    if block.kind == "table":
        counts["tables"] += 1
        return _grid(block.rows, mark)
    if block.kind == "labels":
        counts["labelled_drawings"] += 1
        return f'    <p{mark} class="{LABEL_CLASS}">{escape(block.text)}</p>'
    if block.kind == "head":
        return f'    <p{mark} class="{RUNNING_HEAD_CLASS}">{escape(block.text)}</p>'
    inner = _marked(block, body_face)
    # What the typesetter set apart, counted where it is written. The field
    # existed and nothing ever filled it: the report said `emphasis: 0` while
    # the owner's manual carried 333 marks, which is a number that lies rather
    # than a number that is missing.
    counts["emphasis"] += inner.count("<strong>") + inner.count("<em>")
    if block.kind in ("h1", "h2"):
        counts["headings"] += 1
        return f"    <{block.kind}{mark}>{inner}</{block.kind}>"
    if block.continued:
        return f'    <p{mark} class="{CONTINUED_CLASS}">{inner}</p>'
    counts["paragraphs"] += 1
    tag = "li" if item else "p"
    return f"    <{tag}{mark}>{inner}</{tag}>"


def _render(blocks: list[Block], title: str, anchored: "set[int] | None" = None,
            body_face: str = "") -> tuple[str, dict]:
    """The section's markup, and what went into it.

    *anchored* names the pages the outline points at. The first block of such a
    page carries the anchor, and `counts["anchored"]` says which pages actually
    got one — a nav entry is only allowed to point where something is.
    """
    counts: dict = {"paragraphs": 0, "headings": 0, "tables": 0,
                    "labelled_drawings": 0, "lists": 0, "emphasis": 0,
                    "anchored": []}
    wanted = set(anchored or ())
    runs = _list_runs(blocks)
    opens = {first for first, _ in runs}
    closes = {last for _, last in runs}
    listed = {index for first, last in runs for index in range(first, last + 1)}
    body: list[str] = []
    for index, block in enumerate(blocks):
        # The anchor goes on the first block that *reaches* the page, not on
        # one that starts there: a paragraph running over the fold means no
        # block begins on the page below it, and the entry pointing at that
        # page would have nowhere to land.
        # Every named page this block reaches is answered by this one element.
        # A paragraph that runs over the fold carries two pages, and the entry
        # for the second points at the paragraph its page begins in — which is
        # true, and is as precise as an anchor can be without cutting the text
        # in half. It was cut, once: an empty `span` between the two halves of
        # a word broken at the fold made the hyphen stage's bookkeeping
        # disagree with the document, and it reverted **every** join in the
        # book rather than write a text it could not account for. It was right
        # to; the anchor was not worth it.
        covered = [p for p in _block_pages(block) if p in wanted]
        mark = ""
        if covered:
            mark = f' id="{_anchor(covered[0])}"'
            for page in covered:
                wanted.discard(page)
                counts["anchored"].append((page, _anchor(covered[0])))
        if index in opens:
            counts["lists"] += 1
            body.append(f'    <ul class="{LIST_CLASS}">')
        body.append(_element(block, mark, counts, item=index in listed, body_face=body_face))
        if index in closes:
            body.append("    </ul>")
    # No `xml:lang` on the document, deliberately. The PDF states one language,
    # in its catalogue, about the whole file; stamping that on all ten documents
    # turns one claim into ten that later look independent. They are not, and
    # the difference shows: the owner's manual declares `en-GB` and is Polish
    # throughout, so the content stage corrected the publication and the eight
    # documents whose text proved it — and *kept* `en-GB` on the two too short
    # to prove anything, because a document stating its own language is stating
    # a fact about itself. It was not stating anything; this reader was. With
    # no declaration on the document, the publication's applies, which is what
    # one claim about one file means.
    # The sheet is linked only where it is needed, which is where a list is.
    sheet = (f'    <link rel="stylesheet" type="text/css" href="../{STYLESHEET_PATH}"/>\n'
             if counts["lists"] else "")
    markup = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "  <head>\n"
        '    <meta charset="utf-8"/>\n'
        f"    <title>{escape(title or ' ')}</title>\n"
        + sheet
        + "  </head>\n"
        "  <body>\n"
        + "\n".join(body)
        + "\n  </body>\n</html>\n"
    )
    return markup, counts


# ------------------------------------------------- the page where it stood


#: The two things this reader can make of a PDF, and why there are two.
#:
#: `reflowable` is everything above: geometry read back into paragraphs,
#: headings, tables and lists, so the text can be set at any size on any
#: screen. It is the default in every mode and should be — a book that
#: reflows is a book anybody can read.
#:
#: `fixed` keeps the page instead. Every line is set where the typesetter set
#: it, at the size he set it, on a page of the source's own measurements, and
#: the publication says `rendition:layout="pre-paginated"` so a reading system
#: scales the whole page rather than reflowing what is on it. That is the
#: right answer for a document whose layout *is* its content — a form, a
#: score, a diagram with words in it, a manual whose numbers stand beside the
#: parts they name — and the wrong one for a novel.
#:
#: What it costs is real and is said in the report: no reflow, no reader font
#: size, a page that must be zoomed on a small screen, and the structure this
#: reader worked out (tables, lists) not written as structure, because a
#: `<table>` cannot be a table and stand where its cells stand at once. The
#: text is still text — every character, in reading order — so it can still be
#: searched, selected and read aloud, and K1 holds exactly as it does above.
#:
#: One cost is not obvious and was measured rather than reasoned: **the hyphen
#: stage stops working.** A word the typesetter broke at a line end is two
#: lines here, standing in two places, so nothing in the document reads as
#: `prze-konaniem` and there is nothing for that stage to join — on one
#: document of the substitute material, 1 202 candidates and 1 157 joins
#: become 9 candidates and none. That is the right answer for this mode:
#: joining the halves would take the second one out of the position it was
#: drawn in. It is a cost all the same, and the report names it.
#:
#: The file is bigger, and by a knowable amount: one document per page and one
#: element per line came to 2.4–2.9 times the reflowable book across the
#: eighteen substitute documents (0.33 MB against 0.13 MB on the largest).
#: Reading time is unchanged — the work above the writing is the same work.
#:
#: The two names are `policy.PDF_LAYOUTS`, which is what the window and the
#: command line offer; a test holds the two lists against each other so neither
#: can grow a mode the other does not know.
REFLOWABLE = "reflowable"
FIXED = "fixed"

#: The page, one line of it, and one picture on it.
FIXED_PAGE_CLASS = "ef-pdf-page"
FIXED_LINE_CLASS = "ef-pdf-line"
FIXED_ART_CLASS = "ef-pdf-art"
FIXED_STYLESHEET_PATH = "styles/pdf-fixed.css"
#: Everything here is either a position the source measured or a rule without
#: which a position means nothing. There is no design in it, because there is
#: no design of this program's to add.
FIXED_STYLESHEET = """\
/* A page of the source, kept as a page. Every number in this book's markup is
   in the PDF's own points; each document says how large its page is, and the
   reading system scales the page as a whole. */
html, body { margin: 0; padding: 0; }
div.ef-pdf-page { position: relative; overflow: hidden; margin: 0; padding: 0; }
/* A line stands where it stood and does not wrap: it is a line, not a
   paragraph, and the source already decided where it ends. */
.ef-pdf-line { position: absolute; margin: 0; padding: 0; line-height: 1;
               white-space: pre; }
"""
#: Written only into a book that has a picture in it. A rule no selector in the
#: book can reach is what the style stage calls an unreachable rule, and it is
#: right to: this program should not be writing the junk it removes elsewhere.
FIXED_ART_STYLE = "img.ef-pdf-art { position: absolute; margin: 0; padding: 0; }\n"


def _pt(value: float) -> str:
    """A measurement as CSS writes it: a tenth of a point is as fine as any
    page needs, and trailing zeros are noise in a file with a line per line."""
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0", "-") else text


def _fixed_items(blocks: "list[Block]") -> "dict[int, list]":
    """The blocks cut per page, in the order they are read.

    Cut rather than re-derived, and that is the load-bearing part: the left
    side of K1 (`text_of`) is the order of *these* blocks, so a fixed page that
    prints the same blocks in the same order carries the source's text in the
    source's order by construction. A paragraph that runs over the fold is two
    entries — its lines on the page they were drawn on, which is the one thing
    a fixed page can say about it.
    """
    items: dict[int, list] = {}
    for block in blocks:
        if block.kind == "image":
            items.setdefault(block.picture.page, []).append((block, []))
            continue
        page = None
        run: list = []
        for line in block.lines:
            if line.page != page:
                if run:
                    items.setdefault(page, []).append((block, run))
                page, run = line.page, []
            run.append(line)
        if run:
            items.setdefault(page, []).append((block, run))
    return items


def _fixed_line(line: Line, page: Page, tag: str, extra: str, body_face: str) -> str:
    """One line of the page, where the page had it.

    The y axis is turned over: a PDF measures from the foot of the page and CSS
    from its head. The face the run was set in is marked as it is in a
    reflowable book — what differs from the body face is a mark the typesetter
    made — and it draws the same way, so the mark and the look agree.
    """
    style = (f"left: {_pt(line.x0)}px; top: {_pt(page.height - line.y1)}px; "
             f"font-size: {_pt(line.size)}px;")
    if line.family:
        style += f" font-family: {line.family};"
    runs = _trimmed(line.runs) if line.runs else _trimmed([(line.text, "")])
    inner = _faced_runs(runs, body_face)
    classes = f"{FIXED_LINE_CLASS} {extra}" if extra else FIXED_LINE_CLASS
    return f'      <{tag} class="{classes}" style="{style}">{inner}</{tag}>'


def _fixed_picture(picture: Picture, page: Page, body_face: str) -> str:
    """The picture in its box, and the words that stand on it where they stand.

    This is what the labels kept their lines for. In a reflowable book a
    callout can only be printed under the drawing it names, because a
    reflowable book has no "beside"; here it has one, and "A16" goes back
    beside the arrow it was drawn beside.
    """
    style = f"left: {_pt(picture.x0)}px; top: {_pt(page.height - picture.y1)}px;"
    width, height = picture.x1 - picture.x0, picture.y1 - picture.y0
    if width > 0 and height > 0:
        style += f" width: {_pt(width)}px; height: {_pt(height)}px;"
    out = [f'      <img class="{FIXED_ART_CLASS}" style="{style}" '
           f'src="../{escape(picture.name)}" alt=""/>']
    # The name first and then the labels, which is the order `_figure` prints
    # them in and therefore the order the left side of K1 reads them in.
    for line in ([picture.caption] if picture.caption is not None else []) + list(picture.labels):
        out.append(_fixed_line(line, page, "div", "", body_face))
    return "\n".join(out)


def _fixed_document(page: Page, items: list, title: str, body_face: str) -> "tuple[str, dict]":
    """One PDF page as one document, and what went onto it."""
    counts: dict = {"lines": 0, "headings": 0, "images": 0, "emphasis": 0}
    body: list[str] = []
    for block, lines in items:
        if block.kind == "image":
            counts["images"] += 1
            body.append(_fixed_picture(block.picture, page, body_face))
            continue
        # A heading is still a heading: a page laid out in absolute positions
        # has no structure a reading system can follow, and the one or two
        # elements that carry any are worth keeping. The tag goes on the first
        # line of the heading only — two `h1`s are two headings, and a title
        # set over two lines is one.
        tag = block.kind if block.kind in ("h1", "h2") else "div"
        extra = RUNNING_HEAD_CLASS if block.kind == "head" else ""
        for index, line in enumerate(lines):
            counts["lines"] += 1
            if index == 0 and tag != "div":
                counts["headings"] += 1
            body.append(_fixed_line(line, page, tag if index == 0 else "div", extra, body_face))
    # Whole numbers: `rendition:viewport` and the `meta` that stands for it are
    # read as a page size in pixels, and half a pixel of page is not a thing.
    width, height = round(page.width), round(page.height)
    # The body face on the page rather than on every line of it — it is the
    # document's, not the line's, and `_faced_runs` marks only what differs.
    page_style = f"width: {width}px; height: {height}px;"
    if "b" in body_face:
        page_style += " font-weight: bold;"
    if "i" in body_face:
        page_style += " font-style: italic;"
    markup = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "  <head>\n"
        '    <meta charset="utf-8"/>\n'
        f'    <meta name="viewport" content="width={width}, height={height}"/>\n'
        f"    <title>{escape(title or ' ')}</title>\n"
        f'    <link rel="stylesheet" type="text/css" href="../{FIXED_STYLESHEET_PATH}"/>\n'
        "  </head>\n"
        "  <body>\n"
        f'    <div class="{FIXED_PAGE_CLASS}" style="{page_style}">\n'
        + "\n".join(body)
        + ("\n" if body else "")
        + "    </div>\n  </body>\n</html>\n"
    )
    return markup, counts


def _fill_the_pages(book: Book, pages: "list[Page]", blocks: "list[Block]",
                    layout: "Layout", outline: "list[Outline]") -> None:
    """One document per page of the source, and the book that is made of them.

    The navigation is the outline the reader already has — the bookmarks, or
    the contents page it read when there were none — and here it needs no
    anchors at all: an entry names a page, and a page *is* a document. The page
    list is free for the same reason and is the whole point of having one: in
    this mode "page 47" of the EPUB is page 47 of the PDF.
    """
    placed: dict[int, str] = {}
    titles = {entry.page: entry.title for entry in outline}
    items = _fixed_items(blocks)
    for page in pages:
        path = f"text/page-{page.number:04d}.xhtml"
        markup, counts = _fixed_document(
            page, items.get(page.number, []),
            titles.get(page.number) or book.metadata.title, layout.body_face,
        )
        layout.headings += counts["headings"]
        layout.emphasis += markup.count("<strong>") + markup.count("<em>")
        book.add(Resource(path=path, media_type="application/xhtml+xml",
                          data=markup.encode("utf-8")))
        book.spine.append(SpineItem(path=path))
        book.page_list.append(PageTarget(label=str(page.number), target=path))
        placed[page.number] = path
    for block in blocks:
        if block.kind == "image" and block.picture.name not in book.resources:
            picture = block.picture
            book.add(Resource(path=picture.name, media_type=picture.media_type, data=picture.data))
            layout.images += 1
    layout.paragraphs = sum(1 for block in blocks if block.kind == "p")
    sheet = FIXED_STYLESHEET + (FIXED_ART_STYLE if layout.images else "")
    book.add(Resource(path=FIXED_STYLESHEET_PATH, media_type="text/css",
                      data=sheet.encode("utf-8")))
    book.rendition["layout"] = "pre-paginated"
    if outline:
        book.toc = _navigation(outline, placed)
    elif book.spine:
        # Nothing in the file said anything about its structure — no bookmarks
        # and no contents page. The page list is already every page; a table of
        # contents that repeated it would say nothing the reader does not
        # already have, so it says the one thing that is true: here is the book.
        book.toc = [NavPoint(label=book.metadata.title or "1", target=book.spine[0].path)]
    layout.navigation_entries = sum(len(list(node.walk())) for node in book.toc)


def _say_the_page_was_kept(report: Report, source: str, layout: "Layout",
                           pages: "list[Page]") -> None:
    """That the book came out pre-paginated, and what that costs.

    Two rules, said every time: one for what was done and one for what it
    means. A mode that keeps the look at the price of reflow is a trade, and a
    trade nobody was told about is not one they made.
    """
    first = pages[0] if pages else None
    report.add(
        "pdf",
        Level.FIX,
        "pdf.fixed-layout",
        values={
            "pages": len(pages),
            "width": round(first.width) if first else 0,
            "height": round(first.height) if first else 0,
        },
        location=source,
    )
    report.add(
        "pdf",
        Level.WARN,
        "pdf.fixed-layout-cost",
        values={"tables": layout.tables, "lists": layout.lists},
        location=source,
    )


def _read_metadata(book: Book, source: str, info: dict) -> None:
    title = info.get("Title") or posixpath.splitext(posixpath.basename(source.replace("\\", "/")))[0]
    book.metadata.titles = [title]
    author = info.get("Author")
    if author:
        book.metadata.creators = [Creator(name=author)]
    language = info.get("Lang") or ""
    if language:
        book.metadata.language = language
    digest = hashlib.sha256(open(source, "rb").read()).hexdigest()
    book.metadata.identifiers = [
        Identifier(value=f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'epubforge-pdf:' + digest)}", scheme="uuid", primary=True)
    ]
    if info.get("Producer"):
        book.metadata.extra_meta.append(("pdf:producer", info["Producer"]))
    if info.get("Creator"):
        book.metadata.extra_meta.append(("pdf:creator", info["Creator"]))
