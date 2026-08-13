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
