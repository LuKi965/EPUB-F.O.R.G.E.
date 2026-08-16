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

            from ..inventory import (
                coverage_report,
                measure,
                summarise,
                to_json as inventory_json,
            )

            measured = []
            for index, path in enumerate(books):
                emit(index, total, os.path.basename(path))
                measured.append(measure(pathlib.Path(path)))
            # Coverage was written from the beginning and shown only by the
            # command line, which the person holding the library does not use.
            # Which families are short is the *question* the inventory answers;
            # printing everything but the answer was the wrong half.
            from .strings import language

            report = (
                summarise(measured) + "\n\n" + coverage_report(measured, language())
            )
            return ("inventory", measured, inventory_json(measured), report)

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
        lines = [tr("survey.books", count=survey.books), ""]
        versions = ", ".join(f"{v}: {n}" for v, n in survey.source_versions.most_common())
        if versions:
            lines.append(tr("survey.versions", versions=versions))
        # The reason, not just the count. "stage failures: 3" on screen and
        # nothing else is a dead end for whoever has the three books.
        for key, entries in (
            ("survey.unreadable", survey.unreadable),
            ("survey.crashed", survey.crashed),
        ):
            if not entries:
                continue
            lines.append(f"{tr(key)}: {len(entries)}")
            for name, reason in entries[:5]:
                lines.append(f"    {name}: {reason}")
        if survey.drm:
            lines.append(tr("survey.drm", count=len(survey.drm)))
        lines += [
            "",
            f"{tr('survey.head.books'):>6} {tr('survey.head.total'):>6}  "
            f"{tr('survey.head.level'):<10} {tr('survey.head.stage'):<14} "
            f"{tr('survey.head.finding')}",
            "",
        ]
        for finding in survey.ranked():
            lines.append(
                f"{finding.books:>6} {finding.occurrences:>6}  "
                f"{finding.level.value:<10} {finding.stage:<14} {finding.message}"
            )
        return "\n".join(lines)


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
        self.folder = self.add_folder_row(tr("diagnostics.files"))

        mode = QLabel(tr("diagnostics.mode"))
        mode.setObjectName("sectionLabel")
        self.layout_.addWidget(mode)

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

        self.add_output(tr("diagnostics.empty"))

    def _books(self) -> list[str]:
        import pathlib as _pathlib

        from ..corpus import books_in

        folder = self.folder.text().strip()
        if not folder:
            return []
        path = _pathlib.Path(folder)
        if path.is_file():
            return [str(path)]
        return [str(book) for book in books_in(path)]

    def _run(self) -> None:
        books = self._books()
        if not books:
            QMessageBox.information(self, tr("common.pickfolder"), tr("common.nofolder"))
            return

        from .. import validate as validate_module

        os.environ[validate_module.ENV_SHARED] = (
            "1" if self.shared_validator.isChecked() else "0"
        )
        if not self.shared_validator.isChecked():
            validate_module.SHARED.stop()

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
            lines: list[str] = []
            for index, book in enumerate(books):
                emit(index, len(books), os.path.basename(book))
                lines.append(f"--- {os.path.basename(book)}")
                lines.extend(answer(book))
                lines.append("")
            return "\n".join(lines)

        self.start(work, [self.run_button])

    @staticmethod
    def _describe(book: str) -> list[str]:
        """What is actually in the file, before anything touches it."""
        from .. import memory
        from ..reader import EpubReadError, read_epub
        from ..report import Report

        report = Report(source=book)
        try:
            parsed = read_epub(book, report)
        except EpubReadError as exc:
            return [f"  nie da się odczytać: {exc}"]
        metadata = parsed.metadata
        identifier = metadata.primary_identifier
        rows = [
            ("wersja", parsed.source_version),
            ("tytuł", metadata.title or "—"),
            ("autorzy", ", ".join(c.name for c in metadata.creators) or "—"),
            ("język", metadata.language or "BRAK"),
            ("identyfikator", identifier.value if identifier else "BRAK"),
            ("zasoby", str(len(parsed.resources))),
            ("kolejność czytania", str(len(parsed.spine))),
            ("wpisy spisu treści", str(sum(1 for root in parsed.toc for _ in root.walk()))),
            ("okładka", parsed.cover_path or "nie wykryto"),
            ("nawigacja", parsed.nav_path or "brak (styl EPUB 2)"),
            ("zaciemnione fonty", str(len(parsed.encrypted)) if parsed.encrypted else "nie"),
            ("DRM", "TAK" if parsed.has_drm else "nie"),
            # Asked before the rebuild rather than found out during it. On a
            # book big enough to matter this is the difference between a line
            # here and a process the system kills without a word.
            ("pamięć", str(memory.check(book))),
        ]
        return [f"  {name:<20} {value}" for name, value in rows]

    @staticmethod
    def _render(book: str) -> list[str]:
        """Rebuild it and compare the two books as *pictures*.

        F-028. Everything else in this panel reads the file; this one draws it.
        The answer when no browser is installed is a paragraph saying which
        browsers count and how to point at one, because "this needs something
        you do not have" is an answer and a disabled control is not.
        """
        from .. import render

        if render.find_renderer() is None:
            return ["  " + line for line in render.why_not().splitlines()]
        # Which engine drew this, said out loud. A result whose engine is not
        # named is a result about somebody's browser, and the person reading it
        # has no way to know that.
        lines = ["  " + line for line in render.describe().splitlines()] + [""]
        return lines + DiagnosticsPanel._render_pages(book)

    @staticmethod
    def _render_pages(book: str) -> list[str]:
        import tempfile

        from .. import render_fidelity
        from ..pipeline import rebuild
        from ..policy import Policy

        with tempfile.TemporaryDirectory() as room:
            destination = os.path.join(room, os.path.basename(book))
            result = rebuild(book, destination, Policy.for_measurement())
            if not result.status.wrote_a_file:
                return ["  nie udało się przebudować, więc nie ma czego porównać"]
            measured = render_fidelity.compare(book, destination)
            lines = [f"  {measured.summary()}"]
            for page in measured.pages:
                mark = "!!" if page.problems else ("··" if page.notes else "ok")
                lines.append(f"  {mark} {page}")
            return lines

    @staticmethod
    def _fidelity(book: str) -> list[str]:
        """Rebuild it into a temporary folder and compare the two.

        Nothing is written where anybody will find it: the question is about the
        rebuild, and the answer does not need the file kept. Everything this
        reports is something EPUBCheck has no opinion about.
        """
        import tempfile

        from .. import fidelity
        from ..pipeline import rebuild
        from ..policy import Policy

        with tempfile.TemporaryDirectory() as room:
            destination = os.path.join(room, os.path.basename(book))
            result = rebuild(book, destination, Policy.preset("preserve"))
            if not result.status.wrote_a_file:
                return ["  nie udało się przebudować, więc nie ma czego porównać"]
            measured = fidelity.compare(book, destination)
            return [f"  {check}" for check in measured.checks]

    @staticmethod
    def _health(book: str) -> list[str]:
        """Every entry, actually decompressed. See `epubforge.repair`."""
        from .. import repair

        health = repair.inspect(book)
        if health.unreadable:
            return [f"  nie da się otworzyć jako archiwum: {health.unreadable}"]
        if not health.damaged:
            return [f"  całe — {len(health.entries)} plików w środku, wszystkie czytelne"]
        lines = [
            f"  USZKODZONE — {len(health.damaged)} z {len(health.entries)} plików "
            f"nie da się rozpakować:"
        ]
        lines.extend(f"    {entry.name} — {entry.reason}" for entry in health.damaged)
        lines.append(
            "    Naprawa: pobierz książkę ponownie. Jeżeli masz drugą, inaczej "
            "uszkodzoną kopię, scal je: epubforge merge kopia-a.epub kopia-b.epub -o cala.epub"
        )
        return lines

    @staticmethod
    def _validate(book: str) -> list[str]:
        from ..report import Report
        from ..validate import SHARED, validate

        result = validate(book, Report(source=book))
        if not result.available:
            return ["  EPUBCheck nie jest dostępny"]
        lines = (
            [f"  poprawny — ostrzeżeń: {result.warnings}"]
            if result.clean
            else [
                f"  NIEPOPRAWNY — błędów krytycznych: {result.fatal}, błędów: {result.errors}",
                *(f"    {message}" for message in result.messages[:40]),
            ]
        )
        # Said out loud rather than kept inside. A batch that quietly went back
        # to a JVM per book is four times slower for a reason somebody would
        # otherwise have to guess at.
        if SHARED.reason:
            lines.append(f"  (osobny proces walidatora: {SHARED.reason})")
        return lines

    def handle(self, result) -> None:
        self.output.setPlainText(result or tr("diagnostics.empty"))


