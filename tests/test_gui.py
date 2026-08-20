"""Headless checks on the window, so a layout mistake fails a test not a user.

Skipped wherever PySide6 is absent, which is most CI. What is asserted here is
deliberately narrow: that the panels wire up, and that the two scaling defects
behind this work cannot return. Anything about how it *looks* belongs in front
of a person.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from epubforge.gui import theme  # noqa: E402
from epubforge.gui.app import MainWindow  # noqa: E402
from epubforge.gui.strings import tr  # noqa: E402

import pathlib  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    yield app


@pytest.fixture
def window(qt_app):
    win = MainWindow(theme.DARK)
    yield win
    win.close()


class TestStructure:
    def test_every_feature_has_a_tab(self, window):
        """Counted rather than named, and the count is a ratchet: a feature that
        arrives without a tab is a feature that does not exist for somebody who
        runs the Windows build. Diagnostics — `inspect` and `check` — lived only
        in the command line until 0.2.22 for exactly that reason."""
        labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert len(labels) == 4
        assert all(labels)

    def test_the_title_names_the_application_once(self, window):
        """Qt appends applicationDisplayName to every title; setting both gave
        "EPUB F.O.R.G.E. 0.1.1 (pre-alpha) - EPUB F.O.R.G.E."."""
        assert window.windowTitle().count("F.O.R.G.E.") == 1

    def test_the_title_states_the_maturity(self, window):
        """Whatever the stage is, the window says it.

        Asserting the literal "pre-alpha" made this a test of one release rather
        than of the rule, and it went red on the day the stage changed — which is
        the day it should have stayed green.
        """
        from epubforge import __stage__

        assert __stage__ and __stage__ in window.windowTitle()


class TestScaling:
    """Both of these were real: the window opened taller than a 768px laptop,
    and the options column was cut off with the run button inside it."""

    def test_the_window_fits_a_small_laptop(self, window):
        assert window.minimumHeight() <= 600
        assert window.minimumWidth() <= 900

    def test_the_options_column_scrolls_rather_than_clipping(self, window):
        from PySide6.QtWidgets import QScrollArea

        assert window.findChildren(QScrollArea), "options are not in a scroll area"

    def test_the_options_column_cannot_swallow_the_window(self, window):
        from PySide6.QtWidgets import QSplitter

        splitters = window.findChildren(QSplitter)
        assert splitters
        for splitter in splitters:
            assert not splitter.childrenCollapsible()

    def test_the_run_button_survives_a_short_window(self, window):
        window.resize(880, 560)
        qt_app = QApplication.instance()
        qt_app.processEvents()
        assert window.run_button.isVisible() or window.run_button.height() > 0


class TestTheWatermarkChoice:
    """Four answers, and the two that take the token out of the text have to be
    picked by a person — which means they have to be visible and explained."""

    def test_every_mode_is_offered(self, window):
        from epubforge import watermark

        offered = [
            window.watermark_combo.itemData(index)
            for index in range(window.watermark_combo.count())
        ]
        assert offered == list(watermark.MODES)

    def test_it_opens_on_the_mode_that_takes_nothing_out_of_the_text(self, window):
        from epubforge.policy import Policy

        assert window.watermark_combo.currentData() == Policy().watermarks
        assert window.watermark_combo.currentData() not in ("gather", "remove")

    def test_each_mode_says_what_it_costs(self, window):
        from PySide6.QtCore import Qt

        for index in range(window.watermark_combo.count()):
            tip = window.watermark_combo.itemData(index, Qt.ToolTipRole)
            assert tip, window.watermark_combo.itemText(index)

    def test_the_choice_reaches_the_policy(self, window):
        from epubforge import watermark

        window.watermark_combo.setCurrentIndex(watermark.MODES.index("gather"))
        assert window._policy().watermarks == "gather"

    def test_container_only_mode_disables_it(self, window):
        """Minimal does not open a content document, so it cannot move a token."""
        window.mode_combo.setCurrentIndex(
            [window.mode_combo.itemData(i) for i in range(window.mode_combo.count())].index("minimal")
        )
        assert not window.watermark_combo.isEnabled()


class TestPanels:
    def _panel(self, window, index):
        return window.tabs.widget(index)

    def test_the_library_panel_offers_both_measurements(self, window):
        panel = self._panel(window, 1)
        assert panel.survey_choice.isChecked()
        assert not panel.inventory_choice.isChecked()

    def test_filenames_are_off_by_default(self, window):
        """The result is meant to be shareable; a shelf listing is not."""
        assert not self._panel(window, 1).with_names.isChecked()

    def test_saving_is_unavailable_until_there_is_something_to_save(self, window):
        assert not self._panel(window, 1).save_button.isEnabled()

    def test_every_control_that_makes_a_choice_explains_it(self, window):
        panel = self._panel(window, 1)
        for control in (panel.survey_choice, panel.inventory_choice, panel.with_names):
            assert control.toolTip(), control.text()

    def test_switching_measurement_withdraws_the_previous_result(self, window):
        """Save wrote whatever the last run produced, under whatever name the
        radio buttons currently said. Running a survey, switching to inventory
        and pressing Save handed over the survey called `spis.json`."""
        panel = self._panel(window, 1)
        panel._payload = '{"pretend": "survey"}'
        panel.save_button.setEnabled(True)

        panel.inventory_choice.setChecked(True)

        assert not panel.save_button.isEnabled()
        assert not panel._payload

    def test_changing_the_folder_withdraws_it_too(self, window):
        panel = self._panel(window, 1)
        panel._payload = '{"pretend": "survey"}'
        panel.save_button.setEnabled(True)

        panel.folder.setText("/inna/polka")

        assert not panel.save_button.isEnabled()

    def test_the_corpus_panel_takes_two_folders(self, window):
        panel = self._panel(window, 2)
        assert panel.books is not None and panel.signatures is not None
        assert panel.signatures.placeholderText()


# The long jobs are deliberately not driven from here. Spinning a QThread and
# pumping the event loop from inside pytest under the offscreen platform
# deadlocks reliably, and a test suite that hangs is worse than one that admits
# a gap. Nothing is lost by it: what the panels add over the command line is
# wiring, and the work itself is covered by `test_survey.py`,
# `test_inventory.py` and the corpus tests, which exercise exactly the
# functions these panels call.


class TestTheEdgeCasesAreReachableFromTheWindow:
    """The corpus family nobody can buy, behind a button rather than a script.

    It was a command line importing from the test suite, on a machine with a
    checkout. The person who can fill that family runs the installer, so the
    instruction "just run the script" asked him to do nothing — and the family
    stayed at zero across four releases while being named as what was missing.
    """

    def corpus_panel(self, window):
        from epubforge.gui.tabs import CorpusPanel

        for index in range(window.tabs.count()):
            panel = window.tabs.widget(index)
            if isinstance(panel, CorpusPanel):
                return panel
        raise AssertionError("no corpus panel")

    def test_the_button_is_there_and_explains_itself(self, window):
        panel = self.corpus_panel(window)
        assert panel.edges_button.text()
        # A tooltip that restates the label helps nobody decide anything.
        assert len(panel.edges_button.toolTip()) > len(panel.edges_button.text())

    def test_it_writes_the_books_and_says_what_they_are(self, window, tmp_path):
        panel = self.corpus_panel(window)
        panel.books.setText(str(tmp_path))

        from epubforge.edge_cases import build_edges

        panel._handle_edges(build_edges(tmp_path))
        text = panel.output.toPlainText()
        assert len(list(tmp_path.glob("*.epub"))) == 4
        for name in ("brzeg-bez-okladki", "brzeg-400-sekcji"):
            assert name in text
        # Not just four filenames: what each one is at the limit of.
        assert "400" in text

    def test_it_refuses_politely_without_a_folder(self, window, monkeypatch):
        panel = self.corpus_panel(window)
        panel.books.setText("")
        asked = []
        monkeypatch.setattr(
            "epubforge.gui.tabs.QMessageBox.information",
            lambda *args, **kwargs: asked.append(args),
        )
        # No folder: it says so and starts no job, rather than building four
        # books into whatever the working directory happens to be.
        panel._build_edges()
        assert asked
        assert not panel.busy


class TestTheRenderCheckIsInTheWindow:
    """F-028. The one check that needs something the program does not ship, and
    therefore the one most likely to become a control nobody can explain."""

    def panel(self, window):
        from epubforge.gui.tabs import DiagnosticsPanel

        for index in range(window.tabs.count()):
            if isinstance(window.tabs.widget(index), DiagnosticsPanel):
                return window.tabs.widget(index)
        raise AssertionError("no diagnostics panel")

    def test_the_choice_is_there_and_explains_itself(self, window):
        panel = self.panel(window)
        assert panel.render_choice.text()
        assert len(panel.render_choice.toolTip()) > 200

    def test_the_tooltip_says_what_counts_as_a_defect(self, window):
        """The rule the real books forced: only loss counts. Somebody reading
        this control needs to know that before they run it on a book whose cover
        this program is about to repair."""
        tip = self.panel(window).render_choice.toolTip()
        assert "strata" in tip.lower() or "loss" in tip.lower()

    def test_with_no_browser_it_says_what_is_missing(self, window, tmp_path, monkeypatch):
        from epubforge import render
        from epubforge.gui.tabs import DiagnosticsPanel

        monkeypatch.setattr(render, "find_renderer", lambda: None)
        lines = DiagnosticsPanel._render(str(tmp_path / "nie-ma.epub"))
        said = " ".join(lines)
        assert render.ENV_BROWSER in said
        assert "Chromium" in said


class TestTheMemoryGuardIsInTheWindow:
    """EF-020. The build most likely to meet a machine that runs out is this
    one: a batch of books, in a window, on a laptop, on Windows — where the
    outcome without a guard is the process disappearing."""

    def test_the_switch_is_there_and_on(self, window):
        assert window.memory_check.isChecked()
        assert len(window.memory_check.toolTip()) > len(window.memory_check.text())

    def test_the_switch_reaches_the_policy(self, window):
        window.memory_check.setChecked(False)
        assert window._policy().check_memory is False
        window.memory_check.setChecked(True)
        assert window._policy().check_memory is True

    def test_the_budget_can_be_typed_and_reaches_the_policy(self, window):
        window.memory_limit_edit.setText("4G")
        assert window._policy().memory_limit == 4 * 1024**3

    def test_an_empty_budget_means_ask_the_machine(self, window):
        window.memory_limit_edit.setText("")
        assert window._policy().memory_limit is None

    def test_a_mistyped_budget_falls_back_rather_than_refusing_everything(self, window):
        """A limit of nonsense read as zero would refuse every book in the
        batch, which is a worse answer to a typo than ignoring it."""
        window.memory_limit_edit.setText("cztery gigabajty")
        assert window._policy().memory_limit is None

    def test_the_inspector_says_what_a_book_will_cost(self, window, tmp_path):
        """Before the rebuild rather than during it. On a book big enough to
        matter this is the difference between a line of text and a process the
        system kills without a word."""
        from epubforge.gui.tabs import DiagnosticsPanel
        from tests.factory import make_modern_epub

        book = tmp_path / "a.epub"
        make_modern_epub(str(book), title="Miara")
        lines = DiagnosticsPanel._describe(str(book))
        assert any("pamięć" in line for line in lines), lines


class TestTheFixtureBooksAreAskedForInTheWindow:
    """Which purchased books the suite is waiting for, in the window.

    The audit called two of them mandatory and blocked three findings on them,
    and the owner's answer was that he had no idea which files were meant. He
    runs the installer; a role catalogue reachable only through `pytest` on a
    checkout would have left the question exactly as unanswered as the audit
    left it.
    """

    def panel(self, window):
        from epubforge.gui.tabs import CorpusPanel

        for index in range(window.tabs.count()):
            if isinstance(window.tabs.widget(index), CorpusPanel):
                return window.tabs.widget(index)
        raise AssertionError("no corpus panel")

    def test_both_buttons_are_there_and_explain_themselves(self, window):
        panel = self.panel(window)
        for button in (panel.fixtures_button, panel.assign_button):
            assert button.text()
            assert len(button.toolTip()) > len(button.text())

    def test_it_names_the_role_and_what_the_book_has_to_contain(self, window):
        """Not "ksiazka-1: missing" — that is the audit's answer restated. The
        panel prints what the book has to have in it, which is the only form of
        the question the owner can act on."""
        from epubforge.fixtures import ROLES, Match

        panel = self.panel(window)
        panel._handle_fixtures([Match(role.id) for role in ROLES])
        text = panel.output.toPlainText()
        for role in ROLES:
            assert role.id in text
            assert role.exercises[0] in text
            for finding in role.findings:
                assert finding in text

    def test_a_book_that_is_there_is_named(self, window, tmp_path):
        import pathlib

        from epubforge.fixtures import Match

        panel = self.panel(window)
        panel._handle_fixtures([Match("ksiazka-1", pathlib.Path(tmp_path / "jest.epub"))])
        assert "jest.epub" in panel.output.toPlainText()

    def test_a_near_miss_is_offered_as_a_question_and_not_as_the_answer(self, window, tmp_path):
        """A shortlist, labelled a shortlist. Matching by resemblance handed a
        different novel to a role when it was allowed to decide by itself."""
        import pathlib

        from epubforge.fixtures import Match

        panel = self.panel(window)
        panel._handle_fixtures(
            [Match("ksiazka-1", None, (pathlib.Path(tmp_path / "podobna.epub"),))]
        )
        text = panel.output.toPlainText()
        assert "podobna.epub" in text
        assert tr("corpus.fixtures.missing") in text


class TestTheStreakIsVisibleFromTheWindow:
    """The owner has been asking this from outside the program.

    He remembered three green metrics and watched the count go back to zero,
    with no way to check which of us was right — the streak was computed by a
    function nothing called, in a package he has no checkout of. A number only
    the developer can read is a number the owner has to take on trust.
    """

    def panel(self, window):
        from epubforge.gui.tabs import CorpusPanel

        for index in range(window.tabs.count()):
            if isinstance(window.tabs.widget(index), CorpusPanel):
                return window.tabs.widget(index)
        raise AssertionError("no corpus panel")

    def ledger(self, tmp_path, entries):
        import json

        signatures = tmp_path / "expected"
        signatures.mkdir(parents=True, exist_ok=True)
        (tmp_path / "runs.json").write_text(json.dumps(entries), encoding="utf-8")
        return signatures

    def test_it_names_the_releases_and_what_was_passed_over(self, window, tmp_path):
        panel = self.panel(window)
        panel._signatures_used = self.ledger(
            tmp_path,
            [
                {"version": "0.2.4", "books": 90, "modes": ["preserve"], "clean": True},
                {"version": "0.2.5", "books": 99, "modes": ["preserve"], "clean": False},
                {"version": "0.2.6", "books": 99, "modes": ["preserve"], "clean": True},
            ],
        )
        said = panel._streak()
        assert "0.2.4" in said and "0.2.6" in said
        assert "0.2.5" in said  # passed over, and said so rather than hidden

    def test_a_missing_ledger_says_nothing_rather_than_guessing(self, window, tmp_path):
        panel = self.panel(window)
        panel._signatures_used = tmp_path / "expected"
        assert panel._streak() == ""


class TestTheWindowSpeaksOneLanguageAtATime:
    def test_neither_dictionary_is_missing_what_the_other_has(self):
        """A missing key falls back to English and then to the key itself, so
        the failure is silent in tests and loud in the window: the user reads
        `corpus.streak` where a sentence should be. Two dictionaries edited by
        hand drift the moment one string is added in a hurry."""
        from epubforge.gui.strings import EN, LANGUAGES

        for name, catalogue in LANGUAGES.items():
            assert set(catalogue) == set(EN), (
                f"{name} and en disagree on: "
                f"{sorted(set(catalogue) ^ set(EN))}"
            )

    def test_the_survey_headings_follow_the_setting(self, window):
        from epubforge.gui import strings
        from epubforge.gui.tabs import LibraryPanel

        panel = next(
            window.tabs.widget(i)
            for i in range(window.tabs.count())
            if isinstance(window.tabs.widget(i), LibraryPanel)
        )

        class FakeSurvey:
            books = 3
            source_versions = __import__("collections").Counter({"2.0": 3})
            unreadable: list = []
            crashed: list = []
            drm: list = []

            def ranked(self):
                return []

        before = strings.language()
        try:
            strings.set_language("pl")
            polish = panel._render_survey(FakeSurvey())
            strings.set_language("en")
            english = panel._render_survey(FakeSurvey())
        finally:
            strings.set_language(before)

        assert "3 książki" in polish and "wersje źródła" in polish
        assert "3 book(s)" in english and "source versions" in english
        # The defect this guards: Polish headings printed over an English report.
        assert "książki" not in english


class TestAskingAboutAReferenceNothingCanResolve:
    """F-010's interactive half, which is the owner's rule made operational.

    *If the application cannot do something itself, let us involve the user* —
    and specifically not: quietly pick whichever answer keeps the validator
    happy, so that the program never has to interrupt anybody. The dialog is
    tested here for what it *returns*, because that is what the rebuild acts
    on; how it looks belongs in front of a person.
    """

    @staticmethod
    def question():
        from epubforge.references import Unresolved

        return Unresolved(
            document="EPUB/text/0002-chapter.xhtml",
            target="EPUB/text/0003-notes.xhtml",
            fragment="fn-17",
            text="17",
            candidates=("fn-1", "fn-2"),
        )

    def dialog(self, qt_app):
        from epubforge.gui.ask import AskDialog

        return AskDialog(self.question())

    def test_it_defaults_to_leaving_the_publishers_reference_alone(self, qt_app):
        from epubforge import references

        assert self.dialog(qt_app).decision().action == references.KEEP

    def test_choosing_an_anchor_repoints_the_link(self, qt_app):
        from epubforge import references

        dialog = self.dialog(qt_app)
        dialog.repoint_radio.setChecked(True)
        dialog.candidates.setCurrentRow(1)
        decision = dialog.decision()
        assert decision.action == references.REPOINT
        assert decision.fragment == "fn-2"

    def test_selecting_from_the_list_is_itself_the_choice(self, qt_app):
        """A list of anchors that does nothing until a radio button above it is
        found is a dialog that answers itself wrongly."""
        from epubforge import references

        dialog = self.dialog(qt_app)
        dialog.candidates.setCurrentRow(0)
        assert dialog.decision().action == references.REPOINT

    def test_the_top_of_the_document_is_available_but_never_the_default(self, qt_app):
        from epubforge import references

        dialog = self.dialog(qt_app)
        assert not dialog.document_radio.isChecked()
        dialog.document_radio.setChecked(True)
        assert dialog.decision().action == references.POINT_AT_DOCUMENT

    def test_one_answer_can_cover_the_book_but_a_chosen_anchor_cannot(self, qt_app):
        dialog = self.dialog(qt_app)
        dialog.all_check.setChecked(True)
        assert dialog.decision().apply_to_all
        dialog.repoint_radio.setChecked(True)
        dialog.candidates.setCurrentRow(0)
        assert not dialog.decision().apply_to_all

    def test_a_document_with_no_anchors_offers_nothing_to_choose(self, qt_app):
        from epubforge.gui.ask import AskDialog
        from epubforge.references import Unresolved

        dialog = AskDialog(Unresolved("a.xhtml", "b.xhtml", "fn-17"))
        assert not dialog.repoint_radio.isEnabled()

    def test_the_window_offers_the_whole_thing_and_wires_it_up(self, window):
        """A dialog nothing reaches is not a feature. The box is on by default:
        somebody is at the window, which is the entire premise."""
        assert window.ask_check.isChecked()
        assert window._ask_resolver() is not None
        window.ask_check.setChecked(False)
        assert window._ask_resolver() is None

    def test_the_resolver_answers_on_the_thread_it_is_called_from(self, window, monkeypatch):
        """Called from the GUI thread it must not use the blocking signal — a
        blocking queued connection to one's own thread is a deadlock."""
        from epubforge import references
        from epubforge.gui import ask

        monkeypatch.setattr(
            ask.Ask, "_answer", lambda self, question: references.Decision(references.KEEP)
        )
        resolver = ask.Ask(window)
        assert resolver.resolve(TestAskingAboutAReferenceNothingCanResolve.question()) is not None

