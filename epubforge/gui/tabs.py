"""The library and corpus panels.

Kept out of `app.py` because they are a different job from rebuilding a book:
these two read a whole shelf and answer a question about it, writing nothing
except a file the person explicitly asks for. Sharing the window is convenient;
sharing a module would just make both harder to read.
"""

from __future__ import annotations

import os
import pathlib

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .strings import tr


class Job(QObject):
    """Runs one long job off the UI thread and reports progress."""

    progress = Signal(int, int, str)
    finished = Signal(object, str)

    def __init__(self, work) -> None:
        super().__init__()
        self._work = work

    def run(self) -> None:
        try:
            self.finished.emit(self._work(self.progress.emit), "")
        except Exception as exc:  # noqa: BLE001 — surfaced in the panel
            self.finished.emit(None, f"{type(exc).__name__}: {exc}")


class Panel(QWidget):
    """Folder picker, a run button, a progress bar and an output area.

    All three long-running features have the same shape, so they share it
    rather than each inventing its own arrangement of the same four things.
    """

    def __init__(self, palette: theme.Palette) -> None:
        super().__init__()
        self.colors = palette
        self._thread: QThread | None = None
        self._job: Job | None = None
        self._payload: str = ""

        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(16, 14, 16, 14)
        self.layout_.setSpacing(12)

    # ------------------------------------------------------------- building
    def add_intro(self, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {self.colors.text_muted};")
        self.layout_.addWidget(label)

    def add_folder_row(self, label: str, placeholder: str = "") -> QLineEdit:
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)

        caption = QLabel(label)
        caption.setObjectName("fieldLabel")
        caption.setMinimumWidth(90)
        line.addWidget(caption)

        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        line.addWidget(edit, stretch=1)

        browse = QPushButton(tr("common.browse"))
        browse.clicked.connect(lambda: self._pick_into(edit))
        line.addWidget(browse)

        self.layout_.addWidget(row)
        return edit

    def _pick_into(self, edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("common.pickfolder"), edit.text())
        if folder:
            edit.setText(folder)

    def add_output(self, placeholder: str) -> QTextEdit:
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QTextEdit.NoWrap)
        self.output.setFont(QFont("Cascadia Mono, Consolas, monospace", 9))
        # Written as content rather than as a placeholder: a read-only QTextEdit
        # does not paint its placeholder under every style, and an empty black
        # rectangle tells nobody what to do next.
        self.output.setPlainText(placeholder)
        self.layout_.addWidget(self.output, stretch=1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.layout_.addWidget(self.progress)
        return self.output

    def separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {self.colors.border}; max-height: 1px;")
        return line

    # -------------------------------------------------------------- running
    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(self, work, buttons: list[QPushButton]) -> None:
        if self.busy:
            return
        for button in buttons:
            button.setEnabled(False)
        self._buttons = buttons
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.output.clear()

        self._thread = QThread()
        self._job = Job(work)
        self._job.moveToThread(self._thread)
        self._thread.started.connect(self._job.run)
        self._job.progress.connect(self._on_progress)
        self._job.finished.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, done: int, total: int, name: str) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        self.window().statusBar().showMessage(tr("common.working", name=name))

    def _on_finished(self, result, error: str) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._job = None
        self.progress.setVisible(False)
        for button in getattr(self, "_buttons", []):
            button.setEnabled(True)
        if error:
            self.output.setPlainText(error)
            self.window().statusBar().showMessage(error)
            return
        self.handle(result)

    def handle(self, result) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def save_payload(self, suggestion: str) -> None:
        if not self._payload:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("common.save"), suggestion, "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._payload)
            self.window().statusBar().showMessage(tr("common.saved", path=path))


