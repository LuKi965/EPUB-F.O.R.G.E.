"""Does this window survive being small — measured, not assumed.

The test this replaces was one line long:

    assert page.findChild(QScrollArea) is not None

which is true of a page whose cards are squeezed to nothing inside a scroll
area nobody can scroll usefully. So every main screen is laid out at five
sizes, in both languages, and asked the four questions in `tests/geometry.py`:
positive sizes, inside what can be reached, nothing overlapping, and the main
action still there.

**Why the pages are measured and not the window.** Qt's offscreen platform —
the only one a test machine has — reports an 800×800 desktop and refuses to
make a window larger than it. A test that resizes the window to 1440 and then
measures is therefore a test of 800 pretending otherwise. A page held as a
*child* is laid out at whatever size it is given, so each screen is put in a
host widget and sized directly; that is the composition being measured, which
is what these tests are about.

The scaling half runs in separate processes (`tools/ui_check_layout.py`): Qt
reads `QT_SCALE_FACTOR` once, before the first `QApplication`, so a 150 % test
inside a process that already started at 100 % is a test of 100 %.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

pytest.importorskip("PySide6.QtWidgets")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from epubforge.gui.shell import tokens as tokens_module  # noqa: E402
from epubforge.gui.shell.backend import DemoBackend  # noqa: E402
from epubforge.gui.shell.models import JobRecord, Stage  # noqa: E402
from epubforge.gui.shell.pages import (  # noqa: E402
    HistoryPage,
    HomePage,
    RebuildPage,
    SettingsPage,
    ToolsPage,
)
from epubforge.gui.shell.responsive import LayoutMode  # noqa: E402
from epubforge.gui.strings import set_language, tr  # noqa: E402
from tests.geometry import problems_with, where  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The five windows the design package names. The page gets a little less than
#: the window: the sidebar takes 244 px, or 64 when it is compact.
SIZES = ((1440, 900), (1180, 700), (1000, 650), (900, 600), (800, 560))


@pytest.fixture(autouse=True)
def own_settings(tmp_path, monkeypatch):
    """Settings of this test's own, including the remembered geometry."""
    from PySide6.QtCore import QSettings

    from epubforge.gui.shell import state
    from epubforge.gui.shell import window as window_module

    store = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr(state, "settings", lambda: store)
    monkeypatch.setattr(window_module, "settings", lambda: store)
    return store


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(tokens_module.stylesheet(tokens_module.DARK))
    yield app


@pytest.fixture
def host(qt_app):
    """Something for a page to be a child of, so it can be given any size."""
    holder = QWidget()
    holder.resize(400, 300)
    holder.show()
    yield holder
    holder.close()


def page_width(window_width: int) -> int:
    """What the page gets when the window is this wide."""
    sidebar = (
        tokens_module.SIDEBAR_COMPACT_WIDTH
        if window_width < tokens_module.COMPACT_BELOW
        else tokens_module.SIDEBAR_WIDTH
    )
    return window_width - sidebar


def laid_out(app, page, host, size) -> None:
    page.setParent(host)
    page.setGeometry(0, 0, page_width(size[0]), size[1])
    page.show()
    for _ in range(8):
        app.processEvents()


def settle(app, until, tries: int = 300) -> None:
    import time

    for _ in range(tries):
        app.processEvents()
        if until():
            return
        time.sleep(0.01)
    raise AssertionError("nie doczekano się stanu")


def rebuild_page(qt_app):
    return RebuildPage(tokens_module.DARK, DemoBackend())


def finish(page) -> None:
    runner = getattr(page, "runner", None)
    if runner is not None:
        runner.stop()
        runner.wait_for_idle()
    page.setParent(None)
    page.close()


HISTORY = [
    JobRecord(when="2026-09-07 21:15", count=12, written=11, attention=1, failed=0,
              preset="Zachowaj wygląd", destinations=("/home/kto/polka", "/home/kto/inne")),
    JobRecord(when="2026-09-06 09:02", count=3, written=3, attention=0, failed=0,
              preset="Wymuś standard", destination="/home/kto/polka"),
]


