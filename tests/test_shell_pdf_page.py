"""The converter's screen, as a screen: its own session, its own settings.

`test_pdf_module.py` holds the boundary below the window; this holds it *in*
the window — the part the owner said a separate directory does not achieve:
*„Nie wystarczy osobny katalog, ukrywanie ustawień PDF ani nowa etykieta nad
tym samym RebuildPage."*

So the questions here are: is it a different page, does it carry a different
plan, does it refuse an EPUB, and does the rebuild refuse a PDF.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6.QtWidgets")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from epubforge.gui.shell import tokens as tokens_module  # noqa: E402
from epubforge.gui.shell.backend import DemoBackend  # noqa: E402
from epubforge.gui.shell.models import BookStatus, Severity, Stage  # noqa: E402
from epubforge.gui.shell.pages.pdf_conversion import PdfConversionPage  # noqa: E402
from epubforge.gui.shell.pdf_backend import DemoPdfBackend  # noqa: E402
from epubforge.gui.shell.window import MainWindow  # noqa: E402
from epubforge.gui.strings import tr  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(tokens_module.stylesheet(tokens_module.DARK))
    yield app


@pytest.fixture
def page(qt_app):
    widget = PdfConversionPage(tokens_module.DARK, DemoPdfBackend())
    yield widget
    widget.runner.stop()
    widget.runner.wait_for_idle()
    widget.close()


@pytest.fixture
def window(qt_app):
    win = MainWindow(tokens_module.DARK, backend=DemoBackend(),
                     pdf_backend=DemoPdfBackend())
    yield win
    win.close()


def settle(app, page, until, tries: int = 200) -> None:
    import time

    for _ in range(tries):
        app.processEvents()
        if until():
            return
        time.sleep(0.01)
    raise AssertionError(f"nie doczekano się stanu; etap = {page.stage}")


class TestItIsItsOwnPageAndNotALabelOnTheRebuild:
    def test_the_window_has_two_task_pages_and_they_are_different_objects(self, window):
        assert window.pdf is not window.rebuild
        assert type(window.pdf) is not type(window.rebuild)
        assert window.pages["pdf"] is window.pdf

    def test_the_sidebar_offers_the_conversion_as_a_destination(self, window):
        assert "pdf" in window.sidebar.buttons
        assert window.sidebar.buttons["pdf"].text().strip().endswith(tr("shell.nav.pdf"))

    def test_the_start_screen_names_two_jobs(self, window):
        home = window.home
        assert home.rebuild_tile.accessibleName() == tr("shell.home.task.rebuild")
        assert home.convert_tile.accessibleName() == tr("shell.home.task.pdf")

    def test_the_two_pages_carry_different_plans(self, qt_app, page, window):
        from epubforge.gui.shell.models import RebuildPlan
        from epubforge.pdfconv.models import PdfConversionPlan

        page.start(["a.pdf"])
        assert isinstance(page.plan(), PdfConversionPlan)
        assert isinstance(window.rebuild.plan(), RebuildPlan)
        # Not the same object under two names, and not one with a flag in it.
        assert not isinstance(page.plan(), RebuildPlan)

    def test_the_settings_on_this_page_are_the_converters_own(self, qt_app, page):
        """Two decisions about the conversion, and the publication gate whose
        refusal a person has to be able to answer. Not the rebuild's forty."""
        page.start(["a.pdf"])
        assert page.stage is Stage.PLAN
        assert set(page._groups) == {"layout", "running_heads", "render_gate"}
        # And not the rebuild's three presets or its drawer.
        assert not hasattr(page, "preset")
        assert not hasattr(page, "drawer")
        # The two that are the converter's live in its settings; the gate does
        # not, because it belongs to the layer both modules share.
        assert set(vars(page.settings)) == {"layout", "running_heads"}
        assert "render_gate" in page.publication


