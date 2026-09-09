"""The shape every specialist tool has, once, instead of three times.

A tool page asks one thing: *what should I look at, and which question should
I ask about it?* So the frame is always the same — a heading that says what
the tool is for in one sentence, somewhere to point it, one clear action, a
compact progress line, and an answer that can be copied or saved. The three
tools differ only in the middle.

The work is never here. It is in `gui.toolwork`, which has no Qt in it and is
what the old window's panels now call too, so a survey prints the same thing
in both windows because it is the same function.
"""

from __future__ import annotations

import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ....strings import tr
from ...responsive import Cards, LayoutMode, Panels, Responsive, spread
from ...state import last_folder, remember_folder
from ...tokens import CARD_GAP, Tokens
from ...widgets import Card, PageHeader, button, clear_layout, label, page_body
from ...workers import Runner, ToolJob


class ToolPage(Responsive, QWidget):
    """One tool, in the shell's own furniture."""

    back_requested = Signal()

    def __init__(self, tokens: Tokens, *, key: str, glyph: str, card_key: str,
                 intro_key: str, empty_key: str) -> None:
        super().__init__()
        self.tokens = tokens
        self.key = key
        self.empty_key = empty_key
        self.runner = Runner(self)
        self._buttons: list = []
        #: Which question is being answered. The form can be changed while the
        #: tool is working, and an answer arriving afterwards would be read as
        #: the answer to what the form says *now* (R08).
        self._question = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroller, page = page_body(CARD_GAP)
        outer.addWidget(scroller)
        # `finish_building` runs later, in the subclass, and needs it then.
        self._scroller = scroller

        top = Panels(CARD_GAP)
        top.add(
            PageHeader(tr("shell.tools.eyebrow"), tr(f"{key}.title"), tr(f"{key}.body")), 3
        )
        back = button(tr("shell.tools.back"), glyph="chevron", tokens=tokens)
        back.clicked.connect(self.back_requested)
        holder = QWidget()
        holding = QHBoxLayout(holder)
        holding.setContentsMargins(0, 0, 0, 0)
        holding.addStretch(1)
        holding.addWidget(back, 0, Qt.AlignTop)
        top.add(holder, 1)
        page.addWidget(top)

        #: What this tool is for, in the one sentence the old panel opened with.
        self.card = Card(tr(card_key), tr(intro_key), glyph=glyph, tokens=tokens)
        self.body = self.card.body
        page.addWidget(self.card)

        #: Built in `end_actions`, once it is known how many there are: five
        #: buttons in one row is what made the corpus page unable to be 800 px
        #: wide, and a page whose minimum width exceeds the screen is a window
        #: that cannot open small however well the rest of it reflows.
        self.actions = None

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setAccessibleName(tr(f"{key}.title"))
        self.news = label("", "muted")

        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setPlainText(tr(empty_key))
        self.result.setAccessibleName(tr("shell.tool.result"))
        self.result.setMinimumHeight(180)
        self._answer = None

        self.answer_card = Card(tr("shell.tool.result"), glyph="text", tokens=tokens)
        # The structural summary, above the raw text (F11). The audit's point
        # was that a wall of prose is not a result a person can read at a
        # glance — and its other point was that a summary must come from
        # numbers the backend hands over, not from a regex run over the prose.
        # So this is empty until a tool fills `ToolAnswer.facts`, and empty is
        # honest: it means that tool has nothing structural to say yet.
        self.facts = Cards(
            {LayoutMode.WIDE: 4, LayoutMode.MEDIUM: 2, LayoutMode.COMPACT: 1}, 10
        )
        self.facts.hide()
        self.answer_card.body.addWidget(self.facts)
        self.report_title = label(tr("shell.tool.report"), "cardTitle")
        self.report_title.hide()
        self.answer_card.body.addWidget(self.report_title)
        self.answer_card.body.addWidget(self.result, 1)
        answer_actions = QHBoxLayout()
        self.copy_button = button(tr("shell.tool.copy"), glyph="save", tokens=tokens,
                                  tip=tr("shell.tool.copy.tip"))
        self.copy_button.clicked.connect(self._copy)
        answer_actions.addWidget(self.copy_button)
        self.save_button = button(tr("common.save"), glyph="save", tokens=tokens)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)
        answer_actions.addWidget(self.save_button)
        answer_actions.addStretch(1)
        self.answer_card.body.addLayout(answer_actions)
        self._answer_page = page

    def finish_building(self) -> None:
        """Call at the end of a subclass's `__init__`, once its controls exist."""
        if isinstance(self.actions, QHBoxLayout):
            self.body.addLayout(self.actions)
        elif self.actions is not None:
            self.body.addWidget(self.actions)
        self.body.addWidget(self.news)
        self.body.addWidget(self.progress)
        self._answer_page.addWidget(self.answer_card, 1)
        self.begin_tracking(self._scroller)

    def reflow(self, mode: LayoutMode) -> None:
        spread(self, mode)

    # -- the pieces a tool builds itself out of -----------------------------
    def add_source(self, label_key: str, *, placeholder: str = "",
                   files: bool = False) -> QLineEdit:
        """Somewhere to point the tool, with a browse button beside it."""
        row = Panels(10)
        caption_side = QWidget()
        caption_holder = QVBoxLayout(caption_side)
        caption_holder.setContentsMargins(0, 0, 0, 0)
        caption_holder.addWidget(label(tr(label_key), "cardTitle"))
        row.add(caption_side, 1)

        chooser_side = QWidget()
        chooser = QHBoxLayout(chooser_side)
        chooser.setContentsMargins(0, 0, 0, 0)
        chooser.setSpacing(8)
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder or tr("shell.tool.source.placeholder"))
        edit.setAccessibleName(tr(label_key))
        chooser.addWidget(edit, 1)
        browse = button(tr("common.browse"), glyph="folder", tokens=self.tokens)
        browse.clicked.connect(lambda: self._pick_into(edit, files=files))
        chooser.addWidget(browse)
        row.add(chooser_side, 3)
        self.body.addWidget(row)
        return edit

    def _pick_into(self, edit: QLineEdit, *, files: bool) -> None:
        start = edit.text().strip() or last_folder("tool")
        if files:
            chosen, _ = QFileDialog.getOpenFileName(
                self, tr("dialog.selectfiles"), start, tr("dialog.filter")
            )
        else:
            chosen = QFileDialog.getExistingDirectory(self, tr("common.pickfolder"), start)
        if chosen:
            remember_folder("tool", chosen)
            edit.setText(chosen)

    def add_action(self, text_key: str, slot, *, primary: bool = False, glyph: str = "play",
                   tip_key: str = "") -> "QWidget":
        item = button(
            tr(text_key), kind="primary" if primary else "", glyph=glyph, tokens=self.tokens,
            tip=tr(tip_key) if tip_key else "",
        )
        item.clicked.connect(slot)
        self._buttons.append(item)
        return item

    def end_actions(self) -> None:
        """Lay the actions out: a row when there are one or two, a grid beyond.

        The grid is what lets a page with five actions be 800 pixels wide. A
        single action keeps its own size and stays on the left, where a primary
        button belongs.
        """
        if len(self._buttons) <= 2:
            row = QHBoxLayout()
            row.setSpacing(8)
            for item in self._buttons:
                row.addWidget(item)
            row.addStretch(1)
            self.actions = row
            return
        grid = Cards(
            {LayoutMode.WIDE: 3, LayoutMode.MEDIUM: 2, LayoutMode.COMPACT: 1}, 8
        )
        for item in self._buttons:
            grid.add(item)
        self.actions = grid

    # -- running ------------------------------------------------------------
    @property
    def busy(self) -> bool:
        return self.runner.working

    def run_work(self, work) -> None:
        """Run one `toolwork` function off the window's thread."""
        if self.busy:
            return
        for item in self._buttons:
            item.setEnabled(False)
        self.save_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.result.setPlainText(tr("shell.tool.working"))
        self._question = uuid.uuid4().hex
        job = ToolJob(work, self._question)
        job.progress.connect(self._on_progress, Qt.QueuedConnection)
        job.failed.connect(self._on_failed, Qt.QueuedConnection)
        job.finished.connect(self._answered, Qt.QueuedConnection)
        self.runner.start(job, on_done=self._idle)

    def _ours(self, question: str) -> bool:
        """Whether a job speaking now is the one this page is waiting for."""
        return question == self._question

    def _idle(self) -> None:
        self.progress.setVisible(False)
        for item in self._buttons:
            item.setEnabled(True)

    def _on_progress(self, question: str, step) -> None:
        if not self._ours(question):
            return
        if step.determinate:
            self.progress.setRange(0, step.total)
            self.progress.setValue(step.done)
        else:
            self.progress.setRange(0, 0)
        self.news.setText(tr("common.working", name=step.name))

    def _on_failed(self, question: str, message: str) -> None:
        if not self._ours(question):
            return
        self.result.setPlainText(message)
        self.news.setText(message.splitlines()[0] if message else "")

    def _answered(self, question: str, answer) -> None:
        """One tool has finished. Show it only if the page still asked it.

        Somebody can change the form while the tool is working; an answer
        arriving afterwards describes the old parameters and would be read as
        describing the new ones, so it is dropped rather than displayed (R08).
        """
        if not self._ours(question):
            return
        self.show_answer(answer)

    def show_answer(self, answer) -> None:
        self._answer = answer
        self._show_the_facts(getattr(answer, "facts", ()))
        self.result.setPlainText(answer.text or tr(self.empty_key))
        self.news.setText(answer.headline)
        self.save_button.setEnabled(bool(answer.payload))

    def _show_the_facts(self, facts) -> None:
        """Draw the tool's own numbers, or draw nothing."""
        from ...widgets import MetricCard

        clear_layout(self.facts.layout())
        for caption, value in facts:
            self.facts.add(MetricCard(str(value), caption, self.tokens))
        self.facts.setVisible(bool(facts))
        self.report_title.setVisible(bool(facts))
        spread(self, self.layout_mode)

    def say(self, message: str) -> None:
        self.news.setText(message)

    def invalidate(self) -> None:
        """Forget an answer that no longer describes what the page is set to.

        Saving is offered separately from running, so the two can drift: pick
        one question, run it, pick another, press Save, and out comes the first
        answer under the second one's name.
        """
        self._answer = None
        self.save_button.setEnabled(False)

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.result.toPlainText())
        self.news.setText(tr("shell.tool.copied"))

    def _save(self) -> None:
        if self._answer is None or not self._answer.payload:
            return
        suggestion = self._answer.suggestion or "wynik.txt"
        folder = last_folder("tool")
        start = f"{folder}/{suggestion}" if folder else suggestion
        path, _ = QFileDialog.getSaveFileName(self, tr("common.save"), start)
        if not path:
            return
        remember_folder("tool", path)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self._answer.payload)
        self.news.setText(tr("common.saved", path=path))

    def needs_a_source(self) -> None:
        """The one refusal a tool makes: it was not told what to look at."""
        self.result.setPlainText(tr("common.nofolder"))
        self.news.setText(tr("common.pickfolder"))
