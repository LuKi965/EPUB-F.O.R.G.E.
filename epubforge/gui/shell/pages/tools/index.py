"""Tools: the specialist work, one click away and not in anybody's path.

Library, diagnostics and the regression corpus were three of the four primary
destinations in the old window — equal in weight to the rebuild itself, which
is the thing almost nobody comes here to do. They keep every function they had;
what changes is that a person has to ask for them.

Each of them is now a page of this shell rather than an old panel dropped into
a frame: the same heading, the same cards, the same responsive layout and the
same worker as everything else. What they *do* did not move with them — that
lives in `gui/toolwork.py`, which has no Qt in it and which the old window's
panels call as well, so neither window can drift from the other about what a
survey prints.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from .... import theme as legacy_theme
from ....strings import tr
from ...responsive import Cards, LayoutMode, Responsive, spread
from ...tokens import CARD_GAP, Tokens
from ...widgets import PageHeader, StatusBadge, Tile, page_body


def palette_for(tokens: Tokens) -> legacy_theme.Palette:
    """The panels take the old `Palette`; give them one that matches the shell.

    They use it for a handful of inline styles — a muted note, a status colour
    — so the mapping only has to be honest about roles, which it is.
    """
    return legacy_theme.Palette(
        window=tokens.canvas,
        surface=tokens.surface,
        surface_alt=tokens.surface_2,
        border=tokens.border,
        border_strong=tokens.border_strong,
        text=tokens.text,
        text_muted=tokens.muted,
        accent=tokens.accent,
        accent_hover=tokens.accent_hover,
        accent_text=tokens.accent_text,
        fix=tokens.success,
        preserved=tokens.accent,
        warn=tokens.warning,
        error=tokens.danger,
        info=tokens.muted,
    )


class ToolsPage(Responsive, QWidget):
    """Four tiles, and behind each of them the panel that does the work."""

    TOOLS = (
        ("library", "library", "shell.tools.library", False),
        ("diagnostics", "diagnostics", "shell.tools.diagnostics", False),
        ("corpus", "tools", "shell.tools.corpus", True),
        ("merge", "merge", "shell.tools.merge", False),
    )

    merge_requested = Signal()

    def __init__(self, tokens: Tokens) -> None:
        super().__init__()
        self.tokens = tokens
        self.palette_colors = palette_for(tokens)
        self._panels: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.router = QStackedWidget()
        outer.addWidget(self.router)

        index_page = QWidget()
        holder = QVBoxLayout(index_page)
        holder.setContentsMargins(0, 0, 0, 0)
        scroller, layout = page_body(CARD_GAP)
        holder.addWidget(scroller)
        layout.addWidget(
            PageHeader(tr("shell.tools.eyebrow"), tr("shell.tools.title"), tr("shell.tools.subtitle"))
        )
        grid = Cards(
            {LayoutMode.WIDE: 4, LayoutMode.MEDIUM: 2, LayoutMode.COMPACT: 1}, CARD_GAP
        )
        for name, glyph, key, expert in self.TOOLS:
            tile = Tile(glyph, tr(f"{key}.title"), tr(f"{key}.body"), tr("shell.tools.open"), tokens)
            if expert:
                tile.layout().insertWidget(
                    2, StatusBadge(tr("shell.tools.corpus.badge"), "warning", tokens, "expert")
                )
            tile.activated.connect(lambda target=name: self.open_tool(target))
            grid.add(tile)
        layout.addWidget(grid, 1)
        layout.addStretch(1)
        self.router.addWidget(index_page)
        self._index = index_page
        self.begin_tracking()

    def reflow(self, mode: LayoutMode) -> None:
        spread(self, mode)

    def open_tool(self, name: str) -> None:
        """Show one tool. `merge` is a dialog, not a page — it produces a file."""
        if name == "merge":
            self.merge_requested.emit()
            return
        panel = self._panels.get(name)
        if panel is None:
            panel = self._build(name)
            self._panels[name] = panel
            self.router.addWidget(panel)
        self.router.setCurrentWidget(panel)

    def runners(self) -> "list":
        """Every runner the open tools own, for the window's shutdown."""
        return [
            page.runner for page in self._panels.values()
            if getattr(page, "runner", None) is not None
        ]

    def show_index(self) -> None:
        self.router.setCurrentWidget(self._index)

    def say(self, message: str) -> None:
        """One line of news, to whichever tool is open.

        It goes under the tool's own heading, where the person running it is
        already looking, rather than at the far bottom edge of the window.
        """
        page = self.router.currentWidget()
        sink = getattr(page, "say", None)
        if callable(sink):
            sink(message)

    def _build(self, name: str) -> QWidget:
        from .corpus import CorpusToolPage
        from .diagnostics import DiagnosticsToolPage
        from .library import LibraryToolPage

        page = {
            "library": LibraryToolPage,
            "diagnostics": DiagnosticsToolPage,
            "corpus": CorpusToolPage,
        }[name](self.tokens)
        page.back_requested.connect(self.show_index)
        return page
