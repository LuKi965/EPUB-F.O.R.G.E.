"""A13 of the 0.4.4 recovery audit: the report said *„Książka jest zdrowa —
nic nie wymaga Twojej uwagi"* about a book whose appearance and validation
gates were both switched off and which carried a question nobody had
answered. `Report.summary` read its verdict off the findings alone.

These are the pipeline's half of the fix: every gate records what became of
its check — passed, failed, not run, could not run — in `Report.checks`, and
the summary reads that record. `test_report_summary.py` holds the summary's
own cases; this file asks the real pipeline what it writes there.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import FAILED, NOT_CHECKED, PASSED, UNSUPPORTED
from epubforge.validate import find_epubcheck
from tests.factory import make_modern_epub


def rebuilt(tmp_path: pathlib.Path, **policy):
    source = make_modern_epub(str(tmp_path / "in.epub"))
    settings = Policy.preset("preserve", **policy)
    return rebuild(source, str(tmp_path / "out.epub"), settings)


class TestEveryGateLeavesARecordA13:
    def test_gates_switched_off_are_recorded_as_not_checked(self, tmp_path):
        """AC08's setting: no render, no validation. The file is written and
        the report must say what it did not look at — the verdict may not be
        "healthy" by default."""
        result = rebuilt(tmp_path, render_gate="off", validate_before_publish="off")
        assert result.output_path
        assert result.report.checks["render"] == NOT_CHECKED
        assert result.report.checks["validation"] == NOT_CHECKED
        lines = result.report.summary("pl")
        assert "zdrowa" not in lines[1]
        # This fixture warns, so the verdict is spent on the warning and the
        # missing checks are the line below it; a clean book would carry
        # them in the verdict itself (`test_report_summary.py`).
        said = next(line for line in lines[1:] if "sprawdzono" in line)
        assert "wyglądu stron" in said and "EPUBCheck" in said

    def test_a_missing_browser_is_recorded_as_unsupported_not_as_a_setting(self, tmp_path, monkeypatch):
        """A machine with no browser. `stop` with nobody to ask keeps the
        file; `accept_unverified_render` lets it through — and either way the
        check did not run, which is a different fact from "switched off": the
        person is told which tool was missing."""
        from epubforge import render

        monkeypatch.setattr(render, "find_renderer", lambda: None)
        result = rebuilt(
            tmp_path, render_gate="stop", accept_unverified_render=True,
            validate_before_publish="off",
        )
        assert result.output_path
        assert result.report.checks["render"] == UNSUPPORTED
        said = next(line for line in result.report.summary("pl")[1:] if "sprawdz" in line).lower()
        assert "nie dało się sprawdzić: wyglądu stron" in said
        assert "nie sprawdzono: zgodności z epubcheck" in said

    @pytest.mark.skipif(find_epubcheck() is None, reason="EPUBCheck is not on this machine")
    def test_a_validator_that_ran_records_its_verdict(self, tmp_path):
        result = rebuilt(tmp_path, render_gate="off", validate_before_publish="clean")
        assert result.output_path
        assert result.report.checks["validation"] in (PASSED, FAILED)
        # Read from the record, not from the rule names: the summary and the
        # JSON say the same thing about the same check.
        data = result.report.to_dict("pl")
        assert data["checks"]["validation"] == result.report.checks["validation"]
        assert data["checks"]["render"] == NOT_CHECKED

    def test_a_validator_that_is_missing_is_recorded_as_unsupported(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPUBCHECK_JAR", str(tmp_path / "nowhere.jar"))
        from epubforge import validate as validate_module

        monkeypatch.setattr(validate_module, "find_epubcheck", lambda: None)
        result = rebuilt(tmp_path, render_gate="off", validate_before_publish="no-new-errors")
        assert result.output_path
        assert result.report.checks["validation"] == UNSUPPORTED


class TestTheConverterKeepsTheSameRecord:
    """The PDF service composes its own run on the shared machinery; the
    record it leaves has to be the same shape, or the window shows two
    different truths for two kinds of file."""

    def test_a_pdf_conversion_with_gates_off_says_what_it_did_not_check(self, tmp_path):
        from tests.test_pdf import make_pdf, rebuilt as converted

        source = make_pdf(tmp_path / "one.pdf", [[(72, 700, 12.0, "A page of prose for the converter.")]])
        result = converted(source, tmp_path)
        assert result.output_path
        assert result.report.checks["render"] == NOT_CHECKED
        assert result.report.checks["validation"] == NOT_CHECKED
        assert "zdrowa" not in result.report.summary("pl")[1]


@pytest.mark.skipif(os.environ.get("EPUBFORGE_RENDER_TESTS") != "1", reason="needs the pinned browser")
class TestACheckThatRanSaysSo:
    def test_the_render_gate_that_looked_records_passed(self, tmp_path):
        from epubforge import render

        if render.find_renderer() is None:
            pytest.skip("no browser named")
        result = rebuilt(tmp_path, render_gate="stop", render_sample=0, validate_before_publish="off")
        assert result.output_path
        assert result.report.checks["render"] == PASSED
