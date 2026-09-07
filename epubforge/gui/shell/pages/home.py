"""Start: what would you like to do?

The first screen asks about the task, not about the machine. Three things are
on it — drop books here, analyse a library, inspect one file — plus what
happened last time and the sentence that matters most to somebody handing a
program their books: this happens on your computer and your originals stay.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ...strings import tr
from .. import icons
from ..models import JobRecord
from ..tokens import CARD_GAP, CONTENT_MARGIN, Tokens
from ..widgets import Card, PageHeader, Tile, button, label, scrolling_body, status_badge

#: What a drop is allowed to bring in. The same two the old window accepted.
SUFFIXES = (".epub", ".pdf")


class DropZone(QFrame):
    """The invitation. A drop target that says what it takes and what it does."""

    files_dropped = Signal(list)

    def __init__(self, tokens: Tokens) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setProperty("active", "false")
        self.setAcceptDrops(True)
        self.setMinimumHeight(260)
        stack = QVBoxLayout(self)
        stack.setAlignment(Qt.AlignCenter)
        stack.setSpacing(10)

        mark = QLabel()
        mark.setPixmap(icons.icon("drop", tokens.accent).pixmap(48, 48))
        mark.setAlignment(Qt.AlignCenter)
        stack.addWidget(mark)
        # Not word-wrapped: a wrapped QLabel reports the height of one line to
        # a centred column, so the next widget is laid out on top of it. Two
        # short lines do not need wrapping; the paragraph below does, and gets
        # a width and a height of its own.
        title = label(tr("shell.drop.title"), "pageTitle", wrap=False)
        title.setAlignment(Qt.AlignCenter)
        stack.addWidget(title, alignment=Qt.AlignCenter)
        subtitle = label(tr("shell.drop.subtitle"), "pageSubtitle", wrap=False)
        subtitle.setAlignment(Qt.AlignCenter)
        stack.addWidget(subtitle, alignment=Qt.AlignCenter)

        self.choose = button(
            tr("shell.drop.choose"), kind="primary", glyph="folder", tokens=tokens,
            tip=tr("toolbar.add.tip"),
        )
        self.choose.clicked.connect(self._choose)
        stack.addWidget(self.choose, alignment=Qt.AlignCenter)

        hint = label(tr("shell.drop.hint"), "muted")
        hint.setAlignment(Qt.AlignCenter)
        hint.setFixedWidth(460)
        hint.setMinimumHeight(hint.fontMetrics().height() * 3)
        stack.addWidget(hint, alignment=Qt.AlignCenter)
        self.setAccessibleName(tr("shell.drop.title"))
        self.setAccessibleDescription(tr("shell.drop.hint"))

    def _choose(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dialog.selectfiles"), "", tr("dialog.filter")
        )
        if paths:
            self.files_dropped.emit(list(paths))

    def _highlight(self, on: bool) -> None:
        self.setProperty("active", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt casing
        if event.mimeData().hasUrls():
            self._highlight(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._highlight(False)
        paths = [
            url.toLocalFile() for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile().lower().endswith(SUFFIXES)
        ]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


class HomePage(QWidget):
    rebuild_requested = Signal(list)
    route_requested = Signal(str)
    tool_requested = Signal(str)

    def __init__(self, tokens: Tokens, history: "list[JobRecord] | None" = None) -> None:
        super().__init__()
        self.tokens = tokens
        layout = QVBoxLayout(self)
        layout.setContentsMargins(CONTENT_MARGIN, 24, CONTENT_MARGIN, 22)
        layout.setSpacing(CARD_GAP)

        header = QHBoxLayout()
        header.addWidget(
            PageHeader(tr("shell.home.eyebrow"), tr("shell.home.title"), tr("shell.home.subtitle")),
            1,
        )
        aside = label(tr("shell.home.aside"), "pageSubtitle")
        aside.setAlignment(Qt.AlignRight | Qt.AlignTop)
        header.addWidget(aside)
        layout.addLayout(header)

        scroller, page = scrolling_body(CARD_GAP)
        layout.addWidget(scroller, 1)
        body = QHBoxLayout()
        body.setSpacing(CARD_GAP)

        main = QVBoxLayout()
        main.setSpacing(CARD_GAP)
        self.drop = DropZone(tokens)
        self.drop.files_dropped.connect(self.rebuild_requested)
        main.addWidget(self.drop, 3)

        tiles = QHBoxLayout()
        tiles.setSpacing(CARD_GAP)
        self.library_tile = Tile(
            "library", tr("shell.home.library.title"), tr("shell.home.library.body"),
            tr("shell.home.open"), tokens,
        )
        self.library_tile.activated.connect(lambda: self.tool_requested.emit("library"))
        tiles.addWidget(self.library_tile, 1)
        self.diagnostics_tile = Tile(
            "inspect", tr("shell.home.diagnostics.title"), tr("shell.home.diagnostics.body"),
            tr("shell.home.open"), tokens,
        )
        self.diagnostics_tile.activated.connect(lambda: self.tool_requested.emit("diagnostics"))
        tiles.addWidget(self.diagnostics_tile, 1)
        main.addLayout(tiles, 2)
        body.addLayout(main, 2)

        side = QVBoxLayout()
        side.setSpacing(CARD_GAP)
        self.recent = Card(tr("shell.home.recent"), tr("shell.home.recent.body"), glyph="history",
                           tokens=tokens)
        self._recent_rows = QVBoxLayout()
        self._recent_rows.setSpacing(8)
        self.recent.body.addLayout(self._recent_rows)
        self.recent.body.addStretch(1)
        more = button(tr("shell.home.recent.all"), kind="ghost", glyph="chevron", tokens=tokens)
        more.clicked.connect(lambda: self.route_requested.emit("history"))
        self.recent.body.addWidget(more)
        side.addWidget(self.recent, 2)

        local = QFrame()
        local.setObjectName("successCard")
        local_layout = QHBoxLayout(local)
        local_layout.setContentsMargins(16, 14, 16, 14)
        local_layout.setSpacing(12)
        shield = QLabel()
        shield.setPixmap(icons.icon("shield", tokens.success).pixmap(22, 22))
        local_layout.addWidget(shield, 0, Qt.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(3)
        words.addWidget(label(tr("shell.local.title"), "cardTitle"))
        words.addWidget(label(tr("shell.local.body"), "cardSubtitle"))
        local_layout.addLayout(words, 1)
        side.addWidget(local)
        body.addLayout(side, 1)
        page.addLayout(body, 1)

        self.set_history(history or [])

    def set_history(self, records: "list[JobRecord]") -> None:
        """Redraw the recent list. Called on arrival and after every finished job."""
        from ..widgets import clear_layout

        clear_layout(self._recent_rows)
        if not records:
            self._recent_rows.addWidget(label(tr("shell.home.recent.empty"), "muted"))
            return
        for record in records[:3]:
            row = QHBoxLayout()
            row.setSpacing(10)
            names = QVBoxLayout()
            names.setSpacing(2)
            title = record.titles[0] if record.titles else tr("shell.history.title")
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
            self._recent_rows.addLayout(row)
