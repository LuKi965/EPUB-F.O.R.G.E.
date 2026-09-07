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
        news = window.tools._news[window.tools.router.currentWidget()]
        assert news.text() == "gotowe: 12"

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
            assert (
                hasattr(policy, option.key) or option.key in backend_module.NOT_POLICY_FIELDS
            ), f"{option.key} ustawia nic"

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
        assert field in options_module.BY_KEY, (
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
        """1100×700 is the floor; below the content's own height the page has to
        scroll, because Qt's answer to "not enough room" is to squeeze widgets
        past their minimum and print them over each other."""
        from PySide6.QtWidgets import QScrollArea

        assert page.findChild(QScrollArea) is not None


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
