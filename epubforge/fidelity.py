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
            root = xhtml.parse_document(resource.data).root
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


#: Every check this stage of the harness runs. A list rather than a hard-coded
#: sequence so the rendering comparison of stage two is an entry here.
CHECKS = (text_survives, shape_survives, media_survives, reading_order_survives)


def compare(source: str, rebuilt: str) -> Fidelity:
    """Run every check over one pair of files."""
    return Fidelity(source, rebuilt, [check(source, rebuilt) for check in CHECKS])


__all__ = ["Check", "Fidelity", "CHECKS", "compare"]
