"""Shared components. They render models and emit intent; they do no work.

Every clickable thing here is reachable from the keyboard, carries an
accessible name, and states its status in three ways at once — colour, glyph
and word — because the acceptance list says a status may never be carried by
colour alone and because that is simply true for the person reading it.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..strings import tr
from . import icons
from .models import STATUS_LOOK, BookItem, BookStatus, Preset, Stage
from .tokens import SIDEBAR_COMPACT_WIDTH, SIDEBAR_WIDTH, Tokens


def label(text: str, object_name: str = "", *, wrap: bool = True) -> QLabel:
    item = QLabel(text)
    if object_name:
        item.setObjectName(object_name)
    item.setWordWrap(wrap)
    return item


def button(text: str, *, kind: str = "", glyph: str = "", tokens: Tokens | None = None,
           tip: str = "") -> QPushButton:
    """A button with an optional glyph, an accessible name and a tooltip."""
    item = QPushButton(text)
    if kind:
        item.setObjectName(kind)
    if glyph and tokens is not None:
        colour = tokens.accent_text if kind == "primary" else tokens.text
        item.setIcon(icons.icon(glyph, colour))
        item.setIconSize(QSize(16, 16))
    item.setAccessibleName(text)
    if tip:
        item.setToolTip(tip)
        item.setAccessibleDescription(tip)
    item.setCursor(Qt.PointingHandCursor)
    return item


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("separator")
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    return line


def clear_layout(layout) -> None:
    """Empty a layout, deleting what was in it.

    The pages of the rebuild flow are rebuilt rather than mutated: four states
    that share a frame, each drawing itself from the session. Anything left
    behind would keep receiving signals it no longer understands.
    """
    while layout.count():
        child = layout.takeAt(0)
        widget = child.widget()
        if widget is not None:
            # Both, and in this order: unparenting takes it off the screen now,
            # `deleteLater` frees it when Qt is next idle. Asking `child` for
            # the widget a second time answers `None` — the item no longer has
            # one — which is how the first version of this crashed.
            widget.setParent(None)
            widget.deleteLater()
            continue
        inner = child.layout()
        if inner is not None:
            clear_layout(inner)
            inner.deleteLater()


def scrolling_body(spacing: int = 14):
    """A vertical layout that scrolls when the window is shorter than it.

    The layouts are drawn for 1536×960 and have to survive 1100×700, which is
    the smallest supported window. Without this, Qt squeezes cards below their
    own minimum and widgets overlap — the "Save report" button printed across
    the one above it, which is what this replaces.

    Returns `(scroll_area, layout)`; put the page's content in the layout and
    the scroll area in the page.
    """
    from PySide6.QtWidgets import QScrollArea

    holder = QWidget()
    body = QVBoxLayout(holder)
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(spacing)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(holder)
    return area, body


class Card(QFrame):
    """A titled surface. The one container this interface has."""

    def __init__(self, title: str = "", subtitle: str = "", *, glyph: str = "",
                 tokens: Tokens | None = None) -> None:
        super().__init__()
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(10)
        if title:
            heading = QHBoxLayout()
            heading.setSpacing(8)
            if glyph and tokens is not None:
                mark = QLabel()
                mark.setPixmap(icons.icon(glyph, tokens.muted).pixmap(18, 18))
                heading.addWidget(mark, 0, Qt.AlignTop)
            heading.addWidget(label(title, "cardTitle"), 1)
            self.body.addLayout(heading)
        if subtitle:
            self.body.addWidget(label(subtitle, "cardSubtitle"))

    def add(self, widget) -> None:
        self.body.addWidget(widget)


class PageHeader(QWidget):
    """Eyebrow, title, one sentence. The same shape on every page."""

    def __init__(self, eyebrow: str, title: str, subtitle: str) -> None:
        super().__init__()
        stack = QVBoxLayout(self)
        stack.setContentsMargins(0, 0, 0, 4)
        stack.setSpacing(4)
        self.eyebrow = label(eyebrow, "eyebrow")
        self.title = label(title, "pageTitle")
        self.subtitle = label(subtitle, "pageSubtitle")
        stack.addWidget(self.eyebrow)
        stack.addWidget(self.title)
        stack.addWidget(self.subtitle)

    def retitle(self, title: str, subtitle: str = "") -> None:
        self.title.setText(title)
        if subtitle:
            self.subtitle.setText(subtitle)


class Sidebar(QWidget):
    """Five destinations, the last one anchored at the bottom.

    No decorative tile: the design package forbids it twice, and the reason is
    good — the window already carries the application icon in its title bar and
    its taskbar button, so a second one inside the window is decoration wearing
    the clothes of navigation.
    """

    route_requested = Signal(str)

    ROUTES = (
        ("home", "home", "shell.nav.home"),
        ("rebuild", "rebuild", "shell.nav.rebuild"),
        ("tools", "tools", "shell.nav.tools"),
        ("history", "history", "shell.nav.history"),
    )

    def __init__(self, tokens: Tokens, version: str) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.tokens = tokens
        self._compact = False
        self.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(6)

        self.brand = label("EPUB F.O.R.G.E.", "brand")
        self.version = label(version, "version")
        layout.addWidget(self.brand)
        layout.addWidget(self.version)
        layout.addSpacing(20)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for route, glyph, key in self.ROUTES:
            layout.addWidget(self._nav_button(route, glyph, key))
        layout.addStretch(1)
        layout.addWidget(self._nav_button("settings", "settings", "shell.nav.settings"))
        self.tagline = label(tr("shell.tagline"), "tagline")
        layout.addWidget(self.tagline)
        self.set_active("home")

    def _nav_button(self, route: str, glyph: str, key: str) -> QPushButton:
        item = QPushButton(tr(key))
        item.setObjectName("nav")
        item.setCheckable(True)
        item.setIcon(icons.icon(glyph, self.tokens.muted))
        item.setIconSize(QSize(17, 17))
        item.setMinimumHeight(42)
        item.setCursor(Qt.PointingHandCursor)
        item.setAccessibleName(tr(key))
        item.setToolTip(tr(key))
        item.clicked.connect(lambda _checked=False, name=route: self.route_requested.emit(name))
        self.group.addButton(item)
        self.buttons[route] = item
        return item

    def set_active(self, route: str) -> None:
        item = self.buttons.get(route)
        if item is not None:
            item.setChecked(True)

    def set_compact(self, compact: bool) -> None:
        """Icons only, for windows too narrow to spend 244 px on names."""
        if compact == self._compact:
            return
        self._compact = compact
        self.setFixedWidth(SIDEBAR_COMPACT_WIDTH if compact else SIDEBAR_WIDTH)
        for route, _glyph, key in (*self.ROUTES, ("settings", "settings", "shell.nav.settings")):
            item = self.buttons[route]
            item.setText("" if compact else tr(key))
        for widget in (self.brand, self.version, self.tagline):
            widget.setVisible(not compact)


class Stepper(QWidget):
    """Pliki → Analiza → Plan przebudowy → Wyniki.

    A done step says so with a tick as well as a colour; the current one is
    outlined as well as filled. Each step is a label with an accessible name,
    so a screen reader reads "krok 2 z 4, Analiza, w toku" rather than a glyph.
    """

    KEYS = ("shell.step.files", "shell.step.analysis", "shell.step.plan", "shell.step.results")

    def __init__(self, tokens: Tokens) -> None:
        super().__init__()
        self.tokens = tokens
        self._labels: list[QLabel] = []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)
        for index, key in enumerate(self.KEYS):
            item = QLabel(f"{index + 1}   {tr(key)}")
            item.setAlignment(Qt.AlignCenter)
            item.setMinimumHeight(40)
            item.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._labels.append(item)
            row.addWidget(item, 1)
        self.set_stage(Stage.FILES)

    def set_stage(self, stage: Stage) -> None:
        current = stage.step
        for index, item in enumerate(self._labels):
            name = tr(self.KEYS[index])
            done = index < current
            item.setText(("✓   " if done else f"{index + 1}   ") + name)
            if done:
                item.setStyleSheet(f"color:{self.tokens.success}; font-weight:700;")
                state = tr("shell.step.done")
            elif index == current:
                item.setStyleSheet(
                    f"background:{self.tokens.accent_wash}; border:1px solid {self.tokens.accent};"
                    f" border-radius:9px; font-weight:700;"
                )
                state = tr("shell.step.current")
            else:
                item.setStyleSheet(f"color:{self.tokens.muted};")
                state = tr("shell.step.todo")
            item.setAccessibleName(
                tr("shell.step.reader", index=index + 1, total=len(self._labels), name=name, state=state)
            )


class StatusBadge(QWidget):
    """Colour, glyph and word. Never fewer than all three.

    Sized to its text and no wider: an earlier version let the chip stretch,
    and a warning badge beside a heading ate two thirds of the row, wrapping
    the name of the setting into a column four words deep.
    """

    def __init__(self, text: str, role: str, tokens: Tokens, glyph: str = "check") -> None:
        super().__init__()
        colour = getattr(tokens, role if role != "muted" else "muted")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        chip = QLabel(f'{icons.rich(glyph, colour, 14)}&nbsp; {text}')
        chip.setTextFormat(Qt.RichText)
        chip.setStyleSheet(
            f"color:{colour}; background:{_wash(tokens, role)}; border:1px solid {colour};"
            " border-radius:11px; padding:4px 10px; font-weight:650;"
        )
        chip.setAccessibleName(text)
        chip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        row.addWidget(chip)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAccessibleName(text)


def _wash(tokens: Tokens, role: str) -> str:
    return {
        "success": tokens.success_wash,
        "warning": tokens.warning_wash,
        "danger": tokens.danger_wash,
        "accent": tokens.accent_wash,
    }.get(role, tokens.surface_2)


def status_badge(status: BookStatus, tokens: Tokens) -> StatusBadge:
    glyph, role = STATUS_LOOK[status]
    return StatusBadge(tr(f"shell.status.{status.value}"), role, tokens, glyph)


class MetricCard(QFrame):
    """One number and what it counts, for the results banner."""

    def __init__(self, value: str, caption: str, tokens: Tokens, role: str = "text",
                 glyph: str = "") -> None:
        super().__init__()
        self.setObjectName("metricCard")
        stack = QVBoxLayout(self)
        stack.setContentsMargins(14, 12, 14, 12)
        stack.setSpacing(2)
        head = QLabel(
            (icons.rich(glyph, getattr(tokens, role), 16) + "&nbsp; " if glyph else "") + value
        )
        head.setTextFormat(Qt.RichText)
        head.setObjectName("metric")
        head.setAlignment(Qt.AlignCenter)
        head.setStyleSheet(f"color:{getattr(tokens, role)};")
        stack.addWidget(head)
        words = label(caption, "muted")
        words.setAlignment(Qt.AlignCenter)
        stack.addWidget(words)
        # Two lines of caption is normal in Polish ("Naprawione problemy") and
        # the card must have room for them rather than clipping the second.
        self.setMinimumHeight(84)
        self.setAccessibleName(f"{value} {caption}")


class SafetyNote(QFrame):
    """The sentence that has to be visible before anything is written."""

    def __init__(self, tokens: Tokens, title: str = "", body: str = "") -> None:
        super().__init__()
        self.setObjectName("successCard")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(icons.icon("shield", tokens.success).pixmap(22, 22))
        row.addWidget(mark, 0, Qt.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(3)
        words.addWidget(label(title or tr("shell.safety.title"), "cardTitle"))
        words.addWidget(label(body or tr("shell.safety.body"), "cardSubtitle"))
        row.addLayout(words, 1)
        self.setAccessibleName(title or tr("shell.safety.title"))


class Clickable(QFrame):
    """A card that behaves like a button: focus ring, Space and Enter, name."""

    activated = Signal()

    def __init__(self, object_name: str) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt casing
        self.setFocus(Qt.MouseFocusReason)
        self.activated.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.activated.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class PresetCard(Clickable):
    """One of the three understandable choices."""

    chosen = Signal(object)

    def __init__(self, preset: Preset, title: str, description: str, tokens: Tokens,
                 *, recommended: bool = False, selected: bool = False) -> None:
        super().__init__("preset")
        self.preset = preset
        stack = QVBoxLayout(self)
        stack.setContentsMargins(15, 14, 15, 14)
        stack.setSpacing(8)
        stack.addWidget(label(title, "cardTitle"))
        if recommended:
            stack.addWidget(StatusBadge(tr("shell.preset.recommended"), "success", tokens))
        stack.addWidget(label(description, "cardSubtitle"))
        stack.addStretch(1)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.set_selected(selected)
        self.activated.connect(lambda: self.chosen.emit(self.preset))


class BookRow(Clickable):
    """One book in the plan, or one book in the results.

    The same row in both places on purpose: it is the same book, and a person
    who learned to read it once should not have to learn a second table.
    """

    removed = Signal(object)
    toggled = Signal(object, bool)
    opened = Signal(object)

    def __init__(self, book: BookItem, tokens: Tokens, *, results: bool = False) -> None:
        super().__init__("bookRow")
        self.book = book
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(14)

        if not results:
            self.choose = QCheckBox()
            self.choose.setChecked(book.chosen)
            self.choose.setAccessibleName(tr("shell.plan.include", title=book.title))
            self.choose.toggled.connect(lambda state: self.toggled.emit(self.book, state))
            row.addWidget(self.choose)

        mark = QLabel()
        mark.setPixmap(icons.icon("book", tokens.muted).pixmap(22, 22))
        mark.setFixedWidth(26)
        row.addWidget(mark)

        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(label(book.title, "cardTitle"))
        meta = "  ·  ".join(part for part in (book.author, book.kind, book.size_text) if part)
        names.addWidget(label(meta, "muted"))
        if results and book.output:
            names.addWidget(label(str(book.output), "muted"))
        row.addLayout(names, 3)

        if book.summary or book.error:
            row.addWidget(label(book.error or book.summary, "muted"), 2)

        row.addWidget(status_badge(book.status, tokens))

        if results:
            counts = QLabel(f"{book.fixed}\n{tr('shell.results.fixed')}")
            counts.setAlignment(Qt.AlignCenter)
            counts.setObjectName("cardTitle")
            counts.setAccessibleName(tr("shell.results.fixed.reader", count=book.fixed))
            row.addWidget(counts)
            open_report = button(
                "", glyph="chevron", tokens=tokens, kind="ghost",
                tip=tr("shell.results.open", title=book.title),
            )
            open_report.setAccessibleName(tr("shell.results.open", title=book.title))
            open_report.clicked.connect(lambda: self.opened.emit(self.book))
            row.addWidget(open_report)
        else:
            drop = button("", glyph="trash", tokens=tokens, kind="ghost",
                          tip=tr("shell.plan.remove", title=book.title))
            drop.setAccessibleName(tr("shell.plan.remove", title=book.title))
            drop.clicked.connect(lambda: self.removed.emit(self.book))
            row.addWidget(drop)

        self.setAccessibleName(book.title)
        self.setAccessibleDescription(
            f"{meta}. {tr(f'shell.status.{book.status.value}')}. {book.summary or book.error}"
        )
        self.activated.connect(lambda: self.opened.emit(self.book))


class Tile(Clickable):
    """A task on the Start page: a name, a promise and a way in."""

    def __init__(self, glyph: str, title: str, description: str, action: str,
                 tokens: Tokens) -> None:
        super().__init__("tile")
        stack = QVBoxLayout(self)
        stack.setContentsMargins(18, 16, 18, 16)
        stack.setSpacing(8)
        mark = QLabel()
        mark.setPixmap(icons.icon(glyph, tokens.accent).pixmap(24, 24))
        stack.addWidget(mark)
        stack.addWidget(label(title, "cardTitle"))
        stack.addWidget(label(description, "cardSubtitle"))
        stack.addStretch(1)
        self.button = button(action, glyph="chevron", tokens=tokens)
        self.button.clicked.connect(self.activated)
        stack.addWidget(self.button)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
