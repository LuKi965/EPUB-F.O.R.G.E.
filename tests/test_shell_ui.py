"""The new window, checked where a person cannot: structure, states, safety.

Three things this file is for.

**Parity.** The old window's rule — every choice the program offers must be
offerable in the window — now has to hold for a window built out of a preset
and a drawer. `TestEveryChoiceIsStillReachable` is that rule, restated against
the option catalogue.

**The flow.** Files → analysis → plan → results, on a fake backend, including
the two states that are easy to leave untested: a cancelled run and a batch in
which one book fails.

**The promises.** Originals are never overwritten, a risky option is not
switched on behind somebody's back, Escape closes the drawer and gives focus
back, and every status says what it is in words as well as in colour.
"""

from __future__ import annotations

import os
import pathlib

import pytest

pytest.importorskip("PySide6.QtWidgets")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from epubforge.gui.shell import backend as backend_module  # noqa: E402
from epubforge.gui.shell import options as options_module  # noqa: E402
from epubforge.gui.shell import tokens as tokens_module  # noqa: E402
from epubforge.gui.shell.backend import DemoBackend, policy_for  # noqa: E402
from epubforge.gui.shell.models import (  # noqa: E402
    STATUS_LOOK,
    BookItem,
    BookStatus,
    JobRecord,
    Preset,
    RebuildPlan,
    Stage,
)
from epubforge.gui.shell.pages.rebuild import RebuildPage  # noqa: E402
from epubforge.gui.shell.window import MainWindow  # noqa: E402
from epubforge.gui.strings import EN, PL, tr  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(tokens_module.stylesheet(tokens_module.DARK))
    yield app


@pytest.fixture
def window(qt_app):
    win = MainWindow(tokens_module.DARK, backend=DemoBackend())
    yield win
    win.close()


@pytest.fixture
def page(qt_app):
    """The rebuild flow on its own, which is how it is meant to be testable."""
    widget = RebuildPage(tokens_module.DARK, DemoBackend())
    yield widget
    widget.runner.stop()
    # Asking is not the same as having stopped, and a thread that outlives its
    # test takes the next one down with it.
    widget.runner.wait_for_idle()
    widget.close()


def settle(app, page, until, tries: int = 200) -> None:
    """Spin the event loop until the flow reaches a state, or give up loudly."""
    import time

    for _ in range(tries):
        app.processEvents()
        if until():
            return
        time.sleep(0.01)
    raise AssertionError(f"nie doczekano się stanu; etap = {page.stage}")


class TestTheShellIsTheArchitectureThatWasApproved:
    def test_five_destinations_in_the_order_the_design_names(self, window):
        assert list(window.pages) == ["home", "rebuild", "tools", "history", "settings"]

    def test_settings_is_the_one_anchored_at_the_bottom(self, window):
        """Everything else is navigation; settings is where you go last."""
        bar = window.sidebar
        routes = [route for route, _glyph, _key in bar.ROUTES]
        assert routes == ["home", "rebuild", "tools", "history"]
        assert "settings" in bar.buttons

    def test_there_is_no_decorative_tile_in_the_sidebar(self):
        """Forbidden twice in the design package, and for a good reason: the
        application icon is already in the title bar and the taskbar."""
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "epubforge" / "gui" / "shell").rglob("*.py")
        )
        assert "brandGlyph" not in source
        assert '"EF"' not in source

    def test_the_specialist_panels_are_under_tools_and_not_beside_the_rebuild(self, window):
        window.navigate("tools")
        assert [name for name, *_ in window.tools.TOOLS] == [
            "library", "diagnostics", "corpus", "merge"
        ]

    def test_the_window_fits_the_smallest_supported_screen(self, window):
        assert (window.minimumWidth(), window.minimumHeight()) == tokens_module.MIN_WINDOW
        assert tokens_module.MIN_WINDOW <= (800, 520), (
            "the minimum is a promise about the smallest usable window, not a "
            "refusal to be that size"
        )

    def test_the_sidebar_collapses_when_the_window_is_narrow(self, window):
        """244 px of names is a lot to spend on a 900-pixel window."""
        window.show()
        window.resize(900, 600)
        QApplication.processEvents()
        assert window.sidebar.width() == tokens_module.SIDEBAR_COMPACT_WIDTH
        window.resize(1400, 900)
        QApplication.processEvents()
        assert window.sidebar.width() == tokens_module.SIDEBAR_WIDTH


class TestTheOneLayoutMechanism:
    """Three modes, two thresholds, and every page reading the same ruler."""

    @pytest.mark.parametrize(
        ("width", "expected"),
        [(1600, "WIDE"), (1180, "WIDE"), (1179, "MEDIUM"), (900, "MEDIUM"),
         (820, "MEDIUM"), (819, "COMPACT"), (640, "COMPACT")],
    )
    def test_the_mode_follows_the_width_of_the_content(self, width, expected):
        from epubforge.gui.shell.responsive import LayoutMode, mode_for

        assert mode_for(width) is getattr(LayoutMode, expected)

    def test_a_window_dragged_across_a_threshold_does_not_flap(self):
        """The slack is the point: without it, one pixel of mouse jitter
        rebuilds the composition twice a frame."""
        from epubforge.gui.shell.responsive import LayoutMode, mode_for

        assert mode_for(1170, LayoutMode.WIDE) is LayoutMode.WIDE
        assert mode_for(1155, LayoutMode.WIDE) is LayoutMode.MEDIUM
        assert mode_for(1180, LayoutMode.MEDIUM) is LayoutMode.WIDE

    def test_blocks_sit_side_by_side_when_wide_and_stack_when_not(self, qt_app):
        from PySide6.QtWidgets import QLabel

        from epubforge.gui.shell.responsive import LayoutMode, Panels

        panels = Panels()
        left, right = QLabel("A"), QLabel("B")
        panels.add(left, 2)
        panels.add(right, 1)
        grid = panels.layout()
        assert (grid.getItemPosition(grid.indexOf(right))[:2]) == (0, 1)
        panels.set_mode(LayoutMode.COMPACT)
        assert (grid.getItemPosition(grid.indexOf(right))[:2]) == (1, 0)

    def test_a_grid_of_cards_changes_its_column_count(self, qt_app):
        from PySide6.QtWidgets import QLabel

        from epubforge.gui.shell.responsive import Cards, LayoutMode

        cards = Cards({LayoutMode.WIDE: 4, LayoutMode.MEDIUM: 2, LayoutMode.COMPACT: 1})
        for name in "ABCD":
            cards.add(QLabel(name))
        assert cards.columns == 4
        cards.set_mode(LayoutMode.MEDIUM)
        assert cards.columns == 2
        grid = cards.layout()
        assert grid.getItemPosition(grid.indexOf(cards._items[2]))[:2] == (1, 0)
        cards.set_mode(LayoutMode.COMPACT)
        assert cards.columns == 1

    def test_the_same_widget_survives_a_reflow(self, qt_app):
        """Re-placed, never rebuilt: a card that is recreated on every resize
        loses its state, its focus and whatever somebody had typed in it."""
        from PySide6.QtWidgets import QLineEdit

        from epubforge.gui.shell.responsive import LayoutMode, Panels

        panels = Panels()
        edit = QLineEdit()
        edit.setText("nie zgub tego")
        panels.add(edit)
        panels.set_mode(LayoutMode.COMPACT)
        panels.set_mode(LayoutMode.WIDE)
        assert edit.text() == "nie zgub tego"
        assert edit.parent() is panels

    @pytest.mark.parametrize("route", ["home", "rebuild", "tools", "history", "settings"])
    def test_every_page_answers_the_ruler(self, window, route):
        from epubforge.gui.shell.responsive import Responsive

        assert isinstance(window.pages[route], Responsive), route


