"""The seam for the converter, beside the one for the rebuild.

`backend.py` is the rebuild's; this is the conversion's, and they are two
because the jobs are two (D-057). What they share is the shape: plain data
across the line, no `Report` and no `Policy` above it, nothing that cannot be
handed to another thread.

Deliberately not a method on `EngineBackend`. A converter reached through the
rebuild's adapter is a converter reached through the rebuild, whatever the
method is called, and the window would go on having one job with a branch in
it.
"""

from __future__ import annotations

import pathlib

from ...pdfconv import service
from ...pdfconv.models import PdfConversionPlan
from ...pdfconv.settings import PdfSettings
from .models import (BookItem, BookStatus, ChangeCategory, Operation, Progress,
                     Severity)

#: What the converter reads. One tuple, so the routing and the drop zone
#: cannot disagree about it.
SUFFIXES = (".pdf",)


class PdfBackend:
    """What the conversion page needs from the program underneath it."""

    def __init__(self, language: str = "pl") -> None:
        self.language = language
        #: source path → the report of its last conversion, for exporting.
        self._reports: dict = {}

    # -- looking at the documents ------------------------------------------
    def analyse(self, paths, *, progress=None, cancelled=None) -> "list[BookItem]":
        """Say what each file is. Nothing is written.

        Each file is opened and measured (`service.look_at`, A10): pages,
        a text layer on a sample of pages, encryption, the renderer, links
        and bookmarks. The row says those numbers, and "Nie sprawdzono"
        only for what was not measured; a preflight that invents a number
        is worse than one that says it did not look (03-PDF-MODULE §3B).
        """
        from ..strings import tr

        documents: list[BookItem] = []
        total = len(paths)
        for index, path in enumerate(paths, start=1):
            if cancelled is not None and cancelled():
                break
            source = pathlib.Path(path)
            if progress is not None:
                progress(Progress(index, total, source.name, "analysis"))
            info = service.look_at(source)
            item = BookItem(
                source=source, title=info.title or source.stem, kind="PDF",
                size=info.size, status=BookStatus.READY,
                summary=self._measured(info), candidates=self._candidates(info),
            )
            if info.refusal:
                item.status = BookStatus.FAILED
                item.error = (
                    tr(f"pdf.analysis.{info.refusal_code}", detail=info.refusal)
                    if info.refusal_code else info.refusal
                )
            documents.append(item)
        return documents

    @staticmethod
    def _measured(info) -> str:
        """The row's line for a document the preflight looked at (A10): the
        numbers it measured, and "not checked" for the one it did not."""
        from ..strings import tr

        if not info.checked:
            return tr("pdf.analysis.unchecked")
        measured = tr(
            "pdf.analysis.checked",
            pages=info.pages,
            text=tr("pdf.analysis.text.yes", sampled=info.sampled_pages) if info.has_text
            else tr("pdf.analysis.text.no"),
            links=info.links,
            renderer=tr("pdf.analysis.renderer.yes") if info.renderer else tr("pdf.analysis.renderer.no"),
        )
        if not info.has_text:
            return measured
        # And what the sample looks like, in the same breath (W10 pt 2).
        return measured + "; " + tr(
            "pdf.analysis.layout", columns=info.columns_pages, drawings=info.drawings,
            tables=info.tables, heads=info.running_head_pages, sampled=info.sampled_pages,
        )

    @staticmethod
    def _candidates(info) -> tuple:
        """What the plan can say the conversion will meet, from the sample.

        Each sentence names a decision or a limit the run will reach — the
        running-heads question, drawings the renderer will or will not carry,
        columns read by area, tables — so a person sets the options after
        seeing what they are for and not only after the run (A10 / W10 pt 2).
        Nothing here is a verdict about the whole file: every number is the
        sample's, and the sentence says so.
        """
        from ..strings import tr

        if not info.checked or not info.has_text:
            return ()
        said: list[str] = []
        sampled = info.sampled_pages
        if info.running_head_pages:
            said.append(tr("pdf.candidate.heads", pages=info.running_head_pages, sampled=sampled))
        if info.drawings:
            key = "pdf.candidate.drawings" if info.renderer else "pdf.candidate.drawings.no-renderer"
            said.append(tr(key, count=info.drawings))
        if info.columns_pages:
            said.append(tr("pdf.candidate.columns", pages=info.columns_pages, sampled=sampled))
        if info.tables:
            said.append(tr("pdf.candidate.tables", count=info.tables))
        return tuple(said)

    def destination_for(self, source: pathlib.Path, folder: "pathlib.Path | None") -> str:
        return service.destination_for(source, folder)

    # -- converting ---------------------------------------------------------
    def convert(self, plan: PdfConversionPlan, documents, *, progress=None,
                cancelled=None, document_done=None, resolver=None) -> "list[BookItem]":
        """Convert the chosen documents and return the rows a person reads.

        The rows are `BookItem`s — the same type the rebuild's results are, on
        purpose: what a *result* means is one contract in this window
        (02-UI-DESIGN §3), and a second one for conversions would be the same
        four axes coded twice. What differs is the plan, the service and the
        screen, which is where the two jobs actually differ.
        """
        chosen = [item for item in documents if item.chosen]
        by_source = {str(item.source): item for item in chosen}

        def one_done(index: int, outcome) -> None:
            item = by_source.get(str(outcome.source))
            if item is not None:
                self._absorb(item, outcome)
            if document_done is not None and item is not None:
                document_done(index, item)

        def tick(done: int, total: int, name: str, phase: str) -> None:
            if progress is not None:
                progress(Progress(done, total, name, phase))

        results = service.convert(
            PdfConversionPlan(
                sources=tuple(item.source for item in chosen),
                destination=plan.destination, settings=plan.settings,
                collision=plan.collision, session_id=plan.session_id, ask=plan.ask,
                validate=plan.validate, render_gate=plan.render_gate,
            ),
            progress=tick, cancellation=cancelled, resolver=resolver,
            document_done=one_done, language=self.language,
        )
        for item in chosen[len(results):]:
            item.status = BookStatus.CANCELLED
        return chosen

    def _absorb(self, item: BookItem, outcome) -> None:
        """One `PdfConversionResult` into the row it becomes."""
        self._reports[str(item.source)] = outcome.report_text
        item.report_text = outcome.report_text
        item.published_outputs = outcome.published_outputs
        item.output = outcome.published_outputs[0] if outcome.published_outputs else None
        item.issues = len(outcome.warnings)
        item.error = outcome.error
        # Every remark, not only the first. The row has space for one line and
        # elides it; the acceptance list asks for the layout and image warnings
        # to be visible *in the result* rather than only in the full report,
        # and "OCR is not something this program does" is the whole of what a
        # refused scan has to say. Keeping one string threw the rest away
        # before anything could show them.
        item.categories = self._what_happened(outcome)
        if not outcome.published:
            item.status = BookStatus.BLOCKED if not outcome.error else BookStatus.FAILED
            item.severity = Severity.ERROR
            return
        # The row's line is the report's verdict (A13): it names the checks
        # that did not run and the decision still owed, and says "healthy"
        # only when the report would. A question nobody answered is worth a
        # person's eye the way a warning is — the file was written and
        # nothing about that question changed.
        if outcome.verdict:
            item.summary = outcome.verdict
        item.severity = Severity.WARNING if outcome.warnings else Severity.CLEAN
        item.status = (
            BookStatus.ATTENTION if outcome.warnings or outcome.undecided else BookStatus.DONE
        )
        if outcome.warnings:
            item.error = outcome.warnings[0]
        elif outcome.undecided:
            item.error = outcome.verdict

    @staticmethod
    def _what_happened(outcome) -> tuple:
        """The remarks of one conversion, in the order they matter."""
        from ..strings import tr

        said: list[str] = []
        if outcome.error:
            said.append(outcome.error)
        said.extend(one for one in outcome.warnings if one not in said)
        if not said:
            return ()
        return (ChangeCategory("warning", tr("pdf.results.notes"), tuple(said)),)

    # -- what the results screen offers -------------------------------------
    def export_report(self, item: BookItem, destination: pathlib.Path) -> None:
        pathlib.Path(destination).write_text(
            self._reports.get(str(item.source), item.report_text), encoding="utf-8"
        )

    def export_batch(self, items, destination: pathlib.Path) -> None:
        pathlib.Path(destination).write_text(
            "\n\n".join(
                self._reports.get(str(item.source), item.report_text) for item in items
            ),
            encoding="utf-8",
        )

    def reveal(self, path: pathlib.Path) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        target = pathlib.Path(path)
        folder = target if target.is_dir() else target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    @staticmethod
    def defaults() -> PdfSettings:
        return PdfSettings()

    @staticmethod
    def operation() -> Operation:
        return Operation.PDF_CONVERSION


