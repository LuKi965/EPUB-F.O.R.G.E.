"""PySide6 front end: drop books in, inspect what changed, write them out."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont
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

LEVEL_COLORS = {
    Level.ERROR: QColor("#c0392b"),
    Level.WARN: QColor("#b9770e"),
    Level.PRESERVED: QColor("#1f6f8b"),
    Level.FIX: QColor("#1e8449"),
    Level.INFO: QColor("#7f8c8d"),
}

STATUS_COLORS = {
    "queued": QColor("#7f8c8d"),
    "working": QColor("#2471a3"),
    "done": QColor("#1e8449"),
    "issues": QColor("#b9770e"),
    "failed": QColor("#c0392b"),
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
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"EPUB-Forge {__version__}")
        self.resize(1100, 720)
        self.setAcceptDrops(True)

        self._sources: list[str] = []
        self._results: dict[int, object] = {}
        self._thread: QThread | None = None
        self._worker: Worker | None = None

        self._build_ui()
        self._build_menu()

    # ---------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        layout.addWidget(self._build_source_row())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setFont(QFont("monospace"))
        self.report_view.setPlaceholderText("Select a book to see what the rebuild changed.")
        layout.addWidget(self.report_view, stretch=2)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.setCentralWidget(central)
        self.statusBar().showMessage(
            "Drop EPUB files anywhere in this window."
            + ("" if find_epubcheck() else "  ·  EPUBCheck not found — validation unavailable.")
        )

    def _build_source_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        add = QPushButton("Add books…")
        add.clicked.connect(self._choose_files)
        layout.addWidget(add)

        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)
        layout.addWidget(clear)

        layout.addSpacing(16)
        layout.addWidget(QLabel("Output folder:"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("leave empty to write next to each source file")
        layout.addWidget(self.output_edit, stretch=1)

        browse = QPushButton("Browse…")
        browse.clicked.connect(self._choose_output)
        layout.addWidget(browse)
        return row

    def _build_table(self) -> QWidget:
        self.table = QTableWidget(0, 5)
        # "Kept" makes deliberate deviations visible without opening the report;
        # a rebuild that fixed nothing but preserved something is not a no-op.
        self.table.setHorizontalHeaderLabels(["Book", "Status", "Fixed", "Kept", "Issues"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_selected_report)
        return self.table

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        options = QGroupBox("Rebuild policy")
        form = QVBoxLayout(options)

        form.addWidget(QLabel("When conformance and appearance conflict:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Preserve appearance, report deviations", "preserve")
        self.mode_combo.addItem("Enforce the standard, even if it changes rendering", "strict")
        self.mode_combo.addItem("Rebuild the container only, leave content alone", "minimal")
        form.addWidget(self.mode_combo)

        self.ncx_check = QCheckBox("Include a legacy NCX for older readers")
        self.ncx_check.setChecked(True)
        form.addWidget(self.ncx_check)

        self.orphans_check = QCheckBox("Remove files nothing references")
        self.orphans_check.setChecked(True)
        form.addWidget(self.orphans_check)

        self.layout_check = QCheckBox("Reorganise files into a typed folder layout")
        self.layout_check.setChecked(True)
        form.addWidget(self.layout_check)

        self.scripts_check = QCheckBox("Strip all scripting")
        form.addWidget(self.scripts_check)

        self.validate_check = QCheckBox("Verify the result with EPUBCheck")
        self.validate_check.setEnabled(find_epubcheck() is not None)
        self.validate_check.setChecked(find_epubcheck() is not None)
        form.addWidget(self.validate_check)

        layout.addWidget(options)

        overrides = QGroupBox("Metadata overrides (optional)")
        override_layout = QVBoxLayout(overrides)
        self.title_edit = self._labelled(override_layout, "Title")
        self.author_edit = self._labelled(override_layout, "Author")
        self.language_edit = self._labelled(override_layout, "Language (BCP 47)")
        layout.addWidget(overrides)

        self.run_button = QPushButton("Rebuild")
        self.run_button.setMinimumHeight(38)
        self.run_button.clicked.connect(self._run)
        layout.addWidget(self.run_button)

        layout.addStretch(1)
        return panel

    def _labelled(self, layout, label: str) -> QLineEdit:
        layout.addWidget(QLabel(label))
        edit = QLineEdit()
        edit.setPlaceholderText("keep what the book already has")
        layout.addWidget(edit)
        return edit

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        for text, slot, shortcut in (
            ("Add books…", self._choose_files, "Ctrl+O"),
            ("Save report…", self._save_report, "Ctrl+S"),
            ("Quit", self.close, "Ctrl+Q"),
        ):
            action = QAction(text, self)
            action.triggered.connect(slot)
            action.setShortcut(shortcut)
            file_menu.addAction(action)

    # ------------------------------------------------------------ file input
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        added = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile().lower().endswith(".epub")
        ]
        self._add(added)

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select EPUB files", "", "EPUB files (*.epub)")
        self._add(files)

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select output folder")
        if directory:
            self.output_edit.setText(directory)

    def _add(self, files: list[str]) -> None:
        for path in files:
            if path and path not in self._sources:
                self._sources.append(path)
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(os.path.basename(path)))
                self._set_status(row, "queued")
                for column in (2, 3, 4):
                    self.table.setItem(row, column, QTableWidgetItem("—"))
        self.statusBar().showMessage(f"{len(self._sources)} book(s) queued.")

    def _clear(self) -> None:
        self._sources.clear()
        self._results.clear()
        self.table.setRowCount(0)
        self.report_view.clear()

    def _set_status(self, row: int, status: str) -> None:
        item = QTableWidgetItem(status)
        item.setForeground(STATUS_COLORS.get(status, QColor("#000000")))
        self.table.setItem(row, 1, item)

    # ------------------------------------------------------------- execution
    def _policy(self) -> Policy:
        policy = Policy.preset(self.mode_combo.currentData())
        policy.write_ncx = self.ncx_check.isChecked()
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
            QMessageBox.information(self, "Nothing to do", "Add at least one EPUB file first.")
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
                    "Output would overwrite the source",
                    f"Choose a different output folder — {os.path.basename(source)} would be "
                    "overwritten in place.",
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
        self.statusBar().showMessage(f"Rebuilding {name}…")

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
        self.statusBar().showMessage(
            f"Finished {len(self._results)} book(s)"
            + (f" — {failures} could not be written." if failures else " — all written.")
        )

    # ---------------------------------------------------------------- output
    def _show_selected_report(self) -> None:
        row = self.table.currentRow()
        result = self._results.get(row)
        if result is None:
            self.report_view.clear()
            return

        lines = [f"source: {result.report.source}"]
        if result.output_path:
            lines.append(f"output: {result.output_path}")
        else:
            lines.append("output: NOT WRITTEN")
        lines.append("")

        self.report_view.clear()
        self.report_view.setTextColor(QColor("#000000"))
        self.report_view.append("\n".join(lines))
        for finding in result.report.sorted_findings():
            self.report_view.setTextColor(LEVEL_COLORS[finding.level])
            where = f"  [{finding.location}]" if finding.location else ""
            self.report_view.append(f"{finding.level.value:>9}  {finding.stage}: {finding.message}{where}")
            if finding.detail:
                self.report_view.append(f"{'':>11}{finding.detail}")
        self.report_view.setTextColor(QColor("#000000"))

    def _save_report(self) -> None:
        row = self.table.currentRow()
        result = self._results.get(row)
        if result is None:
            QMessageBox.information(self, "No report", "Rebuild a book first, then select it.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save report", "report.json", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(result.report.to_json())


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("EPUB-Forge")

    window = MainWindow()
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
