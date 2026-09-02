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
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QRadioButton,
    QVBoxLayout,
)

from .. import decisions, references
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


class DecideDialog(QDialog):
    """Any question at all, in the one shape they now share.

    BA-2026-002 asked for broken links, hard hyphens and metadata conflicts on a
    common API, and this is the front end half of it: a question carries its own
    options, each with the sentence saying what it does to the book, so a new
    class of question needs no new dialog. The list of anchors in `AskDialog`
    above is the one thing that could not be generalised — it is a chooser over
    the target document's ids, which no other question has — so that dialog
    stays for references and this one serves everything else.
    """

    def __init__(self, question, parent=None):
        super().__init__(parent)
        self.question = question
        self.setWindowTitle(tr("decide.title"))
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(9)

        summary = QLabel(question.summary)
        summary.setWordWrap(True)
        summary.setObjectName("sectionLabel")
        layout.addWidget(summary)

        detail = QLabel(question.detail)
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(detail)

        # The picture the question is about, when it carries one. A person
        # asked to describe a picture has to see it (record 039, the owner's
        # answer): the file name, the pixel size and the weight say what the
        # evidence was, and the picture says what the picture is. Scaled to
        # fit, never enlarged — a twelve-pixel scroll blown up to a screen
        # would look like something it is not.
        self.preview = None
        pixmap = _pixmap_of(getattr(question, "preview", None))
        if pixmap is not None:
            self.preview = QLabel()
            self.preview.setPixmap(pixmap)
            self.preview.setAlignment(Qt.AlignCenter)
            self.preview.setToolTip(tr("decide.preview"))
            layout.addWidget(self.preview)

        self.buttons_for = {}
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText(tr("decide.value"))
        self.value_edit.setEnabled(False)
        for option in question.options:
            radio = QRadioButton(option.label)
            # The consequence, on the control itself. A person choosing between
            # "keep" and "join" needs to know what the page will say afterwards,
            # and that sentence travels with the question rather than being
            # written into the window.
            radio.setToolTip(option.consequence)
            radio.setChecked(option.id == question.recommended)
            layout.addWidget(radio)
            self.buttons_for[option.id] = radio
            if option.needs_value:
                radio.toggled.connect(self.value_edit.setEnabled)
                layout.addWidget(self.value_edit)

        # Said out loud rather than left to the tooltip: this is the field a
        # person weighs against the recommendation.
        if not question.reversible:
            warning = QLabel(tr("decide.irreversible"))
            warning.setWordWrap(True)
            warning.setObjectName("sectionLabel")
            layout.addWidget(warning)

        self.all_check = QCheckBox(tr("decide.all"))
        self.all_check.setToolTip(tr("decide.all.tip"))
        self.all_check.setEnabled(bool(question.group))
        layout.addWidget(self.all_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)

    def answer(self):
        chosen = next(
            (
                option_id
                for option_id, radio in self.buttons_for.items()
                if radio.isChecked()
            ),
            decisions.KEEP,
        )
        return decisions.Answer(
            option=chosen,
            value=self.value_edit.text().strip(),
            apply_to_group=self.all_check.isChecked(),
        )


#: The box a preview is scaled into. Wide enough for a chapter ornament to be
#: recognisable, small enough that a full-page plate does not push the
#: options off the screen.
PREVIEW_BOX = 360


def _pixmap_of(preview) -> "QPixmap | None":
    """A pixmap for a question's preview, scaled to fit, or None.

    None whenever the bytes cannot be drawn — a format Qt has no plugin for,
    a broken file, no preview at all. The question is then shown without a
    picture rather than not shown, which is the same rule the front end
    applies to everything it cannot render.
    """
    if preview is None or not getattr(preview, "data", None):
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(preview.data) or pixmap.isNull():
        return None
    if pixmap.width() > PREVIEW_BOX or pixmap.height() > PREVIEW_BOX:
        pixmap = pixmap.scaled(
            PREVIEW_BOX, PREVIEW_BOX, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
    return pixmap


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
    #: The same arrangement for a question of any other kind.
    decided = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.asked.connect(self._show, Qt.BlockingQueuedConnection)
        self.decided.connect(self._show_decision, Qt.BlockingQueuedConnection)

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

    def ask(self, question):
        """The generic half — `decisions.Asker`, same threading, same rules."""
        if QThread.currentThread() is self.thread():
            return self._decide(question)
        mailbox: list = []
        self.decided.emit(question, mailbox)
        return mailbox[0] if mailbox else None

    def _show_decision(self, question, mailbox: list) -> None:
        mailbox.append(self._decide(question))

    def _decide(self, question):
        dialog = DecideDialog(question, self.parent())
        if dialog.exec() != QDialog.Accepted:
            # Closed rather than answered, and that is not the recommendation
            # being accepted by default. A question this program recommends
            # joining stays unjoined until somebody says so.
            return None
        return dialog.answer()

    def _answer(self, question: Unresolved) -> Decision:
        dialog = AskDialog(question, self.parent())
        if dialog.exec() != QDialog.Accepted:
            # Closed rather than answered. Not an answer, and not a licence to
            # invent one: the reference stays as the publisher wrote it, and if
            # the mode is strict the book will be refused and say why.
            return Decision()
        return dialog.decision()


__all__ = ["Ask", "AskDialog", "DecideDialog"]
