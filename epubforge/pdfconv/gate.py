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
from ..report import Level, Report
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
        {"source_characters": sum(wanted.values()), "lost": lost},
    )


def note_prose_check(report: Report) -> None:
    """What stands in for the check that holds each output document against the
    source document it came from: there is no source document, the whole text
    layer was compared instead (K1-PDF), and this says so rather than leaving a
    zip error where a check should be."""
    report.add("package", Level.INFO, "package.prose-check-pdf")


def note_second_opinion(report: Report, check: Check, consented: list) -> str:
    """What it means that the character count refused, and whether that refuses
    the book.

    A character the page draws and the output lacks is a loss — except where a
    named pass removed or reshaped text on somebody's answer, which is what
    *consented* carries. Quotes turned to the book's convention and three dots
    made an ellipsis are that; a sentence in a Form XObject that nobody
    converted is not, and nothing in the report will say otherwise (EF-087).
    """
    if consented:
        report.add(
            "package",
            Level.WARN,
            "package.pdf-characters-changed-on-request",
            values={"rules": ", ".join(consented), "detail": check.detail},
        )
        return ""
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
