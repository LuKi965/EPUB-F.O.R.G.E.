"""A15 of the 0.4.4 recovery audit: the converter inherited the whole of the
rebuild's stage list, so a stage added for EPUBs started running over every
converted book without anybody deciding it should. The list is now the
converter's own (`service.PDF_STAGES`), and the source's digest keeps a stored
answer from being replayed onto a file that has changed.
"""

from __future__ import annotations

import pathlib

import pytest

from epubforge import decisions, pipeline, stages
from epubforge.pdfconv import service
from epubforge.pdfconv.settings import PdfSettings
from epubforge.policy import Policy
from epubforge.report import Report
from epubforge.stages.base import Stage
from tests.test_pdf import THREE_PARAGRAPHS, column, make_pdf

pytest.importorskip("pdfminer.high_level")


def quiet_policy(**overrides) -> Policy:
    return Policy.preset("preserve", validate_before_publish="off", render_gate="off",
                         render_sample=0, **overrides)


class Rogue(Stage):
    """A stage somebody adds to the EPUB rebuild tomorrow."""

    name = "test-rogue"
    ran: list = []

    def run(self, ctx) -> None:
        Rogue.ran.append(ctx.book.source_version)


class TestTheConverterChoosesItsOwnStagesA15:
    def test_the_list_is_named_and_is_the_rebuilds_list_today(self):
        """Naming the list changed nothing about the output: it is the
        rebuild's list, in the rebuild's order. What changed is who decides."""
        assert tuple(service.PDF_STAGES) == tuple(stages.DEFAULT_STAGES)
        assert service.PDF_STAGES is not stages.DEFAULT_STAGES

    def test_a_stage_added_to_the_rebuild_does_not_run_over_a_converted_book(self, tmp_path, monkeypatch):
        """The defect, reproduced by doing what the audit warned about:
        appending a stage to `DEFAULT_STAGES` and converting a PDF."""
        monkeypatch.setattr(stages, "DEFAULT_STAGES", stages.DEFAULT_STAGES + (Rogue,))
        monkeypatch.setattr(pipeline, "DEFAULT_STAGES", pipeline.DEFAULT_STAGES + (Rogue,))
        Rogue.ran.clear()
        source = make_pdf(tmp_path / "one.pdf", [column(THREE_PARAGRAPHS)])
        result = service.convert_document(str(source), str(tmp_path / "out.epub"),
                                          PdfSettings(), quiet_policy())
        assert result.output_path
        assert Rogue.ran == [], "etap dopisany do przebudowy EPUB pobiegl po ksiazce z PDF-a"

    def test_the_same_stage_does_run_over_an_epub(self, tmp_path, monkeypatch):
        """The other half, so the test cannot pass by the stage never
        running at all."""
        from tests.factory import make_modern_epub

        monkeypatch.setattr(stages, "DEFAULT_STAGES", stages.DEFAULT_STAGES + (Rogue,))
        monkeypatch.setattr(pipeline, "DEFAULT_STAGES", pipeline.DEFAULT_STAGES + (Rogue,))
        Rogue.ran.clear()
        source = make_modern_epub(str(tmp_path / "book.epub"))
        result = pipeline.rebuild(source, str(tmp_path / "out.epub"), quiet_policy())
        assert result.output_path, result.report.to_text("pl")
        assert Rogue.ran, "etap dopisany do przebudowy nie pobiegl po EPUB-ie"


class TestAStoredAnswerIsAboutOneVersionOfTheFile:
    """`source_hash` in the plan's words: a decision saved beside the file
    loses its validity when the file changes. The store has been keyed on
    the file's digest since BA-2026-002; this asks it of a PDF, through the
    converter's own door."""

    @staticmethod
    def _manual(tmp_path: pathlib.Path, name: str, extra: str = "") -> pathlib.Path:
        pages = []
        for number in range(1, 7):
            lines = [(72, 760, 10.0, "Instrukcja obslugi"), (300, 40, 10.0, str(number))]
            lines += column([f"Strona {number} niesie zwykla proze w swoim korpusie,",
                             f"zlozona stopniem tekstu.{extra}"], top=690)
            pages.append(lines)
        return make_pdf(tmp_path / name, pages, title="Instrukcja", language="pl")

    def test_an_answer_stored_for_the_file_is_replayed_and_for_a_changed_file_refused(self, tmp_path):
        source = self._manual(tmp_path, "manual.pdf")
        # Answers saved beside this file, keyed to its digest. The set is
        # empty on purpose: what is under test is the key, and a store with
        # the right key is loaded quietly while one with the wrong key is
        # named — with a question in it the second case would look the same.
        store = decisions.Queue().save(decisions.answers_path(source), source=source)
        assert store.is_file()

        report = Report()
        result = service.convert_document(str(source), str(tmp_path / "same.epub"),
                                          PdfSettings(running_heads="ask"), quiet_policy(), report=report)
        assert result.output_path, report.to_text("pl")
        assert "decisions.store-unusable" not in {f.rule for f in report.findings}

        # The file changes under the stored answers: one more character on
        # every page. The digest no longer matches and nothing is replayed.
        changed = self._manual(tmp_path, "manual.pdf", extra=" I jeszcze zdanie.")
        assert changed == source
        report = Report()
        service.convert_document(str(source), str(tmp_path / "changed.epub"),
                                 PdfSettings(running_heads="ask"), quiet_policy(), report=report)
        said = next(f for f in report.findings if f.rule == "decisions.store-unusable")
        assert "different version" in (said.values.get("reason") or "")
