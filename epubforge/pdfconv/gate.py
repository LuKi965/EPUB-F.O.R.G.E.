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


def _folded(text: str) -> Counter:
    """The characters of *text* as the check counts them: same fold, no space.

    It has to be the same fold on both sides or the accounting subtracts
    characters the check never counted — a quote of one shape against a quote
    of another, and a removal that explains nothing looks like one that does.
    """
    return Counter(
        character for character in canonical(legal(text)) if not character.isspace()
    )


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
        paid += _folded(str(entry.get("text") or ""))
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


def render_gate(candidate: str, policy, report: Report, queue, cannot_verify) -> str:
    """The appearance check for a book that came out of a PDF.

    There is no *before* to compare against: the source is a PDF, and until
    EF-086 this gate handed it to `zipfile` and the whole rebuild ended on
    `BadZipFile` — in `preserve`, the preset the window uses, on every PDF the
    owner would ever drop on it. Both PDF acceptance runs missed it because
    both turned the render gate off; a gate nobody runs is a gate nobody
    tests.

    Turning it off for PDFs by default would have been the smaller change and
    the wrong one. What can honestly be measured is measured — a document that
    carries text and draws blank is the damage this gate exists for, and it
    does not need a source page to be a defect — and the report says that is
    what was done, rather than borrowing "checked" from a comparison that did
    not happen.

    *cannot_verify* is the core's own answer to "the check could not run",
    handed in rather than reached for: whether a book may be published
    unverified is a decision about the book, not about the converter.
    """
    from .. import render_fidelity

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
