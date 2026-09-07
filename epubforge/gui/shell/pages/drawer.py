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
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...strings import tr
from .. import icons
from ..options import CATEGORIES, OPTIONS, Option, in_category
from ..responsive import LayoutMode, Panels, spread
from ..tokens import DRAWER_WIDTH, Tokens
from ..widgets import StatusBadge, button, clear_layout, label


class SettingRow(QFrame):
    """One setting: what it is called, what it does, and its control."""

    changed = Signal(str, object)

    def __init__(self, option: Option, value, tokens: Tokens) -> None:
        super().__init__()
        self.option = option
        self.setObjectName("settingRow")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        # Side by side when the drawer is wide enough for both, and stacked
        # when it is not: a combo box with a 150-pixel minimum beside a wrapped
        # Polish sentence leaves the sentence its longest word and the row
        # pushes the list sideways.
        row = Panels(14)
        words_side = QWidget()
        words = QVBoxLayout(words_side)
        words.setContentsMargins(0, 0, 0, 0)
        words.setSpacing(4)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        title = label(tr(option.label_key), "cardTitle", flexible=True)
        # The name takes the row and the badge follows it: without the stretch
        # factor Qt hands the wrapped label its minimum width — the width of
        # its longest word — and a four-word setting name becomes a column.
        heading.addWidget(title, 1)
        if option.risky:
            heading.addWidget(
                StatusBadge(tr("shell.drawer.risky"), "warning", tokens, "warning"), 0
            )
        words.addLayout(heading)
        # The catalogue's help was written for a tooltip: several paragraphs
        # about what a switch does to a book. In a list of forty settings that
        # is a wall, so the row shows the first paragraph and the whole text
        # stays one hover away — nothing is lost, and the list is readable.
        whole = tr(option.help_key)
        first = whole.split("\n\n", 1)[0]
        sentence = label(first, "cardSubtitle", flexible=True)
        sentence.setToolTip(whole)
        words.addWidget(sentence)
        row.add(words_side, 3)
        self.setToolTip(whole)

        self.control = self._control(value, tokens)
        holder = QWidget()
        holding = QHBoxLayout(holder)
        holding.setContentsMargins(0, 0, 0, 0)
        holding.addStretch(1)
        holding.addWidget(self.control, 0, Qt.AlignTop)
        row.add(holder, 1)
        outer.addWidget(row)
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
            combo.setMinimumWidth(150)
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
            spin.setMinimumWidth(110)
            spin.valueChanged.connect(lambda number: self.changed.emit(option.key, number))
            return spin
        edit = QLineEdit(str(value or ""))
        if option.placeholder_key:
            edit.setPlaceholderText(tr(option.placeholder_key))
        edit.setAccessibleName(tr(option.label_key))
        edit.setMinimumWidth(150)
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

        # The category chooser has two shapes. A column of buttons is the right
        # thing when there is room for it beside the list; on a narrow drawer
        # that column is a third of the width, so the same choice becomes a
        # combo box above the list — one that reaches the same seven places and
        # is reachable from the keyboard.
        self.category_combo = QComboBox()
        for name, _glyph, key in CATEGORIES:
            self.category_combo.addItem(tr(key), name)
        self.category_combo.setAccessibleName(tr("shell.drawer.category"))
        self.category_combo.currentIndexChanged.connect(
            lambda _index: self._show_category(self.category_combo.currentData())
        )
        self.category_combo.hide()
        stack.addWidget(self.category_combo)

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
            # Allowed to be narrower than its own label: a `QPushButton` elides
            # what does not fit, and without this the widest category name sets
            # the column's minimum width and pushes its scroll area sideways by
            # exactly the width of a scrollbar.
            item.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            item.setAccessibleName(tr(key))
            item.setToolTip(tr(key))
            item.clicked.connect(lambda _checked=False, target=name: self._show_category(target))
            self._category_buttons.addButton(item)
            self.categories.addWidget(item)
        self.categories.addStretch(1)
        column = QWidget()
        column.setLayout(self.categories)
        # In a scroll area of its own, because a drawer on a 600-pixel screen
        # is shorter than seven buttons: Qt's answer to "not enough room" is to
        # squeeze them past their minimum and print them over each other, which
        # is what a larger font showed. The horizontal bar is off here and only
        # here — a `QPushButton` elides its own label, so nothing is hidden by
        # a narrow column, and a nav column that scrolls sideways is absurd.
        self.category_column = QScrollArea()
        self.category_column.setWidgetResizable(True)
        self.category_column.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.category_column.setFrameShape(QFrame.NoFrame)
        self.category_column.setWidget(column)
        self.category_column.setMinimumWidth(150)
        self.category_column.setMaximumWidth(212)
        body.addWidget(self.category_column)

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

        outer.addWidget(panel, 0)
        self.outer = outer
        self.panel = panel
        self._mode = LayoutMode.WIDE
        self.hide()

    # -- how much of the page it takes --------------------------------------
    def set_mode(self, mode: LayoutMode) -> None:
        """A panel on the right of a wide page; the whole of a narrow one.

        650 px was a fixed width, so on an 800-pixel window the drawer hung
        over the edge and took the Apply button with it. It is a maximum now,
        and the narrow modes give it everything: a settings list is what the
        page is *for* while it is open.
        """
        self._mode = mode
        viewport = self.parentWidget().width() if self.parentWidget() else DRAWER_WIDTH
        if mode is LayoutMode.WIDE:
            width = max(360, min(DRAWER_WIDTH, int(viewport * 0.55)))
            self.panel.setMinimumWidth(width)
            self.panel.setMaximumWidth(width)
            self.outer.setStretch(0, 1)
            self.outer.setStretch(1, 0)
        else:
            self.panel.setMinimumWidth(0)
            self.panel.setMaximumWidth(16777215)
            self.outer.setStretch(0, 0)
            self.outer.setStretch(1, 1)
        narrow = mode is LayoutMode.COMPACT
        self.category_column.setVisible(not narrow)
        self.category_combo.setVisible(narrow)
        self._settle_rows()

    #: A setting row narrower than this puts its control under the sentence.
    #: The drawer's own width decides it: the drawer is a panel on a page, so
    #: the page's mode says nothing about how much room a row in it has.
    ROWS_STACK_BELOW = 520

    def _settle_rows(self) -> None:
        room = self.panel.width() - (self.category_column.width() if
                                     self.category_column.isVisible() else 0)
        spread(
            self.panel,
            LayoutMode.WIDE if room >= self.ROWS_STACK_BELOW else LayoutMode.COMPACT,
        )

    # -- opening and closing ------------------------------------------------
    def open_with(self, defaults: dict, overrides: dict, books: int, opener: QWidget | None = None
                  ) -> None:
        self._defaults = dict(defaults)
        self._values = {**defaults, **overrides}
        self._opener = opener
        self.subtitle.setText(tr("shell.drawer.subtitle", count=books))
        self.setGeometry(self.parentWidget().rect())
        self.set_mode(getattr(self.parentWidget(), "layout_mode", LayoutMode.WIDE))
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
        if name == self._category:
            return
        self._category = name
        index = self.category_combo.findData(name)
        if index >= 0 and index != self.category_combo.currentIndex():
            self.category_combo.setCurrentIndex(index)
        for item in self._category_buttons.buttons():
            if item.text() == dict((n, tr(k)) for n, _g, k in CATEGORIES)[name]:
                item.setChecked(True)
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
            self.rows.addWidget(label(tr(name), "sectionTitle", flexible=True))
            self.rows.addWidget(label(tr(f"{name}.body"), "cardSubtitle", flexible=True))

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
        self._settle_rows()
        self._update_count()

    def _toggle_expert(self) -> None:
        self._expert = not self._expert
        self._draw()
