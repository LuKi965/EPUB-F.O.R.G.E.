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
from .models import BookItem, BookStatus, Operation, Progress, Severity

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
        """Say what each file is. Nothing is opened and nothing is written.

        The screen this feeds shows "Nie sprawdzono" where nothing was checked,
        because reading a PDF's structure costs what the conversion's own first
        phase costs. A preflight that pretended otherwise would be inventing
        a number (03-PDF-MODULE §3B).
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
                summary=tr("pdf.analysis.unchecked"),
            )
            if info.refusal:
                item.status = BookStatus.FAILED
                item.error = info.refusal
            documents.append(item)
        return documents

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
        if not outcome.published:
            item.status = BookStatus.BLOCKED if not outcome.error else BookStatus.FAILED
            item.severity = Severity.ERROR
            return
        item.severity = Severity.WARNING if outcome.warnings else Severity.CLEAN
        item.status = BookStatus.ATTENTION if outcome.warnings else BookStatus.DONE
        if outcome.warnings:
            item.error = outcome.warnings[0]

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
            else:
                folder = plan.destination or item.source.parent
                item.published_outputs = (
                    pathlib.Path(folder) / f"{item.source.stem}.epub",
                )
                item.output = item.published_outputs[0]
                item.issues = 1 if index else 0
                item.severity = Severity.WARNING if item.issues else Severity.CLEAN
                item.status = BookStatus.ATTENTION if item.issues else BookStatus.DONE
                if item.issues:
                    item.error = tr("pdf.warning.reading-order")
            item.report_text = f"{item.title}\n{'-' * len(item.title)}\n(demo)"
            if document_done is not None:
                document_done(index, item)
        return chosen