class TestTheKeyboardWithoutAMenu:
    """The old furniture is gone and the shortcuts are not.

    Both bars were the old window's, kept out of habit: every destination in
    `Plik / Ustawienia / Pomoc` is in the sidebar or on a page, and the status
    bar spent a row on a sentence the page already carries.
    """

    def test_there_is_no_menu_bar_and_no_status_bar(self, window):
        from PySide6.QtWidgets import QMenuBar, QStatusBar

        assert window.findChild(QMenuBar) is None
        assert window.findChild(QStatusBar) is None

    def test_and_nothing_in_the_shell_asks_for_one(self):
        """`QMainWindow.statusBar()` *creates* the bar it is asked for, so one
        call anywhere in here grows the furniture back.

        Read as code rather than as text: the prose in this package explains
        that trap in several places, and a test a comment can fail is a test
        somebody will delete.
        """
        import ast

        offenders = []
        for path in (ROOT / "epubforge" / "gui" / "shell").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("statusBar", "menuBar")
                ):
                    offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, offenders

    @pytest.mark.parametrize(
        ("key", "sequence"),
        [("open", "Ctrl+O"), ("save", "Ctrl+S"), ("save-batch", "Ctrl+Shift+S"),
         ("merge", "Ctrl+M"), ("settings", "Ctrl+,"), ("quit", "Ctrl+Q")],
    )
    def test_every_shortcut_the_menu_carried_still_works(self, window, key, sequence):
        action = window.actions_by_key[key]
        assert action.shortcut().toString() == sequence
        assert action in window.actions()

    def test_saving_a_report_is_not_an_action_before_there_is_one(self, qt_app, window):
        assert window.rebuild.stage is Stage.FILES
        assert not window.actions_by_key["save"].isEnabled()
        assert not window.actions_by_key["save-batch"].isEnabled()

    def test_and_is_one_in_the_results(self, qt_app, window):
        window.rebuild.start(["A.epub", "B.epub"])
        settle(qt_app, window.rebuild, lambda: window.rebuild.stage is Stage.PLAN)
        window.rebuild.run()
        settle(qt_app, window.rebuild, lambda: window.rebuild.stage is Stage.RESULTS)
        assert window.actions_by_key["save"].isEnabled()
        assert window.actions_by_key["save-batch"].isEnabled()

    def test_the_window_takes_a_panel_s_news_instead_of_a_status_bar(self, window):
        """A panel deep in a page cannot know what furniture its window has, so
        it says its line and the window decides. Without this the old call
        would have built a status bar on the window that refuses to have one."""
        window.navigate("tools")
        window.tools.open_tool("library")
        window.say("gotowe: 12")
        from PySide6.QtWidgets import QStatusBar

        assert window.findChild(QStatusBar) is None
        assert window.tools.router.currentWidget().news.text() == "gotowe: 12"

    def test_a_panel_in_the_old_window_still_reaches_its_status_bar(self, qt_app):
        """The seam works both ways, or the old window loses its progress line
        while it is still the one shipped behind the flag."""
        from PySide6.QtWidgets import QMainWindow

        from epubforge.gui import theme
        from epubforge.gui.tabs import LibraryPanel

        holder = QMainWindow()
        panel = LibraryPanel(theme.active_palette(qt_app))
        holder.setCentralWidget(panel)
        panel.say("skończone")
        assert holder.statusBar().currentMessage() == "skończone"
        holder.close()


