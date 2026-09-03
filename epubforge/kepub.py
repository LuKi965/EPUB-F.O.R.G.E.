"""Kobo's own flavour of the file, written on request.

A Kobo reader opens a plain `.epub` with Adobe's renderer and a `.kepub.epub`
with its own, and only the second gives the reader what the device was bought
for: reading statistics, page numbers that match the book, highlights and
annotations, footnote pop-ups. The difference between the two files is not a
format — the package is the same EPUB — but a handful of markers the renderer
looks for:

* ``div#book-columns > div#book-inner`` around the body's content, which is
  what the renderer paginates;
* ``<span class="koboSpan" id="kobo.P.S">`` around every sentence and every
  image, which is what a highlight or a bookmark points at;
* the style block Kobo's own files carry, zeroing the wrapper's margins.

All three are what the reference converter writes — kepubify 4.0.4,
``kepub/transform.go``, the transforms it calls mandatory — and the sentence
splitter below is that program's state machine carried over rule for rule, so
a book converted here carries the ids the reference converter would give it.
Record 044 measures how often that holds on the shelf.

What this is not: a compatibility concession. :mod:`epubforge.compat` promises
that a measure never rewrites markup the book already had; this rewrites every
text node in the book. So it is a separate export with its own switch and its
own file name, and it is never applied to a plain ``.epub``.

Not carried over from the reference: smartened punctuation (this program does
not rewrite prose), the extra CSS and find-and-replace (a person's one-off
tweaks), and the blank page it inserts in front of a first chapter that is
not a cover — a page the publisher never wrote, added on a heuristic that
program's own comment calls subject to change. The condition it fires on is
reported instead, so a person holding a Kobo can judge.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import xhtml

SPAN_CLASS = "koboSpan"
COLUMNS_ID = "book-columns"
INNER_ID = "book-inner"
STYLE_CLASS = "kobostylehacks"
#: Kobo's own files carry a longer block (font sizes, link colours, every
#: margin zeroed); the reference converter keeps only the line that concerns
#: the wrapper it added, and so does this.
STYLE_TEXT = "div#book-inner { margin-top: 0; margin-bottom: 0;}"
EXTENSION = ".kepub.epub"

#: Elements whose text stays as it is: code and verse keep their whitespace,
#: and the rest are not text at all.
_KEEP_AS_IS = frozenset({"script", "style", "pre", "audio", "video", "svg", "math"})
#: Entering one of these starts a new paragraph counter — at the first span
#: written inside it, not on entry, so an empty one does not use up a number.
_NEW_PARAGRAPH = frozenset({"p", "ol", "ul", "table", "h1", "h2", "h3", "h4", "h5", "h6"})

_END = frozenset(".!?")
_EXTRA = frozenset("'\"”’“…")
#: ASCII only, as the reference's ``\s`` is: a no-break space after a full
#: stop does not end the sentence.
_SPACE = frozenset("\t\n\f\r ")


def split_sentences(text: str) -> list[str]:
    """Cut *text* where the reference converter cuts it.

    A sentence ends at ``.``, ``!`` or ``?``, one optional closing quote or
    ellipsis, and a run of ASCII whitespace; the whitespace belongs to the
    sentence it ends. What is left after the last cut is a sentence of its own
    when it is not empty, and an empty string splits into one empty sentence.
    The pieces always join back into the input.
    """
    default, after_end, after_extra, after_space = range(4)
    state = default
    sentences: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char in _END:
            kind = "end"
        elif char in _EXTRA:
            kind = "extra"
        elif char in _SPACE:
            kind = "space"
        else:
            kind = "any"

        cut = False
        if state == default:
            state = after_end if kind == "end" else default
        elif state == after_end:
            state = {"end": after_end, "extra": after_extra, "space": after_space}.get(kind, default)
        elif state == after_extra:
            state = {"end": after_end, "space": after_space}.get(kind, default)
        elif kind == "space":
            state = after_space
        else:
            cut = True
            state = after_end if kind == "end" else default
        if cut:
            sentences.append(text[start:index])
            start = index

    rest = text[start:]
    if rest or not sentences:
        sentences.append(rest)
    return sentences


@dataclass
class Marking:
    """What one document received."""

    #: Sentences wrapped.
    spans: int = 0
    #: Images wrapped.
    images: int = 0
    #: The two wrapper divs were added.
    wrapped: bool = False
    #: The style block was added.
    styled: bool = False
    #: The document already carried Kobo's spans; none were added.
    already: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.spans or self.images or self.wrapped or self.styled)


def _has_class(element, token: str) -> bool:
    return token in (element.get("class") or "").split()


def _body_of(root):
    return root.find(xhtml.qname("body"))


def already_marked(root) -> bool:
    """Whether a document carries Kobo's spans — one is enough, as it is for
    the reference converter."""
    body = _body_of(root)
    if body is None:
        return False
    return any(
        isinstance(e.tag, str) and _has_class(e, SPAN_CLASS) for e in body.iter()
    )


def _wrapped(body) -> bool:
    for child in body:
        if isinstance(child.tag, str) and child.get("id") == COLUMNS_ID:
            for inner in child:
                if isinstance(inner.tag, str) and inner.get("id") == INNER_ID:
                    return True
    return False


def _wrap_body(root, body) -> None:
    columns = root.makeelement(xhtml.qname("div"), {"id": COLUMNS_ID})
    inner = root.makeelement(xhtml.qname("div"), {"id": INNER_ID})
    inner.text = body.text
    body.text = None
    for child in list(body):
        # `append` moves the element and its tail with it; the order is kept.
        inner.append(child)
    columns.append(inner)
    body.append(columns)


def _styled(root) -> bool:
    head = root.find(xhtml.qname("head"))
    if head is None:
        return True  # nowhere to put it, and nothing to do
    return any(
        xhtml.local_name(child) == "style" and _has_class(child, STYLE_CLASS)
        for child in head
        if isinstance(child.tag, str)
    )


def _add_style(root) -> bool:
    head = root.find(xhtml.qname("head"))
    if head is None:
        return False
    style = root.makeelement(xhtml.qname("style"), {"type": "text/css", "class": STYLE_CLASS})
    style.text = STYLE_TEXT
    head.append(style)
    return True


class _Marker:
    """One document's counters, walking the tree in reading order.

    The reference walks a stack of nodes depth first; this walks the same
    order over lxml's shape, where text lives on elements as ``.text`` and
    ``.tail`` rather than as nodes of its own. Every element is rebuilt from
    its parts — its leading text, then each child with the text that follows
    it — and each piece of text either stays text or becomes a span, in place.
    """

    def __init__(self, root) -> None:
        self.root = root
        self.paragraph = 0
        self.segment = 0
        self.new_paragraph_pending = False
        self.spans = 0
        self.images = 0

    def _span(self):
        self.segment += 1
        return self.root.makeelement(
            xhtml.qname("span"),
            {"class": SPAN_CLASS, "id": f"kobo.{self.paragraph}.{self.segment}"},
        )

    def walk(self, element) -> None:
        if xhtml.local_name(element) in _NEW_PARAGRAPH:
            self.new_paragraph_pending = True

        parts: list[tuple[str, object]] = [("text", element.text)]
        for child in list(element):
            parts.append(("node", child))
            parts.append(("text", child.tail))
            child.tail = None
            element.remove(child)
        element.text = None

        last = [None]

        def emit_text(piece: str) -> None:
            if last[0] is None:
                element.text = (element.text or "") + piece
            else:
                last[0].tail = (last[0].tail or "") + piece

        def emit_node(node) -> None:
            element.append(node)
            last[0] = node

        for kind, payload in parts:
            if kind == "text":
                if payload:
                    self._text(payload, element, emit_text, emit_node)
                continue
            child = payload
            if not isinstance(child.tag, str):
                emit_node(child)  # a comment or a processing instruction
                continue
            name = xhtml.local_name(child)
            if name == "img":
                # A picture is a paragraph of its own, numbered at once.
                self.paragraph += 1
                self.segment = 0
                self.new_paragraph_pending = False
                span = self._span()
                span.append(child)
                emit_node(span)
                self.images += 1
            elif name in _KEEP_AS_IS:
                emit_node(child)
            else:
                self.walk(child)
                emit_node(child)

    def _text(self, text: str, parent, emit_text, emit_node) -> None:
        inside_paragraph = xhtml.local_name(parent) == "p"
        for sentence in split_sentences(text):
            # Whitespace between elements stays whitespace — except directly
            # inside a paragraph, where the reference wraps it too.
            if sentence.isspace() and not inside_paragraph:
                emit_text(sentence)
                continue
            if self.new_paragraph_pending:
                self.paragraph += 1
                self.segment = 0
                self.new_paragraph_pending = False
            span = self._span()
            span.text = sentence
            emit_node(span)
            self.spans += 1


def mark(root) -> Marking:
    """Give one parsed document Kobo's markers, in place.

    Idempotent in every part: a document that already has the wrappers, the
    style block or a single Kobo span keeps what it has, and only the missing
    parts are added — the same three checks the reference converter makes.
    """
    marking = Marking()
    body = _body_of(root)
    if body is None:
        return marking

    if not _styled(root):
        marking.styled = _add_style(root)
    if not _wrapped(body):
        _wrap_body(root, body)
        marking.wrapped = True
    if already_marked(root):
        marking.already = True
        return marking

    marker = _Marker(root)
    marker.walk(body)
    marking.spans = marker.spans
    marking.images = marker.images
    return marking


def first_page_reads_as_a_cover(book) -> tuple[bool, str | None]:
    """The reference converter's test for whether the first page needs a
    blank page in front of it — ``(is a cover, path of the first page)``.

    Kobo lays the first page of a KEPUB out as a full-screen cover, without
    margins. A first page that is a chapter therefore loses its margins, and
    the reference converter answers with a page of its own. The test is
    reproduced so the condition can be *reported*; the page is not added.
    """
    first = next((item for item in book.spine if item.linear), None)
    resource = book.get(first.path) if first else None
    if resource is None or not resource.is_content_doc:
        return True, None
    name = resource.basename.lower()
    if "cover" in name or "title" in name:
        return True, resource.path
    try:
        root = xhtml.parse_document(resource.data, resource.path).root
    except Exception:  # noqa: BLE001 — a page that will not parse is not judged
        return True, resource.path
    body = _body_of(root) if root is not None else None
    if body is None:
        return True, resource.path

    paragraphs = images = long_words = 0

    def visit(element) -> bool:
        nonlocal paragraphs, images, long_words
        name = xhtml.local_name(element)
        if name == "p":
            paragraphs += 1
            if paragraphs > 4:
                return True
        if name in ("img", "svg"):
            images += 1
            return False
        if name in ("script", "style", "pre", "audio", "video", "math"):
            return False
        for text in (element.text, *(child.tail for child in element)):
            for word in (text or "").split():
                if len(word) > 3:
                    long_words += 1
            if long_words > 20:
                return True
        return any(visit(child) for child in element if isinstance(child.tag, str))

    if visit(body):
        return False, resource.path
    if (images == 0 and long_words < 5) or images > 4:
        return False, resource.path
    return True, resource.path


__all__ = [
    "COLUMNS_ID",
    "EXTENSION",
    "INNER_ID",
    "SPAN_CLASS",
    "STYLE_CLASS",
    "STYLE_TEXT",
    "Marking",
    "already_marked",
    "first_page_reads_as_a_cover",
    "mark",
    "split_sentences",
]
