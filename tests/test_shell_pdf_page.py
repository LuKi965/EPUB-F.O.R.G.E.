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
import pathlib

import pytest

pytest.importorskip("PySide6.QtWidgets")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from epubforge.gui.shell import tokens as tokens_module  # noqa: E402
from epubforge.decisions import KEEP  # noqa: E402
from epubforge.gui.shell.backend import DemoBackend  # noqa: E402
from epubforge.gui.shell.models import BookStatus, Severity, Stage  # noqa: E402
from epubforge.gui.shell.pages.pdf_conversion import PdfConversionPage  # noqa: E402
from epubforge.gui.shell.pdf_backend import DemoPdfBackend  # noqa: E402
from epubforge.gui.shell import window as window_module  # noqa: E402
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


class TestTheQuestionReachesAPersonA01:
    """A01 of the 0.4.4 recovery plan: *„pytaj" w PDF nie dociera do
    użytkownika.*

    The screen offers `running_heads = ask`, and the owner's whole position is
    that the program should ask where it does not know. Four links stand
    between that choice and a person, and **each one alone is enough** to
    break it:

    1. `PdfConversionPage` is built without a `resolver_factory` — the rebuild
       next door is given one (`window.py`);
    2. `PdfConversionPage.plan()` writes `ask=False` into the plan;
    3. `ConversionJob.run` calls `backend.convert(...)` with no `resolver=`;
    4. `service._convert_one` then computes `asker=resolver if plan.ask
       else None`, which is `None` either way.

    So the queue answers `UNANSWERED`, whose `option` defaults to `keep`, and
    the stage writes `pdf.running-heads-kept` — a line that says *as chosen*.
    Nobody chose. That last part is a separate defect from the wiring and is
    asserted separately: a report that cannot tell a decision from a silence
    is worse than one that does not report at all.

    These tests go through the real page, the real plan, the real worker and
    the real backend. A probe of the plan alone would only prove that one
    number is `False`.
    """

    @staticmethod
    def _asked_about(page, qt_app, source, tmp_path) -> "tuple[list, object]":
        """Run one conversion through the page and return what was asked."""
        put = []

        class Responder:
            """Somebody to ask. Answers `remove`, so that an answer that
            arrives is visible in the result and cannot be confused with the
            silence that also produces `keep`."""

            def ask(self, question):
                from epubforge.decisions import Answer

                put.append(question)
                return Answer(option="remove", apply_to_group=True)

        page.set_resolver_factory(Responder)
        page.start([str(source)])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.settings.running_heads = "ask"
        page.destination = tmp_path / "out"
        page.destination.mkdir(exist_ok=True)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS, tries=3000)
        return put, page

    def test_choosing_ask_puts_the_question_to_somebody(self, qt_app, tmp_path):
        from epubforge.gui.shell.pdf_backend import PdfBackend
        from tests.test_pdf import book_with_heads

        page = PdfConversionPage(tokens_module.DARK, PdfBackend("pl"))
        try:
            put, page = self._asked_about(page, qt_app, book_with_heads(tmp_path), tmp_path)
            assert put, (
                "nikogo nie zapytano, choć na ekranie wybrano „pytaj” — "
                "wybór nie dociera do respondera (A01)"
            )
            assert any(q.group == "pdf:running-heads" for q in put), [q.group for q in put]
        finally:
            page.runner.stop()
            page.runner.wait_for_idle()
            page.close()

    def test_the_plan_carries_the_choice_instead_of_a_written_false(self, qt_app):
        page = PdfConversionPage(tokens_module.DARK, DemoPdfBackend())
        try:
            page.settings.running_heads = "ask"
            assert page.plan().ask is True, (
                "plan mówi ask=False, choć ekran pyta — to drugie z czterech ogniw"
            )
            page.settings.running_heads = "keep"
            assert page.plan().ask is False, (
                "plan ma pytać tylko wtedy, gdy człowiek o to poprosił"
            )
        finally:
            page.close()

    def test_the_answer_reaches_the_book_and_not_only_the_recorder(self, qt_app, tmp_path):
        """Asking is half of it. The answer has to change the result, or the
        dialog is decoration."""
        from epubforge.gui.shell.pdf_backend import PdfBackend
        from tests.test_pdf import book_with_heads

        page = PdfConversionPage(tokens_module.DARK, PdfBackend("pl"))
        try:
            put, page = self._asked_about(page, qt_app, book_with_heads(tmp_path), tmp_path)
            assert put
            written = [item.output for item in page.documents if item.output]
            assert written, [item.status for item in page.documents]
            import zipfile

            with zipfile.ZipFile(written[0]) as archive:
                prose = " ".join(
                    archive.read(name).decode("utf-8", "replace")
                    for name in archive.namelist() if name.endswith(".xhtml")
                )
            assert "THE BOOK OF PAGES" not in prose, (
                "odpowiedziano „usuń”, a żywa pagina została w książce"
            )
        finally:
            page.runner.stop()
            page.runner.wait_for_idle()
            page.close()

    def test_nobody_is_asked_when_nobody_asked_to_be(self, qt_app, tmp_path):
        """`keep` and `remove` are answers already given. Putting a question
        anyway would be the opposite defect: a program that interrupts a
        person who has already decided."""
        from epubforge.gui.shell.pdf_backend import PdfBackend
        from tests.test_pdf import book_with_heads

        put = []

        class Responder:
            def ask(self, question):
                from epubforge.decisions import Answer

                put.append(question)
                return Answer(option="remove", apply_to_group=True)

        page = PdfConversionPage(tokens_module.DARK, PdfBackend("pl"))
        try:
            page.set_resolver_factory(Responder)
            page.start([str(book_with_heads(tmp_path))])
            settle(qt_app, page, lambda: page.stage is Stage.PLAN)
            page.settings.running_heads = "remove"
            page.destination = tmp_path / "out2"
            page.destination.mkdir(exist_ok=True)
            page.run()
            settle(qt_app, page, lambda: page.stage is Stage.RESULTS, tries=3000)
            assert not put, "zapytano, choć człowiek już odpowiedział w ustawieniach"
        finally:
            page.runner.stop()
            page.runner.wait_for_idle()
            page.close()

    def test_a_cancelled_run_stops_asking(self, qt_app, tmp_path):
        """Cancel means stop, including stop asking. A queue that keeps
        putting questions after the person cancelled is a window they cannot
        close."""
        from epubforge.gui.shell.pdf_backend import PdfBackend
        from tests.test_pdf import book_with_heads

        put = []

        class Responder:
            """Cancels the batch the first time it is asked anything."""

            def __init__(self, page) -> None:
                self._page = page

            def ask(self, question):
                from epubforge.decisions import Answer

                put.append(question)
                self._page.runner.stop()
                return Answer(option=KEEP)

        # Three documents, because the running-head question is put once per
        # document: with one there is one question either way and the test
        # would pass without cancelling anything.
        first = book_with_heads(tmp_path)
        sources = [str(first)]
        for number in (2, 3):
            copy = tmp_path / f"heads{number}.pdf"
            copy.write_bytes(first.read_bytes())
            sources.append(str(copy))

        page = PdfConversionPage(tokens_module.DARK, PdfBackend("pl"))
        try:
            page.set_resolver_factory(lambda: Responder(page))
            page.start(sources)
            settle(qt_app, page, lambda: page.stage is Stage.PLAN)
            page.settings.running_heads = "ask"
            page.destination = tmp_path / "out3"
            page.destination.mkdir(exist_ok=True)
            page.run()
            settle(qt_app, page, lambda: page.stage is Stage.RESULTS, tries=6000)
            assert len(put) == 1, f"pytano dalej po anulowaniu: {len(put)}"
        finally:
            page.runner.stop()
            page.runner.wait_for_idle()
            page.close()

    def test_closing_the_window_takes_the_question_back(self, qt_app):
        """A question is a blocking call from the worker into this thread, so
        a conversion waiting for an answer holds the close until somebody
        answers it. The rebuild has been taken back on close since questions
        were wired to it; the converter had no questions to take back, and now
        that it has, it has to be taken back too."""
        window = MainWindow(tokens_module.DARK, backend=DemoBackend(),
                            pdf_backend=DemoPdfBackend())
        try:
            taken = []

            class Resolver:
                def stop(self):
                    taken.append(True)

            window.pdf._resolver = Resolver()
            window.pdf.stop_asking()
            assert taken, "pytania konwersji nie da się odwołać"
            # And the window knows to do it: the close path names both pages.
            source = pathlib.Path(window_module.__file__).read_text(encoding="utf-8")
            assert "self.pdf.stop_asking()" in source
            assert "self.rebuild.stop_asking()" in source
        finally:
            window.close()

    def test_each_run_gets_its_own_asker(self, qt_app, tmp_path):
        """A fresh one per run, like the rebuild's. An asker kept across runs
        carries the standing answers of a batch nobody is looking at any more
        (F05)."""
        made = []

        class Responder:
            def __init__(self) -> None:
                made.append(self)

            def ask(self, question):
                from epubforge.decisions import Answer

                return Answer(option=KEEP)

        page = PdfConversionPage(tokens_module.DARK, DemoPdfBackend())
        try:
            page.set_resolver_factory(Responder)
            page.settings.running_heads = "ask"
            for number in range(2):
                page.start([str(tmp_path / f"a{number}.pdf")])
                settle(qt_app, page, lambda: page.stage is Stage.PLAN)
                page.destination = tmp_path
                page.run()
                settle(qt_app, page, lambda: page.stage is Stage.RESULTS, tries=2000)
            assert len(made) == 2, f"respondentów: {len(made)}"
            assert made[0] is not made[1]
        finally:
            page.runner.stop()
            page.runner.wait_for_idle()
            page.close()


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

    def test_the_stepper_lights_the_step_a_person_is_standing_on(self, qt_app, page):
        """Its own four steps, and the right one of them.

        D-057 is why this module has a stepper of its own rather than *Plan
        przebudowy* written over a conversion. But the names were one slot out:
        `Ustawienia` sat where the flow never stops and `Konwersja` where it
        does, so the settings screen showed the settings step **ticked as done**
        with the next one highlighted — the one thing a stepper exists not to
        do. Seen in a screenshot of this page, not in the code.
        """
        assert page.stepper.KEYS != page.stepper.__class__.KEYS, "kroki przebudowy"
        page.start(["a.pdf"])
        assert page.stage is Stage.PLAN
        here = page.stepper.KEYS[page.stage.step]
        assert here == "pdf.step.settings", here
        assert tr(here) in page.stepper._labels[page.stage.step].text()
        # And the step before it is behind, not the one being chosen.
        assert page.stepper.KEYS.index("pdf.step.settings") == page.stage.step


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

    def test_the_reason_is_on_the_results_screen_and_not_only_in_the_report(
        self, qt_app, page
    ):
        """P05 and P07: *„jawne «OCR nieobsługiwane»"* and *„widoczne
        w wyniku, nie tylko w pełnym raporcie"*.

        The row gives a remark one elided line, and the sentence that says what
        was refused and why ends past the ellipsis. Every remark was thrown
        away besides — the adapter kept `warnings[0]` in one string — so there
        was nothing for a screen to show even if it had wanted to.

        Seen in a screenshot of the real converter: the refused scan's row read
        *„PDF nie ma warstw…"*, and the word OCR was nowhere on the screen.
        """
        from PySide6.QtWidgets import QLabel

        page.start(["Instrukcja.pdf", "Skan bez tekstu.pdf"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        scan = next(one for one in page.outcome.books if one.title == "Skan bez tekstu")
        page._select(scan)
        said = " ".join(
            one.text() for one in page._notes_card.findChildren(QLabel) if one.text()
        )
        assert tr("pdf.needs.ocr") in said, said
        # And a document that converted cleanly does not borrow the scan's.
        clean = next(one for one in page.outcome.books if one.published)
        page._select(clean)
        after = " ".join(
            one.text() for one in page._notes_card.findChildren(QLabel) if one.text()
        )
        assert tr("pdf.needs.ocr") not in after

    def test_every_remark_survives_and_not_only_the_first(self, qt_app, page):
        """`warnings[0]` in a single string is one remark; the rest were lost
        between the service and the row."""
        page.start(["Katalog czesci.pdf"])
        settle(qt_app, page, lambda: page.stage is Stage.PLAN)
        page.run()
        settle(qt_app, page, lambda: page.stage is Stage.RESULTS)
        (item,) = page.outcome.books
        kept = [line for group in item.categories for line in group.lines]
        assert len(kept) >= item.issues, (item.issues, kept)

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
