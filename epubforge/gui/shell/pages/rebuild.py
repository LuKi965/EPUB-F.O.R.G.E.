"""The rebuild: files → analysis → plan → results.

One page, four states, one session object. Each state draws itself from the
session rather than mutating the last one, because a screen that is patched
step by step ends up showing a mixture of two states — which is precisely the
bug class a wizard is supposed to remove.

Everything long runs in `workers`; this file starts jobs, draws what they
report, and never touches an EPUB.
"""

from __future__ import annotations

import pathlib

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ...strings import tr
from .. import icons
from ..models import (
    BatchOutcome,
    BookItem,
    BookStatus,
    Preset,
    Progress,
    RebuildPlan,
    Stage,
)
from ..tokens import CARD_GAP, CONTENT_MARGIN, Tokens
from ..widgets import (
    BookRow,
    Card,
    MetricCard,
    PageHeader,
    SafetyNote,
    Stepper,
    button,
    clear_layout,
    label,
    scrolling_body,
)
from ..workers import AnalysisJob, RebuildJob, Runner
from .drawer import SettingsDrawer
from .home import DropZone

#: The three presets, in the order the plan screen shows them.
PRESET_CARDS = (
    (Preset.PRESERVE, "shell.preset.preserve", True),
    (Preset.STRICT, "shell.preset.strict", False),
    (Preset.CONTAINER, "shell.preset.container", False),
)


