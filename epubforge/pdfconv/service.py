"""Converting a PDF into an EPUB: this module's own job, start to finish.

Not `rebuild_all(pdf, …)` under another name. The repair core's entry takes a
book that is already an EPUB and refuses anything else; this composes its own
run — its reader, its stage in front of the core's list, its settings, its
plan, its result — on top of the publication machinery both modules share
(D-057, 03-PDF-MODULE §4).

What stays shared, and why it must: the writer, the validator, the atomic
publish, the balance, the budget and the two gates. Copying them here would be
two sets of safeguards drifting apart; leaving them out would be a converter
that publishes without them. Composing them is the third option, and it is the
one the owner's decision asks for — *„rozdzielamy workflow i odpowiedzialność,
nie biblioteki"*.

No Qt, no window: the window's adapter (`gui/shell/pdf_backend.py`) calls this,
and so does `epubforge convert-pdf`.
"""

from __future__ import annotations

import os
import pathlib
from functools import partial

from .. import stages as core
from ..policy import Policy
from ..report import Level, Report
from .models import PdfConversionPlan, PdfConversionResult, PdfDocumentInfo
from .settings import PdfSettings

#: The core's stages a book this module *made* goes through, named one by
#: one (A15 of the 0.4.4 recovery audit). This used to be
#: `pipeline.DEFAULT_STAGES` whole, which meant that a stage added to the
#: EPUB rebuild started running over every converted book without anybody
#: deciding it should: a converted book is a new publication, and which
#: repairs make sense for it is this module's decision, taken here.
#:
#: The list is the rebuild's list today, in the rebuild's order, so that
#: naming it changes nothing about the output (a refactoring keeps the
#: characteristics of the result). Each entry says why it applies to a
#: book that was never an EPUB; an entry that turns out not to would be
#: taken out here, and the test beside this list keeps the two lists from
#: drifting back into one.
PDF_STAGES = (
    core.FontStage,           # no fonts to carry, and it says nothing when there are none
    core.ImageStage,          # the pictures the reader cut out and the regions it drew
    core.StructureStage,      # the layout the writer expects, portable names
    core.MetadataStage,       # title, language, identifier from the PDF's own info
    core.ProfileStage,        # what the body text is, for the stages after it
    core.ContentStage,        # language against the prose, encodings, entities
    core.ParagraphStage,      # runs of empty paragraphs, behind its setting
    core.StyleStage,          # the stylesheets this reader wrote
    core.TypographyStage,     # quotes, ellipses, conjunctions — behind switches
    core.HyphenStage,         # words the typesetter broke at line ends, on the ledger
    core.SubstitutionStage,   # one letter written for another, behind its switch
    core.FootnoteStage,       # a manual's notes, when the reader found any
    core.AltTextStage,        # the pictures have no alternative until somebody writes one
    core.TableStage,          # the grids the reader rebuilt as tables
    core.NavigationStage,     # the outline into a navigation document
    core.AccessibilityStage,  # the metadata every book gets
    core.CompatibilityStage,  # the older readers' NCX beside the nav
    core.FontSubsetStage,     # nothing to cut; kept in its place for the order's sake
    core.KepubStage,          # off unless asked for, like everywhere else
)

#: What a converted document is called when nobody says otherwise. The source's
#: own name, because that is what the person will look for.
EXTENSION = ".epub"


#: How many pages the preflight reads. A budget, not a threshold: the layout
#: analysis of a page is what the conversion itself pays per page, and four
#: of them cost a manual of a hundred a fraction of a second while a text
#: layer that exists shows on the first. Four rather than three because the
#: running-head detector says nothing below `reader.RUNNING_HEAD_MIN_PAGES`
#: pages (W10 pt 2: the plan names what the conversion will meet, and a
#: running head on every page is the commonest thing it meets).
PREFLIGHT_PAGES = 4


def look_at(source) -> PdfDocumentInfo:
    """What can be said about one PDF before converting it.

    It used to read the file's size and nothing else, and the screen said
    "Nie sprawdzono" — honestly, but the stepper beside it said the reading
    was done (A10 of the 0.4.4 recovery audit). What is measured now is
    what a person decides on before converting: how many pages, whether
    there is a text layer to read (on a sample of `PREFLIGHT_PAGES`),
    whether the file is encrypted, whether a renderer is installed for its
    drawings, and how many links and bookmarks it declares. Each answer is
    the file's own; nothing here is a guess about quality, and `READY`
    still means ready to run, not good.
    """
    path = pathlib.Path(source)
    info = PdfDocumentInfo(source=path, title=path.stem)
    try:
        info.size = path.stat().st_size
    except OSError as exc:
        info.refusal_code = "not-a-file"
        info.refusal = f"{type(exc).__name__}: {exc}"
        return info
    _preflight(info)
    return info


