"""The window: a sidebar, five pages, and the plumbing between them.

It owns what is shared — the palette, the backend, the history file, the
keyboard — and nothing else. Pages do not talk to each other; they emit intent
and this routes it, which is what keeps the rebuild flow testable on its own.

**No menu bar and no status bar.** Both were the old window's furniture, kept
through the first revamp out of habit: every destination in `Plik / Ustawienia
/ Pomoc` is a click away in the sidebar or on a page, and a status bar spends a
row of the window on a sentence that is already on the page it describes. The
shortcuts stay — they are how somebody works fast, and they cost nothing —
so they hang on the window as actions instead, each one enabled only where it
means something.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from ... import resources, version_string
from ..strings import language, set_language, tr
from . import tokens as tokens_module
from .backend import EngineBackend
from .models import JobRecord
from .pages import HistoryPage, HomePage, RebuildPage, SettingsPage, ToolsPage
from .state import forget_history, load_history, remember, settings
from .tokens import COMPACT_BELOW, COMPACT_SLACK, MIN_WINDOW, Tokens
from .widgets import Sidebar

#: Files this window accepts by drag, drop or command line.
SUFFIXES = (".epub", ".pdf")

#: The keyboard, in one place. Every one of these was in the old menu; they
#: outlive it because a shortcut is not furniture.
SHORTCUTS = {
    "open": "Ctrl+O",
    "save": "Ctrl+S",
    "save-batch": "Ctrl+Shift+S",
    "merge": "Ctrl+M",
    "settings": "Ctrl+,",
    "quit": "Ctrl+Q",
}


def opening_size(screen) -> "tuple[int, int]":
    """How big the window opens: comfortable, and never larger than the screen.

    A window that opens 1440 px wide on a 1366 px laptop has its right edge —
    and half of every side-by-side layout — off the desktop, where nothing can
    drag it back. So the preferred size is a *ceiling*, the screen's working
    area is the real limit, and the floor is the minimum this window promises.
    """
    if screen is None:  # pragma: no cover - only when Qt reports no screen
        return MIN_WINDOW
    available = screen.availableGeometry()
    return (
        max(MIN_WINDOW[0], min(1440, int(available.width() * 0.86))),
        max(MIN_WINDOW[1], min(920, int(available.height() * 0.88))),
    )


def fits_on_a_screen(rect) -> bool:
    """Whether a remembered window rectangle still lands on a screen we have.

    Monitors are unplugged, resolutions change, a laptop comes back from a
    docking station with one screen instead of three. A geometry restored into
    where the second monitor used to be is a window nobody can see.
    """
    for screen in QApplication.screens():
        if screen.availableGeometry().intersects(rect):
            visible = screen.availableGeometry().intersected(rect)
            # A sliver on the edge is not "on the screen": the title bar has to
            # be grabbable, so ask for most of the window to be there.
            if visible.width() >= min(rect.width(), 240) and visible.height() >= 120:
                return True
    return False


def chosen_tokens(app) -> Tokens:
    """Dark, light, or whatever the desktop is set to."""
    choice = str(settings().value("theme", "system"))
    if choice == "dark":
        return tokens_module.DARK
    if choice == "light":
        return tokens_module.LIGHT
    from .. import theme as legacy_theme

    return tokens_module.DARK if legacy_theme.is_dark(app) else tokens_module.LIGHT


class MainWindow(QMainWindow):
    def __init__(self, tokens: Tokens, backend=None, initial_files: "list[str] | None" = None):
        super().__init__()
        self.tokens = tokens
        self.backend = backend or EngineBackend(language())
        self.restart_requested = False
        self.busy = False
        self.setWindowTitle(tr("window.title", version=version_string()))
        self.setMinimumSize(*MIN_WINDOW)
        self.resize(*opening_size(self.screen() or QApplication.primaryScreen()))
        self.setAcceptDrops(True)

        self.history = load_history()

        root = QWidget()
        root.setObjectName("root")
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.sidebar = Sidebar(tokens, version_string())
        row.addWidget(self.sidebar)
        self.router = QStackedWidget()
        self.router.setObjectName("router")
        row.addWidget(self.router, 1)
        self.setCentralWidget(root)

        self.home = HomePage(tokens, self.history)
        self.rebuild = RebuildPage(tokens, self.backend, resolver_factory=self._resolver)
        self.tools = ToolsPage(tokens)
        self.history_page = HistoryPage(tokens, self.history)
        self.settings_page = SettingsPage(
            tokens,
            language=language(),
            theme=str(settings().value("theme", "system")),
            remember=settings().value("remember-folder", True, type=bool),
        )
        self.pages = {
            "home": self.home,
            "rebuild": self.rebuild,
            "tools": self.tools,
            "history": self.history_page,
            "settings": self.settings_page,
        }
        for page in self.pages.values():
            self.router.addWidget(page)

        self.sidebar.route_requested.connect(self.navigate)
        self.home.route_requested.connect(self.navigate)
        self.home.rebuild_requested.connect(self._start_rebuild)
        self.home.tool_requested.connect(self._open_tool)
        self.rebuild.finished.connect(self._record)
        self.rebuild.busy_changed.connect(self._busy_changed)
        self.tools.merge_requested.connect(self._merge_copies)
        self.history_page.open_requested.connect(self._open_folder)
        self.history_page.cleared.connect(self._forget_history)
        self.settings_page.language_changed.connect(self._change_language)
        self.settings_page.theme_changed.connect(self._change_theme)
        self.settings_page.remember_changed.connect(
            lambda state: settings().setValue("remember-folder", state)
        )
        self.settings_page.about_requested.connect(self._show_about)

        self.rebuild.stage_changed.connect(self._stage_changed)
        self._build_actions()
        self.navigate("home")
        if initial_files:
            self._start_rebuild(list(initial_files))

    # -- routing ------------------------------------------------------------
    def navigate(self, route: str) -> None:
        page = self.pages.get(route)
        if page is None:
            return
        if route == "tools":
            self.tools.show_index()
        self.router.setCurrentWidget(page)
        self.sidebar.set_active(route)

    def _open_tool(self, name: str) -> None:
        self.navigate("tools")
        self.tools.open_tool(name)

    def _start_rebuild(self, paths: "list[str]") -> None:
        self.navigate("rebuild")
        self.rebuild.start(paths)

    def _busy_changed(self, busy: bool) -> None:
        self.busy = busy

    def say(self, message: str) -> None:
        """Where a page's one-line news goes now that there is no status bar.

        The page that is showing gets it if it knows what to do with it, and
        nothing happens if it does not. This exists because a panel deep inside
        a page cannot know which window it is in — and because the alternative,
        `self.window().statusBar()`, *creates* a status bar on a window that
        deliberately has none.
        """
        page = self.router.currentWidget()
        sink = getattr(page, "say", None)
        if callable(sink):
            sink(message)

    # -- history ------------------------------------------------------------
    def _record(self, outcome) -> None:
        import datetime

        record = JobRecord(
            when=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            count=len(outcome.books),
            written=outcome.written,
            attention=outcome.attention,
            failed=outcome.failed,
            preset=tr(f"shell.preset.{self.rebuild.preset.name.lower()}"),
            destination=str(outcome.destination or ""),
            titles=tuple(book.title for book in outcome.books[:3]),
            cancelled=outcome.cancelled,
        )
        self.history = remember(record)
        self.home.set_history(self.history)
        self.history_page.set_records(self.history)

    def _forget_history(self) -> None:
        forget_history()
        self.history = []
        self.home.set_history(self.history)
        self.history_page.set_records(self.history)

    def _open_folder(self, where: str) -> None:
        if where:
            QDesktopServices.openUrl(QUrl.fromLocalFile(where))

    # -- questions the rebuild asks -----------------------------------------
    def _resolver(self):
        """Somebody for the rebuild to ask, living in this thread.

        The same object the old window used: it belongs to the window and is
        called from the worker, which is the entire reason it is an object with
        a blocking signal rather than a function.
        """
        from ..ask import Ask

        self._ask = Ask(self)
        return self._ask

    # -- keyboard, drops, dialogs -------------------------------------------
    def _build_actions(self) -> None:
        """The shortcuts, without a menu to hang them in.

        Each one calls a page's own public slot. `_save_report` was reachable
        from the menu as a private method, which made the menu a second, worse
        API for the page — so the flow now says what it offers and this only
        binds keys to it.
        """
        self.actions_by_key = {}
        for key, text, slot in (
            ("open", tr("toolbar.add"), self._open_files),
            ("save", tr("action.save"), lambda: self.rebuild.save_report()),
            ("save-batch", tr("action.save.batch"), lambda: self.rebuild.save_batch_report()),
            ("merge", tr("menu.merge"), self._merge_copies),
            ("settings", tr("shell.nav.settings"), lambda: self.navigate("settings")),
            ("quit", tr("menu.quit"), self.close),
        ):
            action = QAction(text, self)
            action.setShortcut(SHORTCUTS[key])
            # Window-wide, so a shortcut works with the focus anywhere inside —
            # including in a page's text field, which is where somebody who has
            # just typed a folder name has left it.
            action.setShortcutContext(Qt.WindowShortcut)
            action.triggered.connect(slot)
            self.addAction(action)
            self.actions_by_key[key] = action
        self._stage_changed(self.rebuild.stage)

    def _stage_changed(self, stage) -> None:
        """Saving a report means nothing until there is a report.

        The acceptance list asks for the two save shortcuts to be inactive
        outside the results, and this is the whole of it: the flow says where
        it stands, and the keys follow.
        """
        from .models import Stage

        for key in ("save", "save-batch"):
            action = self.actions_by_key.get(key)
            if action is not None:
                action.setEnabled(stage is Stage.RESULTS)

    def _open_files(self) -> None:
        self.navigate("rebuild")
        self.rebuild.add_files()

    def _change_language(self, code: str) -> None:
        if code == settings().value("language", "pl"):
            return
        settings().setValue("language", code)
        set_language(code)
        self.restart_requested = True
        self.close()

    def _change_theme(self, name: str) -> None:
        if name == str(settings().value("theme", "system")):
            return
        settings().setValue("theme", name)
        self.restart_requested = True
        self.close()

    def _merge_copies(self) -> None:
        from ..merge import MergeDialog
        from .pages.tools import palette_for

        MergeDialog(self, palette_for(self.tokens)).exec()

    def _show_about(self) -> None:
        from ..about import AboutDialog
        from .pages.tools import palette_for

        AboutDialog(self, palette_for(self.tokens)).exec()

    def dragEnterEvent(self, event):  # noqa: N802 - Qt casing
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        paths = [
            url.toLocalFile() for url in event.mimeData().urls()
            if url.toLocalFile().lower().endswith(SUFFIXES)
        ]
        if paths:
            self._start_rebuild(paths)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # The one thing still decided from the window's own width, and it has
        # to be: the sidebar is what makes the pages' viewport narrow, so
        # deciding it from that viewport would be a circle. The pages ask
        # themselves (`responsive.Responsive`), which is one way round.
        compact = self.sidebar.compact
        edge = COMPACT_BELOW + (COMPACT_SLACK if compact else 0)
        self.sidebar.set_compact(self.width() < edge)

    def closeEvent(self, event):  # noqa: N802
        """Never leave a thread running behind a closed window."""
        self.rebuild.runner.cancel()
        self.rebuild.runner.stop()
        super().closeEvent(event)


def run(argv: "list[str] | None" = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Before the first window exists, or the taskbar has already decided which
    # icon to group this process under.
    resources.set_windows_app_id()

    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("EPUB F.O.R.G.E.")
    app.setStyle("Fusion")
    icon_path = resources.app_icon()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    set_language(settings().value("language", "pl"))

    queued = [
        path for path in argv[1:]
        if path.lower().endswith(SUFFIXES) and os.path.isfile(path)
    ]

    while True:
        tokens = chosen_tokens(app)
        app.setStyleSheet(tokens_module.stylesheet(tokens))
        window = MainWindow(tokens, initial_files=queued)
        window.show()
        app.exec()
        if not window.restart_requested:
            return 0
        queued = [str(book.source) for book in window.rebuild.books]