class TestTheDocumentsThatReachIt:
    def test_it_takes_pdfs_and_says_the_epub_belongs_next_door(self, qt_app, page):
        sent = []
        page.misrouted.connect(sent.append)
        page.start(["one.pdf", "book.epub"])
        assert [item.source.name for item in page.documents] == ["one.pdf"]
        # Said on the page, not asked in a box: the batch is not held up by it.
        assert sent == [], "przekazanie stało się bez pytania"
        assert page._strangers == ["book.epub"]
        assert page.notice.isVisibleTo(page)
        page.notice.acted.emit()
        assert sent == [["book.epub"]]

    def test_an_epub_alone_starts_nothing_here(self, qt_app, page):
        sent = []
        page.misrouted.connect(sent.append)
        page.start(["book.epub"])
        assert page.documents == []
        assert page.stage is Stage.FILES
        assert page._strangers == ["book.epub"] and sent == []

    def test_hiding_the_notice_forgets_the_files_rather_than_sending_them(
        self, qt_app, page
    ):
        sent = []
        page.misrouted.connect(sent.append)
        page.start(["one.pdf", "book.epub"])
        page.notice.dismissed.emit()
        assert page._strangers == [] and sent == []

    def test_nothing_is_claimed_about_a_document_nobody_has_read(self, qt_app, page):
        page.start(["one.pdf"])
        (item,) = page.documents
        assert item.summary == tr("pdf.analysis.unchecked")

    def test_the_limits_are_said_before_anything_is_asked_for(self, qt_app, page):
        from PySide6.QtWidgets import QLabel

        said = [one.text() for one in page.findChildren(QLabel) if one.text()]
        assert tr("pdf.limits.ocr") in said


