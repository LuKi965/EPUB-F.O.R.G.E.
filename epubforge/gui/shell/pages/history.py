"""History: what was rebuilt, when, and where it went.

The old window forgot everything the moment it closed. That is a small thing
until somebody rebuilds thirty books, closes the window and cannot remember
which folder they chose — so this keeps counts, statuses and destinations, and
nothing else. No report bodies, no book contents: the report is where it was
saved, and this remembers where that is.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QVBoxLayout, QWidget

from ...strings import tr
from ..models import JobRecord
from ..responsive import LayoutMode, Panels, Responsive, spread
from ..tokens import CARD_GAP, Tokens
from ..widgets import Card, Eliding, PageHeader, button, clear_layout, label, status_badge


class HistoryRow(QFrame):
    """One finished job: what it was, how it went, and where the files are."""

    open_requested = Signal(str)

    def __init__(self, record: JobRecord, tokens: Tokens) -> None:
        super().__init__()
        self.setObjectName("bookRow")
        self.record = record
        stack = QVBoxLayout(self)
        stack.setContentsMargins(14, 10, 14, 10)
        stack.setSpacing(6)
        split = Panels(12)

        names_side = QWidget()
        names = QVBoxLayout(names_side)
        names.setContentsMargins(0, 0, 0, 0)
        names.setSpacing(2)
        title = ", ".join(record.titles[:2]) or tr("shell.history.title")
        names.addWidget(Eliding(title, "cardTitle"))
        names.addWidget(
            Eliding(
                f"{tr(record.kind_key)}  ·  "
                f"{tr(record.entry_key, count=record.count, preset=record.preset)}"
                f"  ·  {record.when}",
                "muted",
            )
        )
        split.add(names_side, 3)

        doing_side = QWidget()
        doing = QHBoxLayout(doing_side)
        doing.setContentsMargins(0, 0, 0, 0)
        doing.setSpacing(10)
        doing.addWidget(status_badge(record.status, tokens), 0, Qt.AlignVCenter)
        doing.addStretch(1)
        folders = record.folders
        if len(folders) == 1:
            open_button = button(tr("shell.history.open"), glyph="folder", tokens=tokens,
                                 tip=folders[0])
            open_button.clicked.connect(
                lambda _checked=False, target=folders[0]: self.open_requested.emit(target)
            )
            doing.addWidget(open_button)
        elif folders:
            # A batch written beside its sources lands wherever the books came
            # from. Offering the first folder as though it held all of them is
            # how somebody goes looking for a book that was never there.
            many = button(tr("shell.history.open.many", count=len(folders)), glyph="folder",
                          tokens=tokens, tip="\n".join(folders))
            menu = QMenu(many)
            for place in folders:
                action = menu.addAction(place)
                action.triggered.connect(
                    lambda _checked=False, target=place: self.open_requested.emit(target)
                )
            many.setMenu(menu)
            doing.addWidget(many)
        split.add(doing_side, 2)
        stack.addWidget(split)
        self.setAccessibleName(title)
        self.setAccessibleDescription(
            f"{tr(record.kind_key)}. "
            + tr(record.entry_key, count=record.count, preset=record.preset)
        )


class HistoryPage(Responsive, QWidget):
    open_requested = Signal(str)
    cleared = Signal()

    def __init__(self, tokens: Tokens, records: "list[JobRecord] | None" = None) -> None:
        super().__init__()
        self.tokens = tokens
        from ..widgets import page_body

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroller, layout = page_body(CARD_GAP)
        outer.addWidget(scroller)

        top = Panels(CARD_GAP)
        top.add(
            PageHeader(tr("shell.history.eyebrow"), tr("shell.history.title"),
                       tr("shell.history.subtitle")),
            3,
        )
        forget = button(tr("shell.history.forget"), glyph="trash", tokens=tokens,
                        tip=tr("shell.history.forget.tip"))
        forget.clicked.connect(self.cleared)
        holder = QWidget()
        holding = QHBoxLayout(holder)
        holding.setContentsMargins(0, 0, 0, 0)
        holding.addStretch(1)
        holding.addWidget(forget)
        top.add(holder, 1)
        layout.addWidget(top)

        self.card = Card()
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        self.card.body.addLayout(self.rows)
        layout.addWidget(self.card, 1)
        self.set_records(records or [])
        self.begin_tracking(scroller)

    def reflow(self, mode: LayoutMode) -> None:
        spread(self, mode)

    def set_records(self, records: "list[JobRecord]") -> None:
        clear_layout(self.rows)
        if not records:
            self.rows.addWidget(label(tr("shell.history.empty"), "muted"))
            return
        for record in records:
            row = HistoryRow(record, self.tokens)
            row.open_requested.connect(self.open_requested)
            self.rows.addWidget(row)
        spread(self, self.layout_mode)
