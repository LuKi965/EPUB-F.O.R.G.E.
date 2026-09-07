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


@dataclass
class Picture:
    name: str
    data: bytes
    media_type: str
    page: int
    y1: float


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
    column_pages: int = 0
    body_size: float = 0.0
    torn_paragraphs: int = 0
    fragment_paragraphs: int = 0
    median_paragraph: int = 0


# ----------------------------------------------------------------- reading


def read_pdf(source: str, report: Report, budget=None) -> Book:
    """Load *source* into a :class:`Book`, or refuse it with the reason said."""
    pages, info, outline, layout = _read(source)
    layout.pages = len(pages)
    layout.lines = sum(len(page.lines) for page in pages)
    layout.characters = sum(
        len(line.text.replace(" ", "")) for page in pages for line in page.lines
    )
    if not pages or layout.characters < MIN_CHARACTERS_PER_PAGE * len(pages):
        report.add(
            "pdf",
            Level.ERROR,
            "pdf.no-text-layer",
            values={"pages": len(pages), "characters": layout.characters},
            location=source,
        )
        raise EpubReadError("the PDF has no text layer to read; scanning it would need OCR")

    _mark_running_heads(pages, layout)
    layout.column_pages = sum(1 for page in pages if page.columns)
    body_size = _body_size(pages)
    layout.body_size = body_size

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
    for index, (title, blocks) in enumerate(sections, 1):
        path = f"text/section-{index:04d}.xhtml"
        # A section the outline did not name and no heading opened: the first
        # is the book's own front matter and takes the title; a later one is
        # named by its number, which is the one thing that is true of it.
        label = title or (book.metadata.title if index == 1 else f"{index}")
        markup, counts = _render(blocks, label, book.metadata.language or "")
        layout.paragraphs += counts["paragraphs"]
        layout.headings += counts["headings"]
        for block in blocks:
            if block.kind == "image":
                picture = block.picture
                if picture.name not in book.resources:
                    book.add(Resource(path=picture.name, media_type=picture.media_type, data=picture.data))
                    layout.images += 1
        book.add(Resource(path=path, media_type="application/xhtml+xml", data=markup.encode("utf-8")))
        book.spine.append(SpineItem(path=path))
        book.toc.append(NavPoint(label=label, target=path))
    layout.running_heads = sum(1 for page in pages for line in page.lines if line.running_head)

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
            "sections": len(sections),
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
    # The reader's own count against the raw one: a character the page draws
    # and no line of this reader carries is a loss that has not happened yet
    # and is about to. Said here, with the number, so the K1-PDF refusal that
    # follows has its reason on record; the refusal itself is the gate's.
    placed: Counter = Counter()
    for page in pages:
        for line in page.lines:
            for character in line.text:
                if not character.isspace():
                    placed[character] += 1
    unplaced = character_inventory(source) - placed
    if unplaced:
        sample = "".join(sorted(unplaced)[:12])
        report.add(
            "pdf",
            Level.WARN,
            "pdf.characters-unplaced",
            values={"count": sum(unplaced.values()), "sample": sample},
            location=source,
        )
    report.stats["pdf_characters_unplaced"] = sum(unplaced.values())
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
    of K1 for a PDF source, joined line to line by the same rule the reader
    uses, so that the two sides agree about where a line break was a space
    and where it was not."""
    pages, _, _, _ = _read(source)
    return re.sub(r"\s+", " ", join_lines(line.text for page in pages for line in page.lines)).strip()


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
            return Picture(f"images/pdf-{number:04d}.jpg", image.stream.get_rawdata(), "image/jpeg", page, image.y1)
        if "JPXDecode" in filters:
            data = _png_via_pillow(io.BytesIO(image.stream.get_rawdata()))
            return Picture(f"images/pdf-{number:04d}.png", data, "image/png", page, image.y1) if data else None
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
        return Picture(f"images/pdf-{number:04d}.png", out.getvalue(), "image/png", page, image.y1)
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
    if body_size <= 0:
        return None
    if line.size >= body_size * BODY_RATIO_H1:
        return "h1"
    if line.size >= body_size * BODY_RATIO_H2:
        return "h2"
    return None


def _blocks(pages: list[Page], body_size: float, breaks: set[int] = frozenset()) -> list[Block]:
    """Lines joined into paragraphs and headings, pictures in the flow. A
    page in *breaks* is one the outline names as a chapter's first, and a
    paragraph does not run into a new chapter: the first line there starts
    a block whatever the geometry says."""
    blocks: list[Block] = []
    previous: Line | None = None
    current: Block | None = None
    interrupted = False
    previous_left = previous_width = 0.0
    for page in pages:
        pitch = _pitch(page)
        # Measured per column on a two-column page: against the page's own
        # left edge every right-hand line looked indented and began a
        # paragraph — 5 552 paragraphs where the source had 2 036.
        geometry = _column_geometry(page)
        # The lines in their reading order (column by column on a two-column
        # page); a picture goes in before the first line that stands below
        # it, which on a one-column page is its place in the flow.
        items: list[object] = list(page.lines)
        for picture in sorted(page.pictures, key=lambda p: -p.y1):
            place = next((i for i, line in enumerate(items) if isinstance(line, Line) and line.y1 < picture.y1), len(items))
            items.insert(place, picture)
        for item in items:
            if isinstance(item, Picture):
                blocks.append(Block(kind="image", picture=item))
                current = None
                previous = None
                continue
            line = item
            block_left, width = geometry[0 if page.split is None or line.x0 < page.split else 1]
            if line.running_head:
                blocks.append(Block(kind="head", lines=[line]))
                # A running head does not end the paragraph it interrupts,
                # but the text keeps the page's order: what follows is the
                # paragraph's second half, marked so the stage can rejoin it.
                interrupted = current is not None and current.kind == "p"
                continue
            level = _heading_level(line, body_size)
            kind = level or "p"
            starts_new = (
                current is None
                or current.kind != kind
                or (previous is not None and line.page != previous.page and line.page in breaks)
                or (previous is not None and previous.page == line.page
                    and previous.y0 - line.y1 > PARAGRAPH_GAP_RATIO * pitch)
                or (kind == "p" and line.x0 - block_left > INDENT_POINTS and previous is not None)
                # The short line is the *previous* line, measured in its own
                # column: the last line of a left-hand column is not short
                # against the right-hand column's edge.
                or (kind == "p" and previous is not None
                    and (previous.x1 - previous_left) < SHORT_LINE_RATIO * previous_width
                    and _starts_a_sentence(line.text))
            )
            if starts_new:
                current = Block(kind=kind)
                blocks.append(current)
            elif interrupted:
                current = Block(kind=kind, continued=True)
                blocks.append(current)
            interrupted = False
            current.lines.append(line)
            previous = line
            previous_left, previous_width = block_left, width
    return blocks


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


def _render(blocks: list[Block], title: str, language: str) -> tuple[str, dict]:
    counts = {"paragraphs": 0, "headings": 0}
    body: list[str] = []
    for block in blocks:
        if block.kind == "image":
            body.append(f'    <p><img src="../{escape(block.picture.name)}" alt=""/></p>')
        elif block.kind == "head":
            body.append(f'    <p class="{RUNNING_HEAD_CLASS}">{escape(block.text)}</p>')
        elif block.kind in ("h1", "h2"):
            counts["headings"] += 1
            body.append(f"    <{block.kind}>{escape(block.text)}</{block.kind}>")
        elif block.continued:
            body.append(f'    <p class="{CONTINUED_CLASS}">{escape(block.text)}</p>')
        else:
            counts["paragraphs"] += 1
            body.append(f"    <p>{escape(block.text)}</p>")
    lang = f' xml:lang="{escape(language)}" lang="{escape(language)}"' if language else ""
    markup = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"{lang}>\n'
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
