"""What the books *are*, as opposed to what the tool does to them.

`survey.py` answers "what did the pipeline say about this library" — useful, but
circular: it can only report defects the tool already knows how to name. This
module answers the prior question. Where did these files come from, what damage
do they carry, and what typographic conventions do they use? That is what
decides which rules are worth writing at all: a library that is 70% Calibre
output needs different work from one that is half PDF conversions.

Nothing here modifies a book, and nothing here records a word of anybody's text.
The output is counts and frequencies, keyed by a hash of the file. A separate
map file ties hashes back to filenames and stays on the machine that made it.

**Built on `read_epub`, deliberately.** A standalone scanner working on raw
bytes is easy to write and wrong in ways that are hard to see: `&nbsp;` counted
as six characters of text rather than one non-breaking space, XHTML indentation
counted as double spaces, and a hyphen before a source line break counted as
evidence of PDF hyphenation when it is evidence of a pretty-printer. Those are
not hypothetical — they are the three defects the measurements below would have
inherited. Reading through the same loader as everything else means entity
decoding, encoding detection and archive limits are already correct, and there
is only ever one place in this codebase that knows how to open an EPUB.
"""

from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import re
import unicodedata
from dataclasses import dataclass, field

from . import watermark, xhtml
from .reader import EpubReadError, read_epub
from .report import Report

# --------------------------------------------------------------- provenance

#: Traces of the tool that produced a file, searched in the package document,
#: the stylesheets and the markup. The result is a *list*: files are layered —
#: exported from InDesign, converted by Calibre, patched in Sigil — and that is
#: information rather than noise.
GENERATOR_SIGNATURES: dict[str, tuple[str, ...]] = {
    "calibre": (r"(?i)\bcalibre\b", r'class="[^"]*\bcalibre\d+\b', r"calibre:series"),
    "indesign": (r"_idGenParaOverride", r"_idGenObjectStyle", r"(?i)InDesign"),
    "word": (r"\bMsoNormal\b", r"\bmso-[a-z-]+\s*:", r"<o:p>"),
    "sigil": (r"(?i)Sigil version", r'class="[^"]*\bsgc-'),
    "vellum": (r"(?i)\bvellum\b",),
    "pressbooks": (r"(?i)pressbooks", r'class="[^"]*\bwp-'),
    "pdf-or-ocr": (r'class="[^"]*\bft\d+\b', r"(?i)ABBYY", r"(?i)pdftohtml"),
    "from-mobi": (r"\bfilepos\d+", r"kindle:pos"),
    "gutenberg": (r"x-ebookmaker", r"(?i)Project Gutenberg"),
    "self-publishing": (r"(?i)\b(epubli|lulu\.com|blurb|draft2digital)\b",),
}

#: Class names that carry no meaning — the signature of a converter numbering
#: styles rather than naming them.
_MEANINGLESS_CLASS = re.compile(
    r"^(?:calibre\d+|c\d+|p\d+|s\d+|x\d+|ft\d+|span\d+|para\d+|style\d+)$"
)

_CSS_CLASS = re.compile(r"\.([A-Za-z_][\w-]*)")

# --------------------------------------------------------------- typography

QUOTE_FORMS = {
    "„": "pl-open", "”": "pl-close",
    "«": "guillemet-open", "»": "guillemet-close",
    "“": "en-open", "”": "en-close",
    '"': "straight",
}
DASH_FORMS = {"-": "hyphen", "–": "en-dash", "—": "em-dash"}

#: UTF-8 read as Latin-1 or CP1252 — the classic double-encoding wreck.
MOJIBAKE = re.compile(r"Ã[\x80-\xbf]|Â[\xa0-\xbf]|â€|Å[\x81-\xbc]|Ä[\x84-\x99]")

#: Polish single-letter conjunctions, which typographic convention binds to the
#: following word. Measured both ways, so the answer says whether anybody has
#: already done this to the book — which decides whether we should.
_CONJUNCTION_LOOSE = re.compile(r"(?i)(?<![^\s(„«])[aiouwz] (?=\w)")
_CONJUNCTION_BOUND = re.compile(r"(?i)(?<![^\s(„«])[aiouwz] ")

