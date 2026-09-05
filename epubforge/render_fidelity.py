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
per page, so a sixty-five-document book is a minute. It samples rather than
rendering everything unless asked, for that reason.

It is **not** opt-in, and this paragraph used to say it was (EF-037).
`Policy.render_gate` defaults to `stop`: without a way to see what the pages
look like, the rebuild does not write. D-016 settled that on 2026-08-14 and the
sentence here was never brought into line — so the module explaining the check
was telling the reader the opposite of what the program does. The default is the
truth; a docstring is not a second place to decide policy.
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
    #: The output document carries this program's own cover-refit marker
    #: (`covers.REFIT_MARK`) — a fact the rebuild wrote down, read back from
    #: the artifact, so it holds for a standalone comparison too. See EF-063.
    refit_marked: bool = False

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
    #: Whether the comparison actually ran to the end. `available` says the
    #: engine was there; this says the work got done. EF-081's neighbour
    #: (EF-082): an OPF written with apostrophes — perfectly legal XML, zero
    #: EPUBCheck complaints — made `_spine_of` return nothing, `pages` stayed
    #: empty, and `all([])` is `True`, so a book nothing had looked at was
    #: reported as *checked*. A check that examined no pages is not a check,
    #: and the only honest word for it is the one used when there is no
    #: browser at all: not run.
    completed: bool = False

    @property
    def ok(self) -> bool:
        return self.available and self.completed and all(page.ok for page in self.pages)

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


def _elements(node, name: str):
    """Every descendant whose local name is *name*, whatever its namespace.

    Namespace-blind on purpose: this reads other people's books, and the
    prefixes and default namespaces in the wild are not worth an argument. The
    element names in a container document and a package document are unique
    enough that the local name identifies them.
    """
    from lxml import etree

    for element in node.iter():
        if isinstance(element.tag, str) and etree.QName(element).localname == name:
            yield element


def _parse(path: pathlib.Path):
    """The file as a tree, or `None` if it is not XML this can read."""
    from lxml import etree

    try:
        parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True)
        return etree.fromstring(path.read_bytes(), parser)
    except (etree.XMLSyntaxError, OSError, ValueError):
        return None


def _spine_of(root: pathlib.Path) -> "list[pathlib.Path]":
    """The reading order, as paths on disk, read out of the package document.

    Parsed as XML since EF-082. It used to be read with regular expressions
    demanding double-quoted attribute values, which is true of every package
    this program writes and not of the format: `full-path='EPUB/package.opf'`
    is the same document to any conforming reader, and XML 1.0 says so in as
    many words. A publisher who quotes with apostrophes got an empty reading
    order, no comparisons at all, and a report saying the appearance had been
    checked.
    """
    container = root / "META-INF" / "container.xml"
    if not container.is_file():
        return []
    tree = _parse(container)
    if tree is None:
        return []
    full_path = next(
        (
            value
            for element in _elements(tree, "rootfile")
            for value in (element.get("full-path"),)
            if value
        ),
        "",
    )
    if not full_path:
        return []
    package = root / full_path
    if not package.is_file():
        return []
    tree = _parse(package)
    if tree is None:
        return []
    manifest = {
        element.get("id"): element.get("href")
        for element in _elements(tree, "item")
        if element.get("id") and element.get("href")
    }
    base = package.parent
    import urllib.parse

    order = []
    for element in _elements(tree, "itemref"):
        href = manifest.get(element.get("idref") or "")
        if not href:
            continue
        page = (base / urllib.parse.unquote(href)).resolve()
        if page.is_file() and page.suffix.lower() in (".xhtml", ".html", ".htm"):
            order.append(page)
    return order


#: The numeric prefix this program puts on rebuilt documents, so a stem can be
#: compared with the source's.
_PREFIX = re.compile(r"^\d+-")


def _stem(path: pathlib.Path) -> str:
    return _PREFIX.sub("", path.stem).lower()