def _preflight(info: PdfDocumentInfo) -> None:
    """The measurements behind `look_at`, on the file's structure alone."""
    from pdfminer.pdfdocument import PDFDocument, PDFNoOutlines
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdftypes import resolve1
    from pdfminer.psparser import PSException

    from . import draw, reader

    try:
        with open(info.source, "rb") as handle:
            document = PDFDocument(PDFParser(handle))
            info.encrypted = bool(document.encryption) and not document.is_extractable
            pages = list(PDFPage.create_pages(document))
            info.pages = len(pages)
            for page in pages:
                for annotation in resolve1(page.annots) or ():
                    annotation = resolve1(annotation)
                    subtype = annotation.get("Subtype") if isinstance(annotation, dict) else None
                    if getattr(subtype, "name", subtype) == "Link":
                        info.links += 1
            try:
                info.outline_entries = sum(1 for _ in document.get_outlines())
            except PDFNoOutlines:
                info.outline_entries = 0
        if info.encrypted:
            info.refusal_code = "encrypted"
            info.refusal = "the document is encrypted and its text cannot be read"
            return
        # The sample, read the way the conversion reads a page: what the plan
        # says the conversion will meet is counted by the conversion's own
        # functions (W10 pt 2), not by a second, simpler reading of the page.
        sample = reader.sample_layout(str(info.source), PREFLIGHT_PAGES)
    except (OSError, ValueError, TypeError, KeyError, PSException) as exc:
        # Not a PDF, a truncated one, or one pdfminer will not parse: the
        # refusal names the error, the counts stay at what was read, and
        # `has_text` stays *not checked* rather than `False`.
        info.refusal_code = "unreadable"
        info.refusal = f"{type(exc).__name__}: {exc}"
        return
    info.sampled_pages = sample.pages
    info.characters = sample.characters
    info.columns_pages = sample.column_pages
    info.drawings = sample.drawings
    info.pictures = sample.pictures
    info.tables = sample.tables
    info.running_heads = sample.running_heads
    info.running_head_pages = sample.running_head_pages
    info.has_text = info.characters >= reader.MIN_CHARACTERS_PER_PAGE * max(1, info.sampled_pages)
    info.renderer = draw.available()
    if info.needs_ocr:
        info.refusal_code = "no-text"
        info.refusal = "the sampled pages carry no text layer; scanning them would need OCR"


def destination_for(source, folder=None) -> str:
    """Where one converted document goes: the folder chosen, or beside the PDF.

    Never on top of the source — a PDF and an EPUB cannot share a name — but
    the caller is told the whole path anyway, because a collision with an
    *existing* EPUB is a different question and `convert` answers it.
    """
    path = pathlib.Path(source)
    name = path.stem + EXTENSION
    return str(pathlib.Path(folder) / name) if folder else str(path.with_name(name))


def convert(
    plan: PdfConversionPlan,
    *,
    progress=None,
    cancellation=None,
    resolver=None,
    document_done=None,
    language: str = "pl",
) -> "list[PdfConversionResult]":
    """Convert every document of *plan*, one at a time, reporting as it goes.

    *progress* is `(done, total, name, phase)`, and only phases that actually
    happen are emitted — there is no invented percentage (03-PDF-MODULE §C).
    *cancellation* is asked between documents **and** handed to the machinery,
    so a long document stops in the middle rather than after; what was already
    written stays written and stays marked as written.
    """
    settings = plan.settings or PdfSettings()
    policy = policy_for(plan)
    results: list[PdfConversionResult] = []
    total = len(plan.sources)
    # One dict for the run: an answer given as "do this to all of them" is an
    # answer about a class, and asking it again for the next document is how a
    # batch turns into a questionnaire nobody finishes.
    standing: dict = {}
    for index, source in enumerate(plan.sources):
        if cancellation is not None and cancellation():
            break
        if progress is not None:
            progress(index, total, pathlib.Path(source).name, "read")
        results.append(_convert_one(
            source, plan, policy, settings,
            resolver=resolver, cancellation=cancellation, standing=standing,
            language=language,
        ))
        if document_done is not None:
            document_done(index, results[-1])
    return results