class TestEveryFeatureIsActuallyInTheWindow:
    """Not "the label exists" — the control exists, on the built window.

    Written after the owner asked whether the two new features were reachable
    from the window "or do I have to remind you again". They were, and nothing
    was checking it: the tests around them asserted that the *strings* existed
    and that the *command line* had the commands, which is precisely the shape
    of error the 2026-08-14 baseline caught five times over — proving the parts
    exist while nothing proves they are wired together.

    So this constructs the window and asks it.
    """

    def test_diagnostics_asks_whether_the_file_is_whole(self, window):
        panel = window.tabs.widget(3)
        assert panel.health_choice.text().strip()

    def test_and_that_question_is_wired_to_the_answer(self, window):
        """A radio button connected to nothing looks identical to one that
        works, right up until somebody presses it."""
        panel = window.tabs.widget(3)
        assert callable(panel._health)
        source = (ROOT / "epubforge" / "gui" / "tabs.py").read_text(encoding="utf-8")
        assert "elif self.health_choice.isChecked():" in source
        assert "answer = self._health" in source

    def test_merging_damaged_copies_is_in_the_menu(self, window):
        entries = {
            action.text()
            for menu_action in window.menuBar().actions()
            if menu_action.menu() is not None
            for action in menu_action.menu().actions()
        }
        assert any("Scal" in text or "Merge" in text for text in entries), sorted(entries)

    def test_and_the_dialog_opens_with_nothing_writable(self, window):
        """The human-in-the-loop requirement, asserted on the real dialog: the
        button that writes is disabled until a plan has been computed and
        shown."""
        from epubforge.gui.merge import MergeDialog

        dialog = MergeDialog(window)
        try:
            assert not dialog.write_button.isEnabled()
            dialog._examine()  # with no copies added
            assert not dialog.write_button.isEnabled()
        finally:
            dialog.close()

    def test_the_publication_gate_is_a_choice_somebody_can_make(self, window):
        """0.2.23's invariant, same rule: a policy the window cannot set is a
        policy the owner does not have."""
        from epubforge.policy import GATES

        assert window.gate_combo.count() == len(GATES)
        assert [
            window.gate_combo.itemData(index) for index in range(window.gate_combo.count())
        ] == list(GATES)


