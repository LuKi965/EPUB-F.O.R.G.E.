"""Shared components. They render models and emit intent; they do no work.

Every clickable thing here is reachable from the keyboard, carries an
accessible name, and states its status in three ways at once — colour, glyph
and word — because the acceptance list says a status may never be carried by
colour alone and because that is simply true for the person reading it.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..strings import tr
from . import icons
from .models import STATUS_LOOK, BookItem, BookStatus, Preset, Stage
from .responsive import LayoutMode
from .tokens import (CONTENT_MARGIN, SIDEBAR_COMPACT_WIDTH,
                     SIDEBAR_WIDTH,
                     Tokens)


def label(text: str, object_name: str = "", *, wrap: bool = True,
          flexible: bool = False) -> QLabel:
    """A label. `flexible` lets it be narrower than its longest word.

    A word-wrapped `QLabel` reports the width of its longest word as its
    minimum, and a sentence with `calibre_bookmarks.txt` in it therefore stops
    the column it is in from ever being narrow. Where that matters — a list of
    forty settings in a drawer — the label is told to take whatever width it is
    given; the full text is a tooltip away either way.
    """
    item = QLabel(text)
    if object_name:
        item.setObjectName(object_name)
    item.setWordWrap(wrap)
    if flexible:
        item.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        item.setMinimumWidth(0)
    return item


class ElidingButton(QPushButton):
    """A button whose label shortens rather than widening the column it is in.

    A `QPushButton` reports the width of its whole label as its minimum and
    has no way to be narrower, so a long label on a secondary action decides
    how wide the block holding it must be — and, through the block, the page.
    *Przekaż utworzony EPUB do przebudowy* is 317 px on the machine this is
    written on and 480 at half again the type; on the Windows runner it was
    what kept the converter's results 64 px wider than the page they sit in
    (0.4.4, the run after build 70).

    The whole label stays in the tooltip and the accessible name, so nothing
    is unreachable — the same bargain `Eliding` makes for a title or a path.
    For a **main** action this would be the wrong bargain and it is not
    offered by default: a person has to be able to read what the button they
    are about to press does.
    """

    def __init__(self, text: str, elide: str = "right") -> None:
        super().__init__(text)
        self._full = text
        self._shown = text
        self._busy = False
        # Where the label gives way. A path gives way in the middle (A08 of
        # the 0.4.4 recovery audit): the folder a person chose is the last
        # segment, and a path elided on the right shows every folder but it.
        self._elide = Qt.ElideMiddle if elide == "middle" else Qt.ElideRight
        self._tip = ""
        # Preferred, not Ignored: the button asks for its whole label and
        # gives way down to `minimumSizeHint` only when the row has no room.
        # Ignored let a row with a stretch beside it hand the button no width
        # at all — 0 × 44 px on the plan page, the moment the destination
        # button began to elide (A08).
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def set_tip(self, tip: str) -> None:
        """The tooltip the button carries anyway; the full label is put in
        front of it whenever the label is shortened."""
        self._tip = tip
        self._retell()

    def _retell(self) -> None:
        shortened = self._shown != self._full
        parts = ([self._full] if shortened or not self._tip else []) + ([self._tip] if self._tip else [])
        self.setToolTip("\n".join(parts))

    def _advance(self, text: str) -> int:
        """What the label costs, measured the way `QPushButton.sizeHint` does."""
        return self.fontMetrics().size(Qt.TextShowMnemonic, text).width()

    def sizeHint(self):  # noqa: N802 - Qt casing
        """As wide as the *whole* label, whatever is showing.

        The layout decides the button's width from this hint, and `_shorten`
        decides the label from the width. When the hint followed the shown
        label instead, the two fed each other: a label elided to fit the
        width made a smaller hint, the layout handed that smaller width back,
        and the label was elided again to fit it. Eliding a path to exactly
        the advance of its own result is not a fixed point — it comes back a
        character or two shorter, face by face (39, 37, 35 characters at
        16 pt on DejaVu Sans) — so the loop only stops where the metrics
        happen to agree. On this machine's face that is after a round or
        two; on the Windows runner's it was `\\bardz…ybrany`, thirteen
        characters of a path in a row 726 px wide. A hint that does not
        depend on the shown label has nothing to feed back.
        """
        size = super().sizeHint()
        size.setWidth(size.width() + self._advance(self._full) - self._advance(self._shown))
        return size

    def minimumSizeHint(self):  # noqa: N802 - Qt casing
        """As wide as the frame, the glyph and an ellipsis — not the label."""
        size = super().minimumSizeHint()
        spare = self._advance(self._full) - self._advance("…")
        size.setWidth(max(0, size.width() - max(0, spare)))
        return size

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt casing
        super().resizeEvent(event)
        # Deferred for the reason `StatusBadge._shorten` gives: setting the
        # text from inside a resize re-enters the layout from within itself.
        QTimer.singleShot(0, self._shorten)

    def _shorten(self) -> None:
        if self._busy:
            return
        metrics = self.fontMetrics()
        # The frame, the glyph and the padding: the hint less the whole label.
        spent = self.sizeHint().width() - self._advance(self._full)
        room = max(0, self.width() - spent)
        # A label that fits is shown whole. `elidedText` asked for exactly the
        # advance of the text can still come back with an ellipsis, face by
        # face; it is only asked when there is less room than the label.
        if not room or room >= metrics.horizontalAdvance(self._full):
            shown = self._full
        else:
            shown = metrics.elidedText(self._full, self._elide, room)
        if not shown or shown == self._shown:
            return
        self._busy = True
        try:
            self._shown = shown
            self.setText(shown)
            self._retell()
        finally:
            self._busy = False


def button(text: str, *, kind: str = "", glyph: str = "", tokens: Tokens | None = None,
           tip: str = "", elides: bool = False, elide: str = "right") -> QPushButton:
    """A button with an optional glyph, an accessible name and a tooltip.

    `elides` is for a secondary action with a long label standing in a column
    that has to be able to be narrow. Never for the main action of a page.
    `elide` says where the label gives way: "right" for a sentence, "middle"
    for a path, whose last segment is the part that names the choice.
    """
    item = ElidingButton(text, elide) if elides else QPushButton(text)
    if kind:
        item.setObjectName(kind)
    if glyph and tokens is not None:
        colour = tokens.accent_text if kind == "primary" else tokens.text
        item.setIcon(icons.icon(glyph, colour))
        item.setIconSize(QSize(16, 16))
    item.setAccessibleName(text)
    if elides:
        # The whole label has to stay reachable when the button may shorten
        # it: it goes into the tooltip, in front of whatever the tip says.
        item.set_tip(tip)
        if tip:
            item.setAccessibleDescription(tip)
    elif tip:
        item.setToolTip(tip)
        item.setAccessibleDescription(tip)
    item.setCursor(Qt.PointingHandCursor)
    return item


class _ClickableLabel(QLabel):
    """The sentence of a `Choice`: pressing it presses the button beside it,
    the way pressing a radio button's own label does."""

    pressed = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt casing
        if event.button() == Qt.LeftButton:
            self.pressed.emit()
        super().mousePressEvent(event)