class DemoPdfBackend(PdfBackend):
    """Deterministic documents, for the flow's own tests and for screenshots.

    Like `DemoBackend` beside it: not a mock of the converter but the
    *interface's* idea of one — and holding to the same rules the real one
    does, because a demo that raised attention differently from the engine is
    exactly the drift F03 was.
    """

    #: Generic on purpose: this repository is public (S-06).
    TITLES = ("Instrukcja urzadzenia", "Katalog czesci", "Skan bez tekstu")

    def analyse(self, paths, *, progress=None, cancelled=None) -> "list[BookItem]":
        from ..strings import tr

        chosen = list(paths) or [pathlib.Path(f"{name}.pdf") for name in self.TITLES]
        documents = []
        for index, path in enumerate(chosen, start=1):
            source = pathlib.Path(path)
            if progress is not None:
                progress(Progress(index, len(chosen), source.stem, "analysis"))
            documents.append(BookItem(
                source=source, title=source.stem.replace("_", " "), kind="PDF",
                size=900_000 + index * 400_000, status=BookStatus.READY,
                summary=tr("pdf.analysis.unchecked"),
                # The first document meets the two commonest things a manual
                # has — a running head and drawings — so the plan's list of
                # candidates has something to show (W10 pt 2).
                candidates=(
                    tr("pdf.candidate.heads", pages=4, sampled=4),
                    tr("pdf.candidate.drawings", count=3),
                ) if index == 1 else (),
            ))
        return documents

    def convert(self, plan, documents, *, progress=None, cancelled=None,
                document_done=None, resolver=None) -> "list[BookItem]":
        from ..strings import tr

        chosen = [item for item in documents if item.chosen]
        for index, item in enumerate(chosen):
            if cancelled is not None and cancelled():
                for rest in chosen[index:]:
                    rest.status = BookStatus.CANCELLED
                return chosen
            if progress is not None:
                progress(Progress(index, len(chosen), item.title, "convert"))
            if "skan" in item.title.lower():
                # The one refusal this converter makes on its own, and the one
                # the demo must be able to show: a scan needs OCR and there is
                # none here (P05).
                item.status, item.severity = BookStatus.BLOCKED, Severity.ERROR
                item.error = tr("pdf.needs.ocr")
                item.published_outputs, item.output = (), None
                item.categories = (
                    ChangeCategory("warning", tr("pdf.results.notes"), (item.error,)),
                )
            else:
                folder = plan.destination or item.source.parent
                item.published_outputs = (
                    pathlib.Path(folder) / f"{item.source.stem}.epub",
                )
                item.output = item.published_outputs[0]
                item.issues = 1 if index else 0
                item.severity = Severity.WARNING if item.issues else Severity.CLEAN
                item.status = BookStatus.ATTENTION if item.issues else BookStatus.DONE
                item.categories = ()
                if item.issues:
                    item.error = tr("pdf.warning.reading-order")
                    # The same shape the service's own results take: the demo
                    # holding a different contract is how a screen comes out
                    # tested green and empty in front of somebody.
                    item.categories = (
                        ChangeCategory("warning", tr("pdf.results.notes"), (item.error,)),
                    )
            item.report_text = f"{item.title}\n{'-' * len(item.title)}\n(demo)"
            if document_done is not None:
                document_done(index, item)
        return chosen