class TestEveryStatusHasAColour:
    """EF-066, closed the way the seventh audit's S-2 asked.

    The `blocked` status existed in `STATUS_KEYS` and not in the colour
    table, and the window found out with a KeyError on the one row a person
    most needs to read — a gate's refusal. Nothing in the suite watched the
    two tables agree, so only somebody who happened to hit a refusal could
    see it. The mapping is module-level now precisely so this invariant can
    be a test instead of a manual observation.
    """

    def test_the_two_tables_name_the_same_statuses(self):
        from dataclasses import fields

        from epubforge.gui.app import STATUS_COLOR_ROLES, STATUS_KEYS

        assert set(STATUS_KEYS) == set(STATUS_COLOR_ROLES)
        palette_fields = {f.name for f in fields(theme.Palette)}
        for role in STATUS_COLOR_ROLES.values():
            assert role in palette_fields, role

    def test_every_status_paints_a_row_in_a_real_window(self, window):
        """The audit reproduced EF-066 by calling `_set_status(0, "blocked")`
        in real Qt; this is that measurement, kept. Any status either table
        knows must colour a cell without raising."""
        from epubforge.gui.app import STATUS_KEYS

        window.table.setRowCount(len(STATUS_KEYS))
        for row, status in enumerate(STATUS_KEYS):
            window._set_status(row, status)
            item = window.table.item(row, 1)
            assert item is not None and item.text()
