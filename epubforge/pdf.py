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

from .model import Book, Creator, Identifier, NavPoint, Resource, SpineItem
from .reader import EpubReadError
from .report import Level, Report
from .writer import escape

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
    running_head: bool = False
    #: Which area of the page this line belongs to. Lines of one area are read
    #: one after another; a paragraph never runs from one area into the next.
    region: int = 0


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
    labels: list = field(default_factory=list)
    #: The name written under the picture — "Americano" under the icon of it.
    caption: str = ""

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
    images: int = 0
    images_skipped: int = 0
    running_heads: int = 0
    outline_entries: int = 0
    outline_unresolved: int = 0
    #: Entries in the table of contents the reader built. With an outline this
    #: is the whole of it, not only the entries that became documents.
    navigation_entries: int = 0
    column_pages: int = 0
    body_size: float = 0.0
    torn_paragraphs: int = 0
    fragment_paragraphs: int = 0
    median_paragraph: int = 0
    #: How many areas the pages were cut into. One per page is prose.
    regions: int = 0


# ----------------------------------------------------------------- reading


def read_pdf(source: str, report: Report, budget=None) -> Book:
    """Load *source* into a :class:`Book`, or refuse it with the reason said."""
    pages, info, outline, layout = _read(source)
    _refuse_a_book_of_pictures(pages, layout, source, report)

    body_size = _lay_out_all(pages, layout)

    book = Book()
    book.source_version = "pdf"
    book.source_opf_path = None
    _read_metadata(book, source, info)

    sections = _sections(pages, outline, body_size)
    quality = measure_quality([block for _, blocks in sections for block in blocks])
    layout.torn_paragraphs = quality.torn
    layout.fragment_paragraphs = quality.fragments
    layout.median_paragraph = quality.median_characters
    layout.outline_entries = len(outline)
    _fill_the_book(book, sections, layout, outline)
    layout.running_heads = sum(1 for page in pages for line in page.lines if line.running_head)

    _say_what_was_read(report, source, layout, len(sections), quality)
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
    # After the running heads, because a head at the top of the page is a band
    # of its own and would cut every page in two before anything else could.
    for page in pages:
        _lay_out(page)
    layout.column_pages = sum(1 for page in pages if page.columns)
    layout.regions = sum(len(page.regions) for page in pages)
    layout.body_size = _body_size(pages)
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
    raise EpubReadError("the PDF has no text layer to read; scanning it would need OCR")


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
    for index, (title, blocks) in enumerate(sections, 1):
        path = f"text/section-{index:04d}.xhtml"
        # A section the outline did not name and no heading opened: the first
        # is the book's own front matter and takes the title; a later one is
        # named by its number, which is the one thing that is true of it.
        label = title or (book.metadata.title if index == 1 else f"{index}")
        markup, counts = _render(blocks, label, anchored)
        layout.paragraphs += counts["paragraphs"]
        layout.headings += counts["headings"]
        for page in counts["anchored"]:
            placed.setdefault(page, f"{path}#{_anchor(page)}")
        for block in blocks:
            if block.kind == "image" and block.picture.name not in book.resources:
                picture = block.picture
                book.add(Resource(path=picture.name, media_type=picture.media_type, data=picture.data))
                layout.images += 1
        book.add(Resource(path=path, media_type="application/xhtml+xml", data=markup.encode("utf-8")))
        book.spine.append(SpineItem(path=path))
        if not outline:
            book.toc.append(NavPoint(label=label, target=path))
        # A page the outline names and no block starts on — an empty page, or
        # one whose blocks all began earlier — still has to be reachable: the
        # document it falls in is the truthful answer.
        for page in {p for p in anchored if p not in placed}:
            if any(_block_page(block) >= page for block in blocks):
                placed.setdefault(page, path)
    if outline:
        book.toc.extend(_navigation(outline, placed))
    layout.navigation_entries = sum(len(list(node.walk())) for node in book.toc)


def _anchor(page: int) -> str:
    return f"pdf-page-{page:04d}"


