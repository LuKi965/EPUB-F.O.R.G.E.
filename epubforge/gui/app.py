"""PySide6 front end: drop books in, inspect what changed, write them out."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import resources, version_string, watermark
from ..pipeline import Status, rebuild_all
from ..policy import Policy
from ..quips import quip_for
from ..report import Level, Report, batch_to_json
from .. import rules
from ..validate import find_epubcheck, validate
from . import theme
from .about import AboutDialog
from .tabs import CorpusPanel, DiagnosticsPanel, LibraryPanel
from .strings import LANGUAGES, language, set_language, tr

LEVEL_KEYS = {
    Level.FIX: "level.fix",
    Level.PRESERVED: "level.preserved",
    Level.WARN: "level.warn",
    Level.ERROR: "level.error",
    Level.INFO: "level.info",
}

STATUS_KEYS = {
    "queued": "status.queued",
    "working": "status.working",
    "done": "status.done",
    "issues": "status.issues",
    "failed": "status.failed",
    "blocked": "status.blocked",
}


class Worker(QObject):
    """Runs the rebuild off the UI thread."""

    progress = Signal(int, str)
    #: Emitted when the rebuild is done and the validator takes over. Without
    #: it the window says "rebuilding" for the seconds a JVM needs to start,
    #: which is the longest part of the job and looked like a freeze.
    validating = Signal(int, str)
    finished_one = Signal(int, object)
    finished_all = Signal()

    def __init__(
        self,
        jobs: list[tuple[str, str]],
        policy: Policy,
        run_check: bool,
        resolver=None,
    ):
        super().__init__()
        self._jobs = jobs
        self._policy = policy
        self._run_check = run_check
        #: Who the rebuild asks when it cannot decide — see `gui/ask.py`. It
        #: belongs to the GUI thread and is called from this one, which is the
        #: whole reason it is an object with a blocking signal rather than a
        #: function.
        self._resolver = resolver
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        for index, (source, destination) in enumerate(self._jobs):
            if self._cancelled:
                break
            self.progress.emit(index, os.path.basename(source))
            try:
                # Every rendition, each into its own file. For a book with one
                # — which is every book but a handful — this is exactly what
                # `rebuild` did, and the list has one entry.
                produced = rebuild_all(
                    source, destination, self._policy, resolver=self._resolver
                )
                result = produced[0]
                if self._run_check:
                    for one in produced:
                        if one.output_path:
                            self.validating.emit(index, os.path.basename(source))
                            validate(
                                one.output_path,
                                one.report,
                                content_untouched=not self._policy.rewrite_content,
                            )
                if len(produced) > 1:
                    # The window shows one row per source, so the siblings would
                    # otherwise be written and never mentioned.
                    result.report.add(
                        "package",
                        Level.INFO,
                        "package.renditions-written",
                        values={
                            "count": len(produced),
                            "names": ", ".join(
                                os.path.basename(one.output_path or "—") for one in produced
                            ),
                        },
                    )
            except Exception as exc:  # noqa: BLE001 - surfaced in the UI
                report = Report(source=source, output=destination)
                report.add(
                    "gui",
                    Level.ERROR,
                    "gui.unexpected-failure",
                    values={"error": f'{type(exc).__name__}: {exc}'},
                )
                from ..pipeline import Result

                result = Result(report, None, None)
            self.finished_one.emit(index, result)
        self.finished_all.emit()


def settings() -> QSettings:
    return QSettings("EPUB-Forge", "EPUB-Forge")


class MainWindow(QMainWindow):
    def __init__(self, palette: theme.Palette | None = None, initial_files: list[str] | None = None):
        super().__init__()
        #: Set when the language changes; run() rebuilds the window so every
        #: label is retranslated, carrying the queue across.
        self.restart_requested = False
        self.palette_colors = palette or theme.LIGHT
        self.setWindowTitle(tr("window.title", version=version_string()))
        # A fixed 1180×760 is a comfortable size on the machine it was written
        # on and an unusable one on a 1366×768 laptop, where it opens taller
        # than the screen. Ask for four fifths of the available desktop instead,
        # capped so it does not sprawl on a large monitor, and set a floor low
        # enough that the layout still works at the bottom of that range.
        self.setMinimumSize(880, 560)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(1280, int(available.width() * 0.8)),
                min(860, int(available.height() * 0.85)),
            )
        else:  # pragma: no cover - only when Qt reports no screen at all
            self.resize(1100, 720)
        self.setAcceptDrops(True)

        self._sources: list[str] = []
        self._results: dict[int, object] = {}
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._epubcheck = find_epubcheck() is not None

        self._build_ui()
        self._build_menu()
        if initial_files:
            self._add(initial_files)

    # ---------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_rebuild_tab(), tr("tab.rebuild"))
        self.tabs.addTab(LibraryPanel(self.palette_colors), tr("tab.library"))
        self.tabs.addTab(CorpusPanel(self.palette_colors), tr("tab.corpus"))
        self.tabs.addTab(DiagnosticsPanel(self.palette_colors), tr("tab.diagnostics"))
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)
        self._tab_changed(0)

    def _tab_changed(self, index: int) -> None:
        """The status line belongs to the tab, not to the window.

        "Drop EPUB files anywhere in this window" is good advice on the rebuild
        tab and simply untrue on the other two, which take a folder.
        """
        if index == 0:
            hint = tr("status.hint")
            if not self._epubcheck:
                hint = f"{hint}   ·   {tr('status.hint.nocheck')}"
        else:
            hint = tr("library.intro") if index == 1 else tr("corpus.intro")
        self.statusBar().showMessage(hint)

    def _build_rebuild_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(10)

        layout.addWidget(self._build_source_row())

        # Vertical first: the queue and its report belong together, and giving
        # the options their own column at every width is what left a third of
        # the window empty on the screenshot that started this.
        work = QSplitter(Qt.Vertical)
        work.addWidget(self._build_table())
        work.addWidget(self._build_report_view())
        work.setStretchFactor(0, 3)
        work.setStretchFactor(1, 2)
        work.setChildrenCollapsible(False)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(work)
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, stretch=1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        return page

    def _build_report_view(self) -> QWidget:
        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setFont(QFont("Cascadia Mono, Consolas, monospace", 9))
        self.report_view.setPlaceholderText(tr("report.placeholder"))
        self.report_view.setMinimumHeight(120)
        return self.report_view

    def _build_source_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        add = QPushButton(tr("toolbar.add"))
        add.setToolTip(tr("toolbar.add.tip"))
        add.clicked.connect(self._choose_files)
        layout.addWidget(add)

        clear = QPushButton(tr("toolbar.clear"))
        clear.setToolTip(tr("toolbar.clear.tip"))
        clear.clicked.connect(self._clear)
        layout.addWidget(clear)

        layout.addSpacing(16)
        output_label = QLabel(tr("toolbar.output"))
        output_label.setObjectName("sectionLabel")
        layout.addWidget(output_label)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText(tr("toolbar.output.placeholder"))
        self.output_edit.setToolTip(tr("toolbar.output.tip"))
        layout.addWidget(self.output_edit, stretch=1)

        browse = QPushButton(tr("toolbar.browse"))
        browse.setToolTip(tr("toolbar.browse.tip"))
        browse.clicked.connect(self._choose_output)
        layout.addWidget(browse)
        return row

    def _build_table(self) -> QWidget:
        self.table = QTableWidget(0, 5)
        headers = [
            (tr("table.book"), None),
            (tr("table.status"), None),
            (tr("table.fixed"), tr("table.fixed.tip")),
            (tr("table.kept"), tr("table.kept.tip")),
            (tr("table.issues"), tr("table.issues.tip")),
        ]
        self.table.setHorizontalHeaderLabels([label for label, _ in headers])
        for column, (_, tip) in enumerate(headers):
            if tip:
                self.table.horizontalHeaderItem(column).setToolTip(tip)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_selected_report)
        return self.table

    def _build_side_panel(self) -> QWidget:
        """The options, in a column that scrolls rather than being cut off.

        Three stacked cards plus a button need more height than a 768-pixel
        laptop has once the title bar, the tab strip and the status bar are
        taken out. Without the scroll area the bottom card simply vanishes, and
        the run button with it.
        """
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)

        layout.addWidget(self._build_policy_box())
        layout.addWidget(self._build_compat_box())
        layout.addWidget(self._build_metadata_box())
        layout.addStretch(1)

        scroller = QScrollArea()
        scroller.setWidget(inner)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QScrollArea.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(scroller, stretch=1)

        self.run_button = QPushButton(tr("action.run"))
        self.run_button.setObjectName("primary")
        self.run_button.setToolTip(tr("action.run.tip"))
        self.run_button.setMinimumHeight(42)
        self.run_button.clicked.connect(self._run)
        column.addWidget(self.run_button)

        # Wide enough for the longest option label, narrow enough to leave the
        # queue the majority of any window.
        panel.setMinimumWidth(330)
        panel.setMaximumWidth(460)
        return panel

    def _build_policy_box(self) -> QGroupBox:
        box = QGroupBox(tr("policy.group"))
        layout = QVBoxLayout(box)
        layout.setSpacing(7)

        label = QLabel(tr("policy.mode.label"))
        label.setObjectName("sectionLabel")
        label.setWordWrap(True)
        layout.addWidget(label)

        self.mode_combo = QComboBox()
        self.mode_combo.setToolTip(tr("policy.mode.tip"))
        modes = (
            ("preserve", "policy.mode.preserve"),
            ("strict", "policy.mode.strict"),
            ("minimal", "policy.mode.minimal"),
        )
        for index, (value, key) in enumerate(modes):
            self.mode_combo.addItem(tr(key), value)
            # Per-item tooltips let the consequences of each mode be read before
            # committing to one, which is the whole point of the choice.
            self.mode_combo.setItemData(index, tr(f"{key}.tip"), Qt.ToolTipRole)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        layout.addWidget(self.mode_combo)

        self.ncx_check = self._checkbox(layout, "policy.ncx", checked=True)
        self.orphans_check = self._checkbox(layout, "policy.orphans", checked=False)
        # The last thing in the program that deleted a file by name. It now
        # proves the book does not use it first — and it is a tick all the
        # same, because the standing rule has no exception for obvious cases.
        self.junk_check = self._checkbox(layout, "policy.junk", checked=True)
        self.layout_check = self._checkbox(layout, "policy.layout", checked=True)
        self.scripts_check = self._checkbox(layout, "policy.scripts", checked=False)
        # Ticked by "force the standard" and untickable there all the same.
        # The owner asked for this as a standing rule rather than about this
        # feature: whatever the application ever deletes must be optional to
        # untick, or asked about first.
        self.dead_check = self._checkbox(layout, "policy.dead", checked=False)
        self.typography_check = self._checkbox(layout, "policy.typography", checked=False)

        watermark_label = QLabel(tr("policy.watermark.label"))
        watermark_label.setObjectName("sectionLabel")
        watermark_label.setWordWrap(True)
        watermark_label.setToolTip(tr("policy.watermark.tip"))
        layout.addWidget(watermark_label)
        self.watermark_label = watermark_label

        self.watermark_combo = QComboBox()
        self.watermark_combo.setToolTip(tr("policy.watermark.tip"))
        for index, value in enumerate(watermark.MODES):
            key = f"policy.watermark.{value}"
            self.watermark_combo.addItem(tr(key), value)
            # Each option removes a different amount, and one of them removes
            # the token altogether — nobody should have to guess which.
            self.watermark_combo.setItemData(index, tr(f"{key}.tip"), Qt.ToolTipRole)
        self.watermark_combo.setCurrentIndex(watermark.MODES.index(Policy().watermarks))
        layout.addWidget(self.watermark_combo)

        # Two more things this program changes about a book, and the owner's
        # standing rule says a person gets the last word on each: fonts whose
        # obfuscation is undone, and images converted out of a format EPUB 3
        # does not require. Both were on and neither was reachable from here,
        # which for somebody who runs the Windows build means they were not
        # switches at all.
        self.fonts_check = self._checkbox(layout, "policy.fonts", checked=True)
        self.images_check = self._checkbox(layout, "policy.images", checked=True)

        self.validate_check = self._checkbox(
            layout, "policy.validate", checked=self._epubcheck, enabled=self._epubcheck
        )
        if not self._epubcheck:
            self.validate_check.setToolTip(tr("policy.validate.missing"))

        # The escape hatch for the gate added in 0.2.20. A source that cannot be
        # read in full now stops the rebuild, which is right — and until this
        # box existed the only way past it was a command-line flag, on a program
        # whose owner uses the window. A refusal with no visible way through is
        # not a decision offered to anybody.
        self.incomplete_check = self._checkbox(
            layout, "policy.incomplete", checked=False
        )

        # F-010's other half. A reference whose anchor does not exist cannot be
        # repaired from the file, and the program refuses to invent an answer —
        # so the only way one of these is ever *resolved* rather than reported
        # is a person looking at it. On by default: this is a window, somebody
        # is here, and asking is the point rather than the fallback.
        self.ask_check = self._checkbox(layout, "policy.ask", checked=True)
        # Two builds of one book, byte for byte the same. Off by default,
        # because the honest modification date of a file produced now is now.
        self.reproducible_check = self._checkbox(layout, "policy.reproducible", checked=False)

        self._mode_changed()
        return box

    def _checkbox(self, layout, key: str, *, checked: bool, enabled: bool = True) -> QCheckBox:
        box = QCheckBox(tr(key))
        box.setToolTip(tr(f"{key}.tip"))
        box.setChecked(checked)
        box.setEnabled(enabled)
        layout.addWidget(box)
        return box

    def _build_compat_box(self) -> QGroupBox:
        """Opt-in concessions to particular devices — none of them on by default."""
        box = QGroupBox(tr("compat.group"))
        layout = QVBoxLayout(box)
        layout.setSpacing(7)

        hint = QLabel(tr("compat.hint"))
        hint.setObjectName("sectionLabel")
        hint.setWordWrap(True)
        hint.setToolTip(tr("compat.hint.tip"))
        layout.addWidget(hint)

        self.compat_checks: dict[str, QCheckBox] = {}
        for profile in ("kindle", "kobo", "apple", "legacy"):
            self.compat_checks[profile] = self._checkbox(
                layout, f"compat.{profile}", checked=False
            )

        # Stated in the panel rather than only in a tooltip: it is the one
        # consequence of ticking these boxes that outlives the run.
        note = QLabel(tr("compat.note"))
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {self.palette_colors.text_muted}; font-size: 8.5pt; font-style: italic;"
        )
        layout.addWidget(note)
        return box

    def _build_metadata_box(self) -> QGroupBox:
        box = QGroupBox(tr("meta.group"))
        layout = QVBoxLayout(box)
        layout.setSpacing(4)
        self.title_edit = self._field(layout, "meta.title")
        self.author_edit = self._field(layout, "meta.author")
        self.language_edit = self._field(layout, "meta.language")
        return box

    def _field(self, layout, key: str) -> QLineEdit:
        label = QLabel(tr(key))
        label.setObjectName("fieldLabel")
        label.setToolTip(tr(f"{key}.tip"))
        layout.addWidget(label)
        edit = QLineEdit()
        edit.setPlaceholderText(tr("meta.placeholder"))
        edit.setToolTip(tr(f"{key}.tip"))
        layout.addWidget(edit)
        return edit

    def _mode_changed(self) -> None:
        """Minimal mode regenerates only the container, so content knobs do nothing."""
        content_mode = self.mode_combo.currentData() != "minimal"
        for widget in (self.orphans_check, self.layout_check, self.scripts_check,
                       self.dead_check, self.typography_check,
                       self.watermark_combo, self.watermark_label):
            widget.setEnabled(content_mode)
        # Follows the mode rather than overriding it: "force the standard"
        # means tidiness wins, so it arrives ticked — and stays untickable.
        self.dead_check.setChecked(
            content_mode and self.mode_combo.currentData() == "strict"
        )

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(tr("menu.file"))
        for label, slot, shortcut in (
            (tr("toolbar.add"), self._choose_files, "Ctrl+O"),
            (tr("action.save"), self._save_report, "Ctrl+S"),
            (tr("action.save.batch"), self._save_batch_report, "Ctrl+Shift+S"),
            (tr("menu.quit"), self.close, "Ctrl+Q"),
        ):
            action = QAction(label, self)
            action.triggered.connect(slot)
            action.setShortcut(shortcut)
            file_menu.addAction(action)

        settings_menu = self.menuBar().addMenu(tr("menu.settings"))
        language_menu = settings_menu.addMenu(tr("menu.language"))
        group = QActionGroup(self)
        group.setExclusive(True)
        current = settings().value("language", "pl")
        for code in LANGUAGES:
            action = QAction(tr(f"language.{code}"), self, checkable=True)
            action.setChecked(code == current)
            action.triggered.connect(lambda _checked=False, c=code: self._change_language(c))
            group.addAction(action)
            language_menu.addAction(action)

        help_menu = self.menuBar().addMenu(tr("menu.help"))
        about = QAction(tr("menu.about"), self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _change_language(self, code: str) -> None:
        if code == settings().value("language", "pl"):
            return
        settings().setValue("language", code)
        set_language(code)
        self.restart_requested = True
        self.close()

    def _show_about(self) -> None:
        AboutDialog(self, self.palette_colors).exec()

    # ------------------------------------------------------------ file input
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self._add(
            [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.toLocalFile().lower().endswith(".epub")
            ]
        )

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("dialog.selectfiles"), "", tr("dialog.filter")
        )
        self._add(files)

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, tr("dialog.selectfolder"))
        if directory:
            self.output_edit.setText(directory)

    def _add(self, files: list[str]) -> None:
        for path in files:
            if path and path not in self._sources:
                self._sources.append(path)
                row = self.table.rowCount()
                self.table.insertRow(row)
                item = QTableWidgetItem(os.path.basename(path))
                item.setToolTip(path)
                self.table.setItem(row, 0, item)
                self._set_status(row, "queued")
                for column in (2, 3, 4):
                    self.table.setItem(row, column, QTableWidgetItem("—"))
        self.statusBar().showMessage(tr("status.queued.count", count=len(self._sources)))

    def _clear(self) -> None:
        self._sources.clear()
        self._results.clear()
        self.table.setRowCount(0)
        self.report_view.clear()

    def _set_status(self, row: int, status: str) -> None:
        item = QTableWidgetItem(tr(STATUS_KEYS[status]))
        colors = {
            "queued": self.palette_colors.text_muted,
            "working": self.palette_colors.accent,
            "done": self.palette_colors.fix,
            "issues": self.palette_colors.warn,
            "failed": self.palette_colors.error,
        }
        item.setForeground(QColor(colors[status]))
        self.table.setItem(row, 1, item)

    # ------------------------------------------------------------- execution
    def _policy(self) -> Policy:
        policy = Policy.preset(self.mode_combo.currentData())
        policy.write_ncx = self.ncx_check.isChecked()
        policy.compat_profiles = tuple(
            name for name, box in self.compat_checks.items() if box.isChecked()
        )
        if self.mode_combo.currentData() != "minimal":
            policy.drop_orphans = self.orphans_check.isChecked()
            policy.remove_junk = self.junk_check.isChecked()
            policy.reorganize_files = self.layout_check.isChecked()
            policy.strip_scripts = self.scripts_check.isChecked()
            policy.remove_dead = self.dead_check.isChecked()
            policy.watermarks = self.watermark_combo.currentData()
            policy.typography = self.typography_check.isChecked()
            policy.transcode_images = self.images_check.isChecked()
        policy.deobfuscate_fonts = self.fonts_check.isChecked()
        policy.allow_incomplete = self.incomplete_check.isChecked()
        policy.reproducible = self.reproducible_check.isChecked()
        for key, edit in (
            ("title", self.title_edit),
            ("author", self.author_edit),
            ("language", self.language_edit),
        ):
            value = edit.text().strip()
            if value:
                policy.metadata_overrides[key] = value
                if key == "language":
                    policy.default_language = value
        return policy

    def _ask_resolver(self):
        """Somebody for the rebuild to ask, or nobody, as the box says.

        Built fresh for each run and parented to the window, so it lives in the
        GUI thread — which is the requirement the whole arrangement exists to
        satisfy. `None` means the rebuild behaves exactly as it does in a batch:
        it changes nothing it cannot justify, and reports what it left.
        """
        if not self.ask_check.isChecked():
            return None
        from .ask import Ask

        self._resolver = Ask(self)
        return self._resolver

    def _run(self) -> None:
        if not self._sources:
            QMessageBox.information(self, tr("dialog.nothing.title"), tr("dialog.nothing.body"))
            return
        if self._thread is not None:
            return

        output_dir = self.output_edit.text().strip()
        jobs: list[tuple[str, str]] = []
        for source in self._sources:
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                destination = os.path.join(output_dir, os.path.basename(source))
            else:
                destination = f"{os.path.splitext(source)[0]}.forged.epub"
            if os.path.abspath(destination) == os.path.abspath(source):
                QMessageBox.warning(
                    self,
                    tr("dialog.overwrite.title"),
                    tr("dialog.overwrite.body", name=os.path.basename(source)),
                )
                return
            jobs.append((source, destination))

        self.progress.setVisible(True)
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.run_button.setEnabled(False)

        self._thread = QThread()
        self._worker = Worker(
            jobs,
            self._policy(),
            self.validate_check.isChecked(),
            self._ask_resolver(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.validating.connect(self._on_validating)
        self._worker.finished_one.connect(self._on_one_finished)
        self._worker.finished_all.connect(self._on_all_finished)
        self._thread.start()

    def _on_progress(self, index: int, name: str) -> None:
        self._set_status(index, "working")
        self.statusBar().showMessage(tr("status.working", name=name))

    def _on_validating(self, index: int, name: str) -> None:
        self.statusBar().showMessage(tr("status.validating", name=name))

    def _on_one_finished(self, index: int, result) -> None:
        self._results[index] = result
        report = result.report

        # From the status the pipeline reports, not from whether a file appeared.
        # Those two used to be the same question and were not the same answer:
        # a stage could crash and the file appeared anyway.
        status = getattr(result, "status", None)
        if status is not None and not status.wrote_a_file:
            self._set_status(index, "blocked" if status is Status.BLOCKED else "failed")
        elif report.count(Level.ERROR):
            self._set_status(index, "issues")
        else:
            self._set_status(index, "done")

        counts = (
            report.count(Level.FIX),
            report.count(Level.PRESERVED),
            report.count(Level.ERROR) + report.count(Level.WARN),
        )
        for column, value in enumerate(counts, start=2):
            self.table.setItem(index, column, QTableWidgetItem(str(value)))
        self.progress.setValue(index + 1)
        if self.table.currentRow() in (-1, index):
            self.table.selectRow(index)
            # Drawing the report was left to `itemSelectionChanged`, and that
            # signal does not fire when the row is *already* selected — which is
            # exactly the case with one book in the queue. The result was a
            # blank report panel until a second book was added and the user
            # clicked between the two.
            self._show_selected_report()

    def _on_all_finished(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self.run_button.setEnabled(True)
        self.progress.setVisible(False)
        failures = sum(1 for r in self._results.values() if r.output_path is None)
        total = len(self._results)
        self.statusBar().showMessage(
            tr("status.finished.failures", count=total, failures=failures)
            if failures
            else tr("status.finished", count=total)
        )

    # ---------------------------------------------------------------- output
    def _show_selected_report(self) -> None:
        row = self.table.currentRow()
        result = self._results.get(row)
        if result is None:
            self.report_view.clear()
            return

        colors = {
            Level.FIX: self.palette_colors.fix,
            Level.PRESERVED: self.palette_colors.preserved,
            Level.WARN: self.palette_colors.warn,
            Level.ERROR: self.palette_colors.error,
            Level.INFO: self.palette_colors.info,
        }
        default = QColor(self.palette_colors.text)

        self.report_view.clear()
        self.report_view.setTextColor(default)
        self.report_view.append(f"{tr('report.source')}: {result.report.source}")
        self.report_view.append(
            f"{tr('report.output')}: {result.output_path or tr('report.notwritten')}"
        )
        remark = quip_for(result.report, language())
        if remark:
            self.report_view.setTextColor(QColor(self.palette_colors.text_muted))
            self.report_view.append(f"— {remark}")
        self.report_view.append("")

        width = max(len(tr(key)) for key in LEVEL_KEYS.values())
        for finding in result.report.sorted_findings():
            self.report_view.setTextColor(QColor(colors[finding.level]))
            label = tr(LEVEL_KEYS[finding.level]).rjust(width)
            where = f"  [{finding.location}]" if finding.location else ""
            # The window has been bilingual and the report has not, because the
            # English sentence *was* the identity of a finding. With the
            # catalogue it is not, so the headline follows the interface. The
            # original line stays beneath it only where the translation cannot
            # state the specifics itself, which is what the templates remove.
            headline, _, original = result.report.headline(finding, language()).partition("\n")
            self.report_view.append(f"{label}  {finding.stage}: {headline}{where}")
            if original:
                self.report_view.setTextColor(QColor(self.palette_colors.text_muted))
                self.report_view.append(f"{'':>{width + 2}}{finding.message}")
                self.report_view.setTextColor(QColor(colors[finding.level]))
            detail = result.report.detail_for(finding, language())
            if detail:
                self.report_view.append(f"{'':>{width + 2}}{detail}")
        self.report_view.setTextColor(default)
        self.report_view.moveCursor(QTextCursor.MoveOperation.Start)

    def _save_report(self) -> None:
        row = self.table.currentRow()
        result = self._results.get(row)
        if result is None:
            QMessageBox.information(self, tr("dialog.noreport.title"), tr("dialog.noreport.body"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog.savereport"), "raport.json", "JSON (*.json)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(result.report.to_json(language()))

    def _save_batch_report(self) -> None:
        """Every book in the queue, in one file.

        Saving one report at a time is fine for one book and unusable for
        thirty: the question a batch raises is which of them needs attention,
        and opening thirty files to answer it is slower than not asking.
        """
        if not self._results:
            QMessageBox.information(self, tr("dialog.noreport.title"), tr("dialog.noreport.body"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog.savereport.batch"), "raport-zbiorczy.json", "JSON (*.json)"
        )
        if path:
            reports = [self._results[row].report for row in sorted(self._results)]
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(batch_to_json(reports, language()))
            self.statusBar().showMessage(
                tr("status.batch.saved", count=len(reports))
            )


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Must happen before the first window exists, or the taskbar has already
    # decided which icon to group this process under.
    resources.set_windows_app_id()

    app = QApplication(argv)
    app.setApplicationName("EPUB F.O.R.G.E.")
    # Not setApplicationDisplayName: Qt appends it to every window title, and
    # the result read "EPUB F.O.R.G.E. 0.1.1 (pre-alpha) - EPUB F.O.R.G.E.".
    app.setStyle("Fusion")

    icon_path = resources.app_icon()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    set_language(settings().value("language", "pl"))

    palette = theme.active_palette(app)
    app.setStyleSheet(theme.stylesheet(palette))

    # Paths arrive this way from the installer's "Rebuild with EPUB-Forge"
    # shell verb and from dragging files onto the executable.
    queued = [
        path for path in argv[1:]
        if path.lower().endswith(".epub") and os.path.isfile(path)
    ]

    # Retranslating an imperatively built UI in place means tracking every
    # widget; rebuilding the window is simpler and keeps the queue.
    while True:
        window = MainWindow(palette, initial_files=queued)
        window.show()
        app.exec()
        if not window.restart_requested:
            return 0
        queued = list(window._sources)
