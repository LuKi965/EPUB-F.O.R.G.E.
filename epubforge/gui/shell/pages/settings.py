"""Settings: the application's own preferences, and nothing about one rebuild.

The line this page holds is the design specification's: *settings for one
rebuild do not belong in global settings.* There is not a single `Policy` field
here — those live in the plan's drawer, where they belong to the batch that is
about to run rather than to the program for ever.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ...strings import LANGUAGES, tr
from ..tokens import CARD_GAP, CONTENT_MARGIN, Tokens
from ..widgets import Card, PageHeader, button, label

THEMES = ("system", "light", "dark")


class Row(QFrame):
    """One preference: name, sentence, control."""

    def __init__(self, title: str, description: str, control: QWidget) -> None:
        super().__init__()
        self.setObjectName("settingRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(14)
        words = QVBoxLayout()
        words.setSpacing(3)
        words.addWidget(label(title, "cardTitle"))
        words.addWidget(label(description, "cardSubtitle"))
        row.addLayout(words, 1)
        row.addWidget(control, 0, Qt.AlignTop)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)


class SettingsPage(QWidget):
    language_changed = Signal(str)
    theme_changed = Signal(str)
    remember_changed = Signal(bool)
    about_requested = Signal()

    def __init__(self, tokens: Tokens, *, language: str = "pl", theme: str = "system",
                 remember: bool = True) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(CONTENT_MARGIN, 24, CONTENT_MARGIN, 22)
        layout.setSpacing(CARD_GAP)
        layout.addWidget(
            PageHeader(tr("shell.settings.eyebrow"), tr("shell.settings.title"),
                       tr("shell.settings.subtitle"))
        )

        card = Card(tr("shell.settings.general"), glyph="settings", tokens=tokens)

        self.language = QComboBox()
        for code in LANGUAGES:
            self.language.addItem(tr(f"language.{code}"), code)
        self.language.setCurrentIndex(max(0, list(LANGUAGES).index(language)))
        self.language.setAccessibleName(tr("shell.settings.language"))
        self.language.currentIndexChanged.connect(
            lambda _index: self.language_changed.emit(self.language.currentData())
        )
        card.body.addWidget(
            Row(tr("shell.settings.language"), tr("shell.settings.language.body"), self.language)
        )

        self.theme = QComboBox()
        for name in THEMES:
            self.theme.addItem(tr(f"shell.settings.theme.{name}"), name)
        self.theme.setCurrentIndex(THEMES.index(theme) if theme in THEMES else 0)
        self.theme.setAccessibleName(tr("shell.settings.theme"))
        self.theme.currentIndexChanged.connect(
            lambda _index: self.theme_changed.emit(self.theme.currentData())
        )
        card.body.addWidget(
            Row(tr("shell.settings.theme"), tr("shell.settings.theme.body"), self.theme)
        )

        self.remember = QCheckBox()
        self.remember.setChecked(remember)
        self.remember.setAccessibleName(tr("shell.settings.remember"))
        self.remember.toggled.connect(self.remember_changed)
        card.body.addWidget(
            Row(tr("shell.settings.remember"), tr("shell.settings.remember.body"), self.remember)
        )

        about = button(tr("shell.settings.about.open"), glyph="book", tokens=tokens)
        about.clicked.connect(self.about_requested)
        card.body.addWidget(
            Row(tr("shell.settings.about"), tr("shell.settings.about.body"), about)
        )
        card.body.addWidget(label(tr("shell.settings.restart"), "muted"))
        card.body.addStretch(1)
        layout.addWidget(card, 1)
