"""The two gates that work differently for a book that came out of a PDF.

Both used to live in the core — the appearance check in `pipeline.py` and the
character count in `fidelity.py` — behind `if pdf.is_pdf(source)`. They are the
converter's business: a PDF has no *before* to draw page for page and no
sibling document to pair the output's prose against, and only this module knows
what to do instead (D-056).
"""

from __future__ import annotations

from collections import Counter

from ..fidelity import Check, spine_text_of
from ..stages import base as base_stage
from ..report import FAILED, PASSED, Level, Report
from ..typography import canonical
from ..xmlchars import legal


def characters_survive(source, candidate) -> Check:
    """K1 for a PDF source, counted by a second walk of the page tree.

    `fidelity.text_is_preserved` reads the PDF through the same reader the
    conversion uses, so a construct that reader does not handle is missing from
    *both* sides and the subsequence holds vacuously (EF-087: a page's one
    visible sentence, drawn inside a Form XObject, converted to nothing and
    passed). This is the other side of the ledger: every character the page
    draws, counted without any notion of lines or order, has to be in the
    output at least as many times. Order is the subsequence check's business;
    existence is this one's, and it does not depend on the reader being right —
    the parse is pdfminer's either way, the walk over it is not the reader's
    (`reader.drawn_text`).
    """
    from . import reader

    # Both sides through the fold `spine_text_of` applies — the same one, for
    # the same reason it gives: after it there is no quote style or dash
    # length left to be wrong about, only characters that exist or do not.
    wanted: Counter = Counter(
        character
        for character in canonical(legal(reader.drawn_text(str(source))))
        if not character.isspace()
    )
    present: Counter = Counter(
        character for character in spine_text_of(candidate) if not character.isspace()
    )
    missing = wanted - present
    if not missing:
        return Check("K1-PDF", True, "", {"source_characters": sum(wanted.values())})
    lost = sum(missing.values())
    sample = "".join(sorted(missing)[:12])
    return Check(
        "K1-PDF",
        False,
        f"{lost} znak(ów) narysowanych w PDF-ie nie ma w wyniku (np. {sample!r})",
        {
            "source_characters": sum(wanted.values()),
            "lost": lost,
            # What is missing, not merely how much. A consented removal is
            # paid against *these* characters (Q08); a total cannot be, and a
            # gate that excuses a total excuses everything that adds up to it.
            "missing": dict(missing),
        },
    )


def note_prose_check(report: Report) -> None:
    """What stands in for the check that holds each output document against the
    source document it came from: there is no source document, the whole text
    layer was compared instead (K1-PDF), and this says so rather than leaving a
    zip error where a check should be."""
    report.add("package", Level.INFO, "package.prose-check-pdf")


def instead_of_rebuilding(report: Report) -> None:
    """Why the EPUB rebuild will not take a PDF, and what will.

    The refusal is the core's — whether a file is one it repairs is its
    question — and the sentence is this module's, because the alternative it
    names is this module's (D-057). Nothing is written either way.
    """
    report.add("reader", Level.ERROR, "pdf.not-for-the-rebuild")


#: The ledger this gate spends, written by `stages.base.Stage.text_changed`
#: for every pass that changes a document's text. Imported rather than
#: redeclared: one name for one thing, and the writer is where it is earned.
REMOVAL_LEDGER = base_stage.REMOVAL_LEDGER


def _counted(bag: str) -> Counter:
    """The characters a ledger entry says left, counted and nothing more.

    The entry's `text` was folded once, when `stages.base` wrote it — the
    same fold the check measures in — and then written out as a **sorted
    bag** of characters: every full stop beside every other full stop. Folding
    that bag a second time, as prose, is what this used to do, and `canonical`
    makes an ellipsis of three full stops in a row: 138 full stops from the
    `.xhtml` footers Chromium prints on every page came back as 46 ellipses,
    which paid for nothing the check had counted, because on the page each
    stop stands a footer apart (EF-102, refused on v0.4.4 and every commit
    after). A bag is counted; it is not read.
    """
    return Counter(character for character in bag if not character.isspace())


