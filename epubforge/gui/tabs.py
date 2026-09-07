"""The library and corpus panels.

Kept out of `app.py` because they are a different job from rebuilding a book:
these two read a whole shelf and answer a question about it, writing nothing
except a file the person explicitly asks for. Sharing the window is convenient;
sharing a module would just make both harder to read.
"""

from __future__ import annotations

import os
import pathlib

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
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

from . import theme, toolwork
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
    def begin_card(self, title: str) -> None:
        """Everything added until `end_card` lands inside one titled card.

        WP-21 phase B5: the three tool panels floated their controls straight
        on the window while every other page had learnt to speak in cards.
        Redirecting `layout_` is what keeps the change this small — every
        existing helper keeps adding to `self.layout_` and needs no idea the
        walls moved.
        """
        from PySide6.QtWidgets import QGroupBox

        card = QGroupBox(title)
        inner = QVBoxLayout(card)
        inner.setSpacing(8)
        self._outer_layout = self.layout_
        self._outer_layout.addWidget(card)
        self.layout_ = inner

    def end_card(self) -> None:
        self.layout_ = self._outer_layout

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
        self.say(tr("common.working", name=name))

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
            self.say(error)
            return
        self.handle(result)

    def say(self, message: str) -> None:
        """One line of news, to whatever window is holding this panel.

        It used to reach for the window's status bar directly, which is a
        panel deciding what furniture its window has. The new shell has no
        status bar — and `QMainWindow.statusBar()` *creates* one on demand, so
        the old call would have grown a bar back at the bottom of a window that
        deliberately does without. A window that wants these says so with a
        `say` method; the old window keeps its status bar.
        """
        window = self.window()
        sink = getattr(window, "say", None)
        if callable(sink):
            sink(message)
            return
        bar = getattr(window, "statusBar", None)
        if callable(bar):
            bar().showMessage(message)

    def handle(self, result) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def invalidate(self) -> None:
        """Forget a result that no longer describes what the panel is set to.

        Saving is offered separately from running, so the two can drift: pick
        survey, run it, switch to inventory, press Save, and out comes the
        survey under the inventory's name. It looked like a bug in the
        inventory and was a bug in this button.
        """
        self._payload = ""
        if hasattr(self, "save_button"):
            self.save_button.setEnabled(False)

    def save_payload(self, suggestion: str) -> None:
        if not self._payload:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("common.save"), suggestion, "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._payload)
            self.say(tr("common.saved", path=path))


class LibraryPanel(Panel):
    """Survey and inventory: two questions about a shelf, neither of them
    changing anything on it."""

    def __init__(self, palette: theme.Palette) -> None:
        super().__init__(palette)
        self.add_intro(tr("library.intro"))
        self.begin_card(tr("library.mode"))
        self.folder = self.add_folder_row(tr("common.folder"))

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

        # Anything that changes what a run would produce invalidates the last
        # one, so Save cannot offer yesterday's answer under today's question.
        for widget in (self.survey_choice, self.inventory_choice):
            widget.toggled.connect(lambda _checked: self.invalidate())
        self.with_names.toggled.connect(lambda _checked: self.invalidate())
        self.folder.textChanged.connect(lambda _text: self.invalidate())

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
        self.end_card()

        self.add_output(tr("library.empty"))

    def _suggested_name(self) -> str:
        return "przeglad.json" if self.survey_choice.isChecked() else "spis.json"

    def _run(self) -> None:
        folder = self.folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.information(self, tr("common.pickfolder"), tr("common.nofolder"))
            return

        inventory = self.inventory_choice.isChecked()
        with_names = self.with_names.isChecked()

        def work(emit):
            return toolwork.library(folder, inventory=inventory, with_names=with_names,
                                    tick=emit)

        self.start(work, [self.run_button, self.save_button])

    def handle(self, result) -> None:
        self._payload = result.payload
        self.output.setPlainText(result.text)
        self.say(result.headline)
        self.save_button.setEnabled(bool(result.payload))

    _render_survey = staticmethod(toolwork.render_survey)