class Choice(QWidget):
    """A radio button whose sentence wraps instead of setting the column's floor.

    A `QRadioButton` is as wide as its label and cannot be narrower, so a
    choice worded as a sentence — *Tekst dopasowujący się do ekranu* — decides
    how narrow the card holding it can be, and through the card the page.
    On the Windows runner at the wider face it reached 749 px in a plan 726 px
    wide, and the page scrolled sideways by 70 px (A08 / Tests (Windows) #73).
    A label wraps; a radio button does not. So the button here carries no text
    of its own and the sentence stands beside it in a wrapping label, pressing
    which presses the button. The sentence is the button's accessible name,
    the button is what the keyboard reaches, and a `QButtonGroup` takes
    `button` as it would any other.
    """

    toggled = Signal(bool)

    def __init__(self, text: str, tip: str = "") -> None:
        super().__init__()
        self._text = text
        self.button = QRadioButton()
        self.button.setAccessibleName(text)
        self.sentence = _ClickableLabel(text)
        self.sentence.setWordWrap(True)
        self.sentence.setObjectName("choiceSentence")
        self.sentence.pressed.connect(self.button.click)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self.button, 0, Qt.AlignTop)
        row.addWidget(self.sentence, 1)
        self.setFocusProxy(self.button)
        self.button.toggled.connect(self.toggled)
        if tip:
            self.setToolTip(tip)

    def text(self) -> str:
        return self._text

    def isChecked(self) -> bool:  # noqa: N802 - Qt casing
        return self.button.isChecked()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt casing
        self.button.setChecked(checked)

    def setToolTip(self, tip: str) -> None:  # noqa: N802 - Qt casing
        super().setToolTip(tip)
        self.button.setToolTip(tip)
        self.button.setAccessibleDescription(tip)
        self.sentence.setToolTip(tip)


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