class CorpusPanel(Panel):
    """A library keeping the tool honest, without anybody handing it over."""

    def __init__(self, palette: theme.Palette) -> None:
        super().__init__(palette)
        self._signatures_used: pathlib.Path | None = None
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
            self._signatures_used = target
            total = len(books_in(folder))

            def tick(index: int, name: str) -> None:
                emit(index, total, name)

            return compare(folder, target, record=record, on_book=tick)

        self.start(work, [self.check_button, self.record_button])

    def _build_edges(self) -> None:
        books = self.books.text().strip()
        if not books or not os.path.isdir(books):
            QMessageBox.information(self, tr("common.pickfolder"), tr("common.nofolder"))
            return

        def work(emit):
            from ..edge_cases import EDGES, build_edges

            emit(0, len(EDGES), tr("corpus.edges.working"))
            written = build_edges(books)
            return ("edges", written)

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
            from ..fixtures import ROLES, survey

            emit(0, len(ROLES), tr("corpus.fixtures.working"))
            return ("fixtures", survey(extra=extra))

        self.start(work, [self.check_button, self.record_button, self.fixtures_button])

    def _assign_fixture(self) -> None:
        from ..fixtures import BY_ID, record

        chosen, picked = QFileDialog.getOpenFileName(
            self, tr("corpus.fixtures.assign"), "", "EPUB (*.epub)"
        )
        if not picked or not chosen:
            return
        roles = list(BY_ID)
        role, confirmed = QInputDialog.getItem(
            self, tr("corpus.fixtures.assign"), tr("corpus.fixtures.role"), roles, 0, False
        )
        if not confirmed:
            return
        entry = record(role, pathlib.Path(chosen))
        self.output.setPlainText(
            tr("corpus.fixtures.done", role=role, name=os.path.basename(chosen))
            + f"\nsha256:{entry['sha256']}"
        )

    def _handle_fixtures(self, matches) -> None:
        from ..fixtures import BY_ID, explain

        lines: list[str] = []
        for match in matches:
            role = BY_ID[match.role]
            lines.append(explain(role))
            if match.found:
                lines.append(f"  {tr('corpus.fixtures.present')} — {match.path}")
            else:
                lines.append(f"  {tr('corpus.fixtures.missing')}")
                for candidate in match.candidates:
                    lines.append(
                        "    " + tr("corpus.fixtures.similar", name=str(candidate))
                    )
            lines.append("")
        self.output.setPlainText("\n".join(lines))
        absent = sum(1 for match in matches if not match.found)
        self.window().statusBar().showMessage(
            f"{len(matches) - absent}/{len(matches)} {tr('corpus.fixtures.present')}"
        )

    def handle(self, results) -> None:
        # Three jobs land here, so the result says which it was rather than being
        # guessed at from its shape.
        if isinstance(results, tuple) and results and results[0] == "edges":
            self._handle_edges(results[1])
            return
        if isinstance(results, tuple) and results and results[0] == "fixtures":
            self._handle_fixtures(results[1])
            return
        labels = {
            "unchanged": tr("corpus.status.unchanged"),
            "changed": tr("corpus.status.changed"),
            "new": tr("corpus.status.new"),
            "failed": tr("corpus.status.failed"),
            "duplicate": tr("corpus.status.duplicate"),
        }
        lines: list[str] = []
        for result in results:
            if result.status == "unchanged":
                continue
            lines.append(f"{labels[result.status]:>10}  {result.book}")
            lines.extend(f"            {difference}" for difference in result.differences)

        from ..corpus import summarise

        summary = summarise(results, self._signatures_used)
        streak = self._streak()
        if streak:
            summary += "\n" + streak
        self.output.setPlainText(summary + ("\n\n" + "\n".join(lines) if lines else ""))
        # The status bar is one line high, so it gets the first one; the pane
        # below has room for the sentence that says which errors were whose.
        self.window().statusBar().showMessage(summary.splitlines()[0])

    def _streak(self) -> str:
        """How many releases in a row came out clean, read from the ledger.

        Answering this from memory is how the family count came to be wrong, and
        the owner has been asking it from outside the program: he remembered
        three green metrics and watched the count go back to zero, with no way
        to check which of us was right. It is one file and two functions, and
        the person who owns the books is the person who should be able to read
        it without a checkout.
        """
        import json

        from ..corpus import RUNS, green_streak, widenings

        if self._signatures_used is None:
            return ""
        ledger = pathlib.Path(self._signatures_used).parent / RUNS
        if not ledger.is_file():
            return ""
        try:
            history = json.loads(ledger.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""

        # The same floor the streak rule uses: a run over three books says
        # nothing about a corpus of ninety.
        streak = green_streak(history, minimum=30)
        grown = widenings(history, minimum=30)
        if streak:
            said = tr("corpus.streak", count=len(streak), releases=", ".join(streak))
        else:
            said = tr("corpus.streak.none")
        if grown:
            said += " " + tr("corpus.streak.widened", releases=", ".join(grown))
        return said

    def _handle_edges(self, written) -> None:
        from ..edge_cases import EDGES
        from ..gui.strings import language

        # What each file is for, in the language the window is speaking. Four
        # unfamiliar names appearing in a corpus folder is not an explanation.
        index = 2 if language() == "en" else 1
        what = {name: entry[index] for name, entry in EDGES.items()}
        headline = tr("corpus.edges.done", count=len(written))
        lines = [
            f"    {path.name:26} {what.get(path.stem, '')}" for path in written
        ]
        self.output.setPlainText(headline + "\n" + "\n".join(lines))
        self.window().statusBar().showMessage(headline)
