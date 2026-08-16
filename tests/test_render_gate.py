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

from epubforge import decisions, render
from epubforge.pipeline import rebuild
from epubforge.policy import RENDER_GATES, Policy
from tests.test_render_fidelity import PARAGRAPHS, book

import os

#: These tests measure a *browser*, not this program, and the numbers they
#: assert — how many pixels move, how much ink a page keeps — belong to one
#: engine. Run against whatever browser a machine happens to have, they measure
#: the machine: on the Windows runner they found Edge, took the suite from 200
#: seconds to 961, reported an empty engine version, and disagreed with Chromium
#: about three of the four damage shapes.
#:
#: That is the same defect as BA-2026-004 and as `find_renderer` searching only
#: `PATH`, arriving a third time, and the audit already named the fix: a
#: *pinned* renderer. So these run when somebody says which engine they mean —
#: `EPUBFORGE_RENDER_TESTS=1`, with `EPUBFORGE_CHROME` pointing at it if it is
#: not the one on `PATH` — and skip loudly otherwise rather than measuring
#: whatever turned up. They are run here before every release against
#: Chromium 141.
_ASKED_FOR = os.environ.get("EPUBFORGE_RENDER_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not _ASKED_FOR or render.find_renderer() is None,
    reason=(
        "set EPUBFORGE_RENDER_TESTS=1 and have a Chromium-based browser: these "
        "measure an engine, and an unpinned one measures the machine"
    ),
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
        check = pipeline._render_gate(
            source, settings, report, str(tmp_path / "out.epub"), decisions.Queue()
        )
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
        check = pipeline._render_gate(
            source, settings, report, str(tmp_path / "out.epub"), decisions.Queue()
        )
        assert check(shifted) == ""


class TestWithoutABrowser:
    """The owner's instruction, verbatim: tell the person the verification is
    required, and let them decline it **knowingly**. Not a silent skip, and not
    a refusal that holds their book hostage to a dependency this program
    deliberately does not ship.

    The first implementation kept the second half and dropped the first.
    DELTA-2026-08-15-001 reproduced it in one line: `render_gate="stop"`, no
    browser, and the book was written with a warning. The program had declined
    on the person's behalf and recorded it as though they had been asked, which
    is the one outcome nobody chose — the setting says stop, somebody planned
    around the word, and it did not stop.

    Three ways through and each is somebody deciding rather than the program
    assuming: answer the question, tick the box in advance, or set the gate to
    `report`. With nobody there to answer, an unanswered question falls back to
    "change nothing", and here that means no file — which is what `stop` says.
    """

    def test_nobody_to_ask_means_nothing_is_written(self, tmp_path, monkeypatch):
        monkeypatch.setattr(render, "find_renderer", lambda: None)
        _, result = rebuilt(tmp_path, PARAGRAPHS)
        assert not result.status.wrote_a_file, result.report.to_text()
        assert not (tmp_path / "out.epub").exists()
        assert "render.cannot-run" in rules_of(result)

    def test_a_person_may_decline_the_check_and_get_their_book(self, tmp_path, monkeypatch):
        """The other half of the instruction, and it has to be reachable by
        answering rather than by editing a setting: somebody with no browser is
        told what is missing and can say "write it anyway" on the spot."""
        from epubforge import decisions

        class Waives:
            def ask(self, question):
                assert question.kind == decisions.VERIFICATION
                return decisions.Answer(option="publish")

        monkeypatch.setattr(render, "find_renderer", lambda: None)
        source = book(tmp_path / "in.epub", PARAGRAPHS)
        result = rebuild(
            source, str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off", render_sample=0),
            asker=Waives(),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        assert "render.unverified-accepted" in rules_of(result)

    def test_consent_can_be_given_in_advance_for_a_batch(self, tmp_path, monkeypatch):
        """A shelf being rebuilt overnight has nobody to ask, and refusing all
        of it would be exactly the hostage-taking the owner ruled out. One
        field, set on purpose, and the report still says what was skipped."""
        monkeypatch.setattr(render, "find_renderer", lambda: None)
        _, result = rebuilt(tmp_path, PARAGRAPHS, accept_unverified_render=True)
        assert result.status.wrote_a_file, result.report.to_text()
        assert "render.unverified-accepted" in rules_of(result)

    def test_report_still_reports(self, tmp_path, monkeypatch):
        monkeypatch.setattr(render, "find_renderer", lambda: None)
        _, result = rebuilt(tmp_path, PARAGRAPHS, render_gate="report")
        assert result.status.wrote_a_file, result.report.to_text()
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

    def test_the_level_follows_what_actually_happened(self, tmp_path, monkeypatch):
        """It used to be a warning always, on the reasoning that a missing tool
        is not a broken rebuild. True — and it stopped being the whole story
        once the same condition could refuse to write the file. A line that
        explains why there is no output is an error; the same line next to a
        book that was written is a warning. The level is not a mood, it is
        whether the reader has an output."""
        from epubforge.report import Level

        monkeypatch.setattr(render, "find_renderer", lambda: None)
        _, refused = rebuilt(tmp_path, PARAGRAPHS)
        assert next(
            f for f in refused.report.findings if f.rule == "render.cannot-run"
        ).level is Level.ERROR

        _, reported = rebuilt(tmp_path, PARAGRAPHS, render_gate="report")
        assert next(
            f for f in reported.report.findings if f.rule == "render.cannot-run"
        ).level is Level.WARN


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
            both = pipeline._both_gates(
                source, Policy.preset("preserve"), report, "x", decisions.Queue()
            )
            assert both(source) == "nie tym razem"
        finally:
            pipeline._publication_gate = original_validator
            pipeline._render_gate = monkey
        assert order == ["epubcheck"], "the renderer ran on a book already refused"