def account_for(report: Report, check: Check, consented: list) -> "tuple[Counter, str]":
    """What is still missing after every consented removal is paid for, and why.

    The ledger is spent against the loss, character for character. A removal
    entered for a document pays for the characters it says it took out of that
    document and no others; five copies of one word removed pay for five, not
    for a sixth that went missing somewhere nobody consented to.

    Returns the unpaid remainder and, when the accounting could not be done at
    all, the reason. **Absent accounting is not consent**: a rule that says it
    removed text and does not say what leaves the loss unexplained, and an
    unexplained loss is what this gate is for.
    """
    missing: Counter = Counter(check.values.get("missing") or {})
    entries = [
        entry for entry in (report.stats.get(REMOVAL_LEDGER) or [])
        if entry.get("rule") in set(consented)
    ]
    unaccounted = sorted(set(consented) - {entry.get("rule") for entry in entries})
    if unaccounted:
        return missing, (
            "zgoda na " + ", ".join(unaccounted)
            + " nie mowi, co dokladnie usunieto, wiec nie ma czym rozliczyc ubytku"
        )
    paid: Counter = Counter()
    for entry in entries:
        paid += _counted(str(entry.get("text") or ""))
    return missing - paid, ""


def note_second_opinion(report: Report, check: Check, consented: list) -> str:
    """What it means that the character count refused, and whether that refuses
    the book.

    A character the page draws and the output lacks is a loss — except where a
    named pass removed or reshaped text on somebody's answer, which is what
    *consented* carries. Quotes turned to the book's convention and three dots
    made an ellipsis are that; a sentence in a Form XObject that nobody
    converted is not, and nothing in the report will say otherwise (EF-087).

    **A rule's name is not the licence; its ledger is** (Q08 of the quality
    roadmap, 2026-09-09). This used to return "no refusal" the moment
    *consented* was non-empty, so an answer about running heads — a pass that
    runs on nearly every manual — excused any other loss in the document,
    however far from a running head it was. The package's own probe showed it
    on this checkout: consent to `pdf.running-heads-removed` passed a
    synthetic loss of 500 characters from body prose.

    It is the same defect the core already learned once, one module over: the
    note beside `REMOVES_TEXT_ON_PURPOSE` in `pipeline` records a book that
    came out two characters short and was excused by a watermark
    consolidation which had removed nothing.
    """
    if consented:
        left, why = account_for(report, check, consented)
        if not left and not why:
            report.add(
                "package",
                Level.WARN,
                "package.pdf-characters-changed-on-request",
                values={"rules": ", ".join(consented), "detail": check.detail},
            )
            return ""
        if why:
            detail = f"{check.detail}; {why}"
        else:
            lost = sum(left.values())
            sample = "".join(sorted(left)[:12])
            detail = (
                f"{check.detail}; zgoda na {', '.join(consented)} nie tlumaczy "
                f"{lost} znak(ow) (np. {sample!r})"
            )
        report.add(
            "package",
            Level.ERROR,
            "package.pdf-characters-lost-beyond-consent",
            values={"rules": ", ".join(consented), "detail": detail},
        )
        return f"K1-PDF: {detail}"
    report.add(
        "package",
        Level.ERROR,
        "package.pdf-characters-lost",
        values={"detail": check.detail},
    )
    return f"K1-PDF: {check.detail}"


#: The share of a source page's ink that may be missing from the book's page
#: before the page is refused (A06 of the 0.4.4 recovery audit, Q07 of the
#: quality roadmap). **Measured, not chosen** (D-012), on this machine —
#: Chromium 1194 drawing the fixed page, PDFium drawing the source, both at
#: 612 × 792 px, ink counted per block on a 24 × 32 grid, `missing` = the
#: source's ink that the book's block does not have, as a share of the
#: source's ink:
#:
#:     the same page, Helvetica prose            missing 0.047   worst block 0.067
#:     the same page, a drawing carried          missing 0.023   worst block 0.067
#:     the narrow face, fitted (A03)             missing 0.028   worst block 0.063
#:     the narrow face, unfitted — A03's clip    missing 0.092   worst block 0.110
#:     one line of prose deleted from the book   missing 0.237   worst block 0.195
#:     three lines deleted                       missing 0.490   worst block 0.377
#:     the drawing removed from the book         missing 0.526   worst block 1.000
#:
#: Seven hundredths stands between the faithful pages (at most 0.047) and the
#: smallest loss measured (0.092): half again the one, three quarters of the
#: other. What it does not measure is a Windows machine drawing in Segoe UI,
#: which is why the report names the engine beside the number.
LOST_SHARE = 0.07
#: The grid the ink is counted on: 24 across, 32 down — 25 × 25 px blocks on
#: a letter page, about two lines of 12 pt type each.
INK_GRID = (24, 32)
#: A pixel darker than this is ink. Antialiased text is grey at its edges;
#: the source and the book are both counted the same way, so the edge
#: pixels cancel.
INK_BELOW = 200


