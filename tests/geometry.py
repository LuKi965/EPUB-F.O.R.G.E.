"""Reading a laid-out page the way a person would: what is where, and is it whole.

`findChild(QScrollArea) is not None` was the old test for "this page survives a
small window", and it proved nothing at all: a scroll area with squeezed
content inside it scrolls a mess. So this measures instead — every control a
person has to reach, in the page's own coordinates, and four questions about
each one:

* is it a real size, rather than collapsed to nothing;
* does it lie inside what the page can actually show or scroll to;
* does it overlap another control;
* is the main action among them.

Used by `tests/test_shell_layout.py` and by `tools/ui_check_layout.py`, which
runs the same checks in a separate process for each display scale — Qt reads
the scale factor once, at startup, so a scaling test that is not its own
process is a test of whatever the first one set.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QWidget,
)

#: What counts as a control somebody has to be able to reach and press. Labels
#: and frames are not here: a clipped sentence is a defect of a different size,
#: and these are the things that make a page usable or useless.
CONTROLS = (QAbstractButton, QComboBox, QLineEdit, QSpinBox, QPlainTextEdit)


def controls_of(page: QWidget) -> "list[QWidget]":
    """Every interactive control the page is currently showing."""
    return [
        child for child in page.findChildren(QWidget)
        if isinstance(child, CONTROLS) and child.isVisibleTo(page) and not _inside_a_menu(child)
    ]


def _inside_a_menu(widget: QWidget) -> bool:
    from PySide6.QtWidgets import QMenu

    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QMenu):
            return True
        parent = parent.parentWidget()
    return False


def where(widget: QWidget, page: QWidget) -> QRect:
    """A widget's rectangle in the page's coordinates."""
    corner = widget.mapTo(page, QPoint(0, 0))
    return QRect(corner, widget.size())


def scrollable_area(page: QWidget) -> "QScrollArea | None":
    for child in page.findChildren(QScrollArea):
        if child.isVisibleTo(page):
            return child
    return None


def scroll_ancestor(widget: QWidget, page: QWidget) -> "QScrollArea | None":
    """The scroll area this control lives inside, if it lives inside one.

    Which one matters: a page has an outer scroll area and the settings drawer
    has a second one around its list. A control in the inner list is reachable
    when the *inner* area can scroll to it, and measuring it against the page's
    height instead reports every long list as broken.
    """
    parent = widget.parentWidget()
    while parent is not None and parent is not page:
        if isinstance(parent, QScrollArea):
            return parent
        parent = parent.parentWidget()
    return None


def _room_for(widget: QWidget, page: QWidget):
    """`(rectangle, width, height)` — where the control is and what it must fit."""
    area = scroll_ancestor(widget, page)
    if area is not None and area.widget() is not None:
        content = area.widget()
        return where(widget, content), content.width(), content.height()
    return where(widget, page), page.width(), page.height()


def needs_sideways_scrolling(page: QWidget) -> bool:
    """Whether anything forces the page to scroll horizontally.

    The old shell simply switched the horizontal bar off, which does not make
    content fit — it makes the part that does not fit unreachable.
    """
    area = scrollable_area(page)
    if area is None:
        return False
    return area.horizontalScrollBar().maximum() > 0


def problems_with(page: QWidget, *, main_action=None) -> "list[str]":
    """Everything wrong with this page's layout right now, in plain words."""
    found: list[str] = []
    #: Controls grouped by what they scroll inside, so two things in different
    #: scroll areas are never called an overlap.
    seen: dict = {}

    for control in controls_of(page):
        rect, width, height = _room_for(control, page)
        name = _name_of(control)
        if rect.width() <= 0 or rect.height() <= 0:
            found.append(f"{name}: rozmiar {rect.width()}x{rect.height()}")
            continue
        if rect.right() > width + 1:
            found.append(f"{name}: wystaje poza szerokosc ({rect.right()} > {width})")
        if rect.bottom() > height + 1:
            found.append(f"{name}: ponizej tego, do czego da sie doscrollowac")
        inside = scroll_ancestor(control, page)
        for other_name, other in seen.get(inside, []):
            if rect.intersects(other) and not _one_inside_the_other(rect, other):
                found.append(f"{name} nachodzi na {other_name}")
        seen.setdefault(inside, []).append((name, rect))

    if needs_sideways_scrolling(page):
        found.append("strona wymaga przewijania w poziomie")
    if main_action is not None:
        if not main_action.isVisibleTo(page):
            found.append("glowna akcja jest niewidoczna")
        elif where(main_action, page).height() <= 0:
            found.append("glowna akcja ma zerowa wysokosc")
    return found


def _one_inside_the_other(first: QRect, second: QRect) -> bool:
    """A control drawn inside another — a spin box's buttons, say — is not an
    overlap; two controls sharing a band of the page is."""
    return first.contains(second) or second.contains(first)


def _name_of(widget: QWidget) -> str:
    text = getattr(widget, "text", None)
    said = text() if callable(text) else ""
    return f"{type(widget).__name__}({said[:28] or widget.accessibleName()[:28]})"