def _pair(
    before: "list[pathlib.Path]",
    after: "list[pathlib.Path]",
    after_stems: "list[str] | None" = None,
):
    """Match the two reading orders to each other, allowing for insertions.

    Pairing by position was the first version and it is wrong on any book where
    the rebuild adds or drops a spine entry. Measured on a real one: 70
    documents in, 71 out, because the rebuild generated a cover document the
    source did not have — so every page after the first was compared with its
    neighbour, and two of the three "losses" the gate reported across a
    thirty-two book shelf were that, not damage.

    A gate that compares the wrong pages and then refuses the book is worse than
    no gate at all, which is why this is an alignment and not an index.
    `difflib` over the file stems handles insertion and deletion the way a diff
    does, and needs no assumption beyond the rebuild mostly keeping names.

    Since D-035 the rebuild does *not* mostly keep names — documents are named
    by their role — so the caller passes `after_stems`: the after-side stems
    translated back to their source stems through the rebuild's own rename
    ledger. Measured without it on the 160-book shelf: ten books refused, every
    one a wrong-neighbour comparison, because a renamed spine plus one
    synthesized cover page collapses the diff into a single shifted "replace"
    block. The gate must never guess where the rebuild can simply tell it.

    Returns `(pairs, added, dropped)`.
    """
    import difflib

    before_stems = [_stem(path) for path in before]
    if after_stems is None:
        after_stems = [_stem(path) for path in after]
    matcher = difflib.SequenceMatcher(None, before_stems, after_stems, autojunk=False)
    pairs: list[tuple[pathlib.Path, pathlib.Path]] = []
    added: list[pathlib.Path] = []
    dropped: list[pathlib.Path] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            pairs.extend(zip(before[i1:i2], after[j1:j2]))
        elif tag == "replace":
            # Same position, different name. Compared anyway as far as they
            # pair up: a renamed document is still that document, and the
            # remainder on either side is an addition or a loss.
            shared = min(i2 - i1, j2 - j1)
            pairs.extend(zip(before[i1:i1 + shared], after[j1:j1 + shared]))
            dropped.extend(before[i1 + shared:i2])
            added.extend(after[j1 + shared:j2])
        elif tag == "delete":
            dropped.extend(before[i1:i2])
        elif tag == "insert":
            added.extend(after[j1:j2])
    return pairs, added, dropped


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


def _inside(target: pathlib.Path, root: pathlib.Path) -> bool:
    """Whether *target* is under *root* — as paths, not as text.

    EF-082's twin, EF-085: this used to ask whether the resolved name *starts
    with* the root as a string, and `…/extract-sibling/probe.txt` starts with
    `…/extract`. A prefix of the text is not a prefix of the path, an archive
    can name `../anything`, and the only member of this pair that a person
    would notice is the one that writes outside the directory it was given.
    """
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _extract(book: "str | pathlib.Path", into: pathlib.Path) -> pathlib.Path:
    into.mkdir(parents=True, exist_ok=True)
    root = into.resolve()
    with zipfile.ZipFile(book) as archive:
        for entry in archive.infolist():
            # A member name that climbs out of the directory is not extracted,
            # whatever it is for: `..`, an absolute path, a Windows drive.
            target = (into / entry.filename).resolve()
            if not _inside(target, root):
                continue
            if entry.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
    return into


#: How much earlier the drawn area has to start before it counts as content
#: appearing rather than moving. Two per cent of the viewport — a reflow shifts
#: a line by less, a refitted picture by far more.
_APPEARED = 0.02


#: How much of the drawn *area* has to go with the ink. Five per cent: a reflow
#: nudges the box, a lost paragraph collapses it.
_SHRANK = 0.05


def _shrank(before: "render.Ink", after: "render.Ink") -> bool:
    """Did the area the content occupies get smaller, and not only lighter?"""
    was = before.width * before.height
    now = after.width * after.height
    if was <= 0:
        return False
    return (was - now) / was > _SHRANK


def _refitted(before: "render.Ink", after: "render.Ink") -> bool:
    """Did the output *show more of something*, rather than lose part of it?

    The fourth attempt at reading direction out of pixels, and the first three
    are in `_judge`'s docstring. This one is not a statistic but an argument:

        content cannot appear above, or to the left of, anything that was drawn
        before — unless it was there all along and could not be seen.

    A page that merely lost part of itself keeps its top-left corner: the first
    line is where it was, and the bottom pulls in. A picture drawn at natural
    size on a smaller screen and then fitted does the opposite — the top-left of
    the drawn area moves *up and out*, because the parts that were off the page
    have come onto it.

    Measured on a purchased book, the title page whose image is 1200×1800 at a
    600×800 viewport: source ink `L0.28 T0.38 R1.00`, output `L0.21 T0.15
    R0.81`. Coverage fell by 46% and the reader gained the whole picture. Every
    coverage-based rule called that damage; this one does not.
    """
    return (
        before.left - after.left > _APPEARED
        or before.top - after.top > _APPEARED
    )


