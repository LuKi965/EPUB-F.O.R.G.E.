"""Tools: the specialist work, one click away and not in anybody's path.

Library, diagnostics and the regression corpus were three of the four primary
destinations in the old window — equal in weight to the rebuild itself, which
is the thing almost nobody comes here to do. They keep every function they had;
what changes is that a person has to ask for them.

The panels themselves are the ones the program already has (`gui/tabs.py`).
Rewriting three working panels to change where they are reached from would be
a large diff that improves nothing — and the design package's own rule is to
keep every currently reachable function, not to rebuild it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ... import theme as legacy_theme
from ...strings import tr
from ..tokens import CARD_GAP, CONTENT_MARGIN, Tokens
from ..widgets import PageHeader, StatusBadge, Tile, button, label


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


class ToolsPage(QWidget):
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
        #: Tool page → the label its panel's one-line news goes into.
        self._news: dict = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.router = QStackedWidget()
        outer.addWidget(self.router)

        index_page = QWidget()
        layout = QVBoxLayout(index_page)
        layout.setContentsMargins(CONTENT_MARGIN, 24, CONTENT_MARGIN, 22)
        layout.setSpacing(CARD_GAP)
        layout.addWidget(
            PageHeader(tr("shell.tools.eyebrow"), tr("shell.tools.title"), tr("shell.tools.subtitle"))
        )
        grid = QHBoxLayout()
        grid.setSpacing(CARD_GAP)
        for name, glyph, key, expert in self.TOOLS:
            tile = Tile(glyph, tr(f"{key}.title"), tr(f"{key}.body"), tr("shell.tools.open"), tokens)
            if expert:
                tile.layout().insertWidget(
                    2, StatusBadge(tr("shell.tools.corpus.badge"), "warning", tokens, "expert")
                )
            tile.activated.connect(lambda target=name: self.open_tool(target))
            grid.addWidget(tile, 1)
        layout.addLayout(grid, 1)
        self.router.addWidget(index_page)
        self._index = index_page

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

    def show_index(self) -> None:
        self.router.setCurrentWidget(self._index)

    def say(self, message: str) -> None:
        """The one line a panel used to put in the status bar.

        It goes under the tool's own heading, where the person running the tool
        is already looking, rather than at the far bottom edge of the window.
        """
        news = self._news.get(self.router.currentWidget())
        if news is not None:
            news.setText(message)

    def _build(self, name: str) -> QWidget:
        from ...tabs import CorpusPanel, DiagnosticsPanel, LibraryPanel

        panels = {"library": LibraryPanel, "diagnostics": DiagnosticsPanel, "corpus": CorpusPanel}
        key = {
            "library": "shell.tools.library",
            "diagnostics": "shell.tools.diagnostics",
            "corpus": "shell.tools.corpus",
        }[name]

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(CONTENT_MARGIN, 24, CONTENT_MARGIN, 22)
        layout.setSpacing(CARD_GAP)
        top = QHBoxLayout()
        top.addWidget(
            PageHeader(tr("shell.tools.eyebrow"), tr(f"{key}.title"), tr(f"{key}.body")), 1
        )
        back = button(tr("shell.tools.back"), glyph="chevron", tokens=self.tokens)
        back.clicked.connect(self.show_index)
        top.addWidget(back, 0, Qt.AlignTop)
        layout.addLayout(top)
        news = label("", "muted")
        layout.addWidget(news)
        self._news[page] = news
        layout.addWidget(panels[name](self.palette_colors), 1)
        return page
