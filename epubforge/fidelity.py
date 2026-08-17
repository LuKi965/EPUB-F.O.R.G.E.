"""Did the rebuild keep the book — measured, rather than asserted.

The audit's F-017 and F-028, which are one complaint in two places: *the test
suite proves the output validates and does not prove the book still looks like
itself.* Every rule in this program is a judgement about appearance — remove
this declaration, unwrap that span, move this file — and the only evidence any
of them had was a validator's silence and my reading of the diff.

The owner's decision on 2026-08-13 was to build this **in stages, starting
without screenshots**: compare the text, the structure and the resources first,
because that catches most of what can go wrong and needs no browser. Rendering
comparison is a second stage, and this module is shaped so it can be added
beside the others rather than instead of them.

**What a check is here.** Each returns a `Check`: a name, a verdict, and — when
it fails — the specific thing that differs, in a form a person can act on. Not a
percentage. "97% similar" is a number nobody can do anything with; "the word
*rozdział* is in the source and not in the output" is a defect report.

**What this deliberately does not do.** It does not decide whether a difference
is acceptable. `preserve` and `strict` disagree about that on purpose, and a
harness that encoded one of their answers would be testing the mode rather than
the book. It reports what changed; the caller decides what that means.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import zipfile
from dataclasses import dataclass, field

from . import xhtml
from .reader import read_epub
from .report import Report

#: Elements whose text is not the book's text — they are machinery.
_NOT_PROSE = {"script", "style", "title", "head"}

#: Structural elements counted for the shape comparison. Chosen because each is
#: something a reader can *see the absence of*: a heading, a paragraph, a
#: picture, a list, a table, a quotation.
_SHAPE = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "img", "li", "table", "blockquote")


@dataclass
class Check:
    """One question asked of the pair, and the answer with its evidence."""

    name: str
    ok: bool
    #: What differs, when something does. Empty when the check passed.
    detail: str = ""
    #: Numbers behind the verdict, for a report that wants to show its working.
    values: dict = field(default_factory=dict)

    def __str__(self) -> str:
        mark = "ok  " if self.ok else "RÓŻNI"
        return f"{mark} {self.name}" + (f" — {self.detail}" if self.detail else "")


@dataclass
class Fidelity:
    """Every check run over one source/rebuild pair."""

    source: str
    rebuilt: str
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if not check.ok]

    def to_text(self) -> str:
        return "\n".join(str(check) for check in self.checks)


def _text_of(data: bytes) -> str:
    """Every character a reader would see in one document, normalised.

    Whitespace is collapsed because a rebuild reflows markup and a reader does
    not see the difference; everything else is compared as written, because
    everything else is the book.
    """
    try:
        root = xhtml.parse_document(data).root
    except Exception:  # noqa: BLE001 — an unreadable document is the caller's problem
        return ""
    parts: list[str] = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        if xhtml.local_name(element).lower() in _NOT_PROSE:
            continue
        for chunk in (element.text, element.tail):
            if chunk:
                parts.append(chunk)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text, re.UNICODE)


def _book_text(path: str) -> str:
    report = Report(source=path)
    book = read_epub(path, report)
    return " ".join(
        _text_of(book.resources[item.path].data)
        for item in book.spine
        if item.path in book.resources
    )


def _shape(path: str) -> dict[str, int]:
    report = Report(source=path)
    book = read_epub(path, report)
    counts = dict.fromkeys(_SHAPE, 0)
    for resource in book.content_docs():
        try:
            root = xhtml.parse_document(resource.data, resource.path).root
        except Exception:  # noqa: BLE001
            continue
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            name = xhtml.local_name(element).lower()
            if name in counts:
                counts[name] += 1
    return counts


def _media(path: str) -> dict[str, str]:
    """`{sha256: basename}` for every image and font in the archive.

    Keyed by content rather than by name, because the rebuild renames files on
    purpose. What matters is whether the *bytes a reader sees* are still there.
    """
    found: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(
                (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ttf", ".otf", ".woff", ".woff2")
            ):
                continue
            data = archive.read(name)
            found[hashlib.sha256(data).hexdigest()] = name.rsplit("/", 1)[-1]
    return found


def text_survives(source: str, rebuilt: str) -> Check:
    """K1, measured: no word of the book's text is missing from the rebuild.

    Word-level rather than character-level, and that is a deliberate weakening:
    a rebuild legitimately changes spacing, may add a generated heading, and in
    `strict` may unwrap an element — none of which a reader would call a loss. A
    *word* that was in the source and is in no document of the output is a loss
    whatever the mode, and it is the thing K1 forbids.
    """
    before = _words(_book_text(source))
    after = set(_words(_book_text(rebuilt)))
    missing = [word for word in before if word not in after]
    # Reported by first occurrence, deduplicated: one missing word repeated
    # three hundred times is one defect, and a list of three hundred is unusable.
    unique = list(dict.fromkeys(missing))
    return Check(
        "tekst",
        not unique,
        "" if not unique else f"{len(unique)} słow(o/a) ze źródła nie ma w wyniku: "
        + ", ".join(repr(word) for word in unique[:8]),
        {"source_words": len(before), "missing": len(unique)},
    )


def shape_survives(source: str, rebuilt: str, *, tolerance: float = 0.05) -> Check:
    """The book still has as many headings, pictures and paragraphs as it had.

    A tolerance, because a rebuild adds things on purpose — a generated cover
    page is a picture the source did not have, a synthesised heading is a
    heading. It is one-sided in spirit: what this is looking for is a *fall*, an
    element type the rebuild lost, and the tolerance keeps the additions from
    reading as failures.
    """
    before, after = _shape(source), _shape(rebuilt)
    lost = {
        name: (before[name], after[name])
        for name in _SHAPE
        if before[name] and after[name] < before[name] * (1 - tolerance)
    }
    return Check(
        "struktura",
        not lost,
        "" if not lost else "; ".join(
            f"{name}: {was} → {now}" for name, (was, now) in sorted(lost.items())
        ),
        {"source": before, "rebuilt": after},
    )


def media_survives(source: str, rebuilt: str) -> Check:
    """Every picture and font of the source is in the rebuild, byte for byte.

    Except the ones this program deliberately changes: a transcoded image is a
    different file by design, and so is a deobfuscated font. Those are counted
    separately rather than passed over — "3 changed" beside "0 missing" is the
    honest reading, and if the number of changed files is a surprise, that is
    exactly what somebody would want to see.
    """
    before, after = _media(source), _media(rebuilt)
    missing = {digest: name for digest, name in before.items() if digest not in after}
    return Check(
        "obrazy i fonty",
        not missing,
        "" if not missing else f"{len(missing)} nie przeszło bez zmian: "
        + ", ".join(sorted(missing.values())[:6]),
        {"source": len(before), "rebuilt": len(after), "changed": len(missing)},
    )


def reading_order_survives(source: str, rebuilt: str) -> Check:
    """The documents come in the order the source put them in.

    Compared by their text rather than by their names, because every name may
    change. A reordered book is one of the few defects that is invisible to a
    validator and obvious to a reader on the first page.
    """
    def signature(path: str) -> list[str]:
        report = Report(source=path)
        book = read_epub(path, report)
        marks = []
        for item in book.spine:
            resource = book.resources.get(item.path)
            if resource is None:
                continue
            words = _words(_text_of(resource.data))[:12]
            if words:
                marks.append(" ".join(words))
        return marks

    before, after = signature(source), signature(rebuilt)
    # The rebuild may insert documents — a generated cover page — so the source's
    # order has to be a subsequence of the output's rather than equal to it.
    remaining = list(after)
    out_of_order = []
    for mark in before:
        if mark in remaining:
            remaining = remaining[remaining.index(mark) + 1 :]
        else:
            out_of_order.append(mark)
    return Check(
        "kolejność czytania",
        not out_of_order,
        "" if not out_of_order else f"{len(out_of_order)} dokument(y) nie w tej kolejności "
        f"co w źródle, pierwszy zaczyna się: {out_of_order[0][:60]!r}",
        {"source": len(before), "rebuilt": len(after)},
    )


#: The properties that decide what a page looks like, and the only ones asked
#: about. A complete comparison of every declaration would report differences
#: nobody can see — a shorthand rewritten as its parts, a colour in a different
#: notation — and drown the ones anybody can.
_VISIBLE_PROPERTIES = (
    "display", "float", "text-align", "text-indent", "font-size", "font-weight",
    "font-style", "font-family", "color", "background-color", "margin-left",
    "margin-right", "margin-top", "margin-bottom", "line-height", "width",
    "page-break-before", "page-break-after", "list-style-type", "vertical-align",
)


def _without_ancestors(text: str) -> str:
    """The rules whose applicability this program's cascade model can decide.

    `epubforge.cascade` reads the *rightmost* compound of a selector and ignores
    what precedes it, which is the right approximation for the question that
    module asks and the wrong one for this one. Measured, on the public corpus:
    `.xhtml_center table { display: table }` was reported as applying to every
    table in the book, so a rule correctly removed as dead — no element in the
    book carries that class — came out as four false alarms in `strict`.

    A harness that cries wolf is worse than no harness, because it teaches
    people to skip the output. So a rule whose selector depends on an ancestor
    is outside what this check can answer and is left out of it entirely, rather
    than answered with a guess. What such a rule does to a document still shows
    up in the text and structure checks, which read the finished markup.
    """
    import cssutils

    try:
        sheet = cssutils.parseString(text, validate=False)
    except Exception:  # noqa: BLE001
        return ""
    kept: list[str] = []
    for rule in sheet:
        if rule.type != rule.STYLE_RULE:
            continue
        simple = [
            selector.strip()
            for selector in rule.selectorText.split(",")
            if selector.strip() and not re.search(r"[\s>+~]", selector.strip())
        ]
        if simple:
            kept.append(f"{','.join(simple)} {{ {rule.style.cssText} }}")
    return "\n".join(kept)


def _styles(path: str) -> dict[tuple[str, str], dict[str, str]]:
    """`{(tag, opening words): {property: value}}` for one book.

    Keyed by what the element *is* and what it *says*, because everything else
    about it moves: the file is renamed, the document may be split, and in
    `strict` an element may be unwrapped. Two elements with the same tag and the
    same opening words are the same element for this purpose, and where they are
    not, the check reports a difference that a person can look at — which is the
    right way round for a harness.
    """
    from . import cascade as css_cascade

    report = Report(source=path)
    book = read_epub(path, report)
    found: dict[tuple[str, str], dict[str, str]] = {}
    for resource in book.content_docs():
        try:
            root = xhtml.parse_document(resource.data, resource.path).root
        except Exception:  # noqa: BLE001
            continue
        sources: list[str] = []
        for link in root.iter(xhtml.qname("link")):
            href = (link.get("href") or "").split("#")[0]
            target = None
            if href:
                from . import paths as _paths

                target = _paths.resolve(resource.path, href)
            sheet = book.resources.get(target) if target else None
            if sheet is not None and sheet.is_style:
                sources.append(_without_ancestors(sheet.data.decode("utf-8", "replace")))
        for style in root.iter(xhtml.qname("style")):
            if style.text:
                sources.append(_without_ancestors(style.text))
        cascade = css_cascade.Cascade.parse(sources)
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            tag = xhtml.local_name(element).lower()
            if tag in _NOT_PROSE or tag in ("html", "body"):
                continue
            words = re.sub(r"\s+", " ", "".join(element.itertext())).strip()[:40]
            if not words:
                continue
            classes = frozenset((element.get("class") or "").split())
            applied = {}
            for prop in _VISIBLE_PROPERTIES:
                value, _targeted = cascade.lookup(prop, tag, classes, element.get("id"))
                if value:
                    applied[prop] = value.strip().lower()
            inline = element.get("style") or ""
            for declaration in inline.split(";"):
                name, _, value = declaration.partition(":")
                if name.strip().lower() in _VISIBLE_PROPERTIES and value.strip():
                    applied[name.strip().lower()] = value.strip().lower()
            found[(tag, words)] = applied
    return found


def style_survives(source: str, rebuilt: str) -> Check:
    """The declarations that reach each element are the ones that reached it.

    F-017: *the CSS is modified on an approximate model of the cascade, and
    nothing checks that the modification preserved the rendering.* The model is
    still approximate — but it is applied to **both** sides here, so a difference
    is a real change in what applies to an element rather than an artefact of
    the approximation.

    Only elements present in both books are compared. One that is missing
    entirely is a different defect and `text_survives` is the check that says so;
    reporting it here as well would be one fault counted twice.
    """
    before, after = _styles(source), _styles(rebuilt)
    changed: list[str] = []
    for key, declarations in before.items():
        other = after.get(key)
        if other is None:
            continue
        for prop, value in declarations.items():
            # `other.get(prop, value)` was the first version of this line and it
            # made the check blind to the commonest failure it exists for: a
            # declaration that is simply *gone* compared equal to itself. Two
            # of this file's own tests caught it, which is the argument for
            # testing that a harness can fail rather than that it passes.
            if other.get(prop) != value:
                changed.append(f"{key[0]} „{key[1][:24]}”: {prop} {value} → {other.get(prop)}")
    unique = list(dict.fromkeys(changed))
    return Check(
        "style",
        not unique,
        "" if not unique else f"{len(unique)} zmian(a) w tym, co dotyczy elementu: "
        + "; ".join(unique[:4]),
        {"compared": len(set(before) & set(after)), "changed": len(unique)},
    )


#: Every check this stage of the harness runs. A list rather than a hard-coded
#: sequence so the rendering comparison of stage two is an entry here.
CHECKS = (
    text_survives,
    shape_survives,
    media_survives,
    reading_order_survives,
    style_survives,
)


def compare(source: str, rebuilt: str) -> Fidelity:
    """Run every check over one pair of files."""
    return Fidelity(source, rebuilt, [check(source, rebuilt) for check in CHECKS])


__all__ = ["Check", "Fidelity", "CHECKS", "compare"]

def spine_text_of(book: "str | pathlib.Path") -> str:
    """The book's reading order, folded into the form both sides are compared in.

    Through `typography.canonical`, and that is the load-bearing decision here
    rather than a tidy-up. The typography stage is *allowed* to replace
    characters — three dots become an ellipsis, straight quotes become the
    book's own convention, every dash becomes one dash — and a subsequence test
    on raw characters calls every one of those a loss. Nine typography tests
    said so within a minute of the gate being wired up.

    `canonical` is the fold this program already uses to decide whether a
    typographic rule kept the text it was given: quotes, dashes, ellipses and
    invisible characters fold; letters, digits, meaningful punctuation and word
    boundaries do not. So a lost word, a swallowed letter and two sentences run
    together all still fail. Using it here means K1 and the typography stage
    agree about what "the same text" is, instead of the gate forbidding what the
    stage is for.

    The characters in `xmlchars.FORBIDDEN` are folded out too, on both sides,
    and that is not an exemption granted to the rebuild — it is the only honest
    reading of the invariant. K1 says no character of the book's *text* is lost.
    None of these is text: they are control codes with no glyph, no width and no
    reader that draws them, and the program removes them because a conformant
    EPUB either cannot carry them at all or is refused for carrying them. So the
    comparison is made against the text a conformant EPUB *can* hold, and the
    removal is still said out loud by `xhtml.forbidden-characters-removed`, per
    document and with a count.

    Measured on a real book from the owner's shelf: one U+008F in each of two
    chapters. Before this fold the gate refused the book — correctly by the
    letter of K1 and wrongly by its purpose, because the two characters it was
    protecting are invisible control codes and every one of the 776 555
    characters of the book's own text was present.

    **Why the fold and not another name on `REMOVES_TEXT_ON_PURPOSE`.** That
    list carries the defect that left the gate disarmed for a release: a rule
    appearing anywhere in the report excuses a loss anywhere else in the book.
    Adding a fifth name would have published this book for a reason that
    happens to be true rather than for the reason it is true. Folding both
    sides through the same filter cannot be wrong about *which* loss it
    forgives, because after it there is no loss to forgive.
    """
    from .inventory import spine_text
    from .typography import canonical
    from .xmlchars import legal

    return canonical(legal(spine_text(book)))


def first_character_lost(source_text: str, output_text: str) -> int:
    """Index of the first source character the output does not carry, or -1.

    K1 as it is actually written: *no character is lost*. **Subsequence**, not
    equality and not substring — the rebuild is supposed to generate a cover
    page and a navigation document, so the output may carry text between the
    source's characters without having lost any. Whitespace is compared loosely
    because reflowing markup is not losing text.

    This is the rule the corpus has been running over a hundred and sixty real
    books, lifted here so that the gate in front of the writer and the corpus
    mean the same thing by K1. They did not: `text_survives` above compares
    *word sets*, which is a fair post-hoc measurement and a bad gate — unwrapping
    a `<span>` legitimately joins two half-words into one, so a word disappears
    while every character is exactly where it was. Twenty-two tests said so
    within a minute of it being wired to the gate.

    Returns an index rather than a boolean so a refusal can quote the text
    around the loss. "Something is missing" is not a diagnosis.
    """
    position = 0
    for index, character in enumerate(source_text):
        position = output_text.find(character, position)
        if position < 0:
            return index
        position += 1
    return -1


def text_is_preserved(source: "str | pathlib.Path", candidate: "str | pathlib.Path") -> Check:
    """K1 between two files, with the place it broke if it broke."""
    before = spine_text_of(source)
    after = spine_text_of(candidate)
    lost = first_character_lost(before, after)
    if lost < 0:
        return Check("K1", True, "", {"source_characters": len(before)})
    window = before[max(0, lost - 40):lost + 40].strip()
    return Check(
        "K1",
        False,
        f"tekst źródła urywa się w wyniku na pozycji {lost}: …{window}…",
        {"source_characters": len(before), "lost_at": lost},
    )