def _refit_marked(document: "pathlib.Path") -> bool:
    """Did this program refit this page's cover, said by the page itself?"""
    from . import covers

    try:
        return covers.REFIT_MARK.encode("utf-8") in document.read_bytes()
    except OSError:
        return False


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
    if check.refit_marked and not before.blank and not after.blank:
        # EF-063, third and final shape of this judgement — the first two are
        # a lesson worth the space they take. The gate used to read the fit's
        # ink drop as loss and refused 22 of 82 real covers the program had
        # just fitted correctly. Attempt one replaced that with edge reading
        # ("touching one side with a margin opposite is a cut") and fell to
        # artwork carrying white of its own: 17 of 40 fitted covers read as
        # cut. Attempt two *predicted* the ink box from the image file and
        # fell deeper: a dark cover dominating the page flips what the ink
        # detector calls paper, and 37 of 82 predictions disagreed with
        # measurements of correct fits. Every pixel-side judgement of this
        # page stands on that moving ground.
        #
        # So the judgement is the one the sixth audit proposed in the first
        # place: the marker is a fact this program wrote, and a fact it wrote
        # it may accept — `references.py`'s own rule for `REPAIRED`. Whether
        # the fitting CSS itself works is not re-litigated per book: the
        # render suite measures it with ink on a solid and a photographic
        # cover, and the mutations that break it (`100vh → 100%`, dropping
        # `margin: 0`) fail those tests. The seventh audit measured this
        # sentence and found it half true — the `margin: 0` mutation left
        # the whole render suite green, so the tooth this comment promised
        # did not exist (S-3). It does now: the margin test in the ink class
        # measures the 8px shift directly, and the mutation fails it — the
        # claim above was made true rather than softened, because a comment
        # is the only thing holding this boundary up. What remains for the
        # gate here is
        # the one verdict pixels can still give safely: a blank page is a
        # loss, marker or no marker — `not after.blank` in the condition is
        # what hands that page to the blank check below instead of this note.
        check.notes.append(
            "okładka dopasowana przez przebudowę — spadek tuszu jest "
            f"dopasowaniem, nie stratą ({before.coverage:.1%} → {after.coverage:.1%}); "
            "poprawności reguł dopasowania pilnuje suita renderowa, nie ta brama"
        )
        return
    if after.blank and not before.blank:
        check.problems.append("strona wyszła pusta, a w źródle coś na niej było")
        return
    if before.blank:
        if not after.blank:
            check.notes.append("na stronie coś się pojawiło, a w źródle była pusta")
        return

    # The direction, from the one quantity that carries it — corrected once more
    # by a real book. See `_refitted`.
    lost = before.coverage - after.coverage
    materially_less = (
        before.coverage > 0.001
        and lost / before.coverage > LOST_INK
        and not _refitted(before, after)
        # Content that is lost takes space with it. Measured on a purchased
        # book: a page whose text, box and layout are identical came out 10%
        # lighter because the rebuild settled a different font, and the drawn
        # area was the same to the second decimal — `L0.01 T0.04 R0.99 B0.89`
        # on both sides. Ink alone called that a loss; ink and area together
        # do not, and a page that really lost a paragraph fails both.
        and _shrank(before, after)
    )

    if _refitted(before, after) and lost > 0:
        check.notes.append(
            f"treść jest teraz w całości na stronie, a w źródle wychodziła poza nią "
            f"— stąd mniej tuszu ({before.coverage:.1%} → {after.coverage:.1%})"
        )
    elif materially_less:
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
    renames: "dict[str, str] | None" = None,
) -> RenderFidelity:
    """Render both books page by page and say what changed.

    `sample` of `0` renders the whole spine, which is what a release check wants
    and what nobody wants to wait for interactively.

    `renames` is the rebuild's own ledger of moved files — old archive path to
    new archive path — so the pairing can *know* which output page is which
    source page instead of guessing from names it renamed itself (D-035).
    """
    browser = browser or render.find_renderer()
    if browser is None:
        return RenderFidelity(available=False, reason=render.why_not())
    engine = render.version(browser)
    result = RenderFidelity(available=True, engine=engine)

    # `ignore_cleanup_errors` because of a Windows crash on the owner's own
    # machine: `OSError: [WinError 145] Katalog nie jest pusty`, raised while
    # deleting this directory, which turned into "the rebuilt book could not be
    # written". Windows will not remove a directory while anything still holds a
    # handle inside it — the browser that has just exited, an indexer, an
    # antivirus scanner — and none of that is a reason to lose somebody's book.
    #
    # It was invisible until 0.2.25 fixed browser discovery: this path had never
    # once run on Windows before, because Edge was never found.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as room:
        room_path = pathlib.Path(room)
        before_root = _extract(source, room_path / "przed")
        after_root = _extract(output, room_path / "po")
        before_spine = _spine_of(before_root)
        after_spine = _spine_of(after_root)
        if not before_spine or not after_spine:
            result.reason = "nie udało się odczytać kolejności czytania"
            return result

        after_stems = None
        undone = {new: old for old, new in (renames or {}).items()}
        if undone:
            after_stems = []
            for path in after_spine:
                try:
                    internal = path.resolve().relative_to(after_root.resolve()).as_posix()
                except ValueError:
                    internal = ""
                old = undone.get(internal)
                after_stems.append(
                    _stem(pathlib.Path(old)) if old else _stem(path)
                )
        paired, added, dropped = _pair(before_spine, after_spine, after_stems)
        for path in dropped:
            # A document in the reading order that is not in the output any more.
            # No rendering needed and none possible: this is the loss the whole
            # gate is for, in its plainest form.
            check = PageCheck(document=path.name, viewport=viewports[0])
            check.problems.append("dokument zniknął z kolejności czytania")
            result.pages.append(check)
        for path in added:
            check = PageCheck(document=path.name, viewport=viewports[0])
            check.notes.append("dokument doszedł, nie było go w źródle")
            result.pages.append(check)

        indices = _sample(len(paired), sample) if sample else list(range(len(paired)))
        shots = room_path / "obrazy"
        shots.mkdir()
        for number, index in enumerate(indices):
            source_page, output_page = paired[index]
            name = output_page.name
            if on_page is not None:
                on_page(number, len(indices), name)
            for viewport in viewports:
                check = PageCheck(document=name, viewport=viewport)
                tag = f"{index}-{viewport[0]}x{viewport[1]}"
                try:
                    one = render.shoot(
                        source_page, shots / f"a{tag}.png",
                        viewport=viewport, browser=browser,
                    )
                    two = render.shoot(
                        output_page, shots / f"b{tag}.png",
                        viewport=viewport, browser=browser,
                    )
                except render.RenderError as exc:
                    check.problems.append(f"nie udało się narysować: {exc}")
                    result.pages.append(check)
                    continue
                check.source_ink = render.ink_of(one)
                check.output_ink = render.ink_of(two)
                check.difference = render.difference(one, two)
                check.refit_marked = _refit_marked(output_page)
                _judge(check)
                result.pages.append(check)
        # Said here, at the end, and only if there was something to look at:
        # every early return above leaves `completed` False on purpose.
        result.completed = bool(result.pages)
        if not result.completed:
            result.reason = "nie było czego porównać"
    return result