def every_screen(qt_app):
    """One of each, freshly built, with the state that makes them worth looking at."""
    yield "start", HomePage(tokens_module.DARK, HISTORY)
    yield "narzedzia", ToolsPage(tokens_module.DARK)
    yield "historia", HistoryPage(tokens_module.DARK, HISTORY)
    yield "ustawienia", SettingsPage(tokens_module.DARK)


class TestEveryScreenAtEverySize:
    @pytest.mark.parametrize("size", SIZES)
    def test_the_simple_pages_are_whole(self, qt_app, host, size):
        for name, page in every_screen(qt_app):
            try:
                laid_out(qt_app, page, host, size)
                assert not problems_with(page), (name, size)
            finally:
                finish(page)

    @pytest.mark.parametrize("size", SIZES)
    def test_the_plan_is_whole_and_offers_its_main_action(self, qt_app, host, size):
        page = rebuild_page(qt_app)
        try:
            page.start(["Powiesc.epub", "Zbior.epub", "Poradnik.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, size)
            assert not problems_with(page, main_action=page.run_button), size
        finally:
            finish(page)

    @pytest.mark.parametrize("size", SIZES)
    def test_the_results_are_whole(self, qt_app, host, size):
        page = rebuild_page(qt_app)
        try:
            page.start(["Powiesc.epub", "Zbior.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            page.run()
            settle(qt_app, lambda: page.stage is Stage.RESULTS)
            laid_out(qt_app, page, host, size)
            assert not problems_with(page), size
        finally:
            finish(page)

    @pytest.mark.parametrize("size", SIZES)
    def test_the_drawer_is_whole_and_keeps_its_footer(self, qt_app, host, size):
        from PySide6.QtWidgets import QPushButton

        page = rebuild_page(qt_app)
        try:
            page.start(["Powiesc.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, size)
            page._open_drawer()
            for _ in range(8):
                qt_app.processEvents()
            drawer = page.drawer
            assert not problems_with(drawer), size
            # The footer is always on screen: the list of settings is what
            # scrolls, never the Apply button somebody is scrolling towards.
            apply_button = next(
                item for item in drawer.findChildren(QPushButton)
                if item.text() == tr("shell.drawer.apply")
            )
            rect = where(apply_button, drawer)
            assert 0 <= rect.top() and rect.bottom() <= drawer.height() + 1, (size, rect)
            drawer.close_drawer()
        finally:
            finish(page)

    @pytest.mark.parametrize("size", SIZES)
    @pytest.mark.parametrize("name", ["library", "diagnostics", "corpus"])
    def test_every_tool_page_is_whole(self, qt_app, host, name, size):
        tools = ToolsPage(tokens_module.DARK)
        try:
            tools.open_tool(name)
            page = tools.router.currentWidget()
            laid_out(qt_app, tools, host, size)
            for _ in range(4):
                qt_app.processEvents()
            assert not problems_with(page, main_action=page._buttons[0]), (name, size)
        finally:
            finish(tools)


class TestBothLanguages:
    """Polish is the longer one and English is the one nobody checks."""

    @pytest.fixture(autouse=True)
    def _restore(self):
        from epubforge.gui import strings

        before = strings.language()
        yield
        set_language(before)

    @pytest.mark.parametrize("code", ["pl", "en"])
    @pytest.mark.parametrize("size", [(1440, 900), (900, 600), (800, 560)])
    def test_no_control_is_lost_to_a_longer_word(self, qt_app, host, code, size):
        set_language(code)
        for name, page in every_screen(qt_app):
            try:
                laid_out(qt_app, page, host, size)
                assert not problems_with(page), (code, name, size)
            finally:
                finish(page)


class TestTheCompositionChangesAndNotJustTheSize:
    """The design package's own words: a page has to *reflow*, not shrink."""

    def test_the_start_page_puts_its_aside_below_when_narrow(self, qt_app, host):
        page = HomePage(tokens_module.DARK, HISTORY)
        try:
            laid_out(qt_app, page, host, (1440, 900))
            assert page.layout_mode is LayoutMode.WIDE
            drop, recent = where(page.drop, page), where(page.recent, page)
            assert recent.left() > drop.right() - 2, "obok siebie w szerokim oknie"

            laid_out(qt_app, page, host, (900, 600))
            drop, recent = where(page.drop, page), where(page.recent, page)
            assert recent.top() >= drop.bottom() - 2, "pod spodem w waskim oknie"
        finally:
            finish(page)

    def test_the_tools_index_changes_its_column_count(self, qt_app, host):
        page = ToolsPage(tokens_module.DARK)
        try:
            laid_out(qt_app, page, host, (1440, 900))
            assert page.layout_mode is LayoutMode.WIDE
            laid_out(qt_app, page, host, (800, 560))
            assert page.layout_mode is LayoutMode.COMPACT
        finally:
            finish(page)

    def test_the_presets_go_from_three_columns_to_one(self, qt_app, host):
        page = rebuild_page(qt_app)
        try:
            page.start(["a.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (1440, 900))
            first, second = (where(card, page) for card in page._preset_cards[:2])
            assert second.left() > first.right() - 2, "trzy kolumny w szerokim"

            laid_out(qt_app, page, host, (900, 600))
            first, second = (where(card, page) for card in page._preset_cards[:2])
            assert second.top() >= first.bottom() - 2, "jedna kolumna w waskim"
        finally:
            finish(page)

    def test_the_stepper_keeps_the_current_step_readable_when_compact(self, qt_app, host):
        page = rebuild_page(qt_app)
        try:
            page.start(["a.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (800, 560))
            labels = page.stepper._labels
            current = labels[Stage.PLAN.step]
            assert tr("shell.step.plan") in current.text()
            # The others are numbers, and every one of them still says what it
            # is to a screen reader.
            assert all(item.accessibleName() for item in labels)
            assert tr("shell.step.files") not in labels[0].text()
        finally:
            finish(page)

    def test_the_drawer_takes_the_whole_page_when_there_is_no_room_beside_it(
        self, qt_app, host
    ):
        page = rebuild_page(qt_app)
        try:
            page.start(["a.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (1440, 900))
            page._open_drawer()
            for _ in range(6):
                qt_app.processEvents()
            drawer = page.drawer
            assert drawer.panel.width() < drawer.width(), "szuflada z boku szerokiej strony"
            assert not drawer.category_combo.isVisibleTo(drawer)

            drawer.close_drawer()
            laid_out(qt_app, page, host, (800, 560))
            page._open_drawer()
            for _ in range(6):
                qt_app.processEvents()
            assert drawer.panel.width() >= drawer.width() - 2, "cala szerokosc na waskiej"
            assert drawer.category_combo.isVisibleTo(drawer)
            drawer.close_drawer()
        finally:
            finish(page)

    def test_a_long_path_does_not_widen_the_results(self, qt_app, host):
        """One output path used to push the whole column past the window."""
        page = rebuild_page(qt_app)
        try:
            page.start(["a.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            page.run()
            settle(qt_app, lambda: page.stage is Stage.RESULTS)
            long_one = "/" + "/".join(["bardzo-dluga-nazwa-folderu"] * 8) + "/ksiazka.epub"
            page.books[0].output = pathlib.Path(long_one)
            page.show_results(page.outcome)
            laid_out(qt_app, page, host, (900, 600))
            assert not problems_with(page)
        finally:
            finish(page)


class TestTheSameAtEveryDisplayScale:
    """Qt reads the scale once, at startup, so each of these is a process."""

    @pytest.mark.parametrize("scale", ["1.0", "1.25", "1.5", "2.0"])
    def test_the_window_lays_out_and_fits_the_screen(self, scale):
        answer = _checked_in_its_own_process(scale)
        assert answer["problems"] == [], (scale, answer["problems"])
        assert answer["fits"], (scale, answer["opened"], answer["screen"])


def _checked_in_its_own_process(scale: str) -> dict:
    environment = dict(os.environ)
    environment["QT_SCALE_FACTOR"] = scale
    environment["QT_QPA_PLATFORM"] = "offscreen"
    finished = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "ui_check_layout.py")],
        capture_output=True, text=True, env=environment, timeout=300, cwd=str(ROOT),
    )
    assert finished.returncode == 0, finished.stderr[-2000:]
    return json.loads(finished.stdout.strip().splitlines()[-1])
