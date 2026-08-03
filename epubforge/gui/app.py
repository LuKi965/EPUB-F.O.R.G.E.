"""PySide6 front end: drop books in, inspect what changed, write them out."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont, QTextCursor
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
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..pipeline import rebuild
from ..policy import Policy
from ..report import Level, Report
from ..validate import find_epubcheck, validate
from . import theme
from .strings import tr

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
}


class Worker(QObject):
    """Runs the rebuild off the UI thread."""

    progress = Signal(int, str)
    finished_one = Signal(int, object)
    finished_all = Signal()

    def __init__(self, jobs: list[tuple[str, str]], policy: Policy, run_check: bool):
        super().__init__()
        self._jobs = jobs
        self._policy = policy
        self._run_check = run_check
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        for index, (source, destination) in enumerate(self._jobs):
            if self._cancelled:
                break
            self.progress.emit(index, os.path.basename(source))
            try:
                result = rebuild(source, destination, self._policy)
                if self._run_check and result.output_path:
                    validate(result.output_path, result.report)
            except Exception as exc:  # noqa: BLE001 - surfaced in the UI
                report = Report(source=source, output=destination)
                report.add("gui", Level.ERROR, f"unexpected failure: {type(exc).__name__}: {exc}")
                from ..pipeline import Result

                result = Result(report, None, None)
            self.finished_one.emit(index, result)
        self.finished_all.emit()


class MainWindow(QMainWindow):
    def __init__(self, palette: theme.Palette | None = None):
        super().__init__()
        self.palette_colors = palette or theme.LIGHT
        self.setWindowTitle(tr("window.title", version=__version__))
        self.resize(1180, 760)
        self.setAcceptDrops(True)

        self._sources: list[str] = []
        self._results: dict[int, object] = {}
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._epubcheck = find_epubcheck() is not None

        self._build_ui()
        self._build_menu()

    # ---------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        layout.addWidget(self._build_source_row())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([720, 440])
        layout.addWidget(splitter, stretch=3)

        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setFont(QFont("Cascadia Mono, Consolas, monospace", 9))
        self.report_view.setPlaceholderText(tr("report.placeholder"))
        layout.addWidget(self.report_view, stretch=2)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.setCentralWidget(central)
        hint = tr("status.hint")
        if not self._epubcheck:
            hint = f"{hint}   ·   {tr('status.hint.nocheck')}"
        self.statusBar().showMessage(hint)

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
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._build_policy_box())
        layout.addWidget(self._build_metadata_box())

        self.run_button = QPushButton(tr("action.run"))
        self.run_button.setObjectName("primary")
        self.run_button.setToolTip(tr("action.run.tip"))
        self.run_button.setMinimumHeight(42)
        self.run_button.clicked.connect(self._run)
        layout.addWidget(self.run_button)

        layout.addStretch(1)
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
        self.orphans_check = self._checkbox(layout, "policy.orphans", checked=True)
        self.layout_check = self._checkbox(layout, "policy.layout", checked=True)
        self.scripts_check = self._checkbox(layout, "policy.scripts", checked=False)
        self.validate_check = self._checkbox(
            layout, "policy.validate", checked=self._epubcheck, enabled=self._epubcheck
        )
        if not self._epubcheck:
            self.validate_check.setToolTip(tr("policy.validate.missing"))

        self._mode_changed()
        return box

    def _checkbox(self, layout, key: str, *, checked: bool, enabled: bool = True) -> QCheckBox:
        box = QCheckBox(tr(key))
        box.setToolTip(tr(f"{key}.tip"))
        box.setChecked(checked)
        box.setEnabled(enabled)
        layout.addWidget(box)
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
        for widget in (self.orphans_check, self.layout_check, self.scripts_check):
            widget.setEnabled(content_mode)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(tr("menu.file"))
        for label, slot, shortcut in (
            (tr("toolbar.add"), self._choose_files, "Ctrl+O"),
            (tr("action.save"), self._save_report, "Ctrl+S"),
            (tr("menu.quit"), self.close, "Ctrl+Q"),
        ):
            action = QAction(label, self)
            action.triggered.connect(slot)
            action.setShortcut(shortcut)
            file_menu.addAction(action)

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
        if self.mode_combo.currentData() != "minimal":
            policy.drop_orphans = self.orphans_check.isChecked()
            policy.reorganize_files = self.layout_check.isChecked()
            policy.strip_scripts = self.scripts_check.isChecked()
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
        self._worker = Worker(jobs, self._policy(), self.validate_check.isChecked())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_one.connect(self._on_one_finished)
        self._worker.finished_all.connect(self._on_all_finished)
        self._thread.start()

    def _on_progress(self, index: int, name: str) -> None:
        self._set_status(index, "working")
        self.statusBar().showMessage(tr("status.working", name=name))

    def _on_one_finished(self, index: int, result) -> None:
        self._results[index] = result
        report = result.report

        if result.output_path is None:
            self._set_status(index, "failed")
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
            f"{tr('report.output')}: {result.output_path or tr('report.notwritten')}\n"
        )

        width = max(len(tr(key)) for key in LEVEL_KEYS.values())
        for finding in result.report.sorted_findings():
            self.report_view.setTextColor(QColor(colors[finding.level]))
            label = tr(LEVEL_KEYS[finding.level]).rjust(width)
            where = f"  [{finding.location}]" if finding.location else ""
            self.report_view.append(f"{label}  {finding.stage}: {finding.message}{where}")
            if finding.detail:
                self.report_view.append(f"{'':>{width + 2}}{finding.detail}")
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
                handle.write(result.report.to_json())


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("EPUB-Forge")
    app.setStyle("Fusion")

    palette = theme.active_palette(app)
    app.setStyleSheet(theme.stylesheet(palette))

    window = MainWindow(palette)
    # Paths arrive this way from the installer's "Rebuild with EPUB-Forge"
    # shell verb and from dragging files onto the executable.
    queued = [
        path for path in argv[1:]
        if path.lower().endswith(".epub") and os.path.isfile(path)
    ]
    if queued:
        window._add(queued)
    window.show()
    return app.exec()
