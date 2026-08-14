"""F-028 at the commit point: the check that can refuse to write the file.

The owner chose `stop` as the default himself, after being shown both the cost
— about thirty-six seconds a book — and the measurements: zero refusals across
his thirty-two books, and, for the case he raised, zero across a book whose
forty-six hyphens had all been joined.

His question was the right one. *If the program repairs `wybo-rowy` to
`wyborowy`, the text after it shifts — so what does comparing screenshots even
mean?* It means what it measures: reflow moves ink, it does not remove it. The
gate asks whether a page **lost** something, not whether it changed.
"""

from __future__ import annotations

import pathlib

import pytest

from epubforge import render
from epubforge.pipeline import rebuild
from epubforge.policy import RENDER_GATES, Policy
from tests.test_render_fidelity import PARAGRAPHS, book

pytestmark = pytest.mark.skipif(
    render.find_renderer() is None,
    reason="no Chromium-based browser here; see epubforge.render.why_not()",
)


def rules_of(result) -> set:
    return {finding.rule for finding in result.report.findings if finding.rule}


def rebuilt(tmp_path, body: str, **policy):
    source = book(tmp_path / "in.epub", body)
    policy.setdefault("render_sample", 0)
    settings = Policy.preset("preserve", validate_before_publish="off", **policy)
    return source, rebuild(source, str(tmp_path / "out.epub"), settings)


class TestAnHonestBookGoesThrough:
    def test_it_publishes_and_says_it_looked(self, tmp_path):
        _, result = rebuilt(tmp_path, PARAGRAPHS)
        assert result.status.wrote_a_file, result.report.to_text()
        assert "render.checked" in rules_of(result)

    def test_the_default_is_the_one_the_owner_chose(self):
        assert Policy().render_gate == "stop"
        assert Policy().render_sample == 12

    def test_off_does_not_draw_anything(self, tmp_path):
        _, result = rebuilt(tmp_path, PARAGRAPHS, render_gate="off")
        assert not any(rule.startswith("render.") for rule in rules_of(result))


class TestAPageThatLostSomething:
    """The gate is given a rebuild that damages the book, by handing the writer
    a candidate whose content has been emptied. Nothing in the real pipeline
    does this — which is the point: the gate has to catch what nothing else
    would."""

    def damaged(self, tmp_path, gate: str):
        from epubforge import pipeline

        source = book(tmp_path / "in.epub", PARAGRAPHS)
        broken = book(tmp_path / "broken.epub", "")
        report = pipeline.Report(source=source, output=str(tmp_path / "out.epub"))
        settings = Policy.preset("preserve", render_gate=gate, render_sample=0)
        check = pipeline._render_gate(source, settings, report, str(tmp_path / "out.epub"))
        return check(broken), report

    def test_stop_refuses_and_names_the_page(self, tmp_path):
        refusal, report = self.damaged(tmp_path, "stop")
        assert refusal
        assert "render.page-lost-content" in {
            f.rule for f in report.findings if f.rule
        }

    def test_report_publishes_anyway_but_still_says_so(self, tmp_path):
        refusal, report = self.damaged(tmp_path, "report")
        assert refusal == ""
        assert "render.page-lost-content" in {
            f.rule for f in report.findings if f.rule
        }

    def test_the_pictures_are_kept_beside_the_book(self, tmp_path):
        """The owner's decision, and his argument: without them "this page has
        less on it" is something he would have to take on trust."""
        self.damaged(tmp_path, "stop")
        folder = tmp_path / "out.zrzuty"
        assert folder.is_dir(), sorted(p.name for p in tmp_path.iterdir())
        kept = sorted(p.name for p in folder.glob("*.png"))
        assert any(name.endswith("-przed.png") for name in kept), kept
        assert any(name.endswith("-po.png") for name in kept), kept

    def test_nothing_is_kept_when_nothing_was_lost(self, tmp_path):
        _, result = rebuilt(tmp_path, PARAGRAPHS)
        assert result.status.wrote_a_file
        assert not (tmp_path / "out.zrzuty").exists()


