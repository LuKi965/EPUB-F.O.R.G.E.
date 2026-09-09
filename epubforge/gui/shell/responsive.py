"""Layout modes: one mechanism, and it reads the room the *content* has.

The first version of this shell had a single breakpoint on the width of the
window, and it collapsed the sidebar. That is not responsiveness: the sidebar
is 244 px of a window that may be 800, the pages are what has to change, and
what a page has to fit into is its own viewport rather than the window's outer
edge. So every page asks itself how wide it is and gets one of three answers.

Three rules hold this together.

*One vocabulary.* `WIDE`, `MEDIUM`, `COMPACT` and two thresholds, here. A page
that invents its own number is a page that will disagree with the one beside
it about what "narrow" means.

*Composition changes on the mode, not on the pixel.* `reflow` is called when
the answer changes and never otherwise — a page rebuilt inside `resizeEvent`
flickers, loses the keyboard focus and scrolls back to the top while somebody
is dragging the window edge.

*Widgets move; they are not rebuilt.* Both containers below keep one
`QGridLayout` and re-place what is already in it, so a card being reflowed is
the same object, with the same state, one row lower.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget

from .tokens import CONTENT_MARGIN, SCROLL_BAR_WIDTH


class LayoutMode(Enum):
    """How much room the content has, in the only three sizes anything cares."""

    WIDE = "wide"
    MEDIUM = "medium"
    COMPACT = "compact"

    @property
    def narrow(self) -> bool:
        """True for everything that is not the full side-by-side layout."""
        return self is not LayoutMode.WIDE


#: What the two columns of the side-by-side composition each need, from
#: 02-UI-DESIGN: *„Dwie kolumny tylko gdy lista ma >=580 px, podsumowanie
#: >=300 px i mieści się odstęp."* Named rather than added up into a round
#: number, so changing what a column needs changes the threshold.
LIST_NEEDS = 580
SUMMARY_NEEDS = 300
#: And the gap between them; the same one the cards use.
COLUMN_GAP = 14

#: Content at least this wide gets the side-by-side composition. **Content**,
#: not the page: the page spends its margins and, when it has one, its scroll
#: bar before any of this reaches a column, and measuring the threshold on the
#: page rather than on the room a column actually gets is F08 of the handoff.
WIDE_FROM = LIST_NEEDS + SUMMARY_NEEDS + COLUMN_GAP

#: What a page spends before a column sees any of it: `widgets.page_body` sets
#: 2 x `CONTENT_MARGIN`, and a bar is as wide as the stylesheet says. Both are
#: the shell's own declared numbers rather than a guess about them. What
#: decides a live layout is still `Responsive._bar_room`, which asks the
#: running style; these are here so the restatement below is arithmetic.
PAGE_MARGINS = 2 * CONTENT_MARGIN

#: Below this, one column of anything and the compact form of everything that
#: has one. Unlike `WIDE_FROM` the design package does not name this boundary,
#: so it is not derived from it — it is the boundary the shell already had,
#: restated in content width. The old number was 820 measured on the *page*;
#: moving the measurement into the container (`usable_width`) had to not move
#: this threshold along with it, and 820 of page is this much of content.
MEDIUM_FROM = 820 - PAGE_MARGINS - SCROLL_BAR_WIDTH
#: Slack around a threshold. Without it a window dragged to exactly the width
#: of a threshold flaps between two compositions as the mouse jitters, which is
#: worse than either of them.
HYSTERESIS = 24


def mode_for(width: int, current: "LayoutMode | None" = None) -> LayoutMode:
    """The mode for a viewport of *width*, holding *current* through the slack.

    Widening has to pass the threshold; narrowing has to pass it by
    `HYSTERESIS` more. A layout therefore never oscillates while a person is
    dragging an edge, and the mode it settles on is the same one it would have
    reached from either direction.
    """
    if current is LayoutMode.WIDE:
        if width >= WIDE_FROM - HYSTERESIS:
            return LayoutMode.WIDE
    elif current is LayoutMode.MEDIUM and width < WIDE_FROM:
        if width >= MEDIUM_FROM - HYSTERESIS:
            return LayoutMode.MEDIUM
    if width >= WIDE_FROM:
        return LayoutMode.WIDE
    if width >= MEDIUM_FROM:
        return LayoutMode.MEDIUM
    return LayoutMode.COMPACT


class Responsive:
    """Mixin: a widget that knows its own mode and is told when it changes.

    Mixed in *before* the Qt class, so `resizeEvent` here runs and then calls
    Qt's. A page overrides `reflow`; everything else is this.
    """

    #: What this widget spends before its content gets any: its own margins.
    #: A page built with `widgets.page_body` sets this to the margins that
    #: function applies; anything else keeps 0 and is measured whole.
    content_inset = 0

    def begin_tracking(self, area=None) -> None:
        """Call at the end of `__init__`, once the layout exists.

        *area* is the scroll area the content lives in, when there is one: its
        vertical bar takes width from the columns and therefore belongs in the
        measurement (F08).
        """
        self._layout_mode: "LayoutMode | None" = None
        self._area = area
        if area is not None:
            # `widgets.page_body` says what its margins cost; a caller that
            # hands over some other scroll area gets whatever it declares.
            self.content_inset = getattr(area, "content_inset", 0)
        self._settle_mode()

    def usable_width(self) -> int:
        """The width the *content* has, which is what the thresholds are about.

        The page's own width includes margins it will never give a column and a
        scroll bar it may need. Deciding a composition from that number is
        deciding it from a number nothing is laid out in (F08).

        The bar is subtracted **whether or not it is showing**, and that is not
        a rounding-up: it is what keeps the measurement from feeding back into
        itself. Counting only the visible bar makes the input depend on the
        output — a composition that gets shorter loses its bar, gains width,
        crosses back over the threshold and gets taller again — and no amount
        of hysteresis fixes an oscillation whose *cause* is the change. A
        composition also should not differ between a page that happens to be
        scrolled and the same page that does not.
        """
        return max(0, self.width() - getattr(self, "content_inset", 0) - self._bar_room())

    def _bar_room(self) -> int:
        """What a vertical scroll bar costs this page, from the style."""
        area = getattr(self, "_area", None)
        if area is None:
            return 0
        bar = area.verticalScrollBar()
        return bar.sizeHint().width() if bar is not None else 0

    @property
    def layout_mode(self) -> LayoutMode:
        return getattr(self, "_layout_mode", None) or LayoutMode.WIDE

    def _settle_mode(self) -> None:
        mode = mode_for(self.usable_width(), getattr(self, "_layout_mode", None))
        if mode is not getattr(self, "_layout_mode", None):
            self._layout_mode = mode
            self.reflow(mode)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt casing
        super().resizeEvent(event)
        self._settle_mode()

    def reflow(self, mode: LayoutMode) -> None:  # pragma: no cover - overridden
        """What this widget looks like in *mode*. Called only on a change."""


class Panels(QWidget):
    """Blocks that sit beside each other when there is room and stack when not.

    The main/aside pattern, which is most of this interface: the rebuild's list
    and its summary, the results and what to do next, the drop zone and the
    recent jobs. Side by side in `WIDE`, one under the other otherwise, and the
    aside goes *below* rather than beside because a 300-pixel column of Polish
    is a column of hyphens.
    """

    def __init__(self, gap: int = 14, *, stack_below: LayoutMode = LayoutMode.WIDE) -> None:
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(gap)
        self._items: list = []
        self._stack_below = stack_below
        self._mode = LayoutMode.WIDE

    def add(self, widget: QWidget, weight: int = 1) -> None:
        """One block, with the share of the width it takes in `WIDE`."""
        self._items.append((widget, weight))
        self._place()

    def set_mode(self, mode: LayoutMode) -> None:
        if mode is self._mode:
            return
        self._mode = mode
        self._place()

    @property
    def side_by_side(self) -> bool:
        return self._mode is LayoutMode.WIDE or (
            self._stack_below is LayoutMode.MEDIUM and self._mode is LayoutMode.MEDIUM
        )

    def _place(self) -> None:
        for widget, _weight in self._items:
            self._grid.removeWidget(widget)
        for column in range(max(len(self._items), 1)):
            self._grid.setColumnStretch(column, 0)
        for row in range(max(len(self._items), 1)):
            self._grid.setRowStretch(row, 0)
        for index, (widget, weight) in enumerate(self._items):
            if self.side_by_side:
                self._grid.addWidget(widget, 0, index)
                self._grid.setColumnStretch(index, weight)
            else:
                self._grid.addWidget(widget, index, 0)
                self._grid.setColumnStretch(0, 1)


class Cards(QWidget):
    """A grid of equal things whose column count follows the mode.

    Tiles, presets, metrics, categories of change: the same problem four times,
    which is three too many for four sets of magic numbers.
    """

    def __init__(self, columns: "dict[LayoutMode, int]", gap: int = 14) -> None:
        super().__init__()
        self._columns = dict(columns)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(gap)
        self._items: list[QWidget] = []
        self._mode = LayoutMode.WIDE
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    def add(self, widget: QWidget) -> None:
        self._items.append(widget)
        self._place()

    def set_mode(self, mode: LayoutMode) -> None:
        if mode is self._mode:
            return
        self._mode = mode
        self._place()

    @property
    def columns(self) -> int:
        return max(1, self._columns.get(self._mode, 1))

    def _place(self) -> None:
        for widget in self._items:
            self._grid.removeWidget(widget)
        for column in range(max(self._columns.values(), default=1)):
            self._grid.setColumnStretch(column, 0)
        columns = self.columns
        for index, widget in enumerate(self._items):
            self._grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            self._grid.setColumnStretch(column, 1)


def spread(parent, mode: LayoutMode) -> None:
    """Hand *mode* to every `Panels` and `Cards` under *parent*.

    A page reflows by telling its containers, and its containers are wherever
    the page put them. Walking the children is what keeps `reflow` two lines
    long in the pages that need nothing else.
    """
    for child in parent.findChildren(QWidget):
        if isinstance(child, (Panels, Cards)):
            child.set_mode(mode)