class TestWhatAConversionResultMeans:
    def test_a_scan_is_a_refusal_and_not_a_publication(self, qt_app, page):
        page.start(["Instrukcja.pdf", "Skan bez tekstu.pdf"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        by_title = {item.title: item for item in page.outcome.books}
        scan = by_title["Skan bez tekstu"]
        assert scan.status is BookStatus.BLOCKED
        assert scan.published_outputs == () and not scan.published
        assert scan.error == tr("pdf.needs.ocr")
        assert page.outcome.published == 1, "skan policzył się jako publikacja"

    def test_the_outcome_says_what_kind_of_job_it_was(self, qt_app, page):
        from epubforge.gui.shell.models import Operation

        page.start(["Instrukcja.pdf"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        assert page.outcome.operation is Operation.PDF_CONVERSION
        assert page.outcome.session_id == page.session_id

    def test_a_warning_is_a_note_and_not_a_failure(self, qt_app, page):
        page.start(["Instrukcja.pdf", "Katalog czesci.pdf"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        warned = [item for item in page.outcome.books if item.issues]
        assert warned, "atrapa nie daje uwag — test nic nie mierzy"
        for item in warned:
            assert item.published and item.severity is Severity.WARNING
            assert item.status is BookStatus.ATTENTION

    def test_handing_the_result_on_is_offered_and_never_automatic(self, qt_app, page):
        from PySide6.QtWidgets import QPushButton

        asked = []
        page.handover.connect(asked.append)
        page.start(["Instrukcja.pdf"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        assert asked == [], "przekazanie do przebudowy stało się samo"
        card = page._next_card(page.outcome)
        (send_on,) = [
            one for one in card.findChildren(QPushButton)
            if one.text() == tr("pdf.results.handover")
        ]
        assert send_on.isEnabled()
        send_on.click()
        assert asked and asked[0] == [str(page.outcome.published_outputs[0])]


class TestTheSessionsDoNotReachEachOther:
    def test_a_conversion_result_from_an_old_session_is_dropped(self, qt_app, page):
        page.start(["Instrukcja.pdf"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        before = page.session_id
        page.session_id = "nowa"
        page._converted(before, list(page.documents))
        assert page.outcome is None
        assert page.stage is Stage.PLAN

    def test_the_rebuilds_settings_are_untouched_by_the_converters(self, qt_app, window):
        """P09: two plans, two sessions, no shared state."""
        before = dict(window.rebuild.overrides), window.rebuild.preset
        window.pdf.start(["a.pdf"])
        window.pdf.settings.layout = "fixed"
        assert (dict(window.rebuild.overrides), window.rebuild.preset) == before
        assert not hasattr(window.rebuild.plan(), "settings")

    def test_ctrl_s_follows_the_page_a_person_is_on(self, qt_app, window):
        window.navigate("pdf")
        assert not window.actions_by_key["save"].isEnabled()
        window.pdf.start(["Instrukcja.pdf"])
        settle(qt_app, window.pdf, lambda: window.pdf.stage is Stage.PLAN)
        window.pdf.run()
        settle(qt_app, window.pdf, lambda: window.pdf.stage is Stage.RESULTS)
        assert window.actions_by_key["save"].isEnabled()
        window.navigate("rebuild")
        assert not window.actions_by_key["save"].isEnabled()


class TestTheWindowRoutesWhatIsDroppedOnIt:
    def test_a_pdf_opens_the_conversion_and_an_epub_the_rebuild(self, qt_app, window):
        window.route(["a.pdf"])
        assert window.router.currentWidget() is window.pdf
        assert [item.source.name for item in window.pdf.documents] == ["a.pdf"]

        window.route(["b.epub"])
        assert window.router.currentWidget() is window.rebuild
        settle(qt_app, window.rebuild, lambda: window.rebuild.stage is Stage.PLAN)
        assert [book.source.name for book in window.rebuild.books] == ["b.epub"]

    def test_a_mixed_drop_is_summarised_and_starts_neither_by_itself(
        self, qt_app, window, monkeypatch
    ):
        """02-UI-DESIGN §1: say what the split is, offer two sessions, run
        nothing. The old window put whatever arrived into one batch."""
        offered = []
        monkeypatch.setattr(
            type(window), "_offer_both",
            lambda self, books, documents: offered.append((len(books), len(documents)))
        )
        window.route(["a.epub", "b.pdf", "c.epub"])
        assert offered == [(2, 1)]
        assert window.pdf.documents == [] and window.rebuild.books == []

    def test_adding_both_fills_two_sessions_and_runs_neither(self, qt_app, window):
        """The answer the design asks to be possible: both halves added, as two
        sessions with two ids, and nothing published by a drop."""
        window._start_conversion(["b.pdf"])
        window._start_rebuild(["a.epub", "c.epub"])
        settle(qt_app, window.rebuild, lambda: window.rebuild.stage is Stage.PLAN)
        assert [item.source.name for item in window.pdf.documents] == ["b.pdf"]
        assert [book.source.name for book in window.rebuild.books] == ["a.epub", "c.epub"]
        assert window.pdf.session_id != window.rebuild.session_id
        assert window.pdf.outcome is None and window.rebuild.outcome is None

    def test_a_file_neither_module_reads_starts_nothing(self, qt_app, window):
        window.route(["notes.txt"])
        assert window.pdf.documents == [] and window.rebuild.books == []

    def test_the_history_records_the_conversion_as_its_own_kind(self, qt_app, window,
                                                                monkeypatch):
        written = []
        monkeypatch.setattr(
            "epubforge.gui.shell.window.remember",
            lambda record: written.append(record) or [record],
        )
        window.navigate("pdf")
        window.pdf.start(["Instrukcja.pdf"])
        settle(qt_app, window.pdf, lambda: window.pdf.stage is Stage.PLAN)
        window.pdf.run()
        settle(qt_app, window.pdf, lambda: window.pdf.stage is Stage.RESULTS)
        assert written, "konwersja nie trafiła do historii"
        assert written[-1].operation == "pdf_conversion"
        assert tr(written[-1].kind_key) == tr("shell.history.kind.pdf_conversion")


class TestTheRebuildPageWillNotTakeADocument:
    def test_a_pdf_dropped_on_the_rebuild_is_offered_the_other_module(self, qt_app, window):
        window.navigate("rebuild")
        window.rebuild.start(["a.pdf", "b.epub"])
        settle(qt_app, window.rebuild, lambda: window.rebuild.stage is Stage.PLAN)
        assert [book.source.name for book in window.rebuild.books] == ["b.epub"]
        assert window.rebuild._strangers == ["a.pdf"]
        # Nothing moved by itself; acting on the notice is what does it.
        assert window.router.currentWidget() is window.rebuild
        window.rebuild.notice.acted.emit()
        assert window.router.currentWidget() is window.pdf
        assert [item.source.name for item in window.pdf.documents] == ["a.pdf"]

    def test_and_a_pdf_alone_leaves_the_plan_empty(self, qt_app, window):
        window.rebuild.start(["a.pdf"])
        assert window.rebuild.books == []
        assert window.rebuild.stage is Stage.FILES

    def test_the_rebuild_file_dialog_offers_books_only(self):
        assert ".pdf" not in tr("dialog.filter")
        assert ".pdf" in tr("dialog.filter.pdf")