class DiagnosticsPanel(Panel):
    """`inspect` and `check`, which lived only in the command line.

    The owner's point on 2026-08-13, and it applies to the diagnostics as much
    as to the switches: *everything, the debugging things included, has to be in
    the window.* He runs the Windows build. A command that answers "what is
    actually inside this file" and one that answers "does a validator accept
    it" are exactly what a person reaches for when a book comes out wrong, and
    both were reachable only from a terminal he does not use.

    Neither changes a file. That is why they share a panel and why nothing here
    asks about policy: these are questions, and the rebuild tab is the answer.
    """

    def __init__(self, palette: theme.Palette) -> None:
        super().__init__(palette)
        self.add_intro(tr("diagnostics.intro"))
        self.begin_card(tr("diagnostics.mode"))
        self.folder = self.add_folder_row(tr("diagnostics.files"))

        self.inspect_choice = QRadioButton(tr("diagnostics.inspect"))
        self.inspect_choice.setToolTip(tr("diagnostics.inspect.tip"))
        self.inspect_choice.setChecked(True)
        self.layout_.addWidget(self.inspect_choice)

        self.validate_choice = QRadioButton(tr("diagnostics.validate"))
        self.validate_choice.setToolTip(tr("diagnostics.validate.tip"))
        self.layout_.addWidget(self.validate_choice)

        # The third question, and the one nothing else in the program answers:
        # not "is this file valid" but "did the rebuild keep the book". F-017 and
        # F-028 — the audit's point that the suite proves the output validates
        # and does not prove it still looks like itself.
        self.fidelity_choice = QRadioButton(tr("diagnostics.fidelity"))
        self.fidelity_choice.setToolTip(tr("diagnostics.fidelity.tip"))
        self.layout_.addWidget(self.fidelity_choice)

        # The fourth question, and the one that has to be asked before the
        # others are worth asking: is the file even whole. A source this program
        # cannot read in full stops the rebuild outright — so "why did it
        # refuse" needs an answer that is not another refusal.
        self.health_choice = QRadioButton(tr("diagnostics.health"))
        self.health_choice.setToolTip(tr("diagnostics.health.tip"))
        self.layout_.addWidget(self.health_choice)

        # F-028, and the one question here that needs something the program does
        # not ship. It renders both books and compares the pictures; without a
        # browser it says so in sentences rather than being a greyed-out button
        # nobody can find out the meaning of.
        self.render_choice = QRadioButton(tr("diagnostics.render"))
        self.render_choice.setToolTip(tr("diagnostics.render.tip"))
        self.layout_.addWidget(self.render_choice)

        # Reachable from the window, because everything in this program is —
        # including the switch that turns an optimisation off. "Is it the new
        # fast path?" is the first question worth asking about a verdict that
        # surprises somebody, and it should not require an environment variable
        # and a terminal to answer.
        self.shared_validator = QCheckBox(tr("diagnostics.shared"))
        self.shared_validator.setToolTip(tr("diagnostics.shared.tip"))
        self.shared_validator.setChecked(True)
        self.layout_.addWidget(self.shared_validator)

        for widget in (self.inspect_choice, self.validate_choice, self.fidelity_choice,
                       self.health_choice, self.render_choice):
            widget.toggled.connect(lambda _checked: self.invalidate())
        self.folder.textChanged.connect(lambda _text: self.invalidate())

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
        self.save_button.clicked.connect(lambda: self.save_payload("diagnostyka.txt"))
        row.addWidget(self.save_button)
        row.addStretch(1)
        self.layout_.addWidget(buttons)

        self.end_card()

        self.add_output(tr("diagnostics.empty"))

    def _books(self) -> list[str]:
        return toolwork.books_for(self.folder.text().strip())

    def _run(self) -> None:
        books = self._books()
        if not books:
            QMessageBox.information(self, tr("common.pickfolder"), tr("common.nofolder"))
            return

        toolwork.use_shared_validator(self.shared_validator.isChecked())

        if self.inspect_choice.isChecked():
            answer = self._describe
        elif self.validate_choice.isChecked():
            answer = self._validate
        elif self.health_choice.isChecked():
            answer = self._health
        elif self.render_choice.isChecked():
            answer = self._render
        else:
            answer = self._fidelity

        def work(emit):
            return toolwork.answer_for_each(books, answer, tick=emit)

        self.start(work, [self.run_button])

    # The five answers live in `toolwork`, where the new window reaches them
    # too. They stay named here because this panel's controls are named after
    # them and because a person reading `answer = self._health` should be able
    # to find out what it does from this class.
    _describe = staticmethod(toolwork.describe)
    _validate = staticmethod(toolwork.validate_book)
    _health = staticmethod(toolwork.check_health)
    _render = staticmethod(toolwork.compare_render)
    _fidelity = staticmethod(toolwork.compare_fidelity)

    def handle(self, result) -> None:
        self._payload = result.payload
        self.output.setPlainText(result.text or tr("diagnostics.empty"))
        self.save_button.setEnabled(bool(result.payload))


