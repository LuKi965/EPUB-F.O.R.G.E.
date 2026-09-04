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


@dataclass
class Outline:
    """One outline entry that resolved to a page."""

    level: int
    title: str
    page: int


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
    report.stats["pdf_layout"] = layout.__dict__.copy()
    return book


def text_of(source: str) -> str:
    """Every character of the text layer, whitespace collapsed — the left side
    of K1 for a PDF source, in the order the reader joins the lines."""
    pages, _, _, _ = _read(source)
    return re.sub(r"\s+", " ", " ".join(line.text for page in pages for line in page.lines)).strip()


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
    for number, lt_page in enumerate(extract_pages(source, laparams=LAParams()), 1):
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
        page.columns = _two_columns(page)
        pages.append(page)

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


def _two_columns(page: Page) -> bool:
    """Two clusters of left edges, each narrower than half the page: columns."""
    if len(page.lines) < 8:
        return False
    starts = Counter(round(line.x0 / 10) * 10 for line in page.lines)
    common = [x for x, count in starts.most_common(2) if count >= 3]
    if len(common) < 2:
        return False
    left, right = sorted(common)
    return right - left > page.width * 0.35 and all(
        (line.x1 - line.x0) < page.width * 0.55 for line in page.lines
    )


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
        return " ".join(line.text.strip() for line in self.lines)


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
    for page in pages:
        pitch = _pitch(page)
        block_left = _block_left(page)
        width = _block_width(page, block_left)
        items: list[tuple[float, object]] = [(line.y1, line) for line in page.lines]
        items += [(picture.y1, picture) for picture in page.pictures]
        items.sort(key=lambda item: -item[0])
        for _, item in items:
            if isinstance(item, Picture):
                blocks.append(Block(kind="image", picture=item))
                current = None
                previous = None
                continue
            line = item
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
                or (kind == "p" and previous is not None
                    and (previous.x1 - block_left) < SHORT_LINE_RATIO * width
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
    return blocks


def _pitch(page: Page) -> float:
    ys = sorted({round(line.y1) for line in page.lines}, reverse=True)
    gaps = [a - b for a, b in zip(ys, ys[1:]) if 0 < a - b < 60]
    if not gaps:
        return 14.0
    gaps.sort()
    return float(gaps[len(gaps) // 2])


def _block_left(page: Page) -> float:
    starts = Counter(round(line.x0) for line in page.lines if not line.running_head)
    return float(starts.most_common(1)[0][0]) if starts else 0.0


def _block_width(page: Page, left: float) -> float:
    rights = sorted(line.x1 for line in page.lines if not line.running_head)
    if not rights:
        return page.width
    return max(1.0, rights[int(0.9 * (len(rights) - 1))] - left)


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