class TestTheRebuildFlow:
    def test_it_walks_files_analysis_plan_results(self, qt_app, page):
        assert page.stage is Stage.FILES
        page.start(["Book_one.epub", "Book_two.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        assert [book.title for book in page.books] == ["Book one", "Book two"]
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        assert page.outcome is not None and page.outcome.written == 2

    def test_a_book_can_be_taken_out_of_the_batch_without_leaving_the_list(self, qt_app, page):
        page.start(["a.epub", "b.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page._toggle_book(page.books[0], False)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        assert page.outcome.written == 1
        assert len(page.books) == 2

    def test_cancelling_keeps_what_was_finished_and_says_it_stopped(self, qt_app, page):
        page.start(["a.epub", "b.epub", "c.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        page._cancel()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        assert page.outcome.cancelled
        # Whatever finished before the stop is still there, and the rest is
        # marked as what it is rather than as a failure.
        assert all(
            book.status in (BookStatus.DONE, BookStatus.ATTENTION, BookStatus.CANCELLED)
            for book in page.outcome.books
        )

    def test_a_stage_that_fails_does_not_take_the_others_with_it(self, qt_app, page):
        class Grumpy(DemoBackend):
            def rebuild(self, plan, books, **kwargs):
                outcome = super().rebuild(plan, books, **kwargs)
                outcome.books[0].status = BookStatus.FAILED
                outcome.books[0].error = "nie udało się"
                return outcome

        page.backend = Grumpy()
        page.start(["a.epub", "b.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        assert page.outcome.failed == 1
        assert page.outcome.written == 1


class TestThePlanAgreesWithItself:
    """Everything on the plan screen counts the same books at the same moment."""

    def test_unticking_a_book_changes_the_count_at_once(self, qt_app, page):
        page.start(["a.epub", "b.epub", "c.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        assert page.ready_count == 3
        assert page._summary_values["files"].text() == "3"
        page._toggle_book(page.books[0], False)
        assert page.ready_count == 2
        assert page._summary_values["files"].text() == "2"
        assert tr("shell.plan.count", count=2) == page.books_card.title_label.text()

    def test_and_with_nothing_ticked_the_rebuild_is_not_offered(self, qt_app, page):
        page.start(["a.epub", "b.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        for book in page.books:
            page._toggle_book(book, False)
        assert not page.run_button.isEnabled()
        assert not page.plan_button.isEnabled()
        assert page.nothing_note.isVisibleTo(page)

    def test_a_file_that_could_not_be_read_is_not_in_the_plan(self, qt_app):
        class Broken(DemoBackend):
            def analyse(self, paths, **kwargs):
                books = super().analyse(paths, **kwargs)
                books[0].status = BookStatus.FAILED
                books[0].error = "nie da się otworzyć"
                return books

        widget = RebuildPage(tokens_module.DARK, Broken())
        try:
            widget.start(["broken.epub", "fine.epub"])
            settle(qt_app, widget, lambda: widget.stage is Stage.PLAN)
            broken, fine = widget.books
            assert not broken.chosen and fine.chosen
            assert widget.ready_count == 1
            # And it is still on the list, with its reason: the batch is a
            # record of what was asked for.
            assert broken.error
        finally:
            widget.runner.stop()
            widget.close()

    def test_its_checkbox_cannot_be_ticked_back_on(self, qt_app):
        from epubforge.gui.shell.widgets import BookRow

        book = BookItem(source=pathlib.Path("x.epub"), title="x", status=BookStatus.FAILED,
                        error="nie da się otworzyć")
        row = BookRow(book, tokens_module.DARK)
        assert not row.choose.isEnabled()
        assert row.choose.toolTip()

    def test_a_readable_book_is_still_a_choice(self, qt_app):
        from epubforge.gui.shell.widgets import BookRow

        book = BookItem(source=pathlib.Path("x.epub"), title="x", status=BookStatus.READY)
        assert BookRow(book, tokens_module.DARK).choose.isEnabled()


class TestTheChosenResultIsVisiblyTheChosenOne:
    def test_exactly_one_row_is_selected_and_it_drives_the_report(self, qt_app, page):
        page.start(["a.epub", "b.epub", "c.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        rows = page._result_rows
        assert sum(1 for row in rows if row.property("selected") == "true") == 1
        page._select_book(rows[2].book)
        assert page._selected is rows[2].book
        assert [row.property("selected") == "true" for row in rows] == [False, False, True]
        assert tr("shell.results.selected") in rows[2].accessibleDescription()

    def test_the_keyboard_selects_too(self, qt_app, page):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        page.start(["a.epub", "b.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        second = page._result_rows[1]
        second.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
        assert page._selected is second.book


class TestAFailureDoesNotThrowAwayTheBatch:
    """The flow used to answer every exception by going back to the file
    picker — losing the list, the preset, the folder and every override."""

    def test_the_list_and_the_plan_survive_and_there_is_a_way_on(self, qt_app, page, tmp_path):
        class Angry(DemoBackend):
            def rebuild(self, plan, books, **kwargs):
                raise RuntimeError("silnik padł")

        page.start(["a.epub", "b.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.preset = Preset.STRICT
        page.destination = tmp_path
        page.overrides = {"validate": False}
        page.backend = Angry()
        page.run()
        settle(qt_app, page, lambda: not page.runner.busy)
        qt_app.processEvents()
        assert len(page.books) == 2
        assert page.preset is Preset.STRICT
        assert page.destination == tmp_path
        assert page.overrides == {"validate": False}
        assert page._failure and "silnik" in page._failure

    def test_and_the_problem_files_can_be_dropped_without_losing_the_rest(self, qt_app, page):
        page.start(["a.epub", "b.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.books[0].status = BookStatus.FAILED
        page._drop_failed()
        assert [book.title for book in page.books] == ["b"]
        assert page.stage is Stage.PLAN


class TestTheQuestionsStillReachAPerson:
    """A rebuild that cannot decide something asks — and the thing it asks
    lives in the window's thread. The new shell must not quietly drop that."""

    def test_a_resolver_is_built_for_the_run_and_handed_to_the_backend(self, qt_app):
        seen: dict = {}

        class Recording(DemoBackend):
            def rebuild(self, plan, books, **kwargs):
                seen["resolver"] = kwargs.get("resolver")
                return super().rebuild(plan, books, **kwargs)

        sentinel = object()
        widget = RebuildPage(tokens_module.DARK, Recording(), resolver_factory=lambda: sentinel)
        try:
            widget.books = [BookItem(source=pathlib.Path("a.epub"), title="a")]
            widget.stage = Stage.PLAN
            widget.run()
            settle(qt_app, widget, lambda: widget.stage is Stage.RESULTS)
        finally:
            widget.runner.stop()
            widget.close()
        assert seen["resolver"] is sentinel

    def test_declining_questions_means_nobody_is_asked(self, qt_app):
        seen: dict = {}

        class Recording(DemoBackend):
            def rebuild(self, plan, books, **kwargs):
                seen["resolver"] = kwargs.get("resolver")
                return super().rebuild(plan, books, **kwargs)

        widget = RebuildPage(tokens_module.DARK, Recording(), resolver_factory=lambda: object())
        try:
            widget.books = [BookItem(source=pathlib.Path("a.epub"), title="a")]
            widget.stage = Stage.PLAN
            widget.overrides = {"ask": False}
            widget.run()
            settle(qt_app, widget, lambda: widget.stage is Stage.RESULTS)
        finally:
            widget.runner.stop()
            widget.close()
        assert seen["resolver"] is None


class TestTheOriginalIsNeverTheDestination:
    def test_a_destination_equal_to_the_source_refuses_before_anything_runs(
        self, qt_app, page, tmp_path, monkeypatch
    ):
        source = tmp_path / "book.epub"
        source.write_bytes(b"not really an epub")
        page.books = [BookItem(source=source, title="book")]
        page.destination = tmp_path  # writing "book.epub" here *is* the source
        page.stage = Stage.PLAN

        warned: list = []
        monkeypatch.setattr(
            "PySide6.QtWidgets.QMessageBox.warning",
            lambda *args, **kwargs: warned.append(args[1:3]),
        )
        page.run()
        assert warned, "okno nie ostrzegło przed nadpisaniem oryginału"
        assert page.stage is Stage.PLAN
        assert not page.runner.busy

    def test_the_rule_lives_in_one_place_and_answers_the_same_for_both_backends(self, tmp_path):
        source = tmp_path / "b.epub"
        beside = backend_module.destination_for(source, None, False)
        assert beside.endswith(".forged.epub")
        into = backend_module.destination_for(source, tmp_path / "out", False)
        assert into.endswith(os.path.join("out", "b.epub"))


class TestPresetsAndOverrides:
    def test_a_preset_is_the_engine_s_own_mode(self):
        from epubforge.policy import Policy

        for preset in Preset:
            plan = RebuildPlan(sources=(), preset=preset)
            policy, _check, _plan_only = policy_for(plan)
            assert policy.rewrite_content == Policy.preset(preset.value).rewrite_content

    def test_only_the_deviations_are_overrides(self, qt_app, page):
        defaults = page.backend.defaults_for(Preset.PRESERVE)
        page.books = [BookItem(source=pathlib.Path("a.epub"), title="a")]
        page.show_plan()
        page._open_drawer()
        drawer = page.drawer
        assert drawer.overrides() == {}
        key = "write_ncx"
        drawer._changed(key, not defaults[key])
        assert drawer.overrides() == {key: not defaults[key]}
        drawer._changed(key, defaults[key])
        assert drawer.overrides() == {}
        drawer.close_drawer()

    def test_changing_the_preset_does_not_carry_risky_settings_across(self, qt_app, page):
        page.books = [BookItem(source=pathlib.Path("a.epub"), title="a")]
        page.stage = Stage.PLAN
        page.overrides = {"remove_dead": True}
        page._preset_cards = []
        page._choose_preset(Preset.STRICT)
        assert page.overrides == {}

    def test_every_override_key_is_either_a_policy_field_or_argued_away(self):
        from epubforge.policy import Policy

        policy = Policy()
        for option in options_module.OPTIONS:
            target, *rest = option.key.split(".")
            reaches = hasattr(policy, target) and all(
                # A dotted key walks into a module's settings object; every
                # step of the path has to exist or the option sets nothing.
                hasattr(getattr(policy, target), name) for name in rest[:1]
            )
            assert reaches or option.key in backend_module.NOT_POLICY_FIELDS, (
                f"{option.key} ustawia nic"
            )

    def test_the_switches_that_are_not_policy_fields_still_reach_the_run(self):
        plan = RebuildPlan(
            sources=(),
            preset=Preset.PRESERVE,
            overrides={
                "validate": False, "plan_only": True, "render_all": True,
                "compat.kobo": True, "meta.title": "Tytuł", "meta.language": "pl",
                "memory_limit": "2 GB", "time_budget_seconds": 900,
            },
        )
        policy, run_check, plan_only = policy_for(plan)
        assert run_check is False and plan_only is True
        assert policy.render_sample == 0
        assert policy.compat_profiles == ("kobo",)
        assert policy.metadata_overrides["title"] == "Tytuł"
        assert policy.default_language == "pl"
        assert policy.memory_limit == 2 * 1024**3
        assert policy.time_budget_seconds == 900

    def test_a_size_nobody_can_parse_falls_back_rather_than_refusing(self):
        plan = RebuildPlan(sources=(), overrides={"memory_limit": "dużo"})
        policy, _check, _plan = policy_for(plan)
        assert policy.memory_limit is None


class TestEveryChoiceIsStillReachable:
    """The old window's rule, restated for a window built out of a drawer.

    `tests/test_gui_reaches_everything.py` holds the same line for the legacy
    window; this is the same argument against the new one, and it is the test
    that would catch a policy field added next year and never given a control.
    """

    @pytest.mark.parametrize("field", [
        line for line in __import__("re").findall(
            r"^    ([a-z_][a-z_0-9]*): ",
            (ROOT / "epubforge" / "policy.py").read_text(encoding="utf-8")
            .split("class Policy:", 1)[1],
            __import__("re").M,
        )
    ])
    def test_a_policy_field_is_in_the_catalogue_or_exempt(self, field):
        from tests.test_gui_reaches_everything import NOT_IN_THE_WINDOW

        exempt_here = {
            # Set by the three metadata fields, exactly as in the old window.
            "default_language", "metadata_overrides",
            # One tick per device profile, built from the compat module.
            "compat_profiles",
            # "Check every page instead of a sample" is the choice; the number
            # of pages in a sample is not one a person makes.
            "render_sample",
        }
        if field in NOT_IN_THE_WINDOW or field in exempt_here:
            return
        # A field holding a module's own settings (`Policy.pdf`, D-056) is
        # reachable when its *parts* are: the drawer shows one control per
        # setting, not one per object. The rule is unchanged — nothing may be
        # settable and unreachable — only the address is now a path.
        nested = [key for key in options_module.BY_KEY if key.startswith(f"{field}.")]
        assert field in options_module.BY_KEY or nested, (
            f"Policy.{field} nie ma sterowania w nowym oknie. Dopisz opcję do "
            f"epubforge/gui/shell/options.py albo uzasadnij wyjątek."
        )

    def test_every_option_has_a_label_and_a_sentence_in_both_languages(self):
        for option in options_module.OPTIONS:
            for catalogue in (PL, EN):
                assert catalogue.get(option.label_key), option.key
                assert catalogue.get(option.help_key), option.key

    def test_every_choice_names_its_options_in_both_languages(self):
        for option in options_module.OPTIONS:
            for choice in option.choices:
                for catalogue in (PL, EN):
                    assert catalogue.get(f"{option.label_key}.{choice}"), (option.key, choice)

    def test_the_risky_ones_are_marked_as_such(self):
        risky = {option.key for option in options_module.OPTIONS if option.risky}
        assert {"drop_orphans", "remove_dead", "strip_scripts"} <= risky


class TestTheDrawer:
    def test_escape_closes_it_and_gives_the_focus_back(self, qt_app, page):
        page.show()  # a child of a hidden parent stays hidden, drawer included
        page.books = [BookItem(source=pathlib.Path("a.epub"), title="a")]
        page.show_plan()
        page._open_drawer()
        assert page.drawer.isVisible()
        from PySide6.QtGui import QKeyEvent

        page.drawer.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        assert not page.drawer.isVisible()
        # `hasFocus` asks whether the *active* window's focus is here, and an
        # offscreen window is never active; `focusWidget` is the same question
        # without that condition.
        assert page.focusWidget() is page.details_button

    def test_search_looks_at_what_a_person_can_read(self, qt_app, page):
        page.books = [BookItem(source=pathlib.Path("a.epub"), title="a")]
        page.show_plan()
        page._open_drawer()
        drawer = page.drawer
        drawer._searched("NCX")
        assert any(option.key == "write_ncx" for option in drawer._matching())
        drawer._searched("zzzzz")
        assert drawer._matching() == []
        drawer.close_drawer()

    def test_expert_options_are_behind_a_disclosure(self, qt_app, page):
        everyday = {option.key for option in options_module.in_category("validation")}
        expert = {option.key for option in options_module.in_category("validation", expert=True)}
        assert "plan_only" in expert and "plan_only" not in everyday
        assert "validate_before_publish" in everyday


class TestStatesAreSaidInWordsNotOnlyInColour:
    @pytest.mark.parametrize("status", list(BookStatus))
    def test_every_status_has_a_glyph_a_role_and_a_word(self, status):
        glyph, role = STATUS_LOOK[status]
        from epubforge.gui.shell import icons

        assert glyph in icons.PATHS
        assert role in ("muted", "accent", "success", "warning", "danger")
        for catalogue in (PL, EN):
            assert catalogue.get(f"shell.status.{status.value}"), status

    def test_the_stepper_says_which_step_and_what_state(self, qt_app):
        from epubforge.gui.shell.widgets import Stepper

        stepper = Stepper(tokens_module.DARK)
        stepper.set_stage(Stage.PLAN)
        names = [item.accessibleName() for item in stepper._labels]
        assert tr("shell.step.done") in names[0]
        assert tr("shell.step.current") in names[2]
        assert tr("shell.step.todo") in names[3]


class TestTheKeyboardReachesEverything:
    """A card that can only be clicked is a control half the people cannot use."""

    def test_a_card_takes_focus_and_answers_space_and_enter(self, qt_app):
        from PySide6.QtGui import QKeyEvent

        from epubforge.gui.shell.widgets import PresetCard

        card = PresetCard(Preset.STRICT, "Tytuł", "Opis", tokens_module.DARK)
        assert card.focusPolicy() == Qt.StrongFocus
        seen: list = []
        card.chosen.connect(seen.append)
        for key in (Qt.Key_Space, Qt.Key_Return):
            card.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, key, Qt.NoModifier))
        assert seen == [Preset.STRICT, Preset.STRICT]

    def test_every_interactive_card_says_what_it_is(self, qt_app):
        from epubforge.gui.shell.widgets import Tile

        tile = Tile("library", "Biblioteka", "Zbadaj kolekcję", "Otwórz", tokens_module.DARK)
        assert tile.accessibleName() == "Biblioteka"
        assert tile.accessibleDescription()

    def test_the_page_scrolls_rather_than_squeezing_at_the_smallest_window(self, qt_app, page):
        """Measured, not assumed.

        This test used to be `findChild(QScrollArea) is not None`, which is
        true of a page whose cards are squeezed to nothing inside a scroll area
        as well — the design package said so, and it was right. So it asks the
        page the same four questions `tests/test_shell_layout.py` asks it at
        five sizes: real sizes, nothing past what can be reached, nothing
        overlapping, main action present.
        """
        from tests.geometry import problems_with

        page.start(["a.epub", "b.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.setGeometry(0, 0, 736, 560)  # 800x560 window, compact sidebar
        for _ in range(6):
            qt_app.processEvents()
        assert not problems_with(page, main_action=page.run_button)


class TestHistoryRemembersLittleAndNothingPrivate:
    def test_a_record_survives_a_round_trip(self):
        record = JobRecord(
            when="2026-09-07 21:15", count=3, written=2, attention=1, failed=0,
            preset="Zachowaj wygląd", destination="/tmp/out", titles=("A", "B"),
        )
        again = JobRecord.from_dict(record.as_dict())
        assert again == record
        assert again.status is BookStatus.ATTENTION

    def test_it_holds_counts_and_paths_and_not_book_contents(self):
        fields = set(JobRecord.__dataclass_fields__)
        assert fields == {
            "when", "count", "written", "attention", "failed", "preset",
            "destination", "destinations", "titles", "cancelled",
        }

    def test_a_history_file_from_an_older_version_still_reads(self):
        """`destinations` is new; a file written before it exists must open,
        and its one destination must still be offered."""
        old = {
            "when": "2026-09-01 10:00", "count": 2, "written": 2, "attention": 0,
            "failed": 0, "preset": "Zachowaj wygląd", "destination": "/tmp/out",
            "titles": ["A"], "cancelled": False,
        }
        record = JobRecord.from_dict(old)
        assert record.destinations == ()
        assert record.folders == ("/tmp/out",)

    def test_and_one_written_now_still_carries_the_old_field(self):
        record = JobRecord(
            when="", count=1, written=1, attention=0, failed=0, preset="",
            destination="/a", destinations=("/a", "/b"),
        )
        assert record.as_dict()["destination"] == "/a"
        assert record.folders == ("/a", "/b")

    def test_a_history_file_that_will_not_parse_is_an_empty_list(self, tmp_path, monkeypatch):
        from epubforge.gui.shell import state

        broken = tmp_path / "history.json"
        broken.write_text("{ this is not json", encoding="utf-8")
        monkeypatch.setattr(state, "history_path", lambda: broken)
        assert state.load_history() == []


class TestTheThreadEndsBeforeAnythingIsDestroyed:
    """The runner as a state machine, because the alternative was a wait.

    `thread.quit(); thread.wait(5000)` on the window's thread froze the
    interface for as long as the job took to notice — and if the job was
    blocked on a question, until the wait gave up and abandoned a thread that
    was still running.
    """

    def test_nothing_in_the_shell_waits_on_a_thread_or_kills_one(self):
        import ast

        offenders = []
        for path in (ROOT / "epubforge" / "gui" / "shell").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "terminate":
                        offenders.append(f"{path.name}:{node.lineno} terminate")
                    if node.func.attr == "wait" and path.name != "workers.py":
                        offenders.append(f"{path.name}:{node.lineno} wait")
        assert not offenders, offenders

    def test_the_only_wait_left_says_it_is_for_tests(self):
        source = (ROOT / "epubforge" / "gui" / "shell" / "workers.py").read_text(encoding="utf-8")
        import ast

        tree = ast.parse(source)
        waits = [
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "wait"
        ]
        assert len(waits) == 1, waits
        assert "def wait_for_idle" in source
        assert "**Tests and teardown only.**" in source

    def test_the_runner_owns_nothing_once_the_thread_has_ended(self, qt_app, page):
        page.start(["a.epub"])
        assert page.runner.busy
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        assert page.runner.wait_for_idle(3000)
        assert page.runner.thread is None and page.runner.job is None

    def test_the_idle_signal_arrives_once_per_job(self, qt_app, page):
        seen = []
        page.runner.idle.connect(lambda: seen.append(1))
        page.start(["a.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.runner.wait_for_idle(3000)
        qt_app.processEvents()
        assert seen == [1]

    def test_cancelling_twice_is_the_same_as_cancelling_once(self, qt_app, page):
        page.start(["a.epub", "b.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        page._cancel()
        page._cancel()
        page.runner.cancel()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        assert page.outcome.cancelled

    def test_a_run_asked_for_while_the_last_thread_winds_down_still_happens(self, qt_app, page):
        """The wind-down is a few invisible milliseconds; a button that ignores
        a click during them is a button that did nothing for no reason."""
        page.start(["a.epub"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()  # the analysis thread may not have finished ending yet
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        assert page.outcome.written == 1

    def test_closing_during_a_job_is_refused_until_the_work_has_stopped(self, qt_app, window):
        from PySide6.QtGui import QCloseEvent

        window.rebuild.start(["a.epub", "b.epub", "c.epub"])
        assert window.rebuild.runner.busy
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted(), "the first close asks; it does not close"
        assert window._closing
        assert window.rebuild.runner.cancelled
        settle(qt_app, window.rebuild, lambda: not window.rebuild.runner.busy)
        qt_app.processEvents()
        # And now the same event is accepted, because there is nothing running.
        second = QCloseEvent()
        window.closeEvent(second)
        assert second.isAccepted()

    def test_closing_during_a_rebuild_is_refused_and_stops_the_run(self, qt_app, window):
        """The other half of the same promise: analysis is the short job, the
        rebuild is the one somebody actually walks away from."""
        from PySide6.QtGui import QCloseEvent

        window.rebuild.start(["a.epub", "b.epub", "c.epub"])
        settle(qt_app, window.rebuild, lambda: window.rebuild.stage is Stage.PLAN)
        window.rebuild.run()
        assert window.rebuild.runner.busy
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted()
        settle(qt_app, window.rebuild, lambda: not window.rebuild.runner.busy)
        qt_app.processEvents()
        assert window.rebuild.runner.cancelled

    def test_a_window_with_nothing_running_closes_at_once(self, qt_app, window):
        from PySide6.QtGui import QCloseEvent

        event = QCloseEvent()
        window.closeEvent(event)
        assert event.isAccepted()


class TestAStoppedResolverStopsAsking:
    """A question is a blocking call from the worker into the window's thread.
    Cancelling without stopping it cancels nothing until somebody answers."""

    def test_it_answers_leave_it_alone_without_showing_anything(self, qt_app):
        from epubforge.gui.ask import Ask
        from epubforge.references import KEEP, Unresolved

        ask = Ask()
        ask.stop()
        answer = ask.resolve(
            Unresolved(document="a.xhtml", target="b.xhtml", fragment="x", text="1")
        )
        assert answer is not None and answer.action == KEEP

    def test_and_the_generic_half_answers_nothing(self, qt_app):
        from epubforge.gui.ask import Ask

        ask = Ask()
        ask.stop()
        assert ask.ask(object()) is None

    def test_cancelling_a_run_stops_the_questions(self, qt_app, page):
        stopped = []

        class Resolver:
            def stop(self):
                stopped.append(True)

        page._resolver = Resolver()
        page._cancel()
        assert stopped == [True]


@pytest.fixture
def own_settings(tmp_path, monkeypatch):
    """A settings store of this test's own.

    The real one is the machine's, and a test that writes into it is a test
    that changes where somebody's dialogs open.
    """
    from PySide6.QtCore import QSettings

    from epubforge.gui.shell import state

    store = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    monkeypatch.setattr(state, "settings", lambda: store)
    return store


class TestHistoryKnowsWhereTheFilesActuallyWent:
    def test_the_folders_come_from_the_books_and_not_from_the_choice(self, tmp_path):
        """With no destination chosen the books land beside their sources, and
        the old record wrote "" for exactly that — the common case."""
        from epubforge.gui.shell.models import BatchOutcome

        one, two = tmp_path / "a", tmp_path / "b"
        outcome = BatchOutcome(
            books=(
                BookItem(source=one / "x.epub", title="x", status=BookStatus.DONE,
                         output=one / "x.forged.epub"),
                BookItem(source=two / "y.epub", title="y", status=BookStatus.DONE,
                         output=two / "y.forged.epub"),
            ),
        )
        assert outcome.destination is None
        assert outcome.folders == (str(one), str(two))

    def test_a_book_that_was_not_written_names_no_folder(self, tmp_path):
        from epubforge.gui.shell.models import BatchOutcome

        outcome = BatchOutcome(
            books=(BookItem(source=tmp_path / "x.epub", title="x", status=BookStatus.FAILED),)
        )
        assert outcome.folders == ()

    def test_one_folder_offers_a_button_and_several_offer_a_list(self, qt_app):
        from epubforge.gui.shell.pages.history import HistoryRow

        one = JobRecord(when="", count=1, written=1, attention=0, failed=0, preset="p",
                        destinations=("/tmp/a",))
        row = HistoryRow(one, tokens_module.DARK)
        from PySide6.QtWidgets import QPushButton

        texts = [item.text() for item in row.findChildren(QPushButton)]
        assert texts == [tr("shell.history.open")]

        many = JobRecord(when="", count=2, written=2, attention=0, failed=0, preset="p",
                         destinations=("/tmp/a", "/tmp/b"))
        row = HistoryRow(many, tokens_module.DARK)
        item = row.findChildren(QPushButton)[0]
        assert item.text() == tr("shell.history.open.many", count=2)
        assert [action.text() for action in item.menu().actions()] == ["/tmp/a", "/tmp/b"]

    def test_a_run_that_wrote_nothing_and_was_stopped_is_not_a_success(self, qt_app, window):
        from epubforge.gui.shell.models import BatchOutcome

        outcome = BatchOutcome(
            books=(BookItem(source=pathlib.Path("a.epub"), title="a",
                            status=BookStatus.CANCELLED),),
            cancelled=True,
        )
        record = JobRecord(
            when="", count=1, written=0, attention=0, failed=0, preset="p",
            cancelled=outcome.cancelled,
        )
        assert record.status is BookStatus.CANCELLED
        assert record.folders == ()

    def test_and_a_run_with_no_books_at_all_is_not_written_down(self, qt_app, window, monkeypatch):
        from epubforge.gui.shell.models import BatchOutcome

        written = []
        monkeypatch.setattr(
            "epubforge.gui.shell.window.remember", lambda record: written.append(record) or []
        )
        window._record(BatchOutcome(books=(), cancelled=True))
        assert written == []


class TestTheFolderTheDialogOpensIn:
    """"Remember the last folder" was in the window from the first version and
    did nothing whatever: written by the checkbox, read by nobody."""

    def test_it_is_remembered_when_the_setting_is_on(self, own_settings, tmp_path):
        from epubforge.gui.shell import state

        own_settings.setValue("remember-folder", True)
        state.remember_folder("input", str(tmp_path / "polka" / "ksiazka.epub"))
        assert state.last_folder("input") == str(tmp_path / "polka")

    def test_the_folder_is_kept_and_never_the_file(self, own_settings, tmp_path):
        from epubforge.gui.shell import state

        own_settings.setValue("remember-folder", True)
        state.remember_folder("report", str(tmp_path / "raporty" / "raport.json"))
        assert state.last_folder("report") == str(tmp_path / "raporty")

    def test_nothing_is_remembered_when_the_setting_is_off(self, own_settings, tmp_path):
        from epubforge.gui.shell import state

        own_settings.setValue("remember-folder", False)
        state.remember_folder("input", str(tmp_path / "polka" / "x.epub"))
        assert state.last_folder("input") == ""

    def test_switching_it_off_forgets_what_was_remembered(self, own_settings, tmp_path, qt_app):
        """An instruction, not a pause: somebody who unticks this is saying the
        program should not be keeping a note of where their books are."""
        from epubforge.gui.shell import state

        own_settings.setValue("remember-folder", True)
        for kind in state.FOLDER_KINDS:
            state.remember_folder(kind, str(tmp_path / kind / "x.epub"))
        state.forget_folders()
        own_settings.setValue("remember-folder", True)
        assert [state.last_folder(kind) for kind in state.FOLDER_KINDS] == ["", "", "", ""]

    def test_the_four_kinds_do_not_share_a_memory(self, own_settings, tmp_path):
        from epubforge.gui.shell import state

        own_settings.setValue("remember-folder", True)
        state.remember_folder("input", str(tmp_path / "wejscie" / "a.epub"))
        state.remember_folder("output", str(tmp_path / "wyjscie" / "b.epub"))
        assert state.last_folder("input") == str(tmp_path / "wejscie")
        assert state.last_folder("output") == str(tmp_path / "wyjscie")


class TestTheWindowComesBackWhereItWas:
    def test_a_remembered_rectangle_on_a_screen_we_have_is_used(self, qt_app):
        from PySide6.QtCore import QRect

        from epubforge.gui.shell.window import fits_on_a_screen

        where = QApplication.primaryScreen().availableGeometry()
        assert fits_on_a_screen(QRect(where.x() + 40, where.y() + 40, 900, 600))

    def test_and_one_on_a_monitor_that_is_gone_is_not(self, qt_app):
        """The failure this prevents looks exactly like a program that will not
        start: the window opens where the second monitor used to be."""
        from PySide6.QtCore import QRect

        from epubforge.gui.shell.window import fits_on_a_screen

        assert not fits_on_a_screen(QRect(9000, 5000, 1200, 800))

    def test_the_opening_size_never_exceeds_the_screen(self, qt_app):
        from epubforge.gui.shell.window import opening_size

        screen = QApplication.primaryScreen()
        width, height = opening_size(screen)
        assert width <= screen.availableGeometry().width()
        assert height <= screen.availableGeometry().height()

    def test_a_stored_rectangle_that_makes_no_sense_is_ignored(self, own_settings):
        from epubforge.gui.shell import state

        own_settings.setValue("window/where", [10, 10, 3, 3])
        assert state.remembered_geometry() is None
        state.save_geometry(30, 40, 1000, 700)
        assert state.remembered_geometry() == (30, 40, 1000, 700)


class TestTheToolsAreThisWindowsOwnPages:
    """Not the old panels dropped into a frame.

    The work they do is another matter: that lives in `gui/toolwork.py`, with
    no Qt in it, and both windows call it — so neither can drift from the other
    about what a survey prints.
    """

    def test_the_shell_never_reaches_for_the_old_panels(self):
        import ast

        offenders = []
        for path in (ROOT / "epubforge" / "gui" / "shell").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("tabs"):
                    offenders.append(f"{path.name}:{node.lineno}")
                if isinstance(node, ast.ImportFrom) and node.module is None:
                    names = {alias.name for alias in node.names}
                    if names & {"LibraryPanel", "DiagnosticsPanel", "CorpusPanel"}:
                        offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, offenders

    def test_the_work_itself_has_no_window_in_it(self):
        """`toolwork` is what makes one implementation serve two windows; an
        import of Qt in it would be the first step back to two."""
        source = (ROOT / "epubforge" / "gui" / "toolwork.py").read_text(encoding="utf-8")
        assert "PySide6" not in source
        assert "QWidget" not in source

    def test_and_the_old_panels_call_the_same_functions(self):
        """The point of the move: not a copy, the same code."""
        from epubforge.gui import toolwork
        from epubforge.gui.tabs import DiagnosticsPanel, LibraryPanel

        assert LibraryPanel._render_survey is toolwork.render_survey
        assert DiagnosticsPanel._describe is toolwork.describe
        assert DiagnosticsPanel._health is toolwork.check_health
        assert DiagnosticsPanel._render is toolwork.compare_render
        assert DiagnosticsPanel._fidelity is toolwork.compare_fidelity
        assert DiagnosticsPanel._validate is toolwork.validate_book

    @pytest.mark.parametrize("name", ["library", "diagnostics", "corpus"])
    def test_every_tool_has_the_same_shape(self, qt_app, window, name):
        window.navigate("tools")
        window.tools.open_tool(name)
        page = window.tools.router.currentWidget()
        from epubforge.gui.shell.pages.tools.base import ToolPage

        assert isinstance(page, ToolPage)
        # A sentence about what it is for, somewhere to point it, one main
        # action, a compact progress line, and an answer somebody can take away.
        assert page.card.title_label.text()
        assert page.findChild(type(page.result)) is not None
        assert page._buttons and page._buttons[0].isEnabled()
        assert page.copy_button.isEnabled()
        assert not page.save_button.isEnabled()
        assert not page.progress.isVisible()

    @pytest.mark.parametrize("name", ["library", "diagnostics", "corpus"])
    def test_and_a_way_back_to_the_index(self, qt_app, window, name):
        window.navigate("tools")
        window.tools.open_tool(name)
        assert window.tools.router.currentWidget() is not window.tools._index
        window.tools.router.currentWidget().back_requested.emit()
        assert window.tools.router.currentWidget() is window.tools._index

    def test_they_use_the_shell_s_own_worker(self, qt_app, window):
        from epubforge.gui.shell.workers import Runner

        window.tools.open_tool("library")
        page = window.tools.router.currentWidget()
        assert isinstance(page.runner, Runner)
        # And the window knows about it, so closing stops it like anything else.
        assert page.runner in window.runners()

    def test_a_tool_with_nothing_to_look_at_says_so_and_starts_nothing(self, qt_app, window):
        window.tools.open_tool("library")
        page = window.tools.router.currentWidget()
        page.folder.setText("")
        page.run()
        assert not page.runner.busy
        assert tr("common.nofolder") in page.result.toPlainText()

    def test_a_tool_runs_its_work_and_shows_what_came_back(self, qt_app, window, monkeypatch):
        from epubforge.gui.shell.pages.tools import library as library_page
        from epubforge.gui.toolwork import ToolAnswer

        answer = ToolAnswer(text="120 książek", payload="{}", headline="gotowe: 120",
                            suggestion="przeglad.json")
        monkeypatch.setattr(library_page, "library", lambda folder, **kwargs: answer)
        window.tools.open_tool("library")
        page = window.tools.router.currentWidget()
        page.folder.setText("/tmp")
        page.run()
        settle(qt_app, window.rebuild, lambda: not page.runner.busy)
        qt_app.processEvents()
        assert page.result.toPlainText() == "120 książek"
        assert page.news.text() == "gotowe: 120"
        assert page.save_button.isEnabled()

    def test_changing_the_question_forgets_the_last_answer(self, qt_app, window):
        """Save is offered separately from Run, so the two can drift: run one
        question, pick another, press Save, and out comes the first answer
        under the second one's name."""
        from epubforge.gui.toolwork import ToolAnswer

        window.tools.open_tool("library")
        page = window.tools.router.currentWidget()
        page.show_answer(ToolAnswer(text="x", payload="{}"))
        assert page.save_button.isEnabled()
        page.inventory_choice.setChecked(True)
        assert not page.save_button.isEnabled()

    def test_the_corpus_page_still_answers_the_streak_question(self, qt_app, window, tmp_path):
        """The owner has been asking this from outside the program; it must not
        have been left behind in the old panel."""
        import json

        signatures = tmp_path / "expected"
        signatures.mkdir()
        (tmp_path / "runs.json").write_text(
            json.dumps([
                {"version": "0.2.4", "books": 90, "modes": ["preserve"], "clean": True},
                {"version": "0.2.6", "books": 99, "modes": ["preserve"], "clean": True},
            ]),
            encoding="utf-8",
        )
        window.tools.open_tool("corpus")
        page = window.tools.router.currentWidget()
        page._signatures_used = signatures
        said = page.streak()
        assert "0.2.4" in said and "0.2.6" in said

    def test_merging_copies_is_still_a_dialog_and_still_reachable(self, qt_app):
        """On a page of its own: asking the real window for it would open the
        dialog, and a modal dialog in a test is a test that never ends."""
        from epubforge.gui.shell.pages.tools import ToolsPage

        page = ToolsPage(tokens_module.DARK)
        seen = []
        page.merge_requested.connect(lambda: seen.append(True))
        page.open_tool("merge")
        assert seen == [True]
        assert page.router.currentWidget() is page._index
        page.close()


class TestTheAdapterSpeaksInPlainData:
    def test_pages_never_import_the_engine(self):
        """The seam, as a test rather than as an intention."""
        for path in (ROOT / "epubforge" / "gui" / "shell" / "pages").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for forbidden in ("from ....policy", "from ....pipeline", "from ....report"):
                assert forbidden not in source, f"{path.name} sięga do silnika"

    def test_the_demo_backend_answers_the_protocol(self):
        backend = DemoBackend()
        for name in ("analyse", "defaults_for", "rebuild", "destination_for",
                     "export_report", "reveal"):
            assert callable(getattr(backend, name)), name
