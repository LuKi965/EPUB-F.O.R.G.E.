"""Putting a question the program cannot answer to the person holding the book.

The rebuild is autonomous everywhere it can justify being autonomous. Where it
cannot — today, a link whose anchor does not exist anywhere — the choice used to
be between guessing and giving up, and this program spent years choosing to
guess quietly. The owner's instruction when F-010 was authorised names the third
option and why it is not a compromise:

    *Jeżeli aplikacja czegoś nie może sama to angażujmy użytkownika … Istotnym
    jest byś nie szedł na ustępstwa wyłącznie po to aby zachować autonomię
    aplikacji w postaci braku interakcji ze strony użytkownika.*

So the window can answer. A person can see the link, its text — for a footnote
that is the number the reader sees — and the anchors the target document really
has, and say where it belongs. That answer is evidence the program does not
have, and a reference resolved with it is genuinely repaired.

**Threading.** The rebuild runs in a worker thread and a dialog may only be
built in the GUI thread. `Ask` bridges the two with a blocking queued signal:
the worker emits, stops, and waits; the GUI thread shows the dialog and drops
the answer into the mailbox it was handed; the worker resumes with it. Anything
that goes wrong on the way — no application, the window already closing, the
question arriving on the GUI thread itself — answers "leave it alone", which is
what the rebuild does with no resolver at all.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QRadioButton,
    QVBoxLayout,
)

from .. import references
from ..references import Decision, Unresolved
from .strings import tr


class AskDialog(QDialog):
    """One unresolvable reference, and the three things that may be done to it."""

    def __init__(self, question: Unresolved, parent=None):
        super().__init__(parent)
        self.question = question
        self.setWindowTitle(tr("ask.title"))
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(9)

        explanation = QLabel(tr("ask.explanation"))
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        # The facts, in the order a person needs them: which link, what it says
        # on the page, where it points, and what is actually there.
        facts = QLabel(
            tr(
                "ask.facts",
                document=question.document,
                reference=question.reference,
                text=question.text or tr("ask.no-text"),
            )
        )
        facts.setWordWrap(True)
        facts.setObjectName("sectionLabel")
        facts.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(facts)

        self.keep_radio = QRadioButton(tr("ask.keep"))
        self.keep_radio.setToolTip(tr("ask.keep.tip"))
        self.keep_radio.setChecked(True)
        layout.addWidget(self.keep_radio)

        self.repoint_radio = QRadioButton(tr("ask.repoint"))
        self.repoint_radio.setToolTip(tr("ask.repoint.tip"))
        self.repoint_radio.setEnabled(bool(question.candidates))
        layout.addWidget(self.repoint_radio)

        self.candidates = QListWidget()
        self.candidates.setToolTip(tr("ask.repoint.tip"))
        self.candidates.addItems(list(question.candidates))
        self.candidates.setEnabled(False)
        self.candidates.setMaximumHeight(150)
        # Choosing an anchor *is* choosing the option, so the list does not sit
        # there dead until the radio button above it is found.
        self.candidates.itemSelectionChanged.connect(self._chose_an_anchor)
        self.repoint_radio.toggled.connect(self.candidates.setEnabled)
        layout.addWidget(self.candidates)

        self.document_radio = QRadioButton(tr("ask.document"))
        self.document_radio.setToolTip(tr("ask.document.tip"))
        layout.addWidget(self.document_radio)

        self.all_check = QCheckBox(tr("ask.all"))
        self.all_check.setToolTip(tr("ask.all.tip"))
        layout.addWidget(self.all_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)

    def _chose_an_anchor(self) -> None:
        if self.candidates.currentItem() is not None:
            self.repoint_radio.setChecked(True)

    def decision(self) -> Decision:
        """What the widgets say, as an answer the rebuild understands.

        Separate from showing the dialog so it can be tested without one being
        put in front of anybody, and so a dialog that is closed rather than
        answered falls through to the safe reading: leave the reference alone.
        """
        everywhere = self.all_check.isChecked()
        if self.document_radio.isChecked():
            return Decision(references.POINT_AT_DOCUMENT, apply_to_all=everywhere)
        chosen = self.candidates.currentItem()
        if self.repoint_radio.isChecked() and chosen is not None:
            # `apply_to_all` is deliberately not passed on: "point this one at
            # `fn-2`" is a statement about one link, and `references.Answers`
            # refuses to make it standing even if it were.
            return Decision(references.REPOINT, fragment=chosen.text())
        return Decision(references.KEEP, apply_to_all=everywhere)


class Ask(QObject):
    """The rebuild's `Resolver`, backed by the window.

    Constructed on the GUI thread and handed to the worker, which calls
    `resolve` from its own. Everything after that is the blocking-queued signal
    doing its job.
    """

    #: (question, mailbox). The mailbox is a plain list the GUI thread appends
    #: the answer to — a queued signal cannot return a value, and one-element
    #: lists are how Qt code has always got around that.
    asked = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.asked.connect(self._show, Qt.BlockingQueuedConnection)

    def resolve(self, question: Unresolved) -> Decision | None:
        if QThread.currentThread() is self.thread():
            # Already on the GUI thread — a blocking queued connection to
            # oneself is a deadlock, and a direct call is what it would have
            # meant anyway. Reached by the tests and by any front end that runs
            # the rebuild without a worker.
            return self._answer(question)
        mailbox: list[Decision] = []
        self.asked.emit(question, mailbox)
        return mailbox[0] if mailbox else None

    def _show(self, question: Unresolved, mailbox: list) -> None:
        mailbox.append(self._answer(question))

    def _answer(self, question: Unresolved) -> Decision:
        dialog = AskDialog(question, self.parent())
        if dialog.exec() != QDialog.Accepted:
            # Closed rather than answered. Not an answer, and not a licence to
            # invent one: the reference stays as the publisher wrote it, and if
            # the mode is strict the book will be refused and say why.
            return Decision()
        return dialog.decision()


__all__ = ["Ask", "AskDialog"]
