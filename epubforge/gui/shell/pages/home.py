"""Start: what would you like to do?

The first screen asks about the task, not about the machine. Three things are
on it — drop books here, analyse a library, inspect one file — plus what
happened last time and the sentence that matters most to somebody handing a
program their books: this happens on your computer and your originals stay.

The composition follows the room the page has (`responsive`): the recent jobs
sit beside the drop zone when there is width for both and underneath it when
there is not, because a column of Polish 300 pixels wide is a column of
hyphens.
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
from ..responsive import Cards, LayoutMode, Panels, Responsive, spread
from ..tokens import CARD_GAP, Tokens
from ..widgets import Card, PageHeader, Tile, button, label, page_body, status_badge

#: What a drop on the *start* screen may bring in: either module's files, which
#: the window then sorts (`shell.routing`). A module's own page passes its own
#: list, because a page that takes what it cannot convert is a page that has to
#: apologise afterwards.
SUFFIXES = (".epub", ".pdf")


class DropZone(QFrame):
    """The invitation. A drop target that says what it takes and what it does.

    One class, two modules: the words and the suffixes are arguments, because
    "drop files here" is furniture and what happens to them is not.
    """

    files_dropped = Signal(list)

    def __init__(self, tokens: Tokens, *, suffixes: "tuple[str, ...]" = SUFFIXES,
                 title_key: str = "shell.drop.title",
                 subtitle_key: str = "shell.drop.subtitle",
                 choose_key: str = "shell.drop.choose",
                 hint_key: str = "shell.drop.hint",
                 filter_key: str = "dialog.filter") -> None:
        super().__init__()
        self.suffixes = suffixes
        self.filter_key = filter_key
        self.setObjectName("dropZone")
        self.setProperty("active", "false")
        self.setAcceptDrops(True)
        self.setMinimumHeight(210)
        stack = QVBoxLayout(self)
        stack.setContentsMargins(24, 20, 24, 20)
        stack.setSpacing(10)
        # Centred with stretches rather than with `setAlignment(AlignCenter)`
        # on the layout. That flag hands every child its *hint* width, so a
        # word-wrapped label reports the height of one line and the widget
        # below it is laid out on top of it — a defect that only ever showed up
        # in a screenshot. With stretches the children get the full width and
        # wrap honestly, and the text is centred by the labels themselves.
        stack.addStretch(1)

        mark = QLabel()
        mark.setPixmap(icons.icon("drop", tokens.accent).pixmap(44, 44))
        mark.setAlignment(Qt.AlignCenter)
        stack.addWidget(mark)

        title = label(tr(title_key), "pageTitle")
        title.setAlignment(Qt.AlignCenter)
        stack.addWidget(title)
        subtitle = label(tr(subtitle_key), "pageSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        stack.addWidget(subtitle)

        row = QHBoxLayout()
        row.addStretch(1)
        self.choose = button(
            tr(choose_key), kind="primary", glyph="folder", tokens=tokens,
            tip=tr("toolbar.add.tip"),
        )
        self.choose.clicked.connect(self._choose)
        row.addWidget(self.choose)
        row.addStretch(1)
        stack.addLayout(row)

        self.hint = label(tr(hint_key), "muted")
        self.hint.setAlignment(Qt.AlignCenter)
        stack.addWidget(self.hint)
        stack.addStretch(1)
        self.setAccessibleName(tr(title_key))
        self.setAccessibleDescription(tr(hint_key))

    def _choose(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dialog.selectfiles"), self._start_folder(), tr(self.filter_key)
        )
        if paths:
            remember_folder("input", paths[0])
            self.files_dropped.emit(list(paths))

    @staticmethod
    def _start_folder() -> str:
        return last_folder("input")

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
            if url.isLocalFile() and url.toLocalFile().lower().endswith(self.suffixes)
        ]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


class HomePage(Responsive, QWidget):
    #: Files dropped here. The window sorts them and takes each set where it
    #: belongs (`MainWindow.route`); this page does not decide (D-057).
    files_dropped = Signal(list)
    route_requested = Signal(str)
    tool_requested = Signal(str)

    def __init__(self, tokens: Tokens, history: "list[JobRecord] | None" = None) -> None:
        super().__init__()
        self.tokens = tokens
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroller, page = page_body(CARD_GAP)
        layout.addWidget(scroller)

        self.header_row = Panels(CARD_GAP)
        self.header_row.add(
            PageHeader(tr("shell.home.eyebrow"), tr("shell.home.title"), tr("shell.home.subtitle")),
            3,
        )
        self.aside = label(tr("shell.home.aside"), "pageSubtitle")
        self.aside.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.header_row.add(self.aside, 1)
        page.addWidget(self.header_row)

        body = Panels(CARD_GAP)

        main_side = QWidget()
        main = QVBoxLayout(main_side)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(CARD_GAP)
        self.drop = DropZone(tokens, filter_key="dialog.filter.both")
        self.drop.files_dropped.connect(self.files_dropped)
        main.addWidget(self.drop, 3)

        # Two jobs, said as two (02-UI-DESIGN §1). A person who has a PDF and
        # wants a book out of it should not have to work out that the way in is
        # to drop it on something called "rebuild".
        self.tasks = Cards({LayoutMode.WIDE: 2, LayoutMode.MEDIUM: 2, LayoutMode.COMPACT: 1},
                           CARD_GAP)
        self.rebuild_tile = Tile(
            "rebuild", tr("shell.home.task.rebuild"), tr("shell.home.task.rebuild.body"),
            tr("shell.home.task.rebuild.action"), tokens,
        )
        self.rebuild_tile.activated.connect(lambda: self.route_requested.emit("rebuild"))
        self.tasks.add(self.rebuild_tile)
        self.convert_tile = Tile(
            "book", tr("shell.home.task.pdf"), tr("shell.home.task.pdf.body"),
            tr("shell.home.task.pdf.action"), tokens,
        )
        self.convert_tile.activated.connect(lambda: self.route_requested.emit("pdf"))
        self.tasks.add(self.convert_tile)
        main.addWidget(self.tasks, 2)

        self.tiles = Cards({LayoutMode.WIDE: 2, LayoutMode.MEDIUM: 2, LayoutMode.COMPACT: 1},
                           CARD_GAP)
        self.library_tile = Tile(
            "library", tr("shell.home.library.title"), tr("shell.home.library.body"),
            tr("shell.home.open"), tokens,
        )
        self.library_tile.activated.connect(lambda: self.tool_requested.emit("library"))
        self.tiles.add(self.library_tile)
        self.diagnostics_tile = Tile(
            "inspect", tr("shell.home.diagnostics.title"), tr("shell.home.diagnostics.body"),
            tr("shell.home.open"), tokens,
        )
        self.diagnostics_tile.activated.connect(lambda: self.tool_requested.emit("diagnostics"))
        self.tiles.add(self.diagnostics_tile)
        main.addWidget(self.tiles, 2)
        body.add(main_side, 2)

        aside_side = QWidget()
        side = QVBoxLayout(aside_side)
        side.setContentsMargins(0, 0, 0, 0)
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
        body.add(aside_side, 1)
        page.addWidget(body, 1)

        self.set_history(history or [])
        self.begin_tracking()

    def reflow(self, mode: LayoutMode) -> None:
        spread(self, mode)
        # The aside is a second thought about the page; on a narrow one it is
        # the third thing competing for a line that has room for one.
        self.aside.setVisible(mode is not LayoutMode.COMPACT)
        self.aside.setAlignment(
            (Qt.AlignRight if mode is LayoutMode.WIDE else Qt.AlignLeft) | Qt.AlignTop
        )

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


def last_folder(kind: str) -> str:
    """Where a dialog of this kind should open, when the setting allows it."""
    from ..state import last_folder as remembered

    return remembered(kind)


def remember_folder(kind: str, path: str) -> None:
    """Note the folder somebody just used, for the next dialog of this kind."""
    from ..state import remember_folder as store

    store(kind, path)
