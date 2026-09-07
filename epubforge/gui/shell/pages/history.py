"""History: what was rebuilt, when, and where it went.

The old window forgot everything the moment it closed. That is a small thing
until somebody rebuilds thirty books, closes the window and cannot remember
which folder they chose — so this keeps counts, statuses and destinations, and
nothing else. No report bodies, no book contents: the report is where it was
saved, and this remembers where that is.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ...strings import tr
from ..models import JobRecord
from ..tokens import CARD_GAP, CONTENT_MARGIN, Tokens
from ..widgets import Card, PageHeader, button, clear_layout, label, status_badge


class HistoryPage(QWidget):
    open_requested = Signal(str)
    cleared = Signal()

    def __init__(self, tokens: Tokens, records: "list[JobRecord] | None" = None) -> None:
        super().__init__()
        self.tokens = tokens
        layout = QVBoxLayout(self)
        layout.setContentsMargins(CONTENT_MARGIN, 24, CONTENT_MARGIN, 22)
        layout.setSpacing(CARD_GAP)
        top = QHBoxLayout()
        top.addWidget(
            PageHeader(tr("shell.history.eyebrow"), tr("shell.history.title"),
                       tr("shell.history.subtitle")),
            1,
        )
        forget = button(tr("shell.history.forget"), glyph="trash", tokens=tokens,
                        tip=tr("shell.history.forget.tip"))
        forget.clicked.connect(self.cleared)
        top.addWidget(forget)
        layout.addLayout(top)

        self.card = Card()
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        holder = QWidget()
        holder.setLayout(self.rows)
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setWidget(holder)
        self.card.body.addWidget(scroller, 1)
        layout.addWidget(self.card, 1)
        self.set_records(records or [])

    def set_records(self, records: "list[JobRecord]") -> None:
        clear_layout(self.rows)
        if not records:
            self.rows.addWidget(label(tr("shell.history.empty"), "muted"))
            self.rows.addStretch(1)
            return
        for record in records:
            row = QHBoxLayout()
            row.setSpacing(12)
            names = QVBoxLayout()
            names.setSpacing(2)
            title = ", ".join(record.titles[:2]) or tr("shell.history.title")
            names.addWidget(label(title, "cardTitle"))
            names.addWidget(
                label(
                    f"{tr('shell.history.entry', count=record.count, preset=record.preset)}"
                    f"  ·  {record.when}",
                    "muted",
                )
            )
            row.addLayout(names, 1)
            row.addWidget(status_badge(record.status, self.tokens))
            if record.destination:
                open_button = button(tr("shell.history.open"), glyph="folder", tokens=self.tokens)
                open_button.clicked.connect(
                    lambda _checked=False, where=record.destination: self.open_requested.emit(where)
                )
                row.addWidget(open_button)
            self.rows.addLayout(row)
        self.rows.addStretch(1)
