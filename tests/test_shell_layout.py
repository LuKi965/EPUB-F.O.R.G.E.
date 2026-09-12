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
    PdfConversionPage,
    RebuildPage,
    SettingsPage,
    ToolsPage,
)
from epubforge.gui.shell.pdf_backend import DemoPdfBackend  # noqa: E402
from epubforge.gui.shell.responsive import LayoutMode  # noqa: E402
from epubforge.gui.strings import set_language, tr  # noqa: E402
from tests.geometry import (  # noqa: E402
    problems_with,
    sideways_scrolling,
    where,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The five windows the design package names. The page gets a little less than
#: the window: the sidebar takes 244 px, or 64 when it is compact.
SIZES = ((1440, 900), (1180, 700), (1000, 650), (900, 600), (800, 560))

#: The same stylesheet with a larger type size — the stand-in for a wider font
#: face, built once because generating it writes icon files to disk.
WIDER_TYPE = tokens_module.stylesheet(tokens_module.DARK).replace(
    "font-size: 10pt", "font-size: 13pt"
)

#: Wider still, and 16 is not a round number picked for effect. The Windows
#: runner draws in Segoe UI and failed the ordinary tests at the ordinary
#: font (0.4.4, build 70); this machine's face does not, so the failure had to
#: be reached by widening the type until it appeared. Measured, stepping 10 →
#: 28: the drawer's settings list is first squeezed at **16 pt**, and the
#: converter's results list at 16 pt as well. 13 pt — what `WIDER_TYPE` uses —
#: reproduces neither, which is why the stress class did not catch this.
#:
#: So this is a stand-in for a wider *face* at the ordinary size, not a test
#: of large type: what it asserts is that the layout changes shape rather than
#: scrolling sideways, which is true at every size and every face.
MUCH_WIDER_TYPE = tokens_module.stylesheet(tokens_module.DARK).replace(
    "font-size: 10pt", "font-size: 16pt"
)


@pytest.fixture
def wider_face(qt_app):
    """The stylesheet a wider interface font amounts to, for one test."""
    before = qt_app.styleSheet()
    qt_app.setStyleSheet(MUCH_WIDER_TYPE)
    yield
    qt_app.setStyleSheet(before)


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


def every_screen(qt_app, tokens=None):
    """One of each, freshly built, with the state that makes them worth looking at."""
    tokens = tokens or tokens_module.DARK
    yield "start", HomePage(tokens, HISTORY)
    yield "narzedzia", ToolsPage(tokens)
    yield "historia", HistoryPage(tokens, HISTORY)
    yield "ustawienia", SettingsPage(tokens)


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
    def test_every_category_name_fits_the_column_it_is_written_in(
        self, qt_app, host, size
    ):
        """The column used to be a written 150 px, which is 27 short of *Wygląd
        i typografia*: the name lost its last four letters, **clipped** rather
        than elided — no ellipsis, cut mid-letter. The tooltip and the
        accessible name still carried the whole thing, so it was reachable, but
        a person looking at the drawer had no way to know that.

        The acceptance list says a check on buttons has to cover their whole
        text, and this is why: `problems_with` sees a widget that is on screen
        and the right size, because it is — with four letters missing.

        Seen first in a screenshot of the real window, then written down here.
        """
        page = rebuild_page(qt_app)
        try:
            page.start(["Powiesc.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, size)
            page._open_drawer()
            for _ in range(8):
                qt_app.processEvents()
            drawer = page.drawer
            if not drawer.category_column.isVisibleTo(drawer):
                # Compact swaps the column for a combo box, which is a
                # different answer to the same question and has its own test.
                return
            cut = [
                one.text() for one in drawer._buttons_by_category.values()
                if one.width() < one.sizeHint().width()
            ]
            assert not cut, (size, cut, drawer.category_column.width())
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


class TestTheConverterIsLaidOutToo:
    """The module D-057 created had **no layout test at all**.

    Every test in this file was written when there was one task page, and the
    second one inherited none of them: not the sizes, not the long batch, not
    the question of whether its main action can be reached. A module that is
    its own module has to be its own module here as well, or "separate" means
    separate everywhere except where it is checked.
    """

    @staticmethod
    def _page(qt_app):
        return PdfConversionPage(tokens_module.DARK, DemoPdfBackend())

    @staticmethod
    def _documents(count: int) -> "list[str]":
        return [f"/dokumenty/Instrukcja {number:02d}.pdf" for number in range(count)]

    @pytest.mark.parametrize("size", SIZES)
    def test_the_settings_are_whole_and_the_action_is_reachable(self, qt_app, host, size):
        page = self._page(qt_app)
        try:
            page.start(self._documents(3))
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, size)
            assert not problems_with(page, main_action=page.convert_button), size
        finally:
            finish(page)

    @pytest.mark.parametrize("count", [0, 1, 3, 50, 500])
    def test_a_long_batch_does_not_bury_the_conversion(self, qt_app, host, count):
        page = self._page(qt_app)
        try:
            documents = self._documents(count)
            if not documents:
                page.start(documents)
                assert page.stage is Stage.FILES
                return
            page.start(documents)
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            # Since A09 the expectation differs by composition. At 900×600
            # the column is single and the action is in the footer, outside
            # everything that scrolls: the list is then as tall as its rows
            # and the page scrolls as one surface — a list scrolling inside
            # the page was the audit's own finding. Wide, beside the summary
            # column, the list keeps its share of the page as before (F08).
            laid_out(qt_app, page, host, (900, 600))
            listing = page.document_list
            assert listing.verticalScrollBar().maximum() == 0, (count, "lista przewija sie w srodku strony")
            assert not problems_with(page, main_action=page.convert_button), count
            laid_out(qt_app, page, host, (1440, 900))
            for _ in range(6):
                qt_app.processEvents()
            assert listing.height() <= int(page.height() * listing.SHARE_OF_THE_PAGE) + 2, (
                count, listing.height(), page.height()
            )
            assert not problems_with(page, main_action=page.convert_button), count
        finally:
            finish(page)

    def test_the_conversion_is_on_screen_and_not_below_the_documents(
        self, qt_app, host
    ):
        """Measured, because "reachable" and "on screen" are not the same.

        `problems_with` asks whether the main action exists and can be
        scrolled to; both were true of a button that sat **889 px below** a
        600-pixel page with twelve documents in it. The rebuild's footer put
        its own action at 580 on the same page. That difference is the whole
        of F08, and this module had none of it.
        """
        page = self._page(qt_app)
        try:
            page.start(self._documents(12))
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (900, 600))
            assert not page.footer.isHidden(), "wąsko: stopka miała się pojawić"
            assert page.footer.holds(page.convert_button)
            bottom = where(page.convert_button, page).bottom()
            assert bottom <= page.height(), (bottom, page.height())

            # And back in the column when there is room beside the list.
            laid_out(qt_app, page, host, (1440, 900))
            assert page.footer.isHidden(), "szeroko: stopka nie jest potrzebna"
            assert not page.footer.holds(page.convert_button)
        finally:
            finish(page)

    def test_there_is_never_a_second_live_conversion_button(self, qt_app, host):
        """The same trap the rebuild fell into: a new state builds a new
        button while the old one is still parented to the footer."""
        from PySide6.QtWidgets import QPushButton

        page = self._page(qt_app)
        try:
            page.start(self._documents(4))
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (900, 600))
            page.start(self._documents(2))
            settle(qt_app, lambda: page.stage is Stage.PLAN and len(page.documents) == 2)
            laid_out(qt_app, page, host, (900, 600))
            inside = page.footer.findChildren(QPushButton)
            assert len(inside) == 1, [one.text() for one in inside]
            shown = [
                one for one in page.findChildren(QPushButton)
                if one.text() == tr("pdf.convert") and one.isVisibleTo(page)
            ]
            assert len(shown) == 1, [one.text() for one in shown]
        finally:
            finish(page)

    def test_the_results_are_whole_at_every_size(self, qt_app, host):
        page = self._page(qt_app)
        try:
            page.start(self._documents(2) + ["/dokumenty/Skan bez tekstu.pdf"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            page.run()
            settle(qt_app, lambda: page.stage is Stage.RESULTS)
            for size in SIZES:
                laid_out(qt_app, page, host, size)
                assert not problems_with(page), size
        finally:
            finish(page)

    def test_the_results_survive_being_narrowed_and_widened_again(self, qt_app, host):
        """Both directions, on one page, because the shape has a memory.

        The test above walks the sizes downwards and that is not an accident
        of how it was written — it is the harder direction. A composition
        decided while the page was wide does not undo itself when the page
        narrows unless something asks it to, and the block that will not
        shrink keeps its width and hangs over the edge rather than reporting a
        resize anybody could notice. Measured on the Windows runner as a
        results list squeezed to 290 px for rows that could not be drawn in
        less than 405 (0.4.4, build 70).

        So: down, then up, then down again, and the layout has to be whole at
        every step — not merely whole the first time it reaches a width.

        At the ordinary font on purpose. A first version ran this under a
        wider one and failed on the Windows runner — on `Stepper`, which is
        neither this test's subject nor fixed (EF-101). A direction test that
        fails for an unrelated reason stops being a direction test.
        """
        page = self._page(qt_app)
        try:
            page.start(self._documents(2) + ["/dokumenty/Skan bez tekstu.pdf"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            page.run()
            settle(qt_app, lambda: page.stage is Stage.RESULTS)
            walk = list(SIZES) + list(reversed(SIZES)) + list(SIZES)
            for size in walk:
                laid_out(qt_app, page, host, size)
                assert not problems_with(page), size
        finally:
            finish(page)


class TestNothingSetsAColumnsWidthByItself:
    """The defect behind both failures of the 0.4.4 release build.

    Neither was reproducible here: the Windows runner draws in Segoe UI, wider
    than this machine's face, and the pages fitted at every size measured
    locally. What went wrong is not really about width, though — it is about a
    widget declaring that it *cannot* be narrower, which is a statement about
    the widget and true on every machine. So these ask that, and not how many
    pixels anything happens to take here.

    Two widgets said it. `StatusBadge` was `Fixed`, which forbids growing —
    the behaviour that was wanted — and shrinking, which was not. A
    `QPushButton` has no way at all to be narrower than its label, which on a
    secondary action with a long sentence on it decided how wide the whole
    results page had to be.
    """

    def test_a_status_badge_can_be_narrower_than_its_word(self, qt_app):
        from PySide6.QtGui import QFontMetrics

        from epubforge.gui.shell.widgets import StatusBadge

        badge = StatusBadge("Nie sprawdzono", "warning", tokens_module.DARK)
        whole = QFontMetrics(badge.font()).horizontalAdvance("Nie sprawdzono")
        assert badge.minimumSizeHint().width() < badge.sizeHint().width(), (
            "plakietka nie umie byc wezsza niz jest — to ustawia podloge "
            "kazdej kolumny, w ktorej stoi"
        )
        # And the word is still worth something: it may shorten, not vanish.
        assert badge.minimumSizeHint().width() > 0
        assert whole > 0

    def test_and_still_says_the_status_three_ways(self, qt_app):
        """Colour, glyph and word — the rule the class exists for. Shortening
        the word must not be a way round it, so the whole of it stays where a
        person and a screen reader can both reach it."""
        from epubforge.gui.shell.widgets import StatusBadge

        badge = StatusBadge("Nie sprawdzono", "warning", tokens_module.DARK)
        assert badge.accessibleName() == "Nie sprawdzono"
        assert badge.toolTip() == "Nie sprawdzono"

    def test_a_long_secondary_label_does_not_decide_the_page_width(self, qt_app):
        from PySide6.QtGui import QFontMetrics

        from epubforge.gui.shell.widgets import button

        said = "Przekaż utworzony EPUB do przebudowy"
        plain = button(said)
        eliding = button(said, elides=True)
        whole = QFontMetrics(eliding.font()).horizontalAdvance(said)
        assert plain.minimumSizeHint().width() >= whole, (
            "zwykly przycisk mial nie umiec sie zwezic — jesli umie, ten "
            "test przestal o cokolwiek pytac"
        )
        assert eliding.minimumSizeHint().width() < whole
        assert eliding.toolTip() == said
        assert eliding.accessibleName() == said

    def test_a_shortened_label_does_not_shorten_the_button(self, qt_app):
        """The label gives way to the room the row has — not to itself.

        Measured before the change, with this machine's DejaVu Sans: eliding
        the path in the middle to a width, then again to the width of what
        came out, is not a fixed point. At 16 pt it went 39, 37, 35
        characters; at 10 pt 65, 63. `elidedText` at exactly the advance of
        its own result comes back a character or two shorter, face by face.
        A button whose size hint followed the *shown* label handed that
        narrower width to the layout, the layout handed it back as the
        button's width, and the label was elided again to fit it. This
        machine's face stops after two or three rounds; the Windows runner's
        went on to `\\bardz…ybrany`, thirteen characters of a path in a row
        726 px wide (Tests (Windows) #71 on 631ff2e).

        So the hint is the whole label's, whatever is showing, and the
        button takes the room the row has.
        """
        from PySide6.QtWidgets import QHBoxLayout

        from epubforge.gui.shell.widgets import button

        path = "/" + "/".join(["bardzo-dluga-nazwa-folderu"] * 8) + "/wybrany"
        for points in (10, 16):
            row = QWidget()
            row.setStyleSheet(f"font-size: {points}pt")
            lane = QHBoxLayout(row)
            lane.setContentsMargins(0, 0, 0, 0)
            eliding = button(path, elides=True, elide="middle")
            lane.addWidget(eliding)
            lane.addStretch(1)
            row.setFixedWidth(400)
            row.show()
            try:
                asked = eliding.sizeHint().width()
                assert asked > 400, (points, "sciezka ma nie miescic sie w wierszu")
                for _ in range(12):
                    qt_app.processEvents()
                assert eliding.sizeHint().width() == asked, (
                    points, "podpowiedz rozmiaru poszla za skroconym napisem"
                )
                assert eliding.width() == 400, (points, eliding.width(), eliding.text())
                assert "…" in eliding.text(), (points, eliding.text())
                assert eliding.text().endswith("wybrany"), (points, eliding.text())
            finally:
                row.close()


class TestBothThemes:
    """The light theme shipped and nothing ever laid it out.

    Every layout test in this file built its pages with `tokens_module.DARK`,
    so the second theme — a whole stylesheet, its own metrics, its own
    padding — was drawn only by the application. The acceptance list asks for
    both, and it asks because a theme is not a palette swap here: the sheet
    sets sizes as well as colours, and a control lost behind an edge is lost
    in whichever theme did it.
    """

    #: Built once. Not because generating them is slow — it is not — but
    #: because `QApplication.setStyleSheet` is: it re-polishes every widget
    #: the application owns, and by the middle of this file that is thousands.
    #: Six calls to it took the suite from half a minute to over ten, which is
    #: why the sheet goes on the *page* here and not on the application. The
    #: page is what is being measured either way.
    SHEETS = {name: tokens_module.stylesheet(getattr(tokens_module, name))
              for name in ("DARK", "LIGHT")}

    @pytest.mark.parametrize("theme", ["DARK", "LIGHT"])
    @pytest.mark.parametrize("size", [(1440, 900), (900, 600), (800, 560)])
    def test_no_control_is_lost_in_either_theme(self, qt_app, host, theme, size):
        tokens = getattr(tokens_module, theme)
        for name, page in every_screen(qt_app, tokens):
            try:
                page.setStyleSheet(self.SHEETS[theme])
                laid_out(qt_app, page, host, size)
                assert not problems_with(page), (theme, name, size)
            finally:
                finish(page)

    @pytest.mark.parametrize("theme", ["DARK", "LIGHT"])
    def test_the_plan_keeps_its_main_action_in_either_theme(self, qt_app, host, theme):
        tokens = getattr(tokens_module, theme)
        page = RebuildPage(tokens, DemoBackend())
        try:
            page.setStyleSheet(self.SHEETS[theme])
            page.start(["Powiesc.epub", "Zbior.epub", "Poradnik.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            for size in ((1440, 900), (900, 600)):
                laid_out(qt_app, page, host, size)
                assert not problems_with(page, main_action=page.run_button), (theme, size)
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


class TestALargerFontDoesNotBreakThePage:
    """A page under a font half again as large is squeezed, not broken.

    Build 66 failed on Windows and nowhere else: Segoe UI is wider than the
    fonts on a test machine, and two pages that fitted here needed horizontal
    scrolling there. Fonts cannot be installed here, but the effect can — the
    same stylesheet at a larger type size squeezes the same layouts the same
    way.

    What this asks of them is deliberately not "does it still fit". At 13pt on
    a face that is already wide, *nothing* fits, and a page that scrolls
    sideways for somebody who has chosen enormous text is a page doing what it
    should. What must hold at any size is that the layout stays **whole**:
    controls with a real size, none drawn over another, the main action still
    there. That is what caught the drawer's category column — seven buttons
    squeezed past their minimum into each other — here, before a build.

    Whether things *fit* is `TestEveryScreenAtEverySize`, at the real font,
    which is the question Windows answers for Windows and this machine for
    this one.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def wide_type(cls, qt_app):
        """Set once for the whole class.

        Re-polishing every live widget against a freshly generated stylesheet
        is not free — done per test it cost more than the measurements did.
        """
        before = qt_app.styleSheet()
        qt_app.setStyleSheet(WIDER_TYPE)
        yield
        qt_app.setStyleSheet(before)

    @pytest.mark.parametrize("size", SIZES)
    def test_the_drawer_survives_it(self, qt_app, host, wide_type, size):
        page = rebuild_page(qt_app)
        try:
            page.start(["a.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, size)
            page._open_drawer()
            for _ in range(8):
                qt_app.processEvents()
            assert not problems_with(page.drawer, allow_sideways=True), size
            page.drawer.close_drawer()
        finally:
            finish(page)

    @pytest.mark.parametrize("size", SIZES)
    def test_a_wider_font_changes_the_shape_instead_of_scrolling_sideways(
        self, qt_app, host, wider_face, size
    ):
        """The one thing `allow_sideways` must not be allowed to excuse.

        Every other test in this class permits sideways scrolling, on the
        argument that at half again the type nothing fits and a person who
        chose that has chosen it. True of *height* and of a page as a whole —
        and it let a real defect through: the drawer's panel kept the width a
        narrower font gave it, so the settings list inside it was squeezed
        until it had to scroll sideways. That is not "does not fit", it is a
        list a person cannot read the right-hand side of, and no amount of
        larger type asks for it.

        Found on the Windows runner, which draws in Segoe UI — wider than this
        machine's face — where it failed the ordinary test at the ordinary
        font (0.4.4, build 70). This is that failure made reproducible
        anywhere: a wider font must move the *shape* — the panel widens, and
        past what the page can give, the category rail folds into its combo —
        never the scroll bar.
        """
        page = rebuild_page(qt_app)
        try:
            page.start(["a.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, size)
            page._open_drawer()
            for _ in range(8):
                qt_app.processEvents()
            assert not sideways_scrolling(page.drawer), size
            page.drawer.close_drawer()
        finally:
            finish(page)

    @pytest.mark.parametrize("size", SIZES)
    @pytest.mark.parametrize("name", ["library", "diagnostics", "corpus"])
    def test_and_so_does_every_tool(self, qt_app, host, wide_type, name, size):
        tools = ToolsPage(tokens_module.DARK)
        try:
            tools.open_tool(name)
            page = tools.router.currentWidget()
            laid_out(qt_app, tools, host, size)
            for _ in range(4):
                qt_app.processEvents()
            assert not problems_with(page, allow_sideways=True), (name, size)
        finally:
            finish(tools)

    @pytest.mark.parametrize("size", [(1440, 900), (900, 600), (800, 560)])
    def test_and_the_pages_a_person_starts_on(self, qt_app, host, wide_type, size):
        for name, page in every_screen(qt_app):
            try:
                laid_out(qt_app, page, host, size)
                assert not problems_with(page, allow_sideways=True), (name, size)
            finally:
                finish(page)


class TestF08ALongBatchDoesNotBuryTheDecision:
    """*„Główna akcja osiągalna bez przewijania setek wierszy"* — and the
    batches the acceptance list names: 0, 1, 3, 50 and 500.

    The plan used to put the whole list above the presets and the main action
    and let the page grow to fit it, so a shelf of five hundred put the one
    decision that has nothing to do with the five hundred four hundred rows
    down.
    """

    BATCHES = (0, 1, 3, 50, 500)

    @staticmethod
    def _books(count: int) -> "list[str]":
        """Long titles, Unicode, no author, awkward paths — the list the
        acceptance asks for, not five hundred copies of one clean name."""
        made = []
        for number in range(count):
            if number % 7 == 3:
                name = "Bardzo-dluga-nazwa-" + "z-mysnikami-" * 6 + str(number)
            elif number % 7 == 5:
                name = f"Zażółć gęślą jaźń — wydanie {number}"
            else:
                name = f"Ksiazka {number}"
            made.append(f"/polka/{number % 4}/{name}.epub")
        return made

    @pytest.mark.parametrize("count", BATCHES)
    def test_the_list_stops_growing_and_the_action_stays_reachable(
        self, qt_app, host, count
    ):
        page = rebuild_page(qt_app)
        try:
            books = self._books(count)
            if not books:
                # The empty batch is its own case: nothing to plan, and the
                # page must not pretend otherwise.
                page.start(books)
                assert page.stage is Stage.FILES
                return
            page.start(books)
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (1440, 900))
            assert len(page.books) == count

            listing = page.book_list
            assert listing.height() <= int(page.height() * listing.SHARE_OF_THE_PAGE) + 2, (
                count, listing.height(), page.height()
            )
            # And the decision is where a person can reach it without going
            # through the list: above the fold or in the footer, never below
            # five hundred rows.
            assert not problems_with(page, main_action=page.run_button), count
        finally:
            finish(page)

    def test_a_long_batch_does_not_make_the_page_taller_than_a_short_one(
        self, qt_app, host
    ):
        """The measurement behind the rule: fifty books and three books make
        the same page, because the difference scrolls inside the list."""
        heights = {}
        for count in (3, 50):
            page = rebuild_page(qt_app)
            try:
                page.start(self._books(count))
                settle(qt_app, lambda: page.stage is Stage.PLAN)
                laid_out(qt_app, page, host, (1440, 900))
                heights[count] = page.book_list.height()
            finally:
                finish(page)
        assert heights[50] <= heights[3] * 3, heights
        assert heights[50] <= int(900 * 0.56), heights

    def test_the_footer_carries_the_action_when_the_window_is_narrow(self, qt_app, host):
        """02-UI-DESIGN: in a narrow layout the footer stays outside the
        scrolled content — and there is never a second live primary button."""
        page = rebuild_page(qt_app)
        try:
            page.start(self._books(30))
            settle(qt_app, lambda: page.stage is Stage.PLAN)

            laid_out(qt_app, page, host, (1440, 900))
            assert page.footer.isHidden(), "szeroko: stopka nie jest potrzebna"
            assert page.run_button.parent() is not page.footer

            # Every mode but WIDE puts the summary — and the main action in it
            # — below the list, so every one of them wants the footer.
            laid_out(qt_app, page, host, (900, 600))
            for _ in range(6):
                qt_app.processEvents()
            assert not page.footer.isHidden(), "wąsko: stopka miała się pojawić"
            assert page.run_button.parent() is page.footer
            # One button, moved — not two.
            from PySide6.QtWidgets import QPushButton

            primaries = [
                one for one in page.findChildren(QPushButton)
                if one.text() == tr("shell.run") and one.isVisibleTo(page)
            ]
            assert len(primaries) == 1, [one.text() for one in primaries]
        finally:
            finish(page)

    def test_a_second_batch_does_not_leave_the_old_button_in_the_footer(
        self, qt_app, host
    ):
        """The footer holds one action, not a place where buttons pile up.

        Every state of this page builds its own widgets, so a second plan makes
        a **new** `run_button` while the previous one is still parented to the
        footer — where the body's own teardown cannot reach it. The result is
        two live primary buttons side by side, which is exactly what moving the
        one button instead of duplicating it was for.

        Found in a screenshot of the real window on real books, not in a
        mock-up and not by reading the code.
        """
        from PySide6.QtWidgets import QPushButton

        page = rebuild_page(qt_app)
        try:
            page.start(self._books(4))
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (900, 600))
            for _ in range(6):
                qt_app.processEvents()
            assert not page.footer.isHidden()

            page.start(self._books(2))
            settle(qt_app, lambda: page.stage is Stage.PLAN and len(page.books) == 2)
            laid_out(qt_app, page, host, (900, 600))
            for _ in range(6):
                qt_app.processEvents()

            inside = page.footer.findChildren(QPushButton)
            assert len(inside) == 1, [one.text() for one in inside]
            assert inside[0] is page.run_button, "w stopce został stary przycisk"
            shown = [
                one for one in page.findChildren(QPushButton)
                if one.text() == tr("shell.run") and one.isVisibleTo(page)
            ]
            assert len(shown) == 1, [one.text() for one in shown]
        finally:
            finish(page)

    def test_the_footer_says_the_same_number_as_the_list(self, qt_app, host):
        page = rebuild_page(qt_app)
        try:
            page.start(self._books(6))
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (900, 600))
            for _ in range(6):
                qt_app.processEvents()
            assert tr("shell.plan.count", count=6) == page.footer.count.text()
            page._toggle_book(page.books[0], False)
            assert tr("shell.plan.count", count=5) == page.footer.count.text()
        finally:
            finish(page)


class TestF07TheWindowFitsTheScreenLiterally:
    """The floor was a constant, and a constant cannot fit every screen.

    `opening_size` and `_restore_where_it_was` both said `max(MIN_WINDOW, …)`,
    so on any desktop smaller than 800×520 the window opened *larger than the
    screen*, with its right-hand column where nothing can drag it back. The
    checker agreed with itself: it called that "fits", because it compared
    against `max(screen, MIN_WINDOW)` — which made the one screen where the
    answer matters the one screen it could not fail on.
    """

    #: A desktop smaller than the size this interface wishes for.
    SMALL = (640, 480)

    class Desk:
        """A screen of a stated size, for asking the two functions directly."""

        def __init__(self, width, height):
            from PySide6.QtCore import QRect

            self._room = QRect(0, 0, width, height)

        def availableGeometry(self):  # noqa: N802 - Qt casing
            return self._room

    def test_the_floor_is_this_screens_and_not_a_constant(self):
        from epubforge.gui.shell.window import smallest_here

        big = smallest_here(self.Desk(1920, 1080))
        assert big == tokens_module.MIN_WINDOW, "na dużym ekranie obietnica zostaje"

        small = smallest_here(self.Desk(*self.SMALL), frame=(10, 30))
        assert small[0] <= self.SMALL[0] - 10 and small[1] <= self.SMALL[1] - 30
        assert small[0] < tokens_module.MIN_WINDOW[0], "podłoga nie zeszła poniżej życzenia"

    def test_the_opening_size_never_exceeds_the_screen_minus_the_frame(self):
        from epubforge.gui.shell.window import opening_size

        for size in ((1920, 1080), (1366, 768), (1024, 600), (640, 480), (480, 360)):
            frame = (12, 36)
            width, height = opening_size(self.Desk(*size), frame=frame)
            assert width + frame[0] <= size[0], size
            assert height + frame[1] <= size[1], size

    def test_a_real_window_ends_up_inside_the_working_area(self, qt_app):
        """Not the two functions — the window, after Qt has had its say about
        frames and layout minimums."""
        from epubforge.gui.shell.window import MainWindow

        window = MainWindow(tokens_module.DARK, backend=DemoBackend())
        try:
            window.show()
            for _ in range(6):
                qt_app.processEvents()
            window.fit_the_screen()
            for _ in range(6):
                qt_app.processEvents()
            room = (window.screen() or qt_app.primaryScreen()).availableGeometry()
            frame = window.frameGeometry()
            assert frame.width() <= room.width() + 1, (frame, room)
            assert frame.height() <= room.height() + 1, (frame, room)
            assert room.contains(frame.topLeft())
        finally:
            window.rebuild.runner.stop()
            window.rebuild.runner.wait_for_idle()
            window.close()

    def test_and_every_control_is_still_reachable_when_it_is_squeezed(self, qt_app, host):
        """The fallback the handoff allows is a scroll bar, not a button
        nobody can get to: at 640×480 the plan still has its main action."""
        page = rebuild_page(qt_app)
        try:
            page.start(["Powiesc.epub", "Zbior.epub"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, self.SMALL)
            assert not problems_with(page, main_action=page.run_button,
                                     allow_sideways=True)
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


class TestALongPathDoesNotWidenThePlanA08:
    """A08 of the 0.4.4 recovery audit, reproduced with Qt: at 800×520 with
    a long destination folder the plan needed 231 px of sideways scrolling —
    viewport 726, content 957 — because the destination was an ordinary
    `QPushButton` carrying the whole path in a `QHBoxLayout`, and a button
    is as wide as its label. The layout check passed because it was never
    given a long path; the acceptance data has to be the person's data.

    The audit names both task pages' button; both are asked. The path gives
    way in the middle, so the folder a person chose stays readable, and the
    whole path is in the tooltip.
    """

    LONG = pathlib.Path("/" + "/".join(["bardzo-dluga-nazwa-folderu"] * 8) + "/wybrany")

    @staticmethod
    def _pages(qt_app):
        yield "przebudowa", rebuild_page(qt_app), ["Powiesc.epub"]
        yield "konwersja", PdfConversionPage(tokens_module.DARK, DemoPdfBackend()), ["Instrukcja.pdf"]

    @pytest.mark.parametrize("size", [(800, 520), (900, 600), (1440, 900)])
    def test_the_plan_is_whole_with_a_long_destination(self, qt_app, host, size):
        for name, page, files in self._pages(qt_app):
            try:
                page.destination = self.LONG
                page.start(files)
                settle(qt_app, lambda: page.stage is Stage.PLAN)
                laid_out(qt_app, page, host, size)
                for _ in range(6):
                    qt_app.processEvents()
                assert not problems_with(page), (name, size, face_of(page))
                button = page.destination_button
                assert button.width() > 0 and button.isVisibleTo(page), (name, size)
                assert str(self.LONG) in button.toolTip(), (name, "pelna sciezka ma byc w podpowiedzi")
                # Elided in the middle: the chosen folder is what shows.
                assert button.text().endswith("wybrany"), (
                    name, size, button.text(), button.width(), face_of(page)
                )
            finally:
                finish(page)

    def test_a_short_destination_is_shown_whole(self, qt_app, host):
        """The negative: a path that fits is not shortened, and the tooltip
        is the button's own tip, not the path repeated. Compared as the
        platform spells it: on Windows a `Path` prints with backslashes."""
        short = pathlib.Path("/home/kto/polka")
        for name, page, files in self._pages(qt_app):
            try:
                page.destination = short
                page.start(files)
                settle(qt_app, lambda: page.stage is Stage.PLAN)
                laid_out(qt_app, page, host, (1440, 900))
                for _ in range(6):
                    qt_app.processEvents()
                assert page.destination_button.text() == str(short), name
                assert "…" not in page.destination_button.text(), name
            finally:
                finish(page)

    def test_a_wider_face_does_not_change_the_answer(self, qt_app, host, wider_face):
        for name, page, files in self._pages(qt_app):
            try:
                page.destination = self.LONG
                page.start(files)
                settle(qt_app, lambda: page.stage is Stage.PLAN)
                laid_out(qt_app, page, host, (800, 520))
                for _ in range(6):
                    qt_app.processEvents()
                assert not problems_with(page), (name, face_of(page))
            finally:
                finish(page)

    def test_a_choice_worded_as_a_sentence_does_not_set_the_floor(self, qt_app, host):
        """What the Windows runner named once the diagnostics named more than
        the container (Tests (Windows) #73 on b72a8b0): at the wider face the
        plan of the conversion scrolled sideways by 70 px, and the widest
        thing in it was the radio button *Tekst dopasowujący się do ekranu*,
        reaching 749 px in a viewport 726 wide. A `QRadioButton` is as wide
        as its label and cannot be narrower; measured here at 16 pt its
        minimum was 389 px for a sentence 358 px wide, and on the runner's
        face about 700. The choice is therefore a `Choice`: a button with the
        sentence in a wrapping label beside it, whose floor is the longest
        word and not the sentence.
        """
        from PySide6.QtGui import QFontMetrics
        from PySide6.QtWidgets import QComboBox

        from epubforge.gui.shell.widgets import Choice

        page = PdfConversionPage(tokens_module.DARK, DemoPdfBackend())
        try:
            page.start(["Instrukcja.pdf"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (800, 520))
            choices = page.findChildren(Choice)
            assert len(choices) == 2, [one.text() for one in choices]
            for choice in choices:
                sentence = QFontMetrics(choice.sentence.font()).horizontalAdvance(choice.text())
                assert choice.minimumSizeHint().width() < sentence, (
                    choice.text(), choice.minimumSizeHint().width(), sentence
                )
                assert choice.button.accessibleName() == choice.text()
            # The sentence is still the way to choose: pressing it presses.
            second = next(one for one in choices if not one.isChecked())
            second.sentence.pressed.emit()
            assert second.isChecked()
            assert page.settings.layout == "fixed"
            # And the combo boxes beside them are the next floor down: by
            # default a box is as wide as its widest choice (373 px at 16 pt
            # here for *Pytaj przy każdym dokumencie*), which on the runner's
            # face is over the same 726 px. They ask for a few characters.
            combos = page.findChildren(QComboBox)
            assert len(combos) == 2, [one.accessibleName() for one in combos]
            for combo in combos:
                widest = max(
                    QFontMetrics(combo.font()).horizontalAdvance(combo.itemText(index))
                    for index in range(combo.count())
                )
                assert combo.minimumSizeHint().width() < widest, (
                    combo.accessibleName(), combo.minimumSizeHint().width(), widest
                )
        finally:
            finish(page)


class TestTheSmallWindowKeepsTheDecisionInSightA09:
    """A09 of the 0.4.4 recovery audit: *scaling keeps the rectangles and
    loses the information*. Four things the audit saw at 900×600, each
    measured here on the conversion plan with one document before anything
    was changed:

    - the status badge in the row showed `g…` for *gotowa* — at 1024×720 as
      much as at 800×520, in a row 632 px wide with 190 px of slack;
    - the layout choice sat 532 px down a scroll surface 515 px tall, under
      the header, the stepper and the whole documents card;
    - the footer's count, *1 dokument gotowy do konwersji*, wrapped into
      three lines in a column 108 px wide, in a footer 736 px wide;
    - the list scrolled inside itself inside the scrolling page.
    """

    @staticmethod
    def _plan(qt_app, host, size, documents=1):
        page = PdfConversionPage(tokens_module.DARK, DemoPdfBackend())
        page.start([f"Dokument-{index}.pdf" for index in range(documents)])
        settle(qt_app, lambda: page.stage is Stage.PLAN)
        laid_out(qt_app, page, host, size)
        for _ in range(8):
            qt_app.processEvents()
        return page

    @staticmethod
    def _surface(page):
        """The page's own scroll area — not the list's."""
        from PySide6.QtWidgets import QScrollArea

        return next(
            area for area in page.findChildren(QScrollArea)
            if area.objectName() != "boundedList" and area.isVisibleTo(page)
        )

    def test_the_status_word_is_whole_when_the_row_has_room(self, qt_app, host):
        """The badge shortened itself the way `ElidingButton` did (A08):
        its size hint followed the shown word, its policy is `Maximum`, so
        the layout handed the smaller hint straight back as its width, and
        the word was elided again to fit — down to one letter and an
        ellipsis in a row with room for the whole of it."""
        from PySide6.QtWidgets import QLabel

        from epubforge.gui.shell.widgets import StatusBadge

        for size in ((800, 520), (1024, 720)):
            page = self._plan(qt_app, host, size)
            try:
                badges = [one for one in page.findChildren(StatusBadge) if one.isVisibleTo(page)]
                assert badges, size
                for badge in badges:
                    word = badge.accessibleName()
                    chip = badge.findChild(QLabel)
                    assert chip.text().endswith(word), (size, chip.text(), badge.width())
            finally:
                finish(page)

    def test_the_badges_hint_does_not_follow_the_shown_word(self, qt_app):
        """The invariant under the test above, on the widget alone: in a row
        with room to spare the badge keeps the hint it asked for and shows
        the whole word after the event loop has had its turns."""
        from PySide6.QtWidgets import QHBoxLayout, QLabel

        from epubforge.gui.shell.widgets import Eliding, StatusBadge

        row = QWidget()
        lane = QHBoxLayout(row)
        lane.setContentsMargins(0, 0, 0, 0)
        lane.addWidget(Eliding("Instrukcja", "cardTitle"), 3)
        badge = StatusBadge("gotowa", "success", tokens_module.DARK)
        lane.addWidget(badge)
        row.setFixedWidth(600)
        row.show()
        try:
            asked = badge.sizeHint().width()
            for _ in range(10):
                qt_app.processEvents()
            assert badge.sizeHint().width() == asked, (badge.sizeHint().width(), asked)
            assert badge.findChild(QLabel).text().endswith("gotowa"), badge.findChild(QLabel).text()
        finally:
            row.close()

    @pytest.mark.parametrize("size", [(800, 520), (900, 600)])
    def test_the_layout_choice_is_in_sight_with_one_document(self, qt_app, host, size):
        """03-UI-UX: at 900×600 with one PDF the basic choice has to be
        visible without scrolling past repeated instructions. The decision
        this step is for comes first in the column; the documents, chosen a
        step earlier, are listed under it."""
        from epubforge.gui.shell.widgets import Choice

        page = self._plan(qt_app, host, size)
        try:
            surface = self._surface(page)
            assert surface.verticalScrollBar().value() == 0
            room = surface.viewport().height()
            choices = page.findChildren(Choice)
            assert len(choices) == 2
            for choice in choices:
                bottom = choice.mapTo(surface.widget(), choice.rect().bottomLeft()).y()
                assert bottom <= room, (size, choice.text(), bottom, room)
        finally:
            finish(page)

    def test_the_footer_count_stays_on_one_line(self, qt_app, host):
        """The count is one short sentence beside the main action, not a
        column of three words; the action keeps its whole width first."""
        page = self._plan(qt_app, host, (800, 520))
        try:
            assert not page.footer.isHidden()
            count = page.footer.count
            assert count.text() == tr("pdf.plan.count", count=1)
            # One line's worth of height asked for — the row is as tall as
            # the button beside it, so the height it gets is not the measure.
            assert count.sizeHint().height() < 1.6 * count.fontMetrics().lineSpacing(), (
                count.sizeHint().height(), count.width()
            )
            assert count.width() >= count.fontMetrics().horizontalAdvance(count.text())
            assert page.convert_button.width() >= page.convert_button.sizeHint().width()
        finally:
            finish(page)

    def test_the_footer_stacks_rather_than_cutting_the_count(self, qt_app):
        """What the Windows runner's face showed on the first run of this
        class (Tests (Windows) #77): `1 dokument gotowy do ko…` beside the
        button at 800×520, and `6 książek gotowych do prze…` at 900×600 on
        the rebuild — the footer had the room for one of the two whole, and
        the count lost. The design asks for a controlled second row at the
        extreme, not an ellipsis (03-UI-UX §54). Forced here by width, since
        this machine's face fits both in one row at every supported size.
        """
        from epubforge.gui.shell.widgets import ActionFooter, button

        footer = ActionFooter(tokens_module.DARK)
        action = button("Konwertuj do EPUB", kind="primary")
        said = "1 dokument gotowy do konwersji"
        footer.carry(action, said)
        # Room for the whole sentence alone, and not for the sentence and
        # the button side by side — the runner's case, in this face's units.
        sentence = footer.count.fontMetrics().horizontalAdvance(said)
        narrow = sentence + 2 * tokens_module.CONTENT_MARGIN + 30
        assert narrow < sentence + action.sizeHint().width() + 2 * tokens_module.CONTENT_MARGIN
        footer.setFixedWidth(narrow)
        footer.show()
        try:
            for _ in range(10):
                qt_app.processEvents()
            assert footer.count.text() == said, footer.count.text()
            assert action.width() >= action.sizeHint().width()
            assert action.y() > footer.count.y(), "akcja ma stac pod licznikiem, nie obok"
            footer.setFixedWidth(700)
            for _ in range(10):
                qt_app.processEvents()
            assert footer.count.text() == said
            assert action.y() == footer.count.y() or abs(action.y() - footer.count.y()) < action.height(), (
                "w szerokiej stopce jeden wiersz"
            )
        finally:
            footer.close()

    def test_the_footer_does_not_take_the_action_back(self, qt_app):
        """The second Windows run (Tests (Windows) #79): at 1440×900 the
        conversion button stayed in the footer, and the page's own column
        had lost it — *glowna akcja jest niewidoczna* on four tests. The
        footer had been narrow when it took the button (stacked), the page
        then moved the button home for the wide composition, and the
        footer's deferred re-arrangement, finding it no longer needed to
        stack, re-placed *its* action — reparenting a widget that was not
        its any more. The same sequence, forced by width."""
        from PySide6.QtWidgets import QVBoxLayout

        from epubforge.gui.shell.widgets import ActionFooter, button

        footer = ActionFooter(tokens_module.DARK)
        action = button("Konwertuj do EPUB", kind="primary")
        footer.setFixedWidth(120)
        footer.show()
        footer.carry(action, "1 dokument gotowy do konwersji")
        for _ in range(6):
            qt_app.processEvents()
        home = QWidget()
        column = QVBoxLayout(home)
        column.addWidget(action)
        home.show()
        footer.setFixedWidth(900)
        try:
            for _ in range(10):
                qt_app.processEvents()
            assert action.parent() is home, "stopka odebrala przycisk kolumnie"
            assert not footer.holds(action)
        finally:
            footer.close()
            home.close()

    def test_a_narrow_page_scrolls_as_one_surface(self, qt_app, host):
        """03-UI-UX: in the narrow composition, no list scroll inside the
        page scroll. The reason the list was bounded — the main action under
        four hundred rows (F08) — does not hold there: the action is in the
        footer, outside everything that scrolls. Wide, the list stays
        bounded beside the summary column, as before."""
        page = self._plan(qt_app, host, (800, 520), documents=12)
        try:
            listing = page.document_list
            assert listing.verticalScrollBar().maximum() == 0, "lista przewija sie w srodku strony"
            assert self._surface(page).verticalScrollBar().maximum() > 0
            laid_out(qt_app, page, host, (1440, 900))
            for _ in range(8):
                qt_app.processEvents()
            assert page.layout_mode is LayoutMode.WIDE
            assert listing.verticalScrollBar().maximum() > 0, "szeroka strona: lista ma byc ograniczona"
        finally:
            finish(page)


class TestTheSmallWindowHasACompactHeaderA09:
    """The tail of A09 and EF-101. 03-UI-UX's table for the small window:
    *tytuł 22–24 px jako punkt startowy; zwarty wskaźnik etapu*, and no
    describing the task twice. Measured before the change at 800×520: the
    header was 84 px in every mode — eyebrow 18, title 38 (32 px type),
    status 16 — and the stepper 44 with all four names, which at 20 pt on a
    900 px page reached 837 px in a viewport of 826 (EF-101).
    """

    @staticmethod
    def _face(qt_app, points: int):
        before = qt_app.styleSheet()
        qt_app.setStyleSheet(
            tokens_module.stylesheet(tokens_module.DARK).replace("font-size: 10pt", f"font-size: {points}pt")
        )
        return before

    def test_the_stepper_gives_way_before_the_page_scrolls_sideways(self, qt_app, host):
        """EF-101, reproduced: at 20 pt the four names of the conversion's
        stepper did not fit a 900 px page and the page scrolled sideways.
        The stepper measures its names against its width and keeps only the
        current step's name when they do not fit — whatever the mode says."""
        from epubforge.gui.shell.widgets import Stepper

        before = self._face(qt_app, 20)
        page = PdfConversionPage(tokens_module.DARK, DemoPdfBackend())
        try:
            page.start(["Instrukcja.pdf"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (900, 600))
            for _ in range(8):
                qt_app.processEvents()
            assert not problems_with(page), face_of(page)
            stepper = page.findChild(Stepper)
            texts = [label.text() for label in stepper._labels]
            assert texts[2].endswith(tr("pdf.step.settings")), texts
            # Squeezed exactly when the names do not fit — which is a fact
            # about the face: DejaVu Sans at 20 pt does not fit them in 826 px
            # and the runner's Segoe UI does (Tests (Windows) #91: 199 px for
            # the test sentence at 10 pt against 222 here). Either way the
            # page does not scroll sideways, and that is the property.
            squeezed = [index for index, text in enumerate(texts) if index != 2 and len(text) <= 2]
            assert bool(squeezed) == (not stepper._names_fit()), (texts, stepper.width(), face_of(page))
        finally:
            finish(page)
            qt_app.setStyleSheet(before)

    def test_the_stepper_alone_shrinks_to_numbers_when_the_names_do_not_fit(self, qt_app):
        from PySide6.QtGui import QFontMetrics

        from epubforge.gui.shell.widgets import Stepper

        stepper = Stepper(tokens_module.DARK)
        stepper.set_stage(Stage.FILES)
        names = [label.text() for label in stepper._labels]
        wide = sum(QFontMetrics(label.font()).horizontalAdvance(label.text()) for label in stepper._labels)
        stepper.setFixedWidth(wide // 2)
        stepper.show()
        try:
            for _ in range(8):
                qt_app.processEvents()
            squeezed = [label.text() for label in stepper._labels]
            assert squeezed[0] == names[0], "biezacy krok zachowuje nazwe"
            assert squeezed[1:] == ["2", "3", "4"], squeezed
            stepper.setFixedWidth(wide * 2)
            for _ in range(8):
                qt_app.processEvents()
            assert [label.text() for label in stepper._labels] == names
        finally:
            stepper.close()

    def test_the_header_is_shorter_in_a_small_window(self, qt_app, host):
        page = PdfConversionPage(tokens_module.DARK, DemoPdfBackend())
        try:
            page.start(["Instrukcja.pdf"])
            settle(qt_app, lambda: page.stage is Stage.PLAN)
            laid_out(qt_app, page, host, (800, 520))
            for _ in range(8):
                qt_app.processEvents()
            header = page.header
            assert not header.eyebrow.isVisibleTo(page), "w malym oknie modul nazywa pasek boczny"
            # In points, which is what the stylesheet sets: 18 pt is 24 px at
            # 96 dpi. `QFontInfo.pixelSize()` answered 32 here and -1 on the
            # Windows runner (Tests (Windows) #85) for the same point-sized
            # font, so it is not a measure two machines agree on.
            assert header.title.font().pointSizeF() <= 18, header.title.font().pointSizeF()
            assert header.height() <= 60, header.height()
            assert header.subtitle.isVisibleTo(page), "krotki status zostaje"
            laid_out(qt_app, page, host, (1440, 900))
            for _ in range(8):
                qt_app.processEvents()
            assert header.eyebrow.isVisibleTo(page)
            assert header.title.font().pointSizeF() > 18, header.title.font().pointSizeF()
        finally:
            finish(page)


def face_of(widget) -> str:
    """The face a widget is actually drawn in, for a failure that has to be
    read from another machine's log: the family Qt resolved (not the one the
    stylesheet asked for), its size both ways, the DPI it is scaled by, and
    the width of one Polish sentence in it — the number the Windows runner's
    first answers left out, when its face came out about 1.9 times wider
    than this machine's and nothing said why."""
    from PySide6.QtGui import QFontInfo, QFontMetrics

    font = widget.font()
    info = QFontInfo(font)
    sentence = "Tekst dopasowujący się do ekranu"
    return (
        f"{info.family()!r} (asked {font.family()!r}) {info.pointSize()}pt/{info.pixelSize()}px "
        f"(asked {font.pointSizeF()}pt/{font.pixelSize()}px) @ {widget.logicalDpiX()} dpi, "
        f"ratio {widget.devicePixelRatio()}, {sentence!r} = "
        f"{QFontMetrics(font).horizontalAdvance(sentence)} px"
    )
