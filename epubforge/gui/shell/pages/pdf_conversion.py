"""PDF → EPUB: the converter's own screen, its own session, its own plan.

The other half of D-057. `RebuildPage` repairs books that already are books;
this makes a book out of a document that is not one. They share the window, the
tokens, the job runner and what a *result* means — and nothing else: the plan
is a `PdfConversionPlan`, the work is `pdfconv.service.convert`, the settings
are the converter's two decisions rather than the repair tool's forty, and no
`.epub` reaches this page's list.

Four states, the same shape a person already learned next door: documents →
settings → converting → results.
"""

from __future__ import annotations

import pathlib
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...strings import tr
from .. import icons
from ..models import BookItem, Progress, Stage
from ..pdf_backend import SUFFIXES
from ..responsive import Cards, LayoutMode, Panels, Responsive, spread
from ..state import last_folder, remember_folder
from ..tokens import CARD_GAP, Tokens
from ..widgets import (
    BookRow,
    BoundedList,
    Card,
    MetricCard,
    Notice,
    PageHeader,
    SafetyNote,
    Stepper,
    button,
    clear_layout,
    label,
    page_body,
)
from ..workers import Runner, _Job
from .home import DropZone

#: The converter's settings, in the order the screen asks them. A table rather
#: than four blocks of widget code: what a person is offered is then one thing
#: to read and one thing to test.
CHOICES = (
    ("layout", "pdf.layout", ("reflowable", "fixed")),
    ("running_heads", "pdf.heads", ("ask", "keep", "remove")),
)

#: The publication options the engine already supports, offered because the
#: refusal they produce is one a person has to be able to answer — on a machine
#: with no browser, the appearance gate refuses every conversion and says so
#: (D-016). Not conversion settings: they belong to the shared layer, which is
#: why they sit on the plan and not in `PdfSettings`.
PUBLICATION = (
    ("render_gate", "pdf.gate.render", ("stop", "report", "off")),
)