def policy_for(plan: "PdfConversionPlan | None" = None) -> Policy:
    """The publication settings a conversion runs under.

    A new publication, not a repaired one: it is written the way this program
    writes an EPUB it made itself, so the repair presets — *keep the look*,
    *maximum compatibility*, *container only* — have nothing to say about it
    and are not offered (03-PDF-MODULE §3B). What the person does choose about
    the *conversion* lives in `PdfSettings`; the two gates below are about
    *publishing*, they belong to the shared layer, and they are here because a
    conversion is refused by them exactly as a rebuild is — including on a
    machine with no browser to draw with, which is a refusal a person has to be
    able to answer.
    """
    policy = Policy.preset("preserve")
    if plan is not None:
        policy.validate_before_publish = plan.validate
        policy.render_gate = plan.render_gate
    return policy


def _convert_one(source, plan, policy, settings, *,
                 resolver, cancellation, standing, language) -> PdfConversionResult:
    """One document: read it, build the publication, check it, write it."""
    destination = destination_for(source, plan.destination)
    outcome = PdfConversionResult(source=pathlib.Path(source), layout=settings.layout)
    report = Report(source=str(source), output=destination)

    if _the_name_is_taken(destination, plan):
        # Before anything is opened, and never resolved by guessing: a file
        # already at the destination is somebody's, and this program does not
        # decide on their behalf that it is not.
        report.add("package", Level.ERROR, "pdf.destination-exists",
                   values={"name": os.path.basename(destination)})
        outcome.report_text = report.to_text(language)
        outcome.error = report.headline(report.findings[-1], language).partition("\n")[0]
        return outcome

    try:
        result = convert_document(
            source, destination, settings, policy, report=report,
            resolver=resolver, asker=resolver if plan.ask else None,
            cancellation=cancellation, standing=standing,
        )
    except Exception as exc:  # noqa: BLE001 — a broken conversion is a message
        # Somebody else's file, through pdfminer and lxml. A document that says
        # what went wrong beats a batch that ends on the third of thirty.
        outcome.error = f"{type(exc).__name__}: {exc}"
        return outcome

    return _read_the_result(result, outcome, language)


def convert_document(source, destination, settings=None, policy=None, *, report=None,
                     resolver=None, asker=None, cancellation=None, standing=None):
    """Convert one PDF and return the engine's own `Result`.

    The lower of this module's two levels, and the one that composes the run:
    **this module's reader**, and **this module's stage in front of the core's
    list**, on the publication machinery both modules share. `convert` is the
    batch loop over it and turns each `Result` into the module's own DTO; a
    caller that wants the report itself — the command line's report file, a
    test — asks here.

    The core is never handed the PDF: `pipeline.rebuild` refuses one, and this
    does not call it (D-057).
    """
    from .. import pipeline
    from .stage import PdfStage

    settings = settings or PdfSettings()
    return pipeline.produce(
        str(source), str(destination), policy or policy_for(None),
        report if report is not None else Report(source=str(source), output=str(destination)),
        # This module's reader, named here and nowhere in the core.
        read=partial(_read, settings),
        # This module's composition: its own stage in front of the stages it
        # chose from the core (`PDF_STAGES`), for the documents it read and
        # for no others.
        stages=(partial(PdfStage, settings),) + PDF_STAGES,
        resolver=resolver, asker=asker, cancelled=cancellation, standing=standing,
    )


def _read(settings: PdfSettings, source, report, budget, _policy):
    """The reader, in the shape `pipeline.produce` takes."""
    from .reader import read_pdf

    return read_pdf(source, report, budget, settings.layout)


def _the_name_is_taken(destination: str, plan: PdfConversionPlan) -> bool:
    """Whether writing here would land on a file that is already there."""
    if plan.collision == "overwrite":
        return False
    return os.path.exists(destination)


def _read_the_result(result, outcome: PdfConversionResult, language: str) -> PdfConversionResult:
    """Turn what the machinery produced into what the person is told.

    Three questions kept apart, because a green EPUBCheck is not proof of a
    faithful conversion and a character count is not proof of a sensible
    reading order (03-PDF-MODULE §2). The result says which of them was
    actually answered and never borrows one for another.
    """
    report = result.report
    outcome.report_text = report.to_text(language)
    outcome.verdict = report.summary(language)[1].strip()
    outcome.undecided = int(report.stats.get("questions_unanswered") or 0)
    outcome.text_checked = any(
        finding.rule and finding.rule.startswith("package.prose-check")
        for finding in report.findings
    )
    outcome.epub_validated = report.validated is not None
    outcome.warnings = tuple(
        report.headline(finding, language).partition("\n")[0]
        for finding in report.sorted_findings()
        if finding.level in (Level.ERROR, Level.WARN)
    )
    if result.output_path:
        outcome.published_outputs = (pathlib.Path(result.output_path),)
    elif not outcome.error:
        outcome.error = next(iter(outcome.warnings), "")
    return outcome
