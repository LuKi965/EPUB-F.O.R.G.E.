"""Does the rebuilt book still *look* like the one that went in?

F-028. `fidelity.py` compares structure — the text, the shapes, the media, the
reading order, the declared style — and every one of those checks passes on a
book that comes out cropped, stretched, blank, or with the dedication pushed off
the bottom of the page. The audit's phrase for the gap is exact: the suite
proves the output validates and does not prove it still looks like itself.

The question is asked in the only form that can be answered honestly. "Is this
page laid out correctly" needs a designer and a brief. "Does this page look the
way it looked before this program touched it" needs two screenshots, and it is
the question the finding is actually about — every failure it lists is a
*change* introduced by the rebuild.

So: extract both books, walk the two spines in step, render each pair at a
viewport, and compare. Four things are looked for, and each is a shape of damage
the structural checks cannot see:

* **a page that came out blank** — the commonest catastrophic one, and invisible
  to every existing check because the text is still in the file;
* **content that lost its footing at the bottom edge** — a dedication composed
  against the bottom of the page, pushed off it;
* **a picture that changed shape** — a full-page illustration stretched to fit;
* **everything else**, as a fraction of pixels that differ.

None of it is free. Rendering is about four tenths of a second per page, twice
per page, so a sixty-five-document book is a minute. It is an opt-in check for
that reason, like the validator, and it samples rather than rendering everything
unless asked.
"""

from __future__ import annotations

import pathlib
import re
import tempfile
import zipfile
from dataclasses import dataclass, field

from . import render

#: Viewports a book is checked at. One narrow, one ordinary: the failures this
#: is for — a cover that crops, a dedication that falls off — appear at one size
#: and not the other, which is the whole reason a matrix is needed rather than a
#: single screenshot.
VIEWPORTS = ((600, 800), (390, 640))

#: How many spine documents to render when nobody says otherwise. The first
#: three always, because the cover and the title pages are where the fixture
#: profile for this finding says the risk is; the rest spread across the book.
SAMPLE = 12

#: A page is "materially different" past this fraction of changed pixels.
#: Anti-aliasing and a one-pixel reflow sit well under it; a lost paragraph,
#: a moved image or a changed font sit well over.
DIFFERENT = 0.02

#: How much of the drawn content a page may lose before it counts as loss.
#: A tenth: reflow and a different font move coverage by a per cent or two, and
#: a lost paragraph, a dropped illustration or a clipped page move it by far
#: more than this.
LOST_INK = 0.10


@dataclass
class PageCheck:
    """One document, at one viewport, before and after.

    Two lists, and the split is the whole judgement. `problems` are shapes of
    *loss* — the page shows less than it did. `notes` are everything else that
    moved, including the changes that are repairs.

    That distinction was not in the first version and the first real book took
    it apart. The cover of a purchased book is a 1472×2341 JPEG with no sizing
    style at all; at a 600×800 viewport the source renders it at natural size
    and the reader sees the top-left corner of it. The rebuild adds
    `max-width/max-height: 100%` and the whole cover fits. Twenty per cent of
    the pixels differ, the drawn area changes shape — and every one of those
    signals fired, on a page this program had just repaired. A gate that calls
    that a defect is a gate that gets switched off.
    """

    document: str
    viewport: "tuple[int, int]"
    difference: float = 0.0
    source_ink: "render.Ink | None" = None
    output_ink: "render.Ink | None" = None
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def __str__(self) -> str:
        size = f"{self.viewport[0]}×{self.viewport[1]}"
        if self.problems:
            return f"{self.document} @{size}: " + "; ".join(self.problems)
        if self.notes:
            return f"{self.document} @{size}: " + "; ".join(self.notes)
        return f"{self.document} @{size}: bez zmian ({self.difference:.1%})"


@dataclass
class RenderFidelity:
    """What the rendering said about a whole book."""

    available: bool = False
    engine: str = ""
    reason: str = ""
    pages: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.available and all(page.ok for page in self.pages)

    @property
    def problems(self) -> list:
        return [page for page in self.pages if not page.ok]

    def summary(self) -> str:
        if not self.available:
            return self.reason or "nie sprawdzono"
        if not self.pages:
            return "nie było czego porównać"
        bad = len(self.problems)
        return (
            f"{len(self.pages)} porównań w {self.engine}: "
            + ("wszystkie bez zmian" if not bad else f"{bad} ze zmianą wyglądu")
        )


def _spine_of(root: pathlib.Path) -> "list[pathlib.Path]":
    """The reading order, as paths on disk, read out of the package document."""
    container = root / "META-INF" / "container.xml"
    if not container.is_file():
        return []
    found = re.search(r'full-path="([^"]+)"', container.read_text("utf-8", "replace"))
    if not found:
        return []
    package = root / found.group(1)
    if not package.is_file():
        return []
    text = package.read_text("utf-8", "replace")
    manifest = dict(
        re.findall(r'<item\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', text)
    ) | dict(
        (identifier, href)
        for href, identifier in re.findall(
            r'<item\b[^>]*\bhref="([^"]+)"[^>]*\bid="([^"]+)"', text
        )
    )
    base = package.parent
    import urllib.parse

    order = []
    for idref in re.findall(r"<itemref\b[^>]*\bidref=\"([^\"]+)\"", text):
        href = manifest.get(idref)
        if not href:
            continue
        page = (base / urllib.parse.unquote(href)).resolve()
        if page.is_file() and page.suffix.lower() in (".xhtml", ".html", ".htm"):
            order.append(page)
    return order