class CorpusPanel(Panel):
    """A library keeping the tool honest, without anybody handing it over."""

    def __init__(self, palette: theme.Palette) -> None:
        super().__init__(palette)
        self._signatures_used: pathlib.Path | None = None
        self.add_intro(tr("corpus.intro"))
        self.begin_card(tr("corpus.card"))
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
        # The one family nobody can go and buy. It used to be a command-line
        # script importing from the test suite, which put it out of reach of the
        # only person able to fill it.
        self.edges_button = QPushButton(tr("corpus.edges"))
        self.edges_button.setToolTip(tr("corpus.edges.tip"))
        self.edges_button.clicked.connect(self._build_edges)
        row.addWidget(self.edges_button)
        # The other family nobody can go and buy, and the one the audit stalled
        # on. It named two purchased books "mandatory", blocked three findings
        # for want of them, and never said which books — so the person who owns
        # them could not have handed them over if he wanted to.
        self.fixtures_button = QPushButton(tr("corpus.fixtures"))
        self.fixtures_button.setToolTip(tr("corpus.fixtures.tip"))
        self.fixtures_button.clicked.connect(self._show_fixtures)
        row.addWidget(self.fixtures_button)
        self.assign_button = QPushButton(tr("corpus.fixtures.assign"))
        self.assign_button.setToolTip(tr("corpus.fixtures.assign.tip"))
        self.assign_button.clicked.connect(self._assign_fixture)
        row.addWidget(self.assign_button)
        row.addStretch(1)
        self.layout_.addWidget(buttons)
        self.end_card()

        self.add_output(tr("corpus.empty"))

    def _run(self, *, record: bool) -> None:
        books = self.books.text().strip()
        if not books or not os.path.isdir(books):
            QMessageBox.information(self, tr("common.pickfolder"), tr("common.nofolder"))
            return
        signatures = self.signatures.text().strip()

        def work(emit):
            return toolwork.corpus_check(books, signatures, record=record, tick=emit)

        self.start(work, [self.check_button, self.record_button])

    def _build_edges(self) -> None:
        books = self.books.text().strip()
        if not books or not os.path.isdir(books):
            QMessageBox.information(self, tr("common.pickfolder"), tr("common.nofolder"))
            return

        def work(emit):
            return toolwork.build_edge_cases(books, tick=emit)

        self.start(work, [self.check_button, self.record_button, self.edges_button])

    def _show_fixtures(self) -> None:
        """Which of the two purchased books the suite still cannot see.

        The chosen folder is searched as well as the configured shelves, so a
        person who has just pointed this panel at their library gets the answer
        for *that* library without setting an environment variable first.
        """
        books = self.books.text().strip()
        extra = pathlib.Path(books) if books and os.path.isdir(books) else None

        def work(emit):
            return toolwork.fixtures_survey(str(extra) if extra else "", tick=emit)

        self.start(work, [self.check_button, self.record_button, self.fixtures_button])

    def _assign_fixture(self) -> None:
        chosen, picked = QFileDialog.getOpenFileName(
            self, tr("corpus.fixtures.assign"), "", "EPUB (*.epub)"
        )
        if not picked or not chosen:
            return
        role, confirmed = QInputDialog.getItem(
            self, tr("corpus.fixtures.assign"), tr("corpus.fixtures.role"),
            toolwork.fixture_roles(), 0, False,
        )
        if not confirmed:
            return
        self.output.setPlainText(toolwork.assign_fixture(role, chosen).text)

    def handle(self, result) -> None:
        self._signatures_used = pathlib.Path(result.used) if result.used else self._signatures_used
        self.output.setPlainText(result.text)
        self.say(result.headline)

    def _streak(self) -> str:
        """The streak for the signatures this panel last compared against."""
        return toolwork.streak(self._signatures_used)