def drawn(
    output: "str | pathlib.Path",
    *,
    viewports=VIEWPORTS,
    sample: int = SAMPLE,
    browser=None,
    on_page=None,
) -> RenderFidelity:
    """Draw one book with nothing to compare it against, and look for blank pages.

    For a conversion out of PDF there is no *before* in this sense: the source
    is not a set of documents that could be rendered and paired, and treating
    it as one is what EF-086 was — `compare` opened the PDF with `zipfile` and
    the whole rebuild came apart on `BadZipFile`, in the default preset, which
    is the one the window uses.

    What is left when the comparison is impossible is still worth doing, and
    it is the shape of damage this gate was built for in the first place: a
    document that carries text and draws *nothing*. That is a real defect and
    it is caught here. What this cannot say is whether the page looks like the
    PDF page it came from — so it does not say it, and the report names what
    was done rather than borrowing the word "checked" from the comparison.
    """
    browser = browser or render.find_renderer()
    if browser is None:
        return RenderFidelity(available=False, reason=render.why_not())
    result = RenderFidelity(available=True, engine=render.version(browser))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as room:
        room_path = pathlib.Path(room)
        root = _extract(output, room_path / "po")
        spine = _spine_of(root)
        if not spine:
            result.reason = "nie udało się odczytać kolejności czytania"
            return result
        indices = _sample(len(spine), sample) if sample else list(range(len(spine)))
        shots = room_path / "obrazy"
        shots.mkdir()
        for number, index in enumerate(indices):
            page = spine[index]
            if on_page is not None:
                on_page(number, len(indices), page.name)
            viewport = viewports[0]
            check = PageCheck(document=page.name, viewport=viewport)
            try:
                shot = render.shoot(
                    page, shots / f"{index}.png", viewport=viewport, browser=browser
                )
            except render.RenderError as exc:
                check.problems.append(f"nie udało się narysować: {exc}")
                result.pages.append(check)
                continue
            check.output_ink = render.ink_of(shot)
            if check.output_ink.blank and _has_text(page):
                check.problems.append(
                    "dokument niesie tekst, a strona wyszła pusta"
                )
            result.pages.append(check)
        result.completed = bool(result.pages)
        if not result.completed:
            result.reason = "nie było czego narysować"
    return result


def _has_text(page: pathlib.Path) -> bool:
    """Whether the document carries anything a reader would see as words."""
    from . import fidelity

    try:
        text = fidelity.document_text(page.read_bytes())
    except OSError:
        return False
    return bool(text and text.strip())


__all__ = [
    "DIFFERENT",
    "PageCheck",
    "LOST_INK",
    "RenderFidelity",
    "SAMPLE",
    "VIEWPORTS",
    "compare",
    "drawn",
]