class LibraryPanel(Panel):
    """Survey and inventory: two questions about a shelf, neither of them
    changing anything on it."""

    def __init__(self, palette: theme.Palette) -> None:
        super().__init__(palette)
        self.add_intro(tr("library.intro"))
        self.folder = self.add_folder_row(tr("common.folder"))

        mode = QLabel(tr("library.mode"))
        mode.setObjectName("sectionLabel")
        self.layout_.addWidget(mode)

        self.survey_choice = QRadioButton(tr("library.survey"))
        self.survey_choice.setToolTip(tr("library.survey.tip"))
        self.survey_choice.setChecked(True)
        self.layout_.addWidget(self.survey_choice)

        self.inventory_choice = QRadioButton(tr("library.inventory"))
        self.inventory_choice.setToolTip(tr("library.inventory.tip"))
        self.layout_.addWidget(self.inventory_choice)

        self.with_names = QCheckBox(tr("library.withnames"))
        self.with_names.setToolTip(tr("library.withnames.tip"))
        self.layout_.addWidget(self.with_names)

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.run_button = QPushButton(tr("common.run"))
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self._run)
        row.addWidget(self.run_button)
        self.save_button = QPushButton(tr("common.save"))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(lambda: self.save_payload(self._suggested_name()))
        row.addWidget(self.save_button)
        row.addStretch(1)
        self.layout_.addWidget(buttons)

        self.add_output(tr("library.empty"))

    def _suggested_name(self) -> str:
        return "przeglad.json" if self.survey_choice.isChecked() else "spis.json"

    def _run(self) -> None:
        folder = self.folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.information(self, tr("common.pickfolder"), tr("common.nofolder"))
            return

        survey_mode = self.survey_choice.isChecked()
        with_names = self.with_names.isChecked()

        def work(emit):
            from ..cli import collect_inputs

            books = collect_inputs([folder])
            total = len(books)
            if survey_mode:
                from ..survey import survey_library, to_json

                def tick(index: int, name: str) -> None:
                    emit(index, total, name)

                result = survey_library(books, with_names=with_names, on_book=tick)
                return ("survey", result, to_json(result, with_names=with_names))

            from ..inventory import measure, summarise, to_json as inventory_json

            measured = []
            for index, path in enumerate(books):
                emit(index, total, os.path.basename(path))
                measured.append(measure(pathlib.Path(path)))
            return ("inventory", measured, inventory_json(measured), summarise(measured))

        self.start(work, [self.run_button, self.save_button])

    def handle(self, result) -> None:
        kind = result[0]
        if kind == "survey":
            _, survey, payload = result
            self._payload = payload
            self.output.setPlainText(self._render_survey(survey))
            self.window().statusBar().showMessage(tr("common.done", count=survey.books))
        else:
            _, measured, payload, summary = result
            self._payload = payload
            self.output.setPlainText(summary)
            self.window().statusBar().showMessage(tr("common.done", count=len(measured)))
        self.save_button.setEnabled(True)

    def _render_survey(self, survey) -> str:
        lines = [f"{survey.books} książek", ""]
        versions = ", ".join(f"{v}: {n}" for v, n in survey.source_versions.most_common())
        if versions:
            lines.append(f"wersje źródła: {versions}")
        if survey.unreadable:
            lines.append(f"nieodczytanych: {len(survey.unreadable)}")
        if survey.crashed:
            lines.append(f"awarii etapu: {len(survey.crashed)}")
        if survey.drm:
            lines.append(f"z DRM (odrzucone): {len(survey.drm)}")
        lines += ["", f"{'ksiąg':>6} {'razem':>6}  {'poziom':<10} {'etap':<14} znalezisko", ""]
        for finding in survey.ranked():
            lines.append(
                f"{finding.books:>6} {finding.occurrences:>6}  "
                f"{finding.level.value:<10} {finding.stage:<14} {finding.message}"
            )
        return "\n".join(lines)


class CorpusPanel(Panel):
    """A library keeping the tool honest, without anybody handing it over."""

    def __init__(self, palette: theme.Palette) -> None:
        super().__init__(palette)
        self.add_intro(tr("corpus.intro"))
        self.books = self.add_folder_row(tr("corpus.books"))
        self.signatures = self.add_folder_row(
            tr("corpus.signatures"), tr("corpus.signatures.placeholder")
        )

        note = QLabel(tr("corpus.what"))
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {self.colors.text_muted}; font-size: 8.5pt; font-style: italic;"
        )
        self.layout_.addWidget(note)

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.check_button = QPushButton(tr("corpus.check"))
        self.check_button.setObjectName("primary")
        self.check_button.setToolTip(tr("corpus.check.tip"))
        self.check_button.clicked.connect(lambda: self._run(record=False))
        row.addWidget(self.check_button)
        self.record_button = QPushButton(tr("corpus.record"))
        self.record_button.setToolTip(tr("corpus.record.tip"))
        self.record_button.clicked.connect(lambda: self._run(record=True))
        row.addWidget(self.record_button)
        row.addStretch(1)
        self.layout_.addWidget(buttons)

        self.add_output(tr("corpus.empty"))

    def _run(self, *, record: bool) -> None:
        books = self.books.text().strip()
        if not books or not os.path.isdir(books):
            QMessageBox.information(self, tr("common.pickfolder"), tr("common.nofolder"))
            return
        signatures = self.signatures.text().strip()

        def work(emit):
            from ..corpus import books_in, compare

            folder = pathlib.Path(books)
            target = pathlib.Path(signatures) if signatures else folder / "expected"
            total = len(books_in(folder))

            def tick(index: int, name: str) -> None:
                emit(index, total, name)

            return compare(folder, target, record=record, on_book=tick)

        self.start(work, [self.check_button, self.record_button])

    def handle(self, results) -> None:
        labels = {
            "unchanged": tr("corpus.status.unchanged"),
            "changed": tr("corpus.status.changed"),
            "new": tr("corpus.status.new"),
            "failed": tr("corpus.status.failed"),
        }
        lines: list[str] = []
        for result in results:
            if result.status == "unchanged":
                continue
            lines.append(f"{labels[result.status]:>10}  {result.book}")
            lines.extend(f"            {difference}" for difference in result.differences)

        from ..corpus import summarise

        summary = summarise(results)
        self.output.setPlainText(summary + ("\n\n" + "\n".join(lines) if lines else ""))
        self.window().statusBar().showMessage(summary)