class ConversionJob(_Job):
    """One batch of documents, off the window's thread."""

    document_finished = Signal(str, int, object)  # session, index, BookItem
    finished = Signal(str, object)  # session, list[BookItem]

    def __init__(self, backend, plan, documents) -> None:
        import copy

        super().__init__(getattr(plan, "session_id", ""))
        self._backend = backend
        self._plan = plan
        # A copy, for the reason the rebuild's job takes one: the page keeps
        # drawing its own list while this one is worked on.
        self._documents = copy.deepcopy(list(documents))

    def run(self) -> None:
        import copy

        try:
            done = self._backend.convert(
                self._plan, self._documents,
                progress=lambda step: self.progress.emit(self.session, step),
                cancelled=lambda: self._cancelled,
                document_done=lambda index, item: self.document_finished.emit(
                    self.session, index, copy.deepcopy(item)
                ),
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the window
            self.failed.emit(self.session, f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(self.session, done)


class PdfConversionPage(Responsive, QWidget):
    """The conversion flow, testable on its own like the rebuild's."""

    finished = Signal(object)  # BatchOutcome — the window records it
    busy_changed = Signal(bool)
    stage_changed = Signal(object)  # Stage
    #: Files this page was handed that belong next door.
    misrouted = Signal(list)
    #: EPUBs the person asked to send on to the rebuild, explicitly.
    handover = Signal(list)

    def __init__(self, tokens: Tokens, backend) -> None:
        super().__init__()
        self.tokens = tokens
        self.backend = backend
        self.stage = Stage.FILES
        self.documents: list[BookItem] = []
        self.destination: pathlib.Path | None = None
        self.settings = backend.defaults()
        #: The shared layer's two gates, kept beside the converter's settings
        #: rather than inside them.
        self.publication = {"render_gate": "stop", "validate": "off"}
        self.outcome = None
        self.runner = Runner(self)
        self._selected: BookItem | None = None
        self.session_id: str = uuid.uuid4().hex
        self._queued_paths: list = []
        self._strangers: list = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroller, page = page_body(CARD_GAP)
        outer.addWidget(scroller)
        self.header = PageHeader(
            tr("pdf.eyebrow"), tr("pdf.title.files"), tr("pdf.subtitle.files"),
        )
        page.addWidget(self.header)
        self.stepper = Stepper(tokens, (
            "pdf.step.documents", "pdf.step.settings", "pdf.step.convert",
            "pdf.step.results",
        ))
        page.addWidget(self.stepper)
        self.body = QVBoxLayout()
        self.body.setSpacing(CARD_GAP)
        page.addLayout(self.body, 1)

        self.show_files()
        self.begin_tracking(scroller)

    # -- housekeeping -------------------------------------------------------
    def reflow(self, mode: LayoutMode) -> None:
        spread(self, mode)
        self.stepper.set_compact(mode is LayoutMode.COMPACT)

    def _settle(self) -> None:
        spread(self, self.layout_mode)
        for name in ("document_list", "result_list"):
            listing = getattr(self, name, None)
            if listing is not None and listing.parent() is not None:
                listing.fit_within(self.height())

    def _go(self, stage: Stage) -> None:
        self.stage = stage
        self.stage_changed.emit(stage)
        self.stepper.set_stage(stage)
        name = {Stage.FILES: "files", Stage.ANALYSIS: "files", Stage.PLAN: "settings",
                Stage.RUNNING: "running", Stage.RESULTS: "results"}[stage]
        self.header.retitle(
            tr(f"pdf.title.{name}"),
            tr(f"pdf.subtitle.{name}", count=len(self.documents)),
        )
        clear_layout(self.body)

    @property
    def busy(self) -> bool:
        return self.runner.working

    @property
    def ready_count(self) -> int:
        return sum(1 for item in self.documents if item.chosen and item.rebuildable)

    def can_export_report(self) -> bool:
        """Ctrl+S means *this* module's report, and only on its results."""
        return self.stage is Stage.RESULTS and self.outcome is not None

    # -- 1. the documents ---------------------------------------------------
    def show_files(self) -> None:
        self._go(Stage.FILES)
        self._show_any_strangers()
        zone = DropZone(
            self.tokens, suffixes=SUFFIXES, title_key="pdf.drop",
            subtitle_key="pdf.drop.body", choose_key="pdf.add",
            hint_key="pdf.limits.ocr", filter_key="dialog.filter.pdf",
        )
        zone.files_dropped.connect(self.start)
        self.body.addWidget(zone)
        self.body.addWidget(self._limits_card())

    def start(self, paths: "list[str]") -> None:
        """Take a set of documents and begin. An EPUB among them goes home.

        Nothing is silently replaced here either: a batch under way is left
        alone and the person is asked, exactly as next door (F05).
        """
        from .. import routing

        sorted_out = routing.sort_out(path for path in paths if path)
        strangers = sorted_out["rebuild"]
        chosen = sorted_out["pdf"]
        self._strangers = [str(path) for path in strangers]
        if not chosen:
            if strangers:
                self.show_files()
            return
        if self.runner.working:
            self._ask_about(chosen)
            return
        self.session_id = uuid.uuid4().hex
        self.documents = []
        self.outcome = None
        self._look_at(chosen)

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dialog.selectfiles"), last_folder("input"), tr("dialog.filter.pdf")
        )
        if not paths:
            return
        remember_folder("input", paths[0])
        known = {str(item.source) for item in self.documents}
        fresh = [pathlib.Path(path) for path in paths if path not in known]
        if fresh:
            self._look_at(fresh, keep=True)

    def _ask_about(self, chosen: "list[pathlib.Path]") -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("shell.busy.title"))
        box.setText(tr("shell.busy.body", count=len(chosen)))
        box.setInformativeText(tr("shell.busy.hint"))
        wait = box.addButton(tr("shell.busy.wait"), QMessageBox.AcceptRole)
        box.addButton(tr("shell.busy.stop"), QMessageBox.DestructiveRole)
        drop = box.addButton(tr("shell.busy.forget"), QMessageBox.RejectRole)
        box.setDefaultButton(wait)
        box.exec()
        answered = box.clickedButton()
        if answered is drop:
            return
        self._queued_paths = [str(path) for path in chosen]
        if answered is not wait:
            self._cancel()

    def _show_any_strangers(self) -> None:
        """The notice about books that belong to the rebuild, if any came."""
        if not self._strangers:
            return
        notice = Notice(
            self.tokens,
            tr("pdf.wrong.module.epub", count=len(self._strangers)),
            tr("pdf.wrong.module.go"),
        )
        notice.acted.connect(self._hand_the_strangers_over)
        notice.dismissed.connect(lambda: setattr(self, "_strangers", []))
        self.notice = notice
        self.body.addWidget(notice)

    def _hand_the_strangers_over(self) -> None:
        going, self._strangers = self._strangers, []
        if going:
            self.misrouted.emit(going)

    def _start_queued(self) -> None:
        waiting, self._queued_paths = self._queued_paths, []
        if waiting and not self.runner.working:
            self.start(waiting)

    def _look_at(self, paths: "list[pathlib.Path]", *, keep: bool = False) -> None:
        """What the files are, without opening them — see `PdfBackend.analyse`."""
        existing = list(self.documents) if keep else []
        fresh = self.backend.analyse(list(paths))
        self.documents = existing + list(fresh)
        for item in self.documents:
            item.chosen = item.rebuildable
        self.show_settings()

    # -- 2. the settings ----------------------------------------------------
    def show_settings(self) -> None:
        self._go(Stage.PLAN)
        self._show_any_strangers()
        columns = Panels(CARD_GAP)

        left_side = QWidget()
        left = QVBoxLayout(left_side)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(CARD_GAP)

        self.documents_card = documents_card = Card(
            tr("pdf.documents"), tr("pdf.documents.body"), glyph="book", tokens=self.tokens,
        )
        actions = QHBoxLayout()
        add = button(tr("pdf.add"), glyph="plus", tokens=self.tokens)
        add.clicked.connect(self.add_files)
        actions.addWidget(add)
        self.destination_button = button(
            str(self.destination) if self.destination else tr("pdf.where.beside"),
            glyph="folder", tokens=self.tokens, tip=tr("pdf.where.body"),
        )
        self.destination_button.clicked.connect(self._choose_destination)
        actions.addWidget(self.destination_button)
        actions.addStretch(1)
        documents_card.body.addLayout(actions)
        self._rows = []
        self.document_list = BoundedList()
        for item in self.documents:
            row = BookRow(item, self.tokens)
            row.removed.connect(self._remove)
            row.toggled.connect(self._toggle)
            self._rows.append(row)
            self.document_list.add(row)
        self.document_list.finish()
        documents_card.body.addWidget(self.document_list)
        left.addWidget(documents_card)
        left.addWidget(self._settings_card())
        left.addWidget(self._limits_card())
        columns.add(left_side, 2)
        columns.add(self._summary_card(), 1)
        self.body.addWidget(columns, 1)
        self._settle()

    def _settings_card(self) -> Card:
        """The two decisions that change the result, and nothing else.

        No presets from next door and no policy drawer: those are the repair
        tool's, and offering them here would say a conversion is a kind of
        repair (03-PDF-MODULE §3B).
        """
        card = Card(tr("pdf.settings"), tr("pdf.settings.body"), glyph="settings",
                    tokens=self.tokens)
        self._groups = {}
        for name, key, values in CHOICES:
            card.body.addWidget(label(tr(key), "cardTitle"))
            if name == "layout":
                # The one choice with a cost worth spelling out, so it is
                # radio buttons with their sentences rather than a combo box.
                group = QButtonGroup(self)
                for value in values:
                    option = QRadioButton(tr(f"{key}.{value}"))
                    option.setToolTip(tr(f"{key}.{value}.tip"))
                    option.setChecked(getattr(self.settings, name) == value)
                    option.toggled.connect(
                        lambda on, field=name, chosen=value: self._chose(field, chosen, on)
                    )
                    group.addButton(option)
                    card.body.addWidget(option)
                    hint = label(tr(f"{key}.{value}.tip"), "muted")
                    card.body.addWidget(hint)
                self._groups[name] = group
                continue
            combo = QComboBox()
            combo.setAccessibleName(tr(key))
            for value in values:
                combo.addItem(tr(f"{key}.{value}"), value)
                combo.setItemData(combo.count() - 1, tr(f"{key}.{value}.tip"), Qt.ToolTipRole)
            combo.setCurrentIndex(values.index(getattr(self.settings, name)))
            combo.currentIndexChanged.connect(
                lambda _index, field=name, box=combo: setattr(
                    self.settings, field, box.currentData()
                )
            )
            card.body.addWidget(combo)
            self._groups[name] = combo
        for name, key, values in PUBLICATION:
            card.body.addWidget(label(tr(key), "cardTitle"))
            combo = QComboBox()
            combo.setAccessibleName(tr(key))
            for value in values:
                combo.addItem(tr(f"{key}.{value}"), value)
                combo.setItemData(combo.count() - 1, tr(f"{key}.{value}.tip"), Qt.ToolTipRole)
            combo.setCurrentIndex(values.index(self.publication[name]))
            combo.currentIndexChanged.connect(
                lambda _index, field=name, box=combo: self.publication.__setitem__(
                    field, box.currentData()
                )
            )
            card.body.addWidget(combo)
            self._groups[name] = combo
        return card

    def _chose(self, field: str, value: str, on: bool) -> None:
        if on:
            setattr(self.settings, field, value)

    def _limits_card(self) -> Card:
        """What this converter does not do, said before it is asked to.

        Not a warning that appears after a disappointment: the three sentences
        are the same three every time, and a person choosing a document
        deserves them first (03-PDF-MODULE §3B).
        """
        card = Card(tr("pdf.limits"), "", glyph="warning", tokens=self.tokens)
        for key in ("pdf.limits.ocr", "pdf.limits.layout", "pdf.limits.check"):
            card.body.addWidget(label(tr(key), "muted"))
        return card

    def _summary_card(self) -> Card:
        card = Card(tr("pdf.title.settings"), "", glyph="inspect", tokens=self.tokens)
        self._summary_rows = {}
        for name, caption, value in (
            ("count", tr("pdf.documents"), str(self.ready_count)),
            ("layout", tr("pdf.layout"),
             tr(f"pdf.layout.{self.settings.layout}")),
            ("where", tr("pdf.where"), self._destination_text()),
        ):
            card.body.addWidget(label(caption, "muted"))
            said = label(value, "cardSubtitle")
            self._summary_rows[name] = said
            card.body.addWidget(said)
        card.body.addSpacing(8)
        self.convert_button = button(
            tr("pdf.convert"), kind="primary", glyph="play", tokens=self.tokens,
        )
        self.convert_button.setMinimumHeight(44)
        self.convert_button.setEnabled(bool(self.ready_count))
        self.convert_button.clicked.connect(self.run)
        card.body.addWidget(self.convert_button)
        card.body.addWidget(SafetyNote(self.tokens))
        card.body.addStretch(1)
        return card

    def _destination_text(self) -> str:
        return str(self.destination) if self.destination else tr("pdf.where.body")

    def _choose_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, tr("dialog.selectfolder"), last_folder("output")
        )
        if folder:
            remember_folder("output", folder)
            self.destination = pathlib.Path(folder)
            self.show_settings()

    def _remove(self, item: BookItem) -> None:
        self.documents = [one for one in self.documents if one is not item]
        if self.documents:
            self.show_settings()
        else:
            self.show_files()

    def _toggle(self, item: BookItem, chosen: bool) -> None:
        item.chosen = chosen
        self._refresh_counts()

    def _refresh_counts(self) -> None:
        said = getattr(self, "_summary_rows", {})
        if "count" in said:
            said["count"].setText(str(self.ready_count))
        if hasattr(self, "convert_button"):
            self.convert_button.setEnabled(bool(self.ready_count))

    # -- 3. converting ------------------------------------------------------
    def plan(self):
        from ....pdfconv.models import PdfConversionPlan

        return PdfConversionPlan(
            sources=tuple(item.source for item in self.documents if item.chosen),
            destination=self.destination,
            settings=self.settings,
            session_id=self.session_id,
            validate=self.publication["validate"],
            render_gate=self.publication["render_gate"],
            ask=False,
        )

    def run(self) -> None:
        if self.runner.working:
            return
        chosen = [item for item in self.documents if item.chosen]
        if not chosen:
            QMessageBox.information(self, tr("shell.nothing.title"), tr("shell.nothing.body"))
            return

        self._go(Stage.RUNNING)
        card = Card(tr("pdf.title.running"), tr("pdf.subtitle.running"),
                    glyph="rebuild", tokens=self.tokens)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(chosen))
        self.progress.setAccessibleName(tr("pdf.title.running"))
        self.progress_name = label("", "muted")
        card.body.addStretch(1)
        card.body.addWidget(self.progress_name)
        card.body.addWidget(self.progress)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = button(tr("shell.cancel"), glyph="close", tokens=self.tokens,
                                    tip=tr("shell.cancel.tip"))
        self.cancel_button.clicked.connect(self._cancel)
        row.addWidget(self.cancel_button)
        card.body.addLayout(row)
        self.body.addWidget(card)
        self.body.addWidget(SafetyNote(self.tokens))
        self.body.addStretch(1)

        job = ConversionJob(self.backend, self.plan(), chosen)
        job.progress.connect(self._on_progress, Qt.QueuedConnection)
        job.failed.connect(self._on_failed, Qt.QueuedConnection)
        job.document_finished.connect(self._document_finished, Qt.QueuedConnection)
        job.finished.connect(self._converted, Qt.QueuedConnection)
        self.busy_changed.emit(True)
        self.runner.start(job, on_done=self._idle)

    def _idle(self) -> None:
        self.busy_changed.emit(False)
        self._start_queued()

    def _ours(self, session: str) -> bool:
        return session == self.session_id

    def _cancel(self) -> None:
        self.runner.cancel()
        if hasattr(self, "cancel_button"):
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText(tr("shell.cancelling"))

    def _on_progress(self, session: str, step: Progress) -> None:
        if not self._ours(session) or not hasattr(self, "progress"):
            return
        if step.determinate:
            self.progress.setRange(0, step.total)
            self.progress.setValue(step.done)
        else:
            self.progress.setRange(0, 0)
        self.progress_name.setText(
            f"{step.name}   ·   {tr('shell.progress.of', done=step.done, total=step.total)}"
        )

    def _on_failed(self, session: str, message: str) -> None:
        if not self._ours(session):
            return
        QMessageBox.warning(self, tr("shell.error.title"), tr("shell.error.body", error=message))
        self.show_settings()

    def _document_finished(self, session: str, index: int, item: BookItem) -> None:
        if not self._ours(session):
            return
        chosen = [one for one in self.documents if one.chosen]
        if index < len(chosen):
            for field in ("status", "issues", "output", "published_outputs", "severity",
                          "report_text", "error", "title"):
                setattr(chosen[index], field, getattr(item, field))
        if hasattr(self, "progress"):
            self.progress.setValue(index + 1)

    def _converted(self, session: str, documents: "list[BookItem]") -> None:
        if not self._ours(session):
            return
        from ..models import BatchOutcome, Operation

        by_source = {item.source: item for item in documents}
        for index, item in enumerate(self.documents):
            fresh = by_source.get(item.source)
            if fresh is not None:
                self.documents[index] = fresh
        self.show_results(BatchOutcome(
            books=tuple(documents),
            cancelled=self.runner.cancelled,
            destination=self.destination,
            operation=Operation.PDF_CONVERSION,
            session_id=session,
        ))

    # -- 4. the results -----------------------------------------------------
    def show_results(self, outcome) -> None:
        self.outcome = outcome
        self._go(Stage.RESULTS)
        self.header.retitle(
            tr("pdf.title.results"),
            tr("pdf.subtitle.results", count=outcome.published),
        )
        self.body.addWidget(self._banner(outcome))

        columns = Panels(CARD_GAP)
        results = Card(tr("pdf.results.list"), tr("pdf.results.list.body"), glyph="book",
                       tokens=self.tokens)
        self._result_rows = []
        self.result_list = BoundedList()
        for item in outcome.books:
            row = BookRow(item, self.tokens, results=True, repairs=False)
            row.opened.connect(self._select)
            self._result_rows.append(row)
            self.result_list.add(row)
        self.result_list.finish()
        results.body.addWidget(self.result_list)
        results.body.addStretch(1)

        # What actually happened to the document that is selected, spelled out
        # rather than elided into a row. A refused scan says "OCR is not
        # something this program does" here, and a converted document lists
        # every remark it came with — the acceptance list asks for both to be
        # in the result and not only in the full report.
        self._notes_card = Card(tr("pdf.results.notes"), tr("pdf.results.notes.body"),
                                glyph="warning", tokens=self.tokens)
        self._notes_body = QVBoxLayout()
        self._notes_card.body.addLayout(self._notes_body)
        report_button = button(tr("pdf.results.report"), kind="ghost", glyph="inspect",
                               tokens=self.tokens, tip=tr("pdf.results.report.body"))
        report_button.clicked.connect(self._show_report)
        self._notes_card.body.addWidget(report_button)
        results.body.addWidget(self._notes_card)
        columns.add(results, 2)
        columns.add(self._next_card(outcome), 1)
        self.body.addWidget(columns, 1)
        self._settle()
        first = next((item for item in outcome.books if not item.published), None)
        self._select(first or (outcome.books[0] if outcome.books else None))
        self.finished.emit(outcome)

    def _banner(self, outcome) -> QFrame:
        if outcome.cancelled:
            name, role, glyph = "cancelled", "warningCard", "close"
        elif outcome.failed:
            name, role, glyph = "failed", "dangerCard", "error"
        elif outcome.attention:
            name, role, glyph = "warn", "warningCard", "warning"
        else:
            name, role, glyph = "ok", "successCard", "check"
        colour = {"successCard": self.tokens.success, "warningCard": self.tokens.warning,
                  "dangerCard": self.tokens.danger}[role]

        banner = QFrame()
        banner.setObjectName(role)
        holder = QVBoxLayout(banner)
        holder.setContentsMargins(18, 14, 18, 14)
        split = Panels(14)

        said = QWidget()
        row = QHBoxLayout(said)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        mark = QLabel()
        mark.setPixmap(icons.icon(glyph, colour).pixmap(26, 26))
        row.addWidget(mark, 0, Qt.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(3)
        words.addWidget(label(tr(f"pdf.results.banner.{name}"), "cardTitle"))
        words.addWidget(label(tr(f"pdf.results.banner.{name}.body"), "cardSubtitle"))
        row.addLayout(words, 1)
        split.add(said, 2)

        numbers = [
            (outcome.published, tr("pdf.results.metric.done"), "success", "check"),
            (outcome.attention, tr("pdf.results.metric.warned"), "warning", "warning"),
        ]
        if outcome.failed:
            numbers.append((outcome.failed, tr("pdf.results.metric.failed"), "danger", "error"))
        metrics = Cards(
            {LayoutMode.WIDE: len(numbers), LayoutMode.MEDIUM: 2, LayoutMode.COMPACT: 1}, 10
        )
        for value, caption, role_name, mark_name in numbers:
            metrics.add(MetricCard(str(value), caption, self.tokens, role_name, mark_name))
        split.add(metrics, 2)
        holder.addWidget(split)
        banner.setAccessibleName(tr(f"pdf.results.banner.{name}"))
        return banner

    def _next_card(self, outcome) -> Card:
        card = Card(tr("shell.results.next"), tr("shell.results.next.body"), glyph="chevron",
                    tokens=self.tokens)
        places = outcome.folders
        open_folder = button(tr("shell.results.open.folder"), kind="primary", glyph="folder",
                             tokens=self.tokens, tip=places[0] if places else "")
        open_folder.setEnabled(bool(places))
        open_folder.clicked.connect(
            lambda: self.backend.reveal(pathlib.Path(places[0])) if places else None
        )
        card.body.addWidget(open_folder)
        save = button(tr("shell.results.save"), glyph="save", tokens=self.tokens)
        save.clicked.connect(self.save_report)
        card.body.addWidget(save)

        # Optional and explicit, and it starts nothing (03-PDF-MODULE §3D):
        # only the files that were actually written, only when asked.
        written = [path for path in outcome.published_outputs]
        send_on = button(tr("pdf.results.handover"), glyph="rebuild", tokens=self.tokens,
                         tip=tr("pdf.results.handover.tip"))
        send_on.setEnabled(bool(written))
        send_on.clicked.connect(lambda: self.handover.emit([str(path) for path in written]))
        card.body.addWidget(send_on)

        again = button(tr("pdf.results.again"), glyph="plus", tokens=self.tokens)
        again.clicked.connect(self.show_files)
        card.body.addWidget(again)
        card.body.addSpacing(10)
        card.body.addWidget(label(tr("shell.results.files"), "cardTitle"))
        if not written:
            card.body.addWidget(label(tr("shell.results.none"), "muted"))
        else:
            for place in places:
                if place not in (".", ""):
                    card.body.addWidget(label(place, "cardSubtitle"))
                for path in written:
                    if str(path.parent) == place:
                        card.body.addWidget(label(path.name, "muted"))
        card.body.addStretch(1)
        return card

    def _select(self, item: "BookItem | None") -> None:
        self._selected = item
        for row in getattr(self, "_result_rows", []):
            chosen = row.book is item
            row.set_selected(chosen)
        if not hasattr(self, "_notes_body"):
            return
        clear_layout(self._notes_body)
        said = [line for group in (item.categories if item else ()) for line in group.lines]
        if not said:
            self._notes_body.addWidget(label(tr("pdf.results.notes.none"), "muted"))
            return
        for line in said:
            # Wrapped, not elided: a sentence whose last third is the part that
            # says what to do about it is a sentence that has to be readable.
            self._notes_body.addWidget(label(f"•  {line}", "cardSubtitle"))

    def _show_report(self) -> None:
        """The whole report, for the document in hand."""
        item = self._selected
        if item is None:
            return
        from PySide6.QtWidgets import QDialog, QPlainTextEdit

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("pdf.results.report.title", title=item.title))
        dialog.resize(880, 620)
        stack = QVBoxLayout(dialog)
        view = QPlainTextEdit(item.report_text or tr("report.placeholder"))
        view.setReadOnly(True)
        stack.addWidget(view)
        close = button(tr("about.close"))
        close.clicked.connect(dialog.accept)
        stack.addWidget(close, alignment=Qt.AlignRight)
        dialog.exec()

    def save_report(self) -> None:
        item = self._selected or next(
            (one for one in self.documents if one.report_text), None
        )
        if item is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog.savereport"),
            str(pathlib.Path(last_folder("report")) / f"{item.source.stem}.txt"),
            "Tekst (*.txt)",
        )
        if path:
            remember_folder("report", path)
            self.backend.export_report(item, pathlib.Path(path))

    def save_batch_report(self) -> None:
        items = list(self.outcome.books) if self.outcome else []
        if not items:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog.savereport.batch"),
            str(pathlib.Path(last_folder("report")) / "raport-konwersji.txt"),
            "Tekst (*.txt)",
        )
        if path:
            remember_folder("report", path)
            self.backend.export_batch(items, pathlib.Path(path))
