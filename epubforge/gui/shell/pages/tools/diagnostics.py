"""Diagnostics: five questions about a file, none of which changes it.

The owner's rule, and it applies to the debugging things as much as to the
switches: *everything has to be in the window.* He runs the Windows build. A
command that answers "what is actually inside this file" and one that answers
"does a validator accept it" are exactly what a person reaches for when a book
comes out wrong, and both were once reachable only from a terminal.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QRadioButton

from ....strings import tr
from ....toolwork import books_for, diagnose
from ...responsive import Cards, LayoutMode
from ...tokens import Tokens
from .base import ToolPage

#: The five, in the order the panel has always shown them, with the key each
#: one's label and explanation live under. `render` is last because it is the
#: only one that needs something the program does not ship.
QUESTIONS = (
    ("inspect", "diagnostics.inspect"),
    ("validate", "diagnostics.validate"),
    ("fidelity", "diagnostics.fidelity"),
    ("health", "diagnostics.health"),
    ("render", "diagnostics.render"),
)


class DiagnosticsToolPage(ToolPage):
    def __init__(self, tokens: Tokens) -> None:
        super().__init__(
            tokens, key="shell.tools.diagnostics", glyph="inspect",
            card_key="diagnostics.mode", intro_key="diagnostics.intro",
            empty_key="diagnostics.empty",
        )
        self.folder = self.add_source(
            "diagnostics.files", placeholder=tr("shell.tool.source.file"), files=True
        )
        self.folder.textChanged.connect(lambda _text: self.invalidate())

        # Two columns of questions when there is room, one when there is not.
        grid = Cards({LayoutMode.WIDE: 2, LayoutMode.MEDIUM: 2, LayoutMode.COMPACT: 1}, 8)
        self.choices = {}
        for name, key in QUESTIONS:
            choice = QRadioButton(tr(key))
            choice.setToolTip(tr(f"{key}.tip"))
            choice.setAccessibleDescription(tr(f"{key}.tip"))
            choice.toggled.connect(lambda _checked: self.invalidate())
            self.choices[name] = choice
            grid.add(choice)
        self.choices["inspect"].setChecked(True)
        self.body.addWidget(grid)

        # Reachable from the window, because everything in this program is —
        # including the switch that turns an optimisation off. "Is it the new
        # fast path?" is the first question worth asking about a verdict that
        # surprises somebody.
        self.shared_validator = QCheckBox(tr("diagnostics.shared"))
        self.shared_validator.setToolTip(tr("diagnostics.shared.tip"))
        self.shared_validator.setAccessibleDescription(tr("diagnostics.shared.tip"))
        self.shared_validator.setChecked(True)
        self.body.addWidget(self.shared_validator)

        self.run_button = self.add_action("common.run", self.run, primary=True)
        self.end_actions()
        self.finish_building()

    @property
    def question(self) -> str:
        for name, _key in QUESTIONS:
            if self.choices[name].isChecked():
                return name
        return "inspect"

    def run(self) -> None:
        books = books_for(self.folder.text().strip())
        if not books:
            self.needs_a_source()
            return
        question = self.question
        shared = self.shared_validator.isChecked()
        self.run_work(lambda tick: diagnose(books, question, shared=shared, tick=tick))