#: A hyphen followed by a space, mid-word: what a PDF conversion leaves where it
#: broke a word across lines. Measured on *rendered* text, which is what makes it
#: meaningful — the reader really does see that space, whether it came from a
#: converter or from a source line break, and either way the word is wrong. A
#: pretty-printer cannot fake it, because pretty-printers wrap at spaces and
#: never leave a hyphen hanging at the end of a line.
_BROKEN_HYPHEN = re.compile(r"(?i)[a-ząćęłńóśźż]- (?=[a-ząćęłńóśźż])")

_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}


@dataclass
class Book:
    """One book's measurements. No text, no title, no author."""

    identifier: str
    size_mb: float
    fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.identifier, "size_mb": self.size_mb, **self.fields}


def _percent(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _rendered_text(root) -> str:
    """Readable text with entities decoded and whitespace collapsed.

    The distinction matters more than it looks. On raw markup, `&nbsp;` is six
    characters that are not a space, every indented line is a run of double
    spaces, and a hyphen before a newline looks like a word broken across lines.
    All three would be counted as damage that is not there.
    """
    body = root.find(xhtml.qname("body"))
    text = "".join((body if body is not None else root).itertext())
    return unicodedata.normalize("NFC", re.sub(r"[^\S ]+", " ", text))


def spine_text(path: pathlib.Path) -> str:
    """The readable text of the reading order, in order.

    Separate from `measure` because a count is not enough to check K1 against.
    Two books can hold the same number of characters and not the same
    characters, so the corpus comparison needs the text itself.
    """
    parsed = read_epub(str(path), Report(source=str(path)))
    spine_paths = {item.path for item in parsed.spine}
    parts: list[str] = []
    for item in parsed.spine:
        document = parsed.get(item.path)
        if document is None or item.path not in spine_paths:
            continue
        try:
            root, _ = xhtml.parse(document.data)
        except Exception:  # noqa: BLE001 — one bad document must not stop the read
            continue
        parts.append(_rendered_text(root))
    return " ".join(parts)


def measure(path: pathlib.Path) -> Book:
    """Everything we are willing to record about one book."""
    raw = path.read_bytes()
    book = Book(hashlib.sha256(raw).hexdigest()[:16], round(len(raw) / 1024**2, 2))

    try:
        parsed = read_epub(str(path), Report(source=str(path)))
    except EpubReadError as exc:
        book.fields["error"] = str(exc)
        return book

    documents = [r for r in parsed.content_docs()]
    spine_paths = {item.path for item in parsed.spine}
    styles = parsed.by_type("style")
    css = "\n".join(sheet.text() for sheet in styles)
    markup = "\n".join(document.text() for document in documents)

    # --- structure ---------------------------------------------------------
    book.fields.update(
        version=parsed.source_version,
        language=parsed.metadata.language or "?",
        documents=len(documents),
        stylesheets=len(styles),
        images=len(parsed.by_type("image")),
        fonts=len(parsed.by_type("font")),
        spine_items=len(parsed.spine),
        toc_entries=sum(1 for root in parsed.toc for _ in root.walk()),
        has_nav=parsed.nav_path is not None,
        has_ncx=parsed.ncx_path is not None,
        has_cover=parsed.cover_path is not None,
        has_page_list=bool(parsed.page_list),
        fixed_layout=parsed.rendition.get("layout") == "pre-paginated",
        rtl=parsed.page_progression_direction == "rtl",
        drm=parsed.has_drm,
        obfuscated_fonts=bool(parsed.encrypted) and not parsed.has_drm,
        largest_image_mb=round(
            max((len(r.data) for r in parsed.by_type("image")), default=0) / 1024**2, 2
        ),
    )

    # --- provenance --------------------------------------------------------
    # The package document matters as much as the markup: `calibre:series` and
    # InDesign's identifiers live there, and the model has normalised them away
    # by the time anything else could look.
    package = (parsed.source_package or b"").decode("utf-8", "replace")
    material = f"{package}\n{markup}\n{css}"
    book.fields["generators"] = sorted(
        name
        for name, patterns in GENERATOR_SIGNATURES.items()
        if any(re.search(pattern, material) for pattern in patterns)
    )
    # A visible watermark is what makes a bookshop file a bookshop file, and it
    # is the family the roadmap wants most of. Nothing else here can stand in
    # for it: shop EPUBs carry no generator trace of their own.
    book.fields["watermarked"] = any(
        watermark.is_visible_notice(fragment)
        for fragment in re.findall(r">([^<>]{20,400})<", markup)
    )

    # --- damage ------------------------------------------------------------
    classes = collections.Counter(
        name
        for attribute in re.findall(r'class="([^"]*)"', markup)
        for name in attribute.split()
    )
    declared = set(_CSS_CLASS.findall(css))
    blocks = 0
    spans = 0
    bare_spans = 0
    nested_spans = 0
    empty_paragraphs = 0
    images_without_alt = 0
    images_empty_alt = 0
    text_parts: list[str] = []
    spine_text_parts: list[str] = []

    for document in documents:
        try:
            root, _ = xhtml.parse(document.data)
        except Exception:  # noqa: BLE001 — one bad document must not stop the count
            continue
        rendered = _rendered_text(root)
        text_parts.append(rendered)
        if document.path in spine_paths:
            spine_text_parts.append(rendered)
        for element in xhtml.iter_elements(root):
            tag = xhtml.local_name(element).lower()
            if tag in _BLOCK_TAGS:
                blocks += 1
                if tag == "p" and not (element.text or "").strip() and not len(element):
                    empty_paragraphs += 1
            elif tag == "span":
                spans += 1
                if not any(
                    element.get(a) or element.get(f"{{{xhtml.EPUB_NS}}}type")
                    for a in ("id", "lang", "role", "aria-hidden")
                ):
                    bare_spans += 1
                if any(xhtml.local_name(c).lower() == "span" for c in element):
                    nested_spans += 1
            elif tag == "img":
                alt = element.get("alt")
                if alt is None:
                    images_without_alt += 1
                elif not alt.strip():
                    images_empty_alt += 1

    book.fields.update(
        blocks=blocks,
        distinct_classes=len(classes),
        meaningless_classes=sum(1 for name in classes if _MEANINGLESS_CLASS.match(name)),
        classes_per_100_blocks=round(100 * len(classes) / blocks, 1) if blocks else 0.0,
        dead_classes=len(declared - set(classes)),
        classes_without_rules=len(set(classes) - declared),
        spans=spans,
        bare_spans=bare_spans,
        nested_spans=nested_spans,
        spans_per_block=round(spans / blocks, 2) if blocks else 0.0,
        empty_paragraphs=empty_paragraphs,
        images_without_alt=images_without_alt,
        images_empty_alt=images_empty_alt,
        inline_styles=len(re.findall(r'\bstyle="', markup)),
        presentational_attributes=len(
            re.findall(r'\b(?:align|bgcolor|face|valign|border)="', markup)
        ),
        absolute_font_sizes=len(re.findall(r"font-size\s*:\s*[\d.]+(?:px|pt)", material)),
        forced_page_breaks=len(
            re.findall(r"page-break-(?:before|after)\s*:\s*always", material)
        ),
    )

    # --- typography --------------------------------------------------------
    text = " ".join(text_parts)
    characters = len(text)
    book.fields.update(
        text_characters=characters,
        # The reader's text, excluding anything not in the spine. A rebuild
        # legitimately adds a navigation document, and that document is full of
        # chapter titles: comparing the total before and after would report the
        # table of contents as text that appeared from nowhere. This is the
        # figure K1 is about — what a person actually reads, in reading order.
        spine_text_characters=len(" ".join(spine_text_parts)),
        quotes={label: text.count(mark) for mark, label in QUOTE_FORMS.items() if text.count(mark)},
        dashes={label: text.count(mark) for mark, label in DASH_FORMS.items()},
        ellipsis_character=text.count("…"),
        ellipsis_dots=len(re.findall(r"(?<!\.)\.\.\.(?!\.)", text)),
        non_breaking_spaces=text.count(" "),
        soft_hyphens=text.count("­"),
        zero_width=text.count("​"),
        # Deliberately not measured: runs of ordinary spaces. HTML collapses
        # whitespace, so a double space is invisible to a reader and cannot be
        # damage; counting it on markup measures how the file was indented.
        mojibake=len(MOJIBAKE.findall(text)),
        broken_hyphens=len(_BROKEN_HYPHEN.findall(text)),
        conjunctions_loose=len(_CONJUNCTION_LOOSE.findall(text)),
        conjunctions_bound=len(_CONJUNCTION_BOUND.findall(text)),
    )
    return book


# ----------------------------------------------------------------- coverage

#: The corpus the roadmap asks for, family by family, with how many books each
#: family needs. Taken verbatim from `docs/ROADMAP.md`, point [1] — "dobierać po
#: pochodzeniu, nie po tytule": what a book was made by decides what is wrong
#: with it, and a hundred books from one generator teach less than ten from ten.
#:
#: A book counts towards every family it belongs to; layered files are real
#: (InDesign → Calibre → Sigil) and pretending otherwise would undercount both.
#: Hyphens frozen at what used to be a line end — "sta- rożytności" — is what a
#: PDF leaves behind when its line breaks become text. Measured rather than
#: guessed: nine properly typeset books in this repository and on the owner's
#: disk score exactly **0**, and the one book known to come from a PDF scores
#: 16. The floor sits well above the noise because a false positive here is
#: worse than a miss: it tells someone a family is covered when it is not.
#:
#: This exists because the generator signatures cannot see the case that
#: matters most. They look for ABBYY, pdftohtml and `ft0` class names — traces
#: of three specific tools — and a conversion done by a language model leaves
#: none of them. The family the roadmap calls the worst case for typography was
#: the one family the detector was blind to.
PDF_HYPHEN_FLOOR = 5

CORPUS_FAMILIES: dict[str, tuple[int, str]] = {
    "polish-bookshop": (5, "księgarnie polskie — znak wodny, strony prawne"),
    "indesign-vellum": (4, "InDesign / Vellum — wydawcy dbający o skład"),
    "calibre": (4, "Calibre — konwersja z czegokolwiek"),
    "word": (3, "Word / Google Docs — self-publishing"),
    "pdf-or-ocr": (3, "konwersja z PDF, OCR — najgorszy przypadek dla typografii"),
    "from-mobi": (2, "back-konwersja z MOBI/AZW3 — puste kotwice filepos"),
    "epub2": (3, "EPUB 2 sprzed 2012 — <guide>, NCX, brak nawigacji"),
    "fixed-layout": (2, "fixed-layout, komiks — sprawdzian trybu minimalnego"),
    "pathological": (3, "patologie — brzegi pamięciowe i wydajnościowe"),
    "public-domain": (3, "domena publiczna — jedyne, które wolno commitować"),
}


def families(fields: dict) -> set[str]:
    """Which of the roadmap's families one measured book belongs to."""
    if "error" in fields:
        return set()
    generators = set(fields.get("generators") or ())
    found = set()
    if (
        fields.get("watermarked")
        and str(fields.get("language", "")).lower().startswith("pl")
        and "gutenberg" not in generators
    ):
        # Gutenberg's licence page reads as a purchase notice to the watermark
        # detector, and it is not one: nobody bought that book.
        found.add("polish-bookshop")
    if generators & {"indesign", "vellum"}:
        found.add("indesign-vellum")
    if "calibre" in generators:
        found.add("calibre")
    if "word" in generators:
        found.add("word")
    if "pdf-or-ocr" in generators or fields.get("broken_hyphens", 0) >= PDF_HYPHEN_FLOOR:
        found.add("pdf-or-ocr")
    if "from-mobi" in generators:
        found.add("from-mobi")
    if str(fields.get("version", "")).startswith("2"):
        found.add("epub2")
    if fields.get("fixed_layout"):
        found.add("fixed-layout")
    if "gutenberg" in generators:
        found.add("public-domain")
    # The edges, where memory and performance failures live and nowhere else.
    if (
        not fields.get("has_cover")
        or fields.get("spine_items", 0) >= 400
        or fields.get("largest_image_mb", 0) >= 8
        or fields.get("documents", 0) <= 1
    ):
        found.add("pathological")
    return found


def coverage(books: list[Book]) -> dict[str, dict]:
    """How far the library is from the corpus the roadmap describes.

    A corpus is not "enough books". It is enough books *of each kind*, because
    a rule written without a family represented is a rule nobody has tested —
    and the family missing today is the one whose defects surface at a user.
    """
    counts: collections.Counter = collections.Counter()
    for book in books:
        for family in families(book.fields):
            counts[family] += 1
    return {
        name: {
            "have": counts.get(name, 0),
            "want": want,
            "short": max(want - counts.get(name, 0), 0),
            "what": description,
        }
        for name, (want, description) in CORPUS_FAMILIES.items()
    }


def coverage_report(books: list[Book]) -> str:
    """The gap, as a list of what to go and find."""
    rows = coverage(books)
    short = {name: row for name, row in rows.items() if row["short"]}
    lines = ["corpus coverage (docs/ROADMAP.md, point 1):"]
    for name, row in rows.items():
        mark = "  " if not row["short"] else "->"
        lines.append(
            f"{mark} {name:18} {row['have']:3} / {row['want']:<3}  {row['what']}"
        )
    if short:
        lines += [
            "",
            f"{len(short)} famil{'y' if len(short) == 1 else 'ies'} short. "
            "A rule written for a family the corpus does not hold is untested "
            "in the only way that counts.",
        ]
    else:
        lines += ["", "every family is represented."]
    return "\n".join(lines)


# ------------------------------------------------------------------ summary

def summarise(books: list[Book]) -> str:
    """The shape of the library, as prose a person can act on."""
    good = [b for b in books if "error" not in b.fields]
    if not good:
        return "nothing could be read"

    lines = [f"{len(books)} book(s), {len(good)} readable", ""]

    provenance: collections.Counter = collections.Counter()
    for book in good:
        for generator in book.fields["generators"] or ["unrecognised"]:
            provenance[generator] += 1
    lines.append("provenance (a book may carry several traces):")
    for name, count in provenance.most_common():
        lines.append(f"  {name:18} {count:4}  {_percent(count, len(good)):5.1f}%")

    lines += ["", coverage_report(good)]

    def share(predicate) -> str:
        count = sum(1 for book in good if predicate(book.fields))
        return f"{count:4}  {_percent(count, len(good)):5.1f}%"

    lines += [
        "",
        "structure:",
        f"  EPUB 2                        {share(lambda f: f['version'].startswith('2'))}",
        f"  fixed layout                  {share(lambda f: f['fixed_layout'])}",
        f"  right-to-left                 {share(lambda f: f['rtl'])}",
        f"  has print page numbers        {share(lambda f: f['has_page_list'])}",
        f"  obfuscated fonts              {share(lambda f: f['obfuscated_fonts'])}",
        f"  DRM (refused)                 {share(lambda f: f['drm'])}",
        "",
        "damage:",
        f"  class explosion (>15/100)     {share(lambda f: f['classes_per_100_blocks'] > 15)}",
        f"  span soup (>1.5 per block)    {share(lambda f: f['spans_per_block'] > 1.5)}",
        f"  dead CSS classes (>10)        {share(lambda f: f['dead_classes'] > 10)}",
        f"  empty paragraphs (>20)        {share(lambda f: f['empty_paragraphs'] > 20)}",
        f"  mojibake                      {share(lambda f: f['mojibake'] > 0)}",
        f"  images without alt            {share(lambda f: f['images_without_alt'] > 0)}",
        f"  presentational attributes     {share(lambda f: f['presentational_attributes'] > 0)}",
        f"  absolute font sizes (>10)     {share(lambda f: f['absolute_font_sizes'] > 10)}",
        "",
        "typography:",
        f"  hyphens left by PDF breaks    {share(lambda f: f['broken_hyphens'] > 20)}",
        f"  straight quotes dominate      {share(lambda f: f['quotes'].get('straight', 0) > f['quotes'].get('pl-open', 0))}",
        f"  dialogue on hyphens not dashes{share(lambda f: f['dashes']['hyphen'] > 3 * (f['dashes']['em-dash'] + f['dashes']['en-dash']))}",
        f"  ellipsis typed as three dots  {share(lambda f: f['ellipsis_dots'] > f['ellipsis_character'])}",
        f"  conjunctions left unbound     {share(lambda f: f['conjunctions_bound'] < 0.1 * f['conjunctions_loose'])}",
    ]
    return "\n".join(lines)


def to_json(books: list[Book]) -> str:
    return json.dumps([book.to_dict() for book in books], indent=1, ensure_ascii=False)


__all__ = [
    "Book",
    "CORPUS_FAMILIES",
    "PDF_HYPHEN_FLOOR",
    "GENERATOR_SIGNATURES",
    "coverage",
    "coverage_report",
    "families",
    "measure",
    "summarise",
    "to_json",
]