def _sample(count: int, wanted: int) -> "list[int]":
    """Which documents to render: the first three, then spread out.

    The first three are not a heuristic — the fixture profile this finding was
    written against names the cover and two title pages, and those are the pages
    whose full-bleed images crop and stretch.
    """
    if count <= wanted:
        return list(range(count))
    chosen = list(range(min(3, count)))
    remaining = wanted - len(chosen)
    if remaining > 0:
        step = max(1, (count - len(chosen)) // remaining)
        chosen += list(range(len(chosen), count, step))[:remaining]
    return sorted(set(chosen))


def _extract(book: "str | pathlib.Path", into: pathlib.Path) -> pathlib.Path:
    into.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(book) as archive:
        for entry in archive.infolist():
            # The same refusal as the EPUBCheck staging: a member name that
            # climbs out of the directory is not extracted, whatever it is for.
            target = (into / entry.filename).resolve()
            if not str(target).startswith(str(into.resolve())):
                continue
            if entry.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
    return into


def _judge(check: PageCheck) -> None:
    """Name what changed, and hold only *loss* against the book.

    Three attempts, and the two that failed are worth recording because they
    were both the same mistake — trying to read the direction of a change out of
    pixels that cannot carry it.

    The first version reported any material difference as a defect. The first
    real book had a 1472×2341 cover with no sizing style: at a 600×800 viewport
    the source draws it at natural size and the reader sees a corner of it,
    while the rebuild fits it to the page. A fifth of the pixels differ and the
    book is *better*, and the gate called it damage.

    The second version tried to tell "was overflowing, now fits" from where the
    ink sat. That works on a cover and fails on a title page, because a title
    page is mostly white: the image is twice the viewport in both directions and
    the letters still stop two thirds of the way down. Ink measures where the
    letters are, not where the picture is, and no threshold fixes that.

    So the direction is taken from the one quantity that does carry it. A page
    that lost something shows *less*: it goes blank, or its coverage drops. A
    page that gained — a fitted cover, a centred illustration — shows more.
    Everything else is recorded with its number and held against nobody, which
    is also the project's own rule about appearance: this program is allowed to
    change how a page looks, and is not allowed to lose part of it.
    """
    before, after = check.source_ink, check.output_ink
    if before is None or after is None:
        return
    if after.blank and not before.blank:
        check.problems.append("strona wyszła pusta, a w źródle coś na niej było")
        return
    if before.blank:
        if not after.blank:
            check.notes.append("na stronie coś się pojawiło, a w źródle była pusta")
        return

    # The direction, from the one quantity that carries it.
    lost = before.coverage - after.coverage
    materially_less = before.coverage > 0.001 and lost / before.coverage > LOST_INK

    if materially_less:
        check.problems.append(
            f"na stronie jest mniej treści niż w źródle: {before.coverage:.1%} → "
            f"{after.coverage:.1%} powierzchni"
        )
        # A second signal lived here and was removed after being measured: "the
        # content now runs into the bottom edge, and did not before". It reads
        # well and does not work. A block of text pushed past the bottom of the
        # page leaves its last *visible glyph row* wherever that row happens to
        # fall — measured, a dedication shoved off the page by 20, 40, 60 and 80
        # per cent gave a bottom edge of 0.891, 0.889, 0.884 and 0.879, never
        # the 0.995 the check wanted. It would have fired on an image and by
        # luck on text, which is worse than not firing: the loss above catches
        # every one of those four cases, at 34%, 50%, 67% and 83%.
    elif check.difference > DIFFERENT:
        check.notes.append(
            f"{check.difference:.1%} pikseli się różni, ale treści jest tyle samo "
            f"albo więcej ({before.coverage:.1%} → {after.coverage:.1%})"
        )


def compare(
    source: "str | pathlib.Path",
    output: "str | pathlib.Path",
    *,
    viewports=VIEWPORTS,
    sample: int = SAMPLE,
    browser=None,
    on_page=None,
) -> RenderFidelity:
    """Render both books page by page and say what changed.

    `sample` of `0` renders the whole spine, which is what a release check wants
    and what nobody wants to wait for interactively.
    """
    browser = browser or render.find_renderer()
    if browser is None:
        return RenderFidelity(available=False, reason=render.why_not())
    engine = render.version(browser)
    result = RenderFidelity(available=True, engine=engine)

    with tempfile.TemporaryDirectory() as room:
        room_path = pathlib.Path(room)
        before_root = _extract(source, room_path / "przed")
        after_root = _extract(output, room_path / "po")
        before_spine = _spine_of(before_root)
        after_spine = _spine_of(after_root)
        if not before_spine or not after_spine:
            result.reason = "nie udało się odczytać kolejności czytania"
            return result

        pairs = min(len(before_spine), len(after_spine))
        indices = _sample(pairs, sample) if sample else list(range(pairs))
        shots = room_path / "obrazy"
        shots.mkdir()
        for number, index in enumerate(indices):
            name = after_spine[index].name
            if on_page is not None:
                on_page(number, len(indices), name)
            for viewport in viewports:
                check = PageCheck(document=name, viewport=viewport)
                tag = f"{index}-{viewport[0]}x{viewport[1]}"
                try:
                    one = render.shoot(
                        before_spine[index], shots / f"a{tag}.png",
                        viewport=viewport, browser=browser,
                    )
                    two = render.shoot(
                        after_spine[index], shots / f"b{tag}.png",
                        viewport=viewport, browser=browser,
                    )
                except render.RenderError as exc:
                    check.problems.append(f"nie udało się narysować: {exc}")
                    result.pages.append(check)
                    continue
                check.source_ink = render.ink_of(one)
                check.output_ink = render.ink_of(two)
                check.difference = render.difference(one, two)
                _judge(check)
                result.pages.append(check)
    return result


__all__ = [
    "DIFFERENT",
    "PageCheck",
    "LOST_INK",
    "RenderFidelity",
    "SAMPLE",
    "VIEWPORTS",
    "compare",
]
