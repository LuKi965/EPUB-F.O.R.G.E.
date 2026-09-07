"""The advanced drawer: everything the program can do, once you ask for it.

The main path shows three presets. This is where the other forty-odd choices
live — grouped by consequence, searchable, and each one carrying the sentence
the old window kept in a tooltip. What comes out of it is not a policy: it is
the *difference* from the preset, which is the only thing worth remembering
and the only thing worth showing as "3 changed settings".
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...strings import tr
from .. import icons
from ..options import CATEGORIES, OPTIONS, Option, in_category
from ..tokens import DRAWER_WIDTH, Tokens
from ..widgets import StatusBadge, button, clear_layout, label


class SettingRow(QFrame):
    """One setting: what it is called, what it does, and its control."""

    changed = Signal(str, object)

    def __init__(self, option: Option, value, tokens: Tokens) -> None:
        super().__init__()
        self.option = option
        self.setObjectName("settingRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(14)

        words = QVBoxLayout()
        words.setSpacing(4)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        title = label(tr(option.label_key), "cardTitle")
        heading.addWidget(title)
        if option.risky:
            heading.addWidget(StatusBadge(tr("shell.drawer.risky"), "warning", tokens, "warning"))
        heading.addStretch(1)
        words.addLayout(heading)
        # The catalogue's help was written for a tooltip: several paragraphs
        # about what a switch does to a book. In a list of forty settings that
        # is a wall, so the row shows the first paragraph and the whole text
        # stays one hover away — nothing is lost, and the list is readable.
        whole = tr(option.help_key)
        first = whole.split("\n\n", 1)[0]
        sentence = label(first, "cardSubtitle")
        sentence.setToolTip(whole)
        words.addWidget(sentence)
        row.addLayout(words, 1)
        self.setToolTip(whole)

        self.control = self._control(value, tokens)
        row.addWidget(self.control, 0, Qt.AlignTop)
        self.setAccessibleName(tr(option.label_key))
        self.setAccessibleDescription(tr(option.help_key))

    def _control(self, value, tokens: Tokens) -> QWidget:
        option = self.option
        if option.kind == "bool":
            box = QCheckBox()
            box.setChecked(bool(value))
            box.setAccessibleName(tr(option.label_key))
            box.setAccessibleDescription(tr(option.help_key))
            box.toggled.connect(lambda state: self.changed.emit(option.key, state))
            return box
        if option.kind == "choice":
            combo = QComboBox()
            for choice in option.choices:
                combo.addItem(tr(f"{option.label_key}.{choice}"), choice)
                index = combo.count() - 1
                tip = tr(f"{option.label_key}.{choice}.tip")
                if tip != f"{option.label_key}.{choice}.tip":
                    combo.setItemData(index, tip, Qt.ToolTipRole)
            if value in option.choices:
                combo.setCurrentIndex(option.choices.index(value))
            combo.setAccessibleName(tr(option.label_key))
            combo.setMinimumWidth(190)
            combo.currentIndexChanged.connect(
                lambda _index: self.changed.emit(option.key, combo.currentData())
            )
            return combo
        if option.kind == "int":
            spin = QSpinBox()
            spin.setRange(option.minimum, option.maximum)
            spin.setSingleStep(option.step)
            spin.setValue(int(value or option.minimum))
            spin.setSuffix(" s")
            spin.setAccessibleName(tr(option.label_key))
            spin.setMinimumWidth(140)
            spin.valueChanged.connect(lambda number: self.changed.emit(option.key, number))
            return spin
        edit = QLineEdit(str(value or ""))
        if option.placeholder_key:
            edit.setPlaceholderText(tr(option.placeholder_key))
        edit.setAccessibleName(tr(option.label_key))
        edit.setMinimumWidth(190)
        edit.textChanged.connect(lambda text: self.changed.emit(option.key, text))
        return edit


class SettingsDrawer(QWidget):
    """A modal panel over the page it belongs to.

    Modal by behaviour rather than by being a `QDialog`: it dims the page,
    takes the keyboard, closes on Escape and hands focus back to the button
    that opened it — which is what the acceptance list asks for and what a
    separate window would get wrong on a multi-monitor desk.
    """

    applied = Signal(dict)
    closed = Signal()

    def __init__(self, parent: QWidget, tokens: Tokens) -> None:
        super().__init__(parent)
        self.setObjectName("overlay")
        # A plain QWidget does not paint a stylesheet background; without this
        # the "modal" overlay dims nothing and the page behind stays as bright
        # as the drawer in front of it.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.tokens = tokens
        self._defaults: dict = {}
        self._values: dict = {}
        self._category = CATEGORIES[0][0]
        self._expert = False
        self._search = ""
        self._opener: QWidget | None = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        panel = QFrame()
        panel.setObjectName("drawer")
        panel.setFixedWidth(DRAWER_WIDTH)
        stack = QVBoxLayout(panel)
        stack.setContentsMargins(22, 20, 22, 18)
        stack.setSpacing(12)

        top = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label(tr("shell.drawer.title"), "sectionTitle"))
        self.subtitle = label("", "pageSubtitle")
        titles.addWidget(self.subtitle)
        top.addLayout(titles, 1)
        close = button("", kind="ghost", glyph="close", tokens=tokens,
                       tip=tr("shell.drawer.close"))
        close.setAccessibleName(tr("shell.drawer.close"))
        close.clicked.connect(self.close_drawer)
        top.addWidget(close, 0, Qt.AlignTop)
        stack.addLayout(top)

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("shell.drawer.search"))
        self.search.setAccessibleName(tr("shell.drawer.search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._searched)
        tools.addWidget(self.search, 1)
        reset = button(tr("shell.drawer.reset"), kind="ghost", glyph="restore", tokens=tokens)
        reset.clicked.connect(self._reset)
        tools.addWidget(reset)
        stack.addLayout(tools)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.categories = QVBoxLayout()
        self.categories.setSpacing(4)
        self._category_buttons = QButtonGroup(self)
        self._category_buttons.setExclusive(True)
        for name, glyph, key in CATEGORIES:
            item = QPushButton(tr(key))
            item.setObjectName("nav")
            item.setCheckable(True)
            item.setChecked(name == self._category)
            item.setIcon(icons.icon(glyph, tokens.muted))
            item.setMinimumHeight(40)
            item.setAccessibleName(tr(key))
            item.clicked.connect(lambda _checked=False, target=name: self._show_category(target))
            self._category_buttons.addButton(item)
            self.categories.addWidget(item)
        self.categories.addStretch(1)
        column = QWidget()
        column.setLayout(self.categories)
        column.setFixedWidth(212)
        body.addWidget(column)

        self.list_area = QScrollArea()
        self.list_area.setWidgetResizable(True)
        holder = QWidget()
        self.rows = QVBoxLayout(holder)
        self.rows.setContentsMargins(0, 0, 8, 0)
        self.rows.setSpacing(10)
        self.list_area.setWidget(holder)
        body.addWidget(self.list_area, 1)
        stack.addLayout(body, 1)

        footer = QHBoxLayout()
        self.changed_label = label("", "muted")
        footer.addWidget(self.changed_label, 1)
        cancel = button(tr("shell.drawer.cancel"))
        cancel.clicked.connect(self.close_drawer)
        footer.addWidget(cancel)
        apply_button = button(tr("shell.drawer.apply"), kind="primary", glyph="check", tokens=tokens)
        apply_button.clicked.connect(self._apply)
        footer.addWidget(apply_button)
        stack.addLayout(footer)

        note = label(tr("shell.drawer.footer"), "muted")
        stack.addWidget(note)

        outer.addWidget(panel)
        self.panel = panel
        self.hide()

    # -- opening and closing ------------------------------------------------
    def open_with(self, defaults: dict, overrides: dict, books: int, opener: QWidget | None = None
                  ) -> None:
        self._defaults = dict(defaults)
        self._values = {**defaults, **overrides}
        self._opener = opener
        self.subtitle.setText(tr("shell.drawer.subtitle", count=books))
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._draw()
        self.search.setFocus(Qt.OtherFocusReason)

    def close_drawer(self) -> None:
        self.hide()
        self.closed.emit()
        if self._opener is not None:
            self._opener.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt casing
        if event.key() == Qt.Key_Escape:
            self.close_drawer()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- state --------------------------------------------------------------
    def _searched(self, text: str) -> None:
        self._search = text.strip().lower()
        self._draw()

    def _show_category(self, name: str) -> None:
        self._category = name
        self._draw()

    def _reset(self) -> None:
        self._values = dict(self._defaults)
        self._draw()

    def _changed(self, key: str, value) -> None:
        self._values[key] = value
        self._update_count()

    def overrides(self) -> dict:
        """Only the deviations. Equal values are not overrides."""
        return {
            key: value for key, value in self._values.items()
            if key in self._defaults and value != self._defaults[key]
        }

    def _update_count(self) -> None:
        count = len(self.overrides())
        self.changed_label.setText(tr("shell.drawer.changed", count=count) if count else "")

    def _apply(self) -> None:
        self.applied.emit(self.overrides())
        self.close_drawer()

    # -- drawing ------------------------------------------------------------
    def _matching(self) -> "list[Option]":
        if self._search:
            return [
                option for option in OPTIONS
                if self._search in
                f"{tr(option.label_key)} {tr(option.help_key)}".lower()
            ]
        everyday = list(in_category(self._category))
        if self._expert:
            everyday += list(in_category(self._category, expert=True))
        return everyday

    def _draw(self) -> None:
        clear_layout(self.rows)
        if not self._search:
            name = dict((entry[0], entry[2]) for entry in CATEGORIES)[self._category]
            self.rows.addWidget(label(tr(name), "sectionTitle"))
            self.rows.addWidget(label(tr(f"{name}.body"), "cardSubtitle"))

        options = self._matching()
        if not options:
            self.rows.addWidget(label(tr("shell.drawer.none", text=self._search), "muted"))
            self.rows.addStretch(1)
            self._update_count()
            return

        for option in options:
            row = SettingRow(option, self._values.get(option.key), self.tokens)
            row.changed.connect(self._changed)
            self.rows.addWidget(row)

        if not self._search and in_category(self._category, expert=True):
            toggle = button(
                tr("shell.drawer.expert.hide") if self._expert else tr("shell.drawer.expert"),
                kind="ghost", glyph="expert", tokens=self.tokens,
            )
            toggle.clicked.connect(self._toggle_expert)
            self.rows.addWidget(toggle)
        self.rows.addStretch(1)
        self._update_count()

    def _toggle_expert(self) -> None:
        self._expert = not self._expert
        self._draw()