def ink_blocks(image) -> "list[float]":
    """The share of ink in each block of *image*, row by row."""
    grey = image.convert("L")
    across, down = INK_GRID
    width, height = grey.size
    cell_w, cell_h = max(1, width // across), max(1, height // down)
    pixels = grey.load()
    shares = []
    for row in range(down):
        for col in range(across):
            dark = 0
            for y in range(row * cell_h, min(height, (row + 1) * cell_h)):
                for x in range(col * cell_w, min(width, (col + 1) * cell_w)):
                    if pixels[x, y] < INK_BELOW:
                        dark += 1
            shares.append(dark / (cell_w * cell_h))
    return shares


def missing_share(source_blocks, output_blocks) -> float:
    """The source's ink the output does not have, block by block, as a share
    of the source's ink. Ink the output *adds* does not count against it —
    a font a little heavier is not a loss — and a page with no ink at all
    has nothing to lose."""
    total = sum(source_blocks)
    if total <= 0:
        return 0.0
    return sum(max(0.0, a - b) for a, b in zip(source_blocks, output_blocks)) / total


def _fixed_layout(candidate: str) -> bool:
    """Whether the book declares itself pre-paginated — the one shape whose
    pages can be paired with the source's."""
    import zipfile

    try:
        with zipfile.ZipFile(candidate) as archive:
            for name in archive.namelist():
                if name.endswith(".opf"):
                    return b"pre-paginated" in archive.read(name)
    except (OSError, zipfile.BadZipFile):
        return False
    return False


def compare_fixed(source: str, candidate: str, *, sample: int, browser=None):
    """Every sampled page of the fixed book against the same page of the PDF.

    The source is drawn by PDFium (`draw.Sheet.page`), the book's page by
    the browser the appearance gate uses, both at the page's size in points
    as pixels, and the two are compared by `missing_share` against
    `LOST_SHARE`. Returns a `RenderFidelity` in the core's own shape, so the
    report and the gate read it as they read a rebuild's.
    """
    import pathlib
    import tempfile

    from .. import render, render_fidelity
    from . import draw

    browser = browser or render.find_renderer()
    if browser is None:
        return render_fidelity.RenderFidelity(available=False, reason=render.why_not())
    if not draw.available():
        return render_fidelity.RenderFidelity(
            available=False, reason="brak renderera PDF (pypdfium2), nie ma czym narysować źródła",
        )
    result = render_fidelity.RenderFidelity(available=True, engine=render.version(browser))
    sheet = draw.Sheet(source)
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as room:
            room_path = pathlib.Path(room)
            root = render_fidelity._extract(candidate, room_path / "po")
            spine = render_fidelity._spine_of(root)
            if not spine:
                result.reason = "nie udało się odczytać kolejności czytania"
                return result
            indices = render_fidelity._sample(len(spine), sample) if sample else list(range(len(spine)))
            shots = room_path / "obrazy"
            shots.mkdir()
            for index in indices:
                result.pages.append(_compare_page(sheet, spine[index], index, shots, browser))
            result.completed = bool(result.pages)
            if not result.completed:
                result.reason = "nie było czego narysować"
    finally:
        sheet.close()
    return result


def _compare_page(sheet, page_path, index: int, shots, browser):
    """One page of the fixed book against its source page: the check, with
    the problem named when the book's page lost more ink than allowed."""
    import io

    from PIL import Image

    from .. import render, render_fidelity

    number = _page_number_of(page_path.name, index)
    check = render_fidelity.PageCheck(document=page_path.name, viewport=(0, 0))
    size = sheet.page_size(number)
    if size is None:
        check.notes.append("źródło nie ma tej strony; nie porównano")
        return check
    viewport = (max(1, round(size[0])), max(1, round(size[1])))
    check.viewport = viewport
    original = sheet.page(number, scale=1.0)
    if original is None:
        check.notes.append("PDFium nie narysował strony źródła; nie porównano")
        return check
    try:
        shot = render.shoot(page_path, shots / f"{index}.png", viewport=viewport, browser=browser)
    except (render.RenderError, OSError) as exc:
        # `OSError`: a browser that is named and not there. The page is
        # then a problem of the gate's, said as one, not a crash of the run.
        check.problems.append(f"nie udało się narysować: {exc}")
        return check
    before = ink_blocks(Image.open(io.BytesIO(original)).resize(viewport))
    after = ink_blocks(Image.open(shot).resize(viewport))
    check.output_ink = render.ink_of(shot)
    check.difference = missing_share(before, after)
    if check.difference > LOST_SHARE:
        check.problems.append(
            f"strona {number}: {check.difference:.0%} tuszu strony źródła nie ma "
            f"w książce (próg {LOST_SHARE:.0%})"
        )
    return check


def _page_number_of(name: str, index: int) -> int:
    """The source page a fixed document stands for: `page-0012.xhtml` is page
    12; a document named otherwise is taken in spine order."""
    import re

    match = re.search(r"page-(\d+)", name)
    return int(match.group(1)) if match else index + 1


def render_gate(candidate: str, policy, report: Report, queue, cannot_verify,
                source: "str | None" = None) -> str:
    """The appearance check for a book that came out of a PDF.

    Two shapes, and the report says which ran (A06 of the 0.4.4 recovery
    audit, Q07 of the quality roadmap). A **fixed** book has a page for every
    page of the source, so it is compared page for page: the source drawn by
    PDFium, the book by the browser, and a page that lost more than
    `LOST_SHARE` of the source's ink is refused. A **reflowable** book has no
    page to pair with — its illustrations are accounted for by the drawing
    ledger (A05) and its text by K1 — so what is measured is what can be:
    a document that carries text and draws blank, which is the damage this
    gate was built for (EF-086 is why it exists at all).

    *cannot_verify* is the core's own answer to "the check could not run",
    handed in rather than reached for: whether a book may be published
    unverified is a decision about the book, not about the converter.
    """
    from .. import render_fidelity

    if source is not None and _fixed_layout(candidate):
        return _judge_fixed(source, candidate, policy, report, queue, cannot_verify)
    measured = render_fidelity.drawn(candidate, sample=policy.render_sample)
    if not measured.available:
        return cannot_verify(policy, report, queue)
    if not measured.completed:
        return cannot_verify(policy, report, queue, why=measured.reason)
    report.check("render", PASSED if measured.ok else FAILED)
    for page in measured.problems:
        report.add(
            "render", Level.ERROR, "render.page-blank",
            values={"detail": str(page)}, location=page.document,
        )
    if measured.ok:
        report.add(
            "render", Level.INFO, "render.pdf-drawn",
            values={"count": len(measured.pages), "engine": measured.engine},
        )
        return ""
    if policy.render_gate == "report":
        return ""
    return f"{len(measured.problems)} page(s) came out blank"


def _judge_fixed(source, candidate, policy, report, queue, cannot_verify) -> str:
    measured = compare_fixed(source, candidate, sample=policy.render_sample)
    if not measured.available:
        return cannot_verify(policy, report, queue)
    if not measured.completed:
        return cannot_verify(policy, report, queue, why=measured.reason)
    report.check("render", PASSED if measured.ok else FAILED)
    for page in measured.pages:
        if page.problems:
            report.add(
                "render", Level.ERROR, "render.pdf-page-differs",
                values={"detail": "; ".join(page.problems)}, location=page.document,
            )
    compared = [page for page in measured.pages if page.viewport != (0, 0)]
    report.add(
        "render", Level.INFO if measured.ok else Level.WARN, "render.pdf-compared",
        values={"count": len(compared), "engine": measured.engine,
                "worst": f"{max((p.difference for p in compared), default=0.0):.0%}",
                "limit": f"{LOST_SHARE:.0%}"},
    )
    if measured.ok or policy.render_gate == "report":
        return ""
    return f"{len(measured.problems)} page(s) lost more than {LOST_SHARE:.0%} of the source's ink"