def _block_page(block: "Block") -> int:
    if block.picture is not None:
        return block.picture.page
    return block.lines[0].page if block.lines else 0


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
    if layout.outline_entries:
        report.add(
            "pdf",
            Level.PRESERVED,
            "pdf.outline-used",
            values={"count": layout.outline_entries, "unresolved": layout.outline_unresolved},
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
        for picture in page.pictures:
            texts += picture.labels
            texts.append(picture.caption)
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
        " ".join([block.picture.caption, *block.picture.labels]) if block.kind == "image"
        else block.text
        for block in _blocks(pages, body_size)
    ]
    return re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip()


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
    from pdfminer.layout import LAParams, LTChar, LTFigure, LTImage, LTTextContainer, LTTextLine
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
    for number, lt_page in enumerate(extract_pages(source, laparams=LAParams(all_texts=True)), 1):
        _walk_characters(lt_page, drawn)
        page = Page(number=number, width=lt_page.width, height=lt_page.height)
        stack = list(lt_page)
        while stack:
            element = stack.pop(0)
            if isinstance(element, LTTextContainer):
                for line in element:
                    if isinstance(line, LTTextLine):
                        chars = [c for c in line if isinstance(c, LTChar)]
                        text = line.get_text().replace("\n", "")
                        if not chars or not text.strip():
                            continue
                        page.lines.append(Line(
                            text=text,
                            x0=line.x0, x1=line.x1, y0=line.y0, y1=line.y1,
                            size=round(sum(c.size for c in chars) / len(chars), 1),
                            page=number,
                            bold="bold" in Counter(c.fontname for c in chars).most_common(1)[0][0].lower(),
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
        page.lines.sort(key=lambda line: (-round(line.y1), line.x0))
        split = _two_columns(page)
        page.columns = split is not None
        page.split = split
        _reading_order(page, split)
        pages.append(page)
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
             columns: bool = False, depth: int = 0) -> "list[list[Line]]":
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

    **The vertical cut needs *columns* and takes it from `_two_columns`**,
    which is measured on the whole page. Things standing side by side are
    normally read *across*, not down: that is what a table is. Cutting on any
    wide vertical gap read one Gutenberg book's errata table — page number,
    misprint, correction — as three lists, every page number before every
    misprint, and K1 refused the rebuild. The gate was right; the cut was
    wrong. A page genuinely set in columns is the exception, and it is the one
    thing `_two_columns` is careful about.
    """
    if len(lines) <= 1 or depth >= REGION_DEPTH:
        return [_in_order(lines)] if lines else []
    # A band, when the gap is wider than any ordinary space between
    # paragraphs. Taken before a column split because top-to-bottom is always
    # the reading order and left-to-right is only ever true inside a band.
    across = _widest_gap([(line.y0, line.y1) for line in lines])
    if across and across[0] >= BAND_SHARE * height:
        cut = across[1]
        upper = [line for line in lines if (line.y0 + line.y1) / 2 > cut]
        lower = [line for line in lines if (line.y0 + line.y1) / 2 <= cut]
        if upper and lower:
            return (_regions(upper, width, height, columns, depth + 1)
                    + _regions(lower, width, height, columns, depth + 1))
    down = _widest_gap([(line.x0, line.x1) for line in lines]) if columns else None
    if down and down[0] >= GUTTER_SHARE * width:
        cut = down[1]
        left = [line for line in lines if (line.x0 + line.x1) / 2 < cut]
        right = [line for line in lines if (line.x0 + line.x1) / 2 >= cut]
        if left and right:
            return (_regions(left, width, height, columns, depth + 1)
                    + _regions(right, width, height, columns, depth + 1))
    return [_in_order(lines)]


def _in_order(lines: "list[Line]") -> "list[Line]":
    return sorted(lines, key=lambda line: (-round(line.y1), line.x0))


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
            inside.labels.append(text)
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
            named.caption = text
        else:
            kept.append(line)
    page.lines = kept


def _is_a_fragment(text: str) -> bool:
    """A word or two with no sentence in them: a label, not a paragraph."""
    return bool(text) and len(text.split()) <= FRAGMENT_WORDS and text[-1:] not in tuple(SENTENCE_ENDS)


def _lay_out(page: Page) -> None:
    """Give the page its regions, and its lines in the order they are read.

    Running heads take no part in the cutting. A head at the top of a page is
    a band of its own by any measure, and a page cut under it would lose the
    one thing the head's position tells us: that the paragraph it interrupts
    continues below it. So the areas are found among the body lines, and each
    head then joins the area it stands over.
    """
    _lift_labels(page)
    body = [line for line in page.lines if not line.running_head]
    heads = [line for line in page.lines if line.running_head]
    regions = _regions(body, page.width, page.height, page.columns)
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
        _in_order(list(region) + [h for h in heads if h.region == index])
        for index, region in enumerate(regions)
    ] or ([_in_order(heads)] if heads else [])
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


def _body_size(pages: list[Page]) -> float:
    weights: Counter = Counter()
    for page in pages:
        for line in page.lines:
            if not line.running_head:
                weights[line.size] += len(line.text)
    return weights.most_common(1)[0][0] if weights else 0.0


@dataclass
class Block:
    kind: str  # "p", "h1", "h2", "head" (running head), "image"
    lines: list[Line] = field(default_factory=list)
    picture: Picture | None = None
    #: A paragraph a running head cut in two; this is the second half.
    continued: bool = False

    @property
    def text(self) -> str:
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
    and `Primadonna Aromatic` are all of them. Punctuation at the ends is not
    counted, or the roman numeral `I.` that opens a chapter would fail on its
    own full stop — eleven of those across the Gutenberg corpus, every one a
    real heading.

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
    """One page's areas, in reading order, with its pictures among them."""
    pitch = _pitch(page)
    regions = page.regions or ([page.lines] if page.lines else [])
    pictures = sorted(page.pictures, key=lambda picture: -picture.y1)
    placed = 0
    for region in regions:
        if not region:
            continue
        # A picture stands where it stands: before the first area whose top is
        # below it.
        top = max(line.y1 for line in region)
        while placed < len(pictures) and pictures[placed].y1 > top:
            flow.blocks.append(Block(kind="image", picture=pictures[placed]))
            placed += 1
        left, width = _region_geometry(region, page)
        area = _Area(page=page, left=left, width=width,
                     hanging=_hanging_indent(region, left), pitch=pitch)
        _area_blocks(region, area, flow, body_size, breaks)
    for picture in pictures[placed:]:
        flow.blocks.append(Block(kind="image", picture=picture))


def _area_blocks(region: "list[Line]", area: "_Area", flow: "_Flow",
                 body_size: float, breaks: set[int]) -> None:
    """The lines of one area, joined into paragraphs and headings."""
    for line in region:
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
    # Two areas of a page are two things read one after the other — except on a
    # page set in two columns of one body, where the paragraph at the foot of
    # the left column is the one at the head of the right. That page is
    # recognised by `_two_columns`, which is measured; everywhere else a new
    # area starts a new block.
    if area.first and not area.page.columns:
        return True
    previous = flow.previous
    if previous is None:
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
    if not area.hanging and line.x0 - area.left > INDENT_POINTS:
        return True
    if area.hanging and abs(line.x0 - area.left) <= INDENT_POINTS and _marker(line.text):
        return True
    # The short line is the *previous* line, so it is measured in the area *it*
    # stood in: the last line of a left-hand column fills its column and is not
    # short, though against the right-hand column's edge it looks shorter than
    # nothing.
    return ((flow.previous.x1 - flow.left) < SHORT_LINE_RATIO * flow.width
            and _starts_a_sentence(line.text))


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


def _block_left(lines: list, fallback: float = 0.0) -> float:
    starts = Counter(round(line.x0) for line in lines if not line.running_head)
    return float(starts.most_common(1)[0][0]) if starts else fallback


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
    if not picture.labels and not picture.caption:
        return f"    <p{mark}>{image}</p>"
    inside = [f"      <p>{image}</p>"]
    if picture.caption:
        inside.append(f"      <figcaption>{escape(picture.caption)}</figcaption>")
    if picture.labels:
        labels = " ".join(escape(label) for label in picture.labels)
        inside.append(f'      <p class="{LABEL_CLASS}">{labels}</p>')
    return f"    <figure{mark}>\n" + "\n".join(inside) + "\n    </figure>"


def _render(blocks: list[Block], title: str,
            anchored: "set[int] | None" = None) -> tuple[str, dict]:
    """The section's markup, and what went into it.

    *anchored* names the pages the outline points at. The first block of such a
    page carries the anchor, and `counts["anchored"]` says which pages actually
    got one — a nav entry is only allowed to point where something is.
    """
    counts: dict = {"paragraphs": 0, "headings": 0, "anchored": []}
    wanted = set(anchored or ())
    body: list[str] = []
    for block in blocks:
        page = _block_page(block)
        mark = ""
        if page in wanted:
            wanted.discard(page)
            counts["anchored"].append(page)
            mark = f' id="{_anchor(page)}"'
        if block.kind == "image":
            body.append(_figure(block.picture, mark))
        elif block.kind == "head":
            body.append(f'    <p{mark} class="{RUNNING_HEAD_CLASS}">{escape(block.text)}</p>')
        elif block.kind in ("h1", "h2"):
            counts["headings"] += 1
            body.append(f"    <{block.kind}{mark}>{escape(block.text)}</{block.kind}>")
        elif block.continued:
            body.append(f'    <p{mark} class="{CONTINUED_CLASS}">{escape(block.text)}</p>')
        else:
            counts["paragraphs"] += 1
            body.append(f"    <p{mark}>{escape(block.text)}</p>")
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
    markup = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "  <head>\n"
        '    <meta charset="utf-8"/>\n'
        f"    <title>{escape(title or ' ')}</title>\n"
        "  </head>\n"
        "  <body>\n"
        + "\n".join(body)
        + "\n  </body>\n</html>\n"
    )
    return markup, counts


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