def page_body(spacing: int = 14):
    """The whole page in one scroll area — heading included.

    The earlier arrangement scrolled the *body* and kept the page heading and
    the stepper outside it, which is fine at 960 px of height and a trap at
    520: the fixed part eats a third of the window and the part that scrolls
    gets what is left. Everything scrolls now, so nothing is unreachable at any
    height; the horizontal bar is left to Qt, because a page that needs one is
    telling us something we should hear rather than hide.

    Returns `(scroll_area, layout)`.
    """
    from PySide6.QtWidgets import QScrollArea

    holder = QWidget()
    body = QVBoxLayout(holder)
    body.setContentsMargins(CONTENT_MARGIN, 24, CONTENT_MARGIN, 22)
    body.setSpacing(spacing)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(holder)
    # What this costs a column, so a page can decide its composition from the
    # room its content actually gets rather than from its own width (F08).
    area.content_inset = 2 * CONTENT_MARGIN
    return area, body


class ActionFooter(QWidget):
    """The main action, outside everything that scrolls, with its count.

    F08's other half. `BoundedList` stops the list from stretching the page;
    this stops the one decision from sitting below it. In a single-column
    composition the summary card — and the action in it — is under the list,
    and "scroll past four hundred rows to reach Przebuduj" is not a decision
    anybody makes twice.

    **One button, moved.** Never a second copy: two live primary buttons are
    worse than one in the wrong place. And never more than one at a time —
    each state of a page builds its own widgets, so the action handed here
    can be a *new* object while the last one is still parented here, out of
    reach of the page's own teardown. That is two live primary buttons by
    accident, which is how it was found (a screenshot, etap 5), so taking a
    new one evicts whatever else is holding on.

    Both task pages use this. The rebuild had it and the converter did not,
    and the converter's action measured 889 px below the fold on a 600-pixel
    page — the same defect, on the module that was split out to be its own.
    """

    def __init__(self, tokens: Tokens) -> None:
        super().__init__()
        self.tokens = tokens
        self.setObjectName("actionFooter")
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(CONTENT_MARGIN, 10, CONTENT_MARGIN, 12)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(6)
        # One line that gives way, not a wrapping label: a word-wrapped
        # `QLabel` picks its own width for its size hint, and picked 108 px
        # for *1 dokument gotowy do konwersji* in a footer 736 px wide — three
        # lines in a column (A09 of the 0.4.4 recovery audit). The count
        # takes what the action leaves, so the action keeps its whole width
        # first (03-UI-UX).
        self.count = Eliding("", "cardTitle")
        self._action: "QWidget | None" = None
        # And when the two do not fit in one row — on the Windows runner's
        # face the count came out `1 dokument gotowy do ko…` beside the
        # button at 800×520 — the count goes above the action rather than
        # losing its last words: a controlled second row, which is what the
        # design asks for at the extreme, not an ellipsis (03-UI-UX §54).
        self._stacked = False
        self._place()
        self.hide()

    def carry(self, action: QWidget, said: str) -> None:
        """Hold *action* — and only it — with *said* beside it."""
        self.clear_except(action)
        self._action = action
        if action.parent() is not self:
            self._grid.addWidget(action, 0, 1)
        self.count.setText(said)
        self._stacked = self._must_stack()
        self._place()
        self.setVisible(True)

    def holds(self, action: "QWidget | None") -> bool:
        return action is not None and action.parent() is self

    def clear_except(self, keep: "QWidget | None" = None) -> None:
        """Drop everything but the count and *keep*."""
        for index in reversed(range(self._grid.count())):
            item = self._grid.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None or widget is keep or widget is self.count:
                continue
            self._grid.takeAt(index)
            widget.setParent(None)
            widget.deleteLater()
        if self._action is not keep:
            self._action = None

    def _own_action(self) -> "QWidget | None":
        """The action, while it is still this footer's.

        The page moves the button back into its column for the wide
        composition without telling the footer. A deferred re-arrangement
        that then re-placed "its" action reparented a widget that was not
        its any more — the button vanished from the column on the Windows
        runner (Tests (Windows) #79). What is not a child here is not held.
        """
        if self._action is not None and self._action.parent() is not self:
            self._action = None
        return self._action

    def _place(self) -> None:
        """One row, or the count over the action: the same two widgets."""
        self._grid.removeWidget(self.count)
        self._own_action()
        if self._action is not None:
            self._grid.removeWidget(self._action)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 0)
        if self._stacked and self._action is not None:
            self._grid.addWidget(self.count, 0, 0, 1, 2)
            self._grid.addWidget(self._action, 1, 1, Qt.AlignRight)
            return
        self._grid.addWidget(self.count, 0, 0)
        if self._action is not None:
            self._grid.addWidget(self._action, 0, 1)

    def _must_stack(self) -> bool:
        """Whether the whole count and the whole action fit side by side."""
        if self._own_action() is None:
            return False
        left, _top, right, _bottom = self._grid.getContentsMargins()
        words = self.count.fontMetrics().horizontalAdvance(self.count.full_text())
        needed = left + words + self._grid.horizontalSpacing() + self._action.sizeHint().width() + right
        return self.width() < needed

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt casing
        super().resizeEvent(event)
        # Out of the resize, like every other re-arrangement in this file.
        QTimer.singleShot(0, self._arrange)

    def _arrange(self) -> None:
        stacked = self._must_stack()
        if stacked != self._stacked:
            self._stacked = stacked
            self._place()