class RebuildPage(QWidget):
    """The four-step flow, and the only page that writes anything."""

    finished = Signal(object)  # BatchOutcome — the window records it in history
    busy_changed = Signal(bool)

    def __init__(self, tokens: Tokens, backend, resolver_factory=None) -> None:
        super().__init__()
        self.tokens = tokens
        self.backend = backend
        self._resolver_factory = resolver_factory
        self.stage = Stage.FILES
        self.books: list[BookItem] = []
        self.preset = Preset.PRESERVE
        self.destination: pathlib.Path | None = None
        self.overrides: dict = {}
        self.outcome: BatchOutcome | None = None
        self.runner = Runner(self)
        self._selected: BookItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(CONTENT_MARGIN, 24, CONTENT_MARGIN, 22)
        layout.setSpacing(CARD_GAP)
        self.header = PageHeader(
            tr("shell.rebuild.eyebrow"),
            tr("shell.rebuild.title.files"),
            tr("shell.rebuild.subtitle.files"),
        )
        layout.addWidget(self.header)
        self.stepper = Stepper(tokens)
        layout.addWidget(self.stepper)
        scroller, self.body = scrolling_body(CARD_GAP)
        layout.addWidget(scroller, 1)

        self.drawer = SettingsDrawer(self, tokens)
        self.drawer.applied.connect(self._apply_overrides)
        self.show_files()

    # -- housekeeping -------------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt casing
        super().resizeEvent(event)
        if self.drawer.isVisible():
            self.drawer.setGeometry(self.rect())

    def _go(self, stage: Stage) -> None:
        self.stage = stage
        self.stepper.set_stage(stage)
        name = stage.name.lower()
        self.header.retitle(
            tr(f"shell.rebuild.title.{name}"),
            tr(f"shell.rebuild.subtitle.{name}", count=len(self.books)),
        )
        clear_layout(self.body)

    @property
    def busy(self) -> bool:
        return self.runner.busy

    # -- 1. files -----------------------------------------------------------
    def show_files(self) -> None:
        self._go(Stage.FILES)
        zone = DropZone(self.tokens)
        zone.files_dropped.connect(self.start)
        self.body.addWidget(zone)

    def start(self, paths: "list[str]") -> None:
        """Take a list of files and begin: analysis, then the plan."""
        chosen = [pathlib.Path(path) for path in paths if path]
        if not chosen:
            return
        self.books = []
        self.outcome = None
        self.show_analysis(chosen)

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dialog.selectfiles"), "", tr("dialog.filter")
        )
        if not paths:
            return
        known = {str(book.source) for book in self.books}
        fresh = [path for path in paths if path not in known]
        if fresh:
            self.show_analysis([pathlib.Path(path) for path in fresh], keep=True)

    # -- 2. analysis --------------------------------------------------------
    def show_analysis(self, paths: "list[pathlib.Path]", *, keep: bool = False) -> None:
        self._go(Stage.ANALYSIS)
        existing = list(self.books) if keep else []
        card = Card(tr("shell.rebuild.title.analysis"), tr("shell.analysis.body"),
                    glyph="inspect", tokens=self.tokens)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(paths))
        self.progress.setAccessibleName(tr("shell.rebuild.title.analysis"))
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

        # Queued, every one of them: a worker signal connected to a lambda is
        # delivered in the worker's thread, and building a layout there is
        # undefined behaviour that Qt reports as "cannot set parent, new parent
        # is in a different thread" long after the damage.
        self._carry_over = existing
        job = AnalysisJob(self.backend, paths)
        job.progress.connect(self._on_progress, Qt.QueuedConnection)
        job.failed.connect(self._on_failed, Qt.QueuedConnection)
        job.finished.connect(self._analysed, Qt.QueuedConnection)
        self.busy_changed.emit(True)
        self.runner.start(job, on_done=self._idle)

    def _idle(self) -> None:
        self.busy_changed.emit(False)

    def _analysed(self, books: "list[BookItem]") -> None:
        self.books = list(getattr(self, "_carry_over", [])) + list(books)
        self._carry_over = []
        if not books:
            self.show_files()
            return
        self.show_plan()

    def _on_progress(self, step: Progress) -> None:
        if not hasattr(self, "progress"):
            return
        if step.determinate:
            self.progress.setRange(0, step.total)
            self.progress.setValue(step.done)
        else:
            self.progress.setRange(0, 0)
        if step.phase == "validate":
            self.progress_name.setText(tr("status.validating", name=step.name))
        else:
            self.progress_name.setText(
                f"{step.name}   ·   {tr('shell.progress.of', done=step.done, total=step.total)}"
            )

    def _on_failed(self, message: str) -> None:
        QMessageBox.warning(self, tr("shell.error.title"), tr("shell.error.body", error=message))
        self.show_files()

    def _cancel(self) -> None:
        self.runner.cancel()
        if hasattr(self, "cancel_button"):
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText(tr("shell.cancelling"))

    # -- 3. plan ------------------------------------------------------------
    def show_plan(self) -> None:
        self._go(Stage.PLAN)
        columns = QHBoxLayout()
        columns.setSpacing(CARD_GAP)

        left = QVBoxLayout()
        left.setSpacing(CARD_GAP)
        ready = sum(1 for book in self.books if book.chosen and book.status is not BookStatus.FAILED)
        books_card = Card(tr("shell.plan.count", count=ready), tr("shell.plan.subtitle"),
                          glyph="book", tokens=self.tokens)
        actions = QHBoxLayout()
        add = button(tr("shell.files.add"), glyph="plus", tokens=self.tokens)
        add.clicked.connect(self.add_files)
        actions.addWidget(add)
        self.destination_button = button(
            self._destination_text(), glyph="folder", tokens=self.tokens,
            tip=tr("shell.plan.destination.tip"),
        )
        self.destination_button.clicked.connect(self._choose_destination)
        actions.addWidget(self.destination_button)
        actions.addStretch(1)
        books_card.body.addLayout(actions)

        for book in self.books:
            row = BookRow(book, self.tokens)
            row.removed.connect(self._remove_book)
            row.toggled.connect(self._toggle_book)
            books_card.body.addWidget(row)
        # Spare height goes to the bottom of the card. Without this the layout
        # shares it out between the rows, and the card reads as three widgets
        # adrift in it rather than a list.
        books_card.body.addStretch(1)
        left.addWidget(books_card, 3)

        plan_card = Card(tr("shell.plan.title"), tr("shell.plan.body"), glyph="sliders",
                         tokens=self.tokens)
        presets = QHBoxLayout()
        presets.setSpacing(10)
        self._preset_cards = []
        from ..widgets import PresetCard

        for preset, key, recommended in PRESET_CARDS:
            description = tr(f"{key}.body")
            if self._risky_in(preset):
                # ACCEPTANCE: "risky options are not enabled accidentally by
                # preset changes". `strict` does switch one on — it is what
                # forcing the standard means — so the card says so before it
                # is chosen rather than the drawer saying so afterwards.
                description = f"{description}\n{tr('shell.preset.risky')}"
            card = PresetCard(
                preset, tr(key), description, self.tokens,
                recommended=recommended, selected=preset == self.preset,
            )
            card.chosen.connect(self._choose_preset)
            self._preset_cards.append(card)
            presets.addWidget(card, 1)
        plan_card.body.addLayout(presets)
        details_row = QHBoxLayout()
        self.details_button = button(tr("shell.plan.details"), glyph="sliders", tokens=self.tokens)
        self.details_button.clicked.connect(self._open_drawer)
        details_row.addWidget(self.details_button)
        self.changed_label = label(
            tr("shell.plan.changed", count=len(self.overrides)) if self.overrides else "", "muted"
        )
        details_row.addWidget(self.changed_label)
        details_row.addStretch(1)
        plan_card.body.addLayout(details_row)
        left.addWidget(plan_card, 2)
        columns.addLayout(left, 2)

        columns.addWidget(self._summary_card(), 1)
        self.body.addLayout(columns, 1)

    def _summary_card(self) -> Card:
        card = Card(tr("shell.summary.title"), tr("shell.summary.body"), glyph="check",
                    tokens=self.tokens)
        values = self.backend.defaults_for(self.preset)
        values.update(self.overrides)
        chosen = sum(1 for book in self.books if book.chosen)
        for key, value in (
            (tr("shell.summary.files"), str(chosen)),
            (tr("shell.summary.mode"), tr(dict((p, k) for p, k, _ in PRESET_CARDS)[self.preset])),
            (tr("shell.summary.epubcheck"),
             tr("shell.summary.on") if values.get("validate") else tr("shell.summary.off")),
            (tr("shell.summary.destination"), self._destination_text()),
        ):
            row = QHBoxLayout()
            row.addWidget(label(key, "muted"))
            row.addStretch(1)
            row.addWidget(label(value, "cardTitle"))
            card.body.addLayout(row)
        card.body.addWidget(SafetyNote(self.tokens))
        card.body.addStretch(1)
        run = button(tr("shell.run"), kind="primary", glyph="play", tokens=self.tokens,
                     tip=tr("shell.run.tip"))
        run.setMinimumHeight(44)
        run.clicked.connect(self.run)
        card.body.addWidget(run)
        plan_only = button(tr("shell.run.plan"), glyph="save", tokens=self.tokens,
                           tip=tr("shell.run.plan.tip"))
        plan_only.clicked.connect(lambda: self.run(plan_only=True))
        card.body.addWidget(plan_only)
        card.body.addWidget(label(tr("shell.time.note"), "muted"))
        return card

    def _risky_in(self, preset: Preset) -> bool:
        """Whether this preset switches on anything marked risky."""
        from ..options import OPTIONS

        values = self.backend.defaults_for(preset)
        return any(option.risky and values.get(option.key) for option in OPTIONS)

    def _destination_text(self) -> str:
        return str(self.destination) if self.destination else tr("shell.plan.destination.beside")

    def _choose_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("dialog.selectfolder"))
        if folder:
            self.destination = pathlib.Path(folder)
            self.show_plan()

    def _choose_preset(self, preset: Preset) -> None:
        self.preset = preset
        # Overrides belong to the preset they were made against: keeping them
        # across a change is how a risky option ends up switched on by a choice
        # nobody connected to it (ACCEPTANCE, "risky options").
        self.overrides = {}
        for card in self._preset_cards:
            card.set_selected(card.preset == preset)
        self.show_plan()

    def _remove_book(self, book: BookItem) -> None:
        self.books = [item for item in self.books if item is not book]
        if self.books:
            self.show_plan()
        else:
            self.show_files()

    def _toggle_book(self, book: BookItem, state: bool) -> None:
        book.chosen = state

    def _open_drawer(self) -> None:
        self.drawer.open_with(
            self.backend.defaults_for(self.preset),
            self.overrides,
            sum(1 for book in self.books if book.chosen),
            opener=getattr(self, "details_button", None),
        )

    def _apply_overrides(self, overrides: dict) -> None:
        self.overrides = dict(overrides)
        self.show_plan()

    # -- 4. running and results --------------------------------------------
    def plan(self, *, plan_only: bool = False) -> RebuildPlan:
        overrides = dict(self.overrides)
        if plan_only:
            overrides["plan_only"] = True
        return RebuildPlan(
            sources=tuple(book.source for book in self.books if book.chosen),
            destination=self.destination,
            preset=self.preset,
            overrides=overrides,
            ask=bool(overrides.get("ask", True)),
        )

    def run(self, *, plan_only: bool = False) -> None:
        if self.runner.busy:
            return
        chosen = [book for book in self.books if book.chosen]
        if not chosen:
            QMessageBox.information(self, tr("shell.nothing.title"), tr("shell.nothing.body"))
            return
        # The one refusal that happens before anything is opened: a destination
        # that would land on top of a source.
        for book in chosen:
            target = self.backend.destination_for(
                book.source, self.destination, bool(self.overrides.get("kepub", False))
            )
            if pathlib.Path(target).resolve() == pathlib.Path(book.source).resolve():
                QMessageBox.warning(
                    self, tr("shell.overwrite.title"),
                    tr("shell.overwrite.body", name=book.source.name),
                )
                return

        self._go(Stage.RUNNING)
        card = Card(tr("shell.rebuild.title.running"), tr("shell.rebuild.subtitle.running"),
                    glyph="rebuild", tokens=self.tokens)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(chosen))
        self.progress.setAccessibleName(tr("shell.rebuild.title.running"))
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

        resolver = None
        if self._resolver_factory is not None and self.plan(plan_only=plan_only).ask:
            resolver = self._resolver_factory()
        job = RebuildJob(self.backend, self.plan(plan_only=plan_only), chosen, resolver)
        job.progress.connect(self._on_progress, Qt.QueuedConnection)
        job.failed.connect(self._on_failed, Qt.QueuedConnection)
        job.book_finished.connect(self._book_finished, Qt.QueuedConnection)
        job.finished.connect(self.show_results, Qt.QueuedConnection)
        self.busy_changed.emit(True)
        self.runner.start(job, on_done=self._idle)

    def _book_finished(self, index: int, book: BookItem) -> None:
        chosen = [item for item in self.books if item.chosen]
        if index < len(chosen):
            original = chosen[index]
            for field in ("status", "fixed", "kept", "issues", "output", "report_text",
                          "categories", "error", "title", "author", "summary"):
                setattr(original, field, getattr(book, field))
        if hasattr(self, "progress"):
            self.progress.setValue(index + 1)

    def show_results(self, outcome: BatchOutcome) -> None:
        self.outcome = outcome
        by_source = {book.source: book for book in outcome.books}
        for index, book in enumerate(self.books):
            fresh = by_source.get(book.source)
            if fresh is not None:
                self.books[index] = fresh
        self._go(Stage.RESULTS)
        self.header.retitle(
            tr("shell.rebuild.title.results"),
            tr("shell.rebuild.subtitle.results", count=outcome.written),
        )
        self.body.addWidget(self._banner(outcome))

        columns = QHBoxLayout()
        columns.setSpacing(CARD_GAP)
        results = Card(tr("shell.results.list"), tr("shell.results.list.body"), glyph="book",
                       tokens=self.tokens)
        for book in outcome.books:
            row = BookRow(book, self.tokens, results=True)
            row.opened.connect(self._select_book)
            results.body.addWidget(row)
        results.body.addStretch(1)

        self._changes_card = Card(tr("shell.results.changes"), tr("shell.results.changes.body"),
                                  glyph="text", tokens=self.tokens)
        self._changes_body = QVBoxLayout()
        self._changes_card.body.addLayout(self._changes_body)
        report_button = button(tr("shell.results.report"), kind="ghost", glyph="inspect",
                               tokens=self.tokens, tip=tr("shell.results.report.body"))
        report_button.clicked.connect(self._show_report)
        self._changes_card.body.addWidget(report_button)
        results.body.addWidget(self._changes_card)
        columns.addWidget(results, 2)
        columns.addWidget(self._next_card(outcome), 1)
        self.body.addLayout(columns, 1)

        first = next((book for book in outcome.books if book.status.wrote_a_file), None)
        self._select_book(first or (outcome.books[0] if outcome.books else None))
        self.finished.emit(outcome)

    def _banner(self, outcome: BatchOutcome) -> QFrame:
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
        row = QHBoxLayout(banner)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(14)
        mark = QLabel()
        mark.setPixmap(icons.icon(glyph, colour).pixmap(26, 26))
        row.addWidget(mark, 0, Qt.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(3)
        words.addWidget(label(tr(f"shell.results.banner.{name}"), "cardTitle"))
        words.addWidget(label(tr(f"shell.results.banner.{name}.body"), "cardSubtitle"))
        row.addLayout(words, 2)
        for value, caption, role_name, mark_name in (
            (outcome.written, tr("shell.results.metric.done"), "success", "check"),
            (outcome.fixed, tr("shell.results.metric.fixed"), "accent", "rebuild"),
            (outcome.attention, tr("shell.results.metric.attention"), "warning", "warning"),
        ):
            row.addWidget(MetricCard(str(value), caption, self.tokens, role_name, mark_name), 1)
        if outcome.failed:
            row.addWidget(
                MetricCard(str(outcome.failed), tr("shell.results.metric.failed"),
                           self.tokens, "danger", "error"),
                1,
            )
        banner.setAccessibleName(tr(f"shell.results.banner.{name}"))
        return banner

    def _next_card(self, outcome: BatchOutcome) -> Card:
        card = Card(tr("shell.results.next"), tr("shell.results.next.body"), glyph="chevron",
                    tokens=self.tokens)
        written = [book for book in outcome.books if book.output]
        open_folder = button(tr("shell.results.open.folder"), kind="primary", glyph="folder",
                             tokens=self.tokens)
        open_folder.setEnabled(bool(written))
        open_folder.clicked.connect(
            lambda: self.backend.reveal(written[0].output) if written else None
        )
        card.body.addWidget(open_folder)
        save = button(tr("shell.results.save"), glyph="save", tokens=self.tokens)
        save.clicked.connect(self._save_report)
        card.body.addWidget(save)
        save_all = button(tr("shell.results.save.batch"), glyph="save", tokens=self.tokens)
        save_all.clicked.connect(self._save_batch_report)
        card.body.addWidget(save_all)
        again = button(tr("shell.results.again"), glyph="plus", tokens=self.tokens)
        again.clicked.connect(self.show_files)
        card.body.addWidget(again)
        card.body.addSpacing(10)
        card.body.addWidget(label(tr("shell.results.files"), "cardTitle"))
        if written:
            card.body.addWidget(label(tr("shell.results.files.at"), "muted"))
            card.body.addWidget(label(str(written[0].output.parent), "cardSubtitle"))
            for book in written[:6]:
                card.body.addWidget(label(book.output.name, "muted"))
            card.body.addWidget(label(tr("shell.results.extension"), "muted"))
        else:
            card.body.addWidget(label(tr("shell.results.none"), "muted"))
        card.body.addStretch(1)
        return card

    def _select_book(self, book: "BookItem | None") -> None:
        self._selected = book
        if book is None or not hasattr(self, "_changes_body"):
            return
        clear_layout(self._changes_body)
        if not book.categories:
            self._changes_body.addWidget(label(tr("shell.changes.none"), "muted"))
            return
        row = QHBoxLayout()
        row.setSpacing(10)
        for category in book.categories[:3]:
            small = Card(category.title, glyph=category.icon, tokens=self.tokens)
            for line in category.lines:
                small.body.addWidget(label(f"✓  {line}", "cardSubtitle"))
            row.addWidget(small, 1)
        self._changes_body.addLayout(row)

    def _show_report(self) -> None:
        book = self._selected
        if book is None:
            return
        from PySide6.QtWidgets import QDialog, QPlainTextEdit

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("shell.results.report.title", title=book.title))
        dialog.resize(880, 620)
        stack = QVBoxLayout(dialog)
        view = QPlainTextEdit(book.report_text or tr("report.placeholder"))
        view.setReadOnly(True)
        stack.addWidget(view)
        close = button(tr("about.close"))
        close.clicked.connect(dialog.accept)
        stack.addWidget(close, alignment=Qt.AlignRight)
        dialog.exec()

    def _save_report(self) -> None:
        """One book's report, in the same JSON the old window wrote."""
        book = self._selected or next(
            (item for item in self.books if item.report_text), None
        )
        if book is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog.savereport"), f"{book.source.stem}.json",
            "JSON (*.json);;Tekst (*.txt)",
        )
        if path:
            self.backend.export_report(book, pathlib.Path(path))

    def _save_batch_report(self) -> None:
        """Every book of the run in one file (the old Ctrl+Shift+S)."""
        books = list(self.outcome.books) if self.outcome else []
        if not books:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog.savereport.batch"), "raport-zbiorczy.json", "JSON (*.json)"
        )
        if path:
            self.backend.export_batch(books, pathlib.Path(path))
