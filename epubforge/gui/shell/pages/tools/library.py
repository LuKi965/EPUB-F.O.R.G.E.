"""The library: two questions about a shelf, neither of them changing anything.

*What would this program repair across the whole collection, and how often* —
and *what are these books, and which families of them are thin*. Both read;
neither writes anything except a file somebody explicitly asks for.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QRadioButton

from ....strings import tr
from ....toolwork import library
from ...tokens import Tokens
from .base import ToolPage


class LibraryToolPage(ToolPage):
    def __init__(self, tokens: Tokens) -> None:
        super().__init__(
            tokens, key="shell.tools.library", glyph="library",
            card_key="library.mode", intro_key="library.intro", empty_key="library.empty",
        )
        self.folder = self.add_source("common.folder")
        self.folder.textChanged.connect(lambda _text: self.invalidate())

        self.survey_choice = QRadioButton(tr("library.survey"))
        self.survey_choice.setToolTip(tr("library.survey.tip"))
        self.survey_choice.setAccessibleDescription(tr("library.survey.tip"))
        self.survey_choice.setChecked(True)
        self.body.addWidget(self.survey_choice)

        self.inventory_choice = QRadioButton(tr("library.inventory"))
        self.inventory_choice.setToolTip(tr("library.inventory.tip"))
        self.inventory_choice.setAccessibleDescription(tr("library.inventory.tip"))
        self.body.addWidget(self.inventory_choice)

        self.with_names = QCheckBox(tr("library.withnames"))
        self.with_names.setToolTip(tr("library.withnames.tip"))
        self.with_names.setAccessibleDescription(tr("library.withnames.tip"))
        self.body.addWidget(self.with_names)

        # Anything that changes what a run would produce invalidates the last
        # one, so Save cannot offer yesterday's answer under today's question.
        for widget in (self.survey_choice, self.inventory_choice, self.with_names):
            widget.toggled.connect(lambda _checked: self.invalidate())

        self.run_button = self.add_action("common.run", self.run, primary=True)
        self.end_actions()
        self.finish_building()

    def run(self) -> None:
        folder = self.folder.text().strip()
        if not folder:
            self.needs_a_source()
            return
        inventory = self.inventory_choice.isChecked()
        with_names = self.with_names.isChecked()
        self.run_work(
            lambda tick: library(folder, inventory=inventory, with_names=with_names, tick=tick)
        )