class TestReflowIsNotLoss:
    """The owner's objection, as a test.

    Measured on his own book before this was built: with all forty-six confirmed
    hyphens joined, 7 of 130 page comparisons moved at all, the largest by 1.64%
    of the pixels, and the drawn area changed by five thousandths of a
    percentage point — upwards on the largest. Here the same shape of change is
    made deliberately and asked about directly.
    """

    def test_text_that_shifted_is_not_a_refusal(self, tmp_path):
        from epubforge import pipeline

        # The same paragraphs, one word shorter — exactly what joining a hyphen
        # does to a page, and enough to reflow every line after it.
        source = book(tmp_path / "in.epub", PARAGRAPHS)
        shifted = book(
            tmp_path / "shifted.epub", PARAGRAPHS.replace("Akapit numer 1,", "Akapit 1,")
        )
        report = pipeline.Report(source=source, output=str(tmp_path / "out.epub"))
        settings = Policy.preset("preserve", render_gate="stop", render_sample=0)
        check = pipeline._render_gate(source, settings, report, str(tmp_path / "out.epub"))
        assert check(shifted) == ""


class TestWithoutABrowser:
    """The owner's instruction, verbatim: tell the person the verification is
    required, and let them decline it knowingly. Not a silent skip, and not a
    refusal that holds their book hostage to a dependency this program
    deliberately does not ship."""

    def test_it_publishes_and_says_the_check_did_not_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(render, "find_renderer", lambda: None)
        _, result = rebuilt(tmp_path, PARAGRAPHS)
        assert result.status.wrote_a_file
        assert "render.cannot-run" in rules_of(result)

    def test_the_message_says_it_is_required_and_how_to_decline(self, tmp_path, monkeypatch):
        """Both languages, because the owner reads the Polish one and the
        report renders English by default."""
        from epubforge.rules import CATALOGUES

        monkeypatch.setattr(render, "find_renderer", lambda: None)
        _, result = rebuilt(tmp_path, PARAGRAPHS)
        assert render.ENV_BROWSER in result.report.to_text()
        for phrase in ("required", "decline"):
            assert phrase in CATALOGUES["en"]["render.cannot-run"]
        for phrase in ("obowiązkowa", "świadomie"):
            assert phrase in CATALOGUES["pl"]["render.cannot-run"]

    def test_it_is_a_warning_and_not_an_error(self, tmp_path, monkeypatch):
        """An error would say the rebuild went wrong. It did not: a tool is
        missing, and the person is being told."""
        from epubforge.report import Level

        monkeypatch.setattr(render, "find_renderer", lambda: None)
        _, result = rebuilt(tmp_path, PARAGRAPHS)
        finding = next(f for f in result.report.findings if f.rule == "render.cannot-run")
        assert finding.level is Level.WARN


class TestTheWholeBookCanBeAsked:
    """He asked for this in those words. A sample is somebody else's choice
    about which pages of his book are worth looking at."""

    def test_zero_means_every_page(self, tmp_path):
        _, result = rebuilt(tmp_path, PARAGRAPHS, render_sample=0)
        checked = next(
            f for f in result.report.findings if f.rule == "render.checked"
        )
        assert "1" in checked.message

    def test_the_vocabulary_is_closed(self):
        assert RENDER_GATES == ("off", "report", "stop")


class TestTheCheapRefusalGoesFirst:
    def test_the_validator_gate_runs_before_the_renderer(self, tmp_path):
        """EPUBCheck costs seconds and rendering costs half a minute. A book the
        validator turns away is never drawn."""
        from epubforge import pipeline

        order = []
        source = book(tmp_path / "in.epub", PARAGRAPHS)
        report = pipeline.Report(source=source)
        monkey = pipeline._render_gate

        def spy_validator(*args, **kwargs):
            def gate(candidate):
                order.append("epubcheck")
                return "nie tym razem"
            return gate

        def spy_render(*args, **kwargs):
            def gate(candidate):
                order.append("render")
                return ""
            return gate

        original_validator = pipeline._publication_gate
        pipeline._publication_gate = spy_validator
        pipeline._render_gate = spy_render
        try:
            both = pipeline._both_gates(source, Policy.preset("preserve"), report, "x")
            assert both(source) == "nie tym razem"
        finally:
            pipeline._publication_gate = original_validator
            pipeline._render_gate = monkey
        assert order == ["epubcheck"], "the renderer ran on a book already refused"
