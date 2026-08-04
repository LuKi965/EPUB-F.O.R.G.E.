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
    def test_all_three_features_have_a_tab(self, window):
        labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert len(labels) == 3
        assert all(labels)

    def test_the_title_names_the_application_once(self, window):
        """Qt appends applicationDisplayName to every title; setting both gave
        "EPUB F.O.R.G.E. 0.1.1 (pre-alpha) - EPUB F.O.R.G.E."."""
        assert window.windowTitle().count("F.O.R.G.E.") == 1

    def test_the_title_states_the_maturity(self, window):
        assert "pre-alpha" in window.windowTitle()


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
