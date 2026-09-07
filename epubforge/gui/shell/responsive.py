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


class LayoutMode(Enum):
    """How much room the content has, in the only three sizes anything cares."""

    WIDE = "wide"
    MEDIUM = "medium"
    COMPACT = "compact"

    @property
    def narrow(self) -> bool:
        """True for everything that is not the full side-by-side layout."""
        return self is not LayoutMode.WIDE


#: A page viewport at least this wide gets the side-by-side composition. The
#: number is the design package's, and it is where two columns of readable text
#: plus their gaps stop fitting.
WIDE_FROM = 1180
#: Below this, one column of anything.
MEDIUM_FROM = 820
#: Slack around a threshold. Without it a window dragged to exactly 1180 px
#: flaps between two compositions as the mouse jitters, which is worse than
#: either of them.
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

    def begin_tracking(self) -> None:
        """Call at the end of `__init__`, once the layout exists."""
        self._layout_mode: "LayoutMode | None" = None
        self._settle_mode()

    @property
    def layout_mode(self) -> LayoutMode:
        return getattr(self, "_layout_mode", None) or LayoutMode.WIDE

    def _settle_mode(self) -> None:
        mode = mode_for(self.width(), getattr(self, "_layout_mode", None))
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