class BoundedList(QScrollArea):
    """A list that scrolls inside itself instead of stretching the page.

    F08. With fifty books — let alone five hundred — the plan grew to fifty
    rows tall and everything under it, the presets and the main action
    included, went with it. A person then scrolled past four hundred rows to
    reach a decision that has nothing to do with the four hundred.

    Bounded in *rows* rather than in pixels, because the row's own height is
    what changed when covers arrived: "about eight books" stays about eight
    books whatever a row turns out to measure.
    """

    #: How much of the list to show before it starts scrolling on its own.
    ROWS = 8
    #: And never taller than this share of the page, so a short window does not
    #: give the whole of itself to the list.
    SHARE_OF_THE_PAGE = 0.55
    #: What "no bound" is spelled as in Qt.
    UNBOUNDED = 16777215

    def __init__(self, spacing: int = 8) -> None:
        super().__init__()
        self.setObjectName("boundedList")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self.rows = QVBoxLayout(holder)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(spacing)
        self.setWidget(holder)
        self._tallest = 0
        self._room = 0
        self._mode = LayoutMode.WIDE

    def _wanted(self) -> int:
        """As tall as its rows, up to the bound.

        `QScrollArea` caps its own hint at twenty-four line heights and asks
        for almost nothing as a minimum, so on a page whose surface is
        sized by minimums a list of twelve rows was handed a strip and
        scrolled inside it — inside the page's own scroll (A09). The rows
        are what the list is; it asks for them, and the bound is the only
        thing that cuts the request short.
        """
        inner = self.widget().sizeHint().height() + 2 * self.frameWidth()
        return min(inner, self.maximumHeight())

    def sizeHint(self):  # noqa: N802 - Qt casing
        return QSize(super().sizeHint().width(), self._wanted())

    def minimumSizeHint(self):  # noqa: N802 - Qt casing
        return QSize(super().minimumSizeHint().width(), self._wanted())

    def set_mode(self, mode: LayoutMode) -> None:
        """Bounded beside a summary column; the page's own height under one.

        The bound exists so the main action is not under four hundred rows
        (F08). In every composition but `WIDE` that action is in the footer,
        outside everything that scrolls, and the bound then only puts a
        scroll inside a scroll — the list moving under a finger that meant
        to move the page (03-UI-UX, A09). So a narrow page scrolls as one
        surface, and the list is as tall as its rows.
        """
        self._mode = mode
        self._bound()

    def _bound(self) -> None:
        if not self._tallest:
            return
        if self._mode.narrow:
            self.setMaximumHeight(self.UNBOUNDED)
            return
        tallest = self._tallest
        if self._room:
            tallest = max(140, min(self._tallest, int(self._room * self.SHARE_OF_THE_PAGE)))
        self.setMaximumHeight(tallest)

    def add(self, widget: QWidget) -> None:
        self.rows.addWidget(widget)

    def finish(self) -> None:
        """Call once the rows are in: work out how tall this may be.

        Short lists keep their natural height — a batch of two books in a box
        with room for eight is a box with a hole in it — and long ones stop
        growing.
        """
        self.rows.addStretch(1)
        rows = [
            self.rows.itemAt(index).widget()
            for index in range(self.rows.count())
            if self.rows.itemAt(index).widget() is not None
        ]
        if not rows:
            self._tallest = 0
            return
        one = max(row.sizeHint().height() for row in rows)
        spacing = self.rows.spacing()
        self._tallest = self.ROWS * one + (self.ROWS - 1) * spacing
        wanted = len(rows) * one + max(0, len(rows) - 1) * spacing
        if wanted <= self._tallest:
            # Short enough to show whole; no bound, no scroll bar, no hole.
            self._tallest = 0
            self.setMaximumHeight(self.UNBOUNDED)
            self.setMinimumHeight(0)
            return
        self._bound()

    def fit_within(self, height: int) -> None:
        """Take at most a share of *height*, whatever the row count says."""
        self._room = height
        self._bound()


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
        #: Kept so a card whose title counts something can be retitled without
        #: the page around it being rebuilt.
        self.title_label = None
        if title:
            heading = QHBoxLayout()
            heading.setSpacing(8)
            if glyph and tokens is not None:
                mark = QLabel()
                mark.setPixmap(icons.icon(glyph, tokens.muted).pixmap(18, 18))
                heading.addWidget(mark, 0, Qt.AlignTop)
            self.title_label = label(title, "cardTitle")
            heading.addWidget(self.title_label, 1)
            self.body.addLayout(heading)
        if subtitle:
            self.body.addWidget(label(subtitle, "cardSubtitle"))

    def retitle(self, title: str) -> None:
        if self.title_label is not None:
            self.title_label.setText(title)

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

    #: The two jobs are two entries, and that is D-057 in one tuple: a person
    #: looking for "make a book out of a PDF" finds it here rather than by
    #: dropping a PDF on the rebuild and hoping.
    ROUTES = (
        ("home", "home", "shell.nav.home"),
        ("rebuild", "rebuild", "shell.nav.rebuild"),
        ("pdf", "book", "shell.nav.pdf"),
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

    @property
    def compact(self) -> bool:
        return self._compact

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

    #: The rebuild's four. A module with different steps passes its own —
    #: "Plan przebudowy" over a conversion would be exactly the label-over-the-
    #: same-page the owner said is not a separate module (D-057).
    KEYS = ("shell.step.files", "shell.step.analysis", "shell.step.plan", "shell.step.results")

    def __init__(self, tokens: Tokens, keys: "tuple[str, ...] | None" = None) -> None:
        super().__init__()
        self.tokens = tokens
        if keys is not None:
            self.KEYS = keys
        self._labels: list[QLabel] = []
        self._compact = False
        self._stage = Stage.FILES
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

    def set_compact(self, compact: bool) -> None:
        """Four names do not fit a narrow page; four numbers do.

        The step a person is *on* keeps its name either way — that is the one
        thing the stepper is for — and every step keeps its accessible name, so
        a screen reader reads the same four steps at every width.
        """
        if compact == self._compact:
            return
        self._compact = compact
        self.set_stage(self._stage)

    def set_stage(self, stage: Stage) -> None:
        self._stage = stage
        current = stage.step
        for index, item in enumerate(self._labels):
            name = tr(self.KEYS[index])
            done = index < current
            shown = name if not self._compact or index == current else ""
            item.setText(("✓" if done else f"{index + 1}") + ("   " + shown if shown else ""))
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

    **No wider, and — since 0.4.4 — narrower when it has to be.** "Must not
    stretch" was written as `Fixed`, which also means *must not shrink*, and
    that turned out to be the widest-reaching defect of the release. The badge
    is as wide as its word in the font in use; on Windows, which draws in Segoe
    UI, it is wider than on the machine this is written on. A widget that
    cannot shrink sets the floor of every column it stands in, so one badge in
    a results row and one in a history row between them starved the converter's
    list (290 px for rows needing 405) and pushed the start page's aside past
    what a third of the page can give. Both were failures of the release build,
    on the same widget, from opposite sides of the interface.

    So the word elides when the room is short, keeping the glyph and the
    colour, and the whole word stays in the tooltip and the accessible name.
    All three ways of stating the status survive — that rule is what this class
    is for — and none of them decides how wide a column must be.
    """

    #: What the chip cannot go below: the glyph, its padding and enough of the
    #: word to be an ellipsis with a letter or two in front of it. Measured
    #: from the font rather than written down, in `_shorten`.
    LEAST_WORD = 3

    def __init__(self, text: str, role: str, tokens: Tokens, glyph: str = "check") -> None:
        super().__init__()
        colour = getattr(tokens, role if role != "muted" else "muted")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._word = text
        self._mark = icons.rich(glyph, colour, 14)
        chip = QLabel(f"{self._mark}&nbsp; {text}")
        chip.setTextFormat(Qt.RichText)
        chip.setStyleSheet(
            f"color:{colour}; background:{_wash(tokens, role)}; border:1px solid {colour};"
            " border-radius:11px; padding:4px 10px; font-weight:650;"
        )
        chip.setAccessibleName(text)
        chip.setToolTip(text)
        # Maximum, not Fixed: the size hint stays the ceiling — the badge never
        # grows to fill a row, which is the behaviour the paragraph above is
        # about — while the floor comes from `minimumSizeHint`, which the
        # eliding below brings down to the glyph and a shortened word.
        chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        row.addWidget(chip)
        self._chip = chip
        self._shown = text
        self._busy = False
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setAccessibleName(text)
        self.setToolTip(text)

    def _advance(self, text: str) -> int:
        return self._chip.fontMetrics().horizontalAdvance(text)

    def sizeHint(self):  # noqa: N802 - Qt casing
        """The whole word's, whatever the chip is showing.

        The same loop `ElidingButton` had (A08): with the hint following the
        shown word and the policy `Maximum`, the layout handed a shortened
        chip its smaller hint as its width, and the word was shortened again
        to fit — *gotowa* came out as `g…` in a row with 190 px to spare
        (A09). The hint is what the word costs, and the width the row gives
        decides the word, never the other way round.
        """
        size = super().sizeHint()
        size.setWidth(size.width() + self._advance(self._word) - self._advance(self._shown))
        return size

    def minimumSizeHint(self):  # noqa: N802 - Qt casing
        """The glyph, the padding and the least of the word it will show."""
        size = super().minimumSizeHint()
        shortest = self._advance(self._word[: self.LEAST_WORD] + "…")
        widest = self._advance(self._word)
        size.setWidth(max(0, size.width() - max(0, widest - shortest)))
        return size

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt casing
        super().resizeEvent(event)
        # Out of the resize, not inside it. Changing a child's text while Qt is
        # in the middle of laying the row out re-enters the layout from inside
        # itself, and at a display scale of 2 that recursed until the C++ stack
        # was gone — a segmentation fault with no Python traceback to read.
        # Deferred to the next turn of the event loop it converges instead:
        # each pass either settles the text or finds it already right.
        QTimer.singleShot(0, self._shorten)

    def _shorten(self) -> None:
        """Fit the word to the room, keeping the glyph and the colour.

        Guarded against itself, and it needed to be: setting the text changes
        what the chip asks for, which lays the row out again, which resizes
        this, which shortens the text. The first version of this recursed
        until the process died — a segmentation fault, not an exception, which
        is what a blown C++ stack looks like from Python.
        """
        if self._busy:
            return
        metrics = self._chip.fontMetrics()
        # The padding, the border and the glyph: the hint less the whole word.
        spent = self.sizeHint().width() - self._advance(self._word)
        room = max(0, self.width() - spent)
        if not room or room >= self._advance(self._word):
            shown = self._word
        else:
            shown = metrics.elidedText(self._word, Qt.ElideRight, room)
        if not shown:
            shown = self._word[: self.LEAST_WORD] + "…"
        if shown == self._shown:
            return
        self._busy = True
        try:
            self._shown = shown
            self._chip.setText(f"{self._mark}&nbsp; {shown}")
        finally:
            self._busy = False


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


class Notice(QFrame):
    """One sentence at the top of a page, with at most one thing to do about it.

    A modal box would have been fewer lines and the wrong shape: "these three
    files belong to the other module" is information, not a question that has
    to be answered before the program will go on. It sits on the page, the
    person acts on it or does not, and the batch underneath is untouched.
    """

    acted = Signal()
    dismissed = Signal()

    def __init__(self, tokens: Tokens, text: str, action: str = "", *,
                 glyph: str = "warning", role: str = "warning") -> None:
        super().__init__()
        self.setObjectName("warningCard")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(icons.icon(glyph, getattr(tokens, role)).pixmap(20, 20))
        row.addWidget(mark, 0, Qt.AlignTop)
        row.addWidget(label(text, "cardSubtitle"), 1)
        if action:
            self.action = button(action, glyph="chevron", tokens=tokens)
            self.action.clicked.connect(self.acted)
            row.addWidget(self.action, 0, Qt.AlignTop)
        close = button("", glyph="close", tokens=tokens, tip=tr("shell.notice.dismiss"))
        close.setAccessibleName(tr("shell.notice.dismiss"))
        close.clicked.connect(self.dismissed)
        close.clicked.connect(self.hide)
        row.addWidget(close, 0, Qt.AlignTop)
        self.setAccessibleName(text)


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
        self._stack = stack = QVBoxLayout(self)
        stack.setContentsMargins(15, 14, 15, 14)
        stack.setSpacing(8)
        stack.addWidget(label(title, "cardTitle"))
        self.badge = (
            StatusBadge(tr("shell.preset.recommended"), "success", tokens)
            if recommended else None
        )
        if self.badge is not None:
            stack.addWidget(self.badge)
        self.description = label(description, "cardSubtitle")
        stack.addWidget(self.description)
        self._tail = stack.count()
        stack.addStretch(1)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.set_selected(selected)
        self.activated.connect(lambda: self.chosen.emit(self.preset))

    def set_compact(self, compact: bool) -> None:
        """Three tall cards, or a compact row that says the same thing.

        02-UI-DESIGN: three columns only where each can hold its content;
        otherwise *„zwarta lista radio-card z krótkim opisem, nie trzy ogromne
        pionowe karty"*. The description is what makes them tall, so it is what
        goes — into the tooltip, which is where it is still reachable rather
        than gone.
        """
        self.description.setVisible(not compact)
        self._stack.setContentsMargins(15, 10, 15, 10) if compact else \
            self._stack.setContentsMargins(15, 14, 15, 14)
        self.setToolTip(self.accessibleDescription() if compact else "")


class Eliding(QLabel):
    """A label that shortens its text instead of widening its parent.

    A book's title, its author and above all the path it was written to are
    values a layout must not be sized by: one long path used to push the whole
    results column past the window and take the scrollbar with it. What is cut
    is never lost — the full text is the tooltip and the accessible name, both
    of which a person and a screen reader can reach.
    """

    def __init__(self, text: str, object_name: str = "", mode=Qt.ElideRight) -> None:
        super().__init__()
        if object_name:
            self.setObjectName(object_name)
        self._mode = mode
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt casing
        self._full = text or ""
        self.setToolTip(self._full)
        self.setAccessibleName(self._full)
        self._shorten()

    def full_text(self) -> str:
        return self._full

    def _shorten(self) -> None:
        room = max(0, self.width() - 2)
        shown = (
            self.fontMetrics().elidedText(self._full, self._mode, room)
            if room else self._full
        )
        QLabel.setText(self, shown)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._shorten()


#: A book row narrower than this puts its one-line summary under the title
#: rather than beside it. It is the row's own width, not the page's: a row in a
#: card in a column is narrower than the page it is on.
ROW_STACKS_BELOW = 620

#: And above this, the row has room for the larger cover the design allows —
#: 56×84 rather than 48×72. One number, so a row cannot disagree with itself
#: about how much room it has.
ROW_IS_ROOMY_ABOVE = 900


class Cover(QLabel):
    """A book's own cover, at the size the list draws it — or a placeholder.

    The row used to carry a 22 px generic book glyph for every title, which is
    the same picture whatever the book is (F02). This draws the book's own,
    from the bytes the adapter decoded off the GUI thread, and falls back to a
    placeholder **of the same geometry** so a list of covers and a list without
    them are the same shape and nothing jumps.
    """

    #: Logical pixels, from 02-UI-DESIGN: 48×72 in the list, 56×84 in a large
    #: view, 40×60 when the row goes compact — and the cover stays visible in
    #: all three, which the generic icon did not.
    SIZES = {
        LayoutMode.WIDE: (56, 84),
        LayoutMode.MEDIUM: (48, 72),
        LayoutMode.COMPACT: (40, 60),
    }

    def __init__(self, book: BookItem, tokens: Tokens,
                 mode: LayoutMode = LayoutMode.MEDIUM) -> None:
        super().__init__()
        self.setObjectName("cover")
        self.book = book
        self.tokens = tokens
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self.set_mode(mode)

    def set_mode(self, mode: LayoutMode) -> None:
        width, height = self.SIZES.get(mode, self.SIZES[LayoutMode.MEDIUM])
        self.setFixedSize(width, height)
        self._draw(width, height)

    def _draw(self, width: int, height: int) -> None:
        from PySide6.QtGui import QPixmap

        book = self.book
        if getattr(book, "has_a_cover", False):
            picture = QPixmap()
            # The only decoding that happens on this thread, and it is of a
            # thumbnail at most 112×168 — the expensive half was done in
            # `thumbnails.shrink` before this object existed.
            if picture.loadFromData(book.cover):
                # `contain`: the whole cover inside the box, proportions kept.
                self.setPixmap(picture.scaled(
                    width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
                self.setToolTip(book.title)
                self.setAccessibleName(tr("shell.cover.of", title=book.title))
                return
        self.setPixmap(
            icons.icon("book", self.tokens.muted).pixmap(min(width - 12, 28),
                                                         min(width - 12, 28))
        )
        self.setToolTip(tr("shell.cover.none"))
        self.setAccessibleName(tr("shell.cover.none"))


class BookRow(Clickable):
    """One book in the plan, or one book in the results.

    The same row in both places on purpose: it is the same book, and a person
    who learned to read it once should not have to learn a second table.
    """

    removed = Signal(object)
    toggled = Signal(object, bool)
    opened = Signal(object)

    def __init__(self, book: BookItem, tokens: Tokens, *, results: bool = False,
                 repairs: bool = True) -> None:
        super().__init__("bookRow")
        self.book = book
        self._narrow: bool | None = None
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(14)
        self._row = row

        if not results:
            self.choose = QCheckBox()
            self.choose.setChecked(book.chosen)
            self.choose.setEnabled(book.rebuildable)
            self.choose.setAccessibleName(tr("shell.plan.include", title=book.title))
            self.choose.toggled.connect(lambda state: self.toggled.emit(self.book, state))
            if not book.rebuildable:
                # The reason it cannot be rebuilt is beside it; the checkbox
                # says the same thing by being unavailable rather than by
                # letting somebody tick a book that will fail again.
                self.choose.setToolTip(book.error or tr("shell.plan.unavailable"))
            row.addWidget(self.choose)

        self.mark = Cover(book, tokens)
        row.addWidget(self.mark, 0, Qt.AlignVCenter)

        self.names = QVBoxLayout()
        self.names.setSpacing(2)
        self.names.addWidget(Eliding(book.title, "cardTitle"))
        meta = "  ·  ".join(part for part in (book.author, book.kind, book.size_text) if part)
        self.names.addWidget(Eliding(meta, "muted"))
        if results and book.output:
            self.names.addWidget(Eliding(str(book.output), "muted", Qt.ElideMiddle))
        row.addLayout(self.names, 3)

        self.summary = None
        if book.summary or book.error:
            self.summary = Eliding(book.error or book.summary, "muted")
            # Remembered rather than looked up later: a layout cannot be asked
            # for the index of a nested layout, and this is where the summary
            # goes back to when the row is wide again.
            self._summary_at = row.count()
            row.addWidget(self.summary, 2)

        row.addWidget(status_badge(book.status, tokens))

        if results:
            if repairs:
                # A count of repairs is a rebuild's number. A conversion makes
                # a new book and repairs nothing, so it does not carry one —
                # and printing "0 napraw" beside a converted document would be
                # the rebuild's vocabulary on another module's screen.
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

    def _cover_mode(self) -> LayoutMode:
        """Which of the three cover sizes this row has room for."""
        if self.width() < ROW_STACKS_BELOW:
            return LayoutMode.COMPACT
        return LayoutMode.WIDE if self.width() >= ROW_IS_ROOMY_ABOVE else LayoutMode.MEDIUM

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt casing
        super().resizeEvent(event)
        # The cover follows the width every time, not only when the row
        # crosses the stacking line: three sizes, two thresholds.
        self.mark.set_mode(self._cover_mode())
        narrow = self.width() < ROW_STACKS_BELOW
        if narrow is self._narrow:
            return
        self._narrow = narrow
        # Not hidden — resized. The design asks for the cover to stay visible
        # in the compact row, at 40×60, precisely because the generic icon it
        # replaces used to disappear there and take the only picture of the
        # book with it (02-UI-DESIGN, „Komponent książki"). Before the summary,
        # because a row with nothing to say about the book still has a cover.
        self.mark.set_mode(self._cover_mode())
        if self.summary is None:
            return
        # Moved, not rebuilt: the same label, one layout over.
        if narrow:
            self._row.removeWidget(self.summary)
            self.names.addWidget(self.summary)
        else:
            self.names.removeWidget(self.summary)
            self._row.insertWidget(self._summary_at, self.summary, 2)


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
