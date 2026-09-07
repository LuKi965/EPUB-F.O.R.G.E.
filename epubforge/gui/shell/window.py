"""The window: a sidebar, five pages, and the plumbing between them.

It owns what is shared — the palette, the backend, the history file, the menu
— and nothing else. Pages do not talk to each other; they emit intent and this
routes it, which is what keeps the rebuild flow testable on its own.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from ... import resources, version_string
from ..strings import LANGUAGES, language, set_language, tr
from . import tokens as tokens_module
from .backend import EngineBackend
from .models import JobRecord
from .pages import HistoryPage, HomePage, RebuildPage, SettingsPage, ToolsPage
from .state import forget_history, load_history, remember, settings
from .tokens import COMPACT_BELOW, MIN_WINDOW, Tokens
from .widgets import Sidebar

#: Files this window accepts by drag, drop or command line.
SUFFIXES = (".epub", ".pdf")


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
        self.setWindowTitle(tr("window.title", version=version_string()))
        self.setMinimumSize(*MIN_WINDOW)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(1440, int(available.width() * 0.85)),
                min(920, int(available.height() * 0.88)),
            )
        else:  # pragma: no cover - only when Qt reports no screen at all
            self.resize(*MIN_WINDOW)
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

        self._build_menu()
        self.statusBar().showMessage(tr("shell.local.title"))
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
        self.statusBar().showMessage(
            tr("shell.rebuild.title.running") if busy else tr("shell.local.title")
        )

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

    # -- menu, drops, dialogs -----------------------------------------------
    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(tr("menu.file"))
        for text, slot, shortcut in (
            (tr("toolbar.add"), self.rebuild.add_files, "Ctrl+O"),
            (tr("action.save"), self.rebuild._save_report, "Ctrl+S"),
            (tr("action.save.batch"), self.rebuild._save_batch_report, "Ctrl+Shift+S"),
            (tr("menu.merge"), self._merge_copies, "Ctrl+M"),
            (tr("menu.quit"), self.close, "Ctrl+Q"),
        ):
            action = QAction(text, self)
            action.triggered.connect(slot)
            action.setShortcut(shortcut)
            file_menu.addAction(action)

        settings_menu = self.menuBar().addMenu(tr("menu.settings"))
        language_menu = settings_menu.addMenu(tr("menu.language"))
        group = QActionGroup(self)
        group.setExclusive(True)
        current = settings().value("language", "pl")
        for code in LANGUAGES:
            action = QAction(tr(f"language.{code}"), self, checkable=True)
            action.setChecked(code == current)
            action.triggered.connect(lambda _checked=False, c=code: self._change_language(c))
            group.addAction(action)
            language_menu.addAction(action)

        help_menu = self.menuBar().addMenu(tr("menu.help"))
        about = QAction(tr("menu.about"), self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

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
        self.sidebar.set_compact(self.width() < COMPACT_BELOW)

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
