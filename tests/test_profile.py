"""The measuring stage, and the promise that it only measures.

`docs/ROADMAP.md` point [3] asks for a statistical profile of a book, computed
once, so that points [4], [5] and [7] share one answer to "is this construction
this book's rule or its exception" instead of guessing separately. It says the
first release must change nothing in anybody's book, and calls that a condition
rather than a convention.

A condition gets a test. The first class here rebuilds a book with the stage in
place and compares every resource byte for byte against a rebuild without it —
which is the only form of that promise nobody can argue with.

Everything else pins a threshold. Every number in `profile.py` is a named
constant because the first contact with a real shelf will move them, and a
number nobody can find is a number nobody will move; these tests say what each
one currently means so that moving it is a decision rather than an accident.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import profile as book_profile
from epubforge import xhtml
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.profile import (
    BODY_TEXT_SHARE,
    BREAK_RUN,
    INTENT_OCCURRENCES,
    PARADIGM_SHARE,
    SEPARATOR_LENGTH,
    Profile,
    measure,
)
from epubforge.stages import DEFAULT_STAGES, ProfileStage
from tests.factory import MODERN_NAV, MODERN_OPF, png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>Rozdzia&#x142;</title>{head}</head>
  <body>{body}</body>
</html>
"""


def roots(*bodies: str, head: str = ""):
    """Parsed documents, which is what `measure` takes."""
    return [
        xhtml.parse_document(PAGE.format(body=body, head=head).encode()).root
        for body in bodies
    ]


def book(path, *, body: str, css: str = "") -> str:
    entries = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/package.opf": MODERN_OPF.format(title="Test", extra_metadata="").encode(),
        "OEBPS/nav.xhtml": MODERN_NAV.encode(),
        "OEBPS/chapter.xhtml": PAGE.format(body=body, head="").encode(),
        "OEBPS/picture.png": png_bytes(),
    }
    if css:
        entries["OEBPS/style.css"] = css.encode()
        entries["OEBPS/package.opf"] = entries["OEBPS/package.opf"].replace(
            b'<item id="img"',
            b'<item id="css" href="style.css" media-type="text/css"/><item id="img"',
        )
    return write_zip(str(path), entries)


class TestTheStageOnlyMeasures:
    """The condition the roadmap sets, held to bytes rather than to intent."""

    def contents(self, path) -> dict[str, bytes]:
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in sorted(archive.namelist())}

    def test_the_output_is_identical_with_and_without_it(self, tmp_path):
        source = book(
            tmp_path / "in.epub",
            body=(
                '<p class="para">Pierwszy akapit.</p>'
                '<p class="para">Drugi akapit.</p>'
                "<p>* * *</p><p>Trzeci.<br/><br/>Czwarty.</p>"
                '<p style="text-align: center"><b>Rozdział</b></p>'
            ),
            css=".para { text-indent: 1.5em; } .martwa { color: red; }",
        )
        with_stage = rebuild(source, str(tmp_path / "a.epub"), Policy.preset("preserve"))
        without = [s for s in DEFAULT_STAGES if s is not ProfileStage]
        no_stage = rebuild(
            source, str(tmp_path / "b.epub"), Policy.preset("preserve"), stages=without
        )
        assert self.contents(with_stage.output_path) == self.contents(
            no_stage.output_path
        )

    def test_it_is_in_the_pipeline_between_metadata_and_content(self):
        """Earlier is impossible — paths are frozen by the structure stage —
        and later would measure our own output and call it the book."""
        names = [stage.__name__ for stage in DEFAULT_STAGES]
        assert names.index("MetadataStage") < names.index("ProfileStage")
        assert names.index("ProfileStage") < names.index("ContentStage")
        assert names.index("StructureStage") < names.index("ProfileStage")

    def test_it_puts_the_profile_on_the_context(self, tmp_path):
        source = book(tmp_path / "c.epub", body="<p>Tekst.</p>")
        result = rebuild(source, str(tmp_path / "d.epub"), Policy.preset("preserve"))
        assert any(f.stage == "profile" for f in result.report.findings)

    def test_it_says_nothing_at_all_about_an_unreadable_book(self):
        """No documents, no findings — not a profile of nothing."""
        assert measure([], "") == Profile()


class TestTheBodyTextShape:
    def test_a_dominant_shape_is_found(self):
        body = "".join('<p class="para">Zdanie.</p>' for _ in range(9)) + "<p>Inne.</p>"
        profile = measure(roots(body), "")
        assert profile.body.shape == ("p", "para")
        assert profile.body.consistent

    def test_a_book_with_no_dominant_shape_says_so(self):
        """Saying a book has a shape when it does not would be the profile
        inventing the consistency it exists to measure."""
        body = "".join(f'<p class="c{i}">Zdanie.</p>' for i in range(10))
        profile = measure(roots(body), "")
        assert not profile.body.consistent

    def test_the_share_is_kept_even_when_it_is_too_low(self):
        """How far off the book was is the useful part; rounding it to None
        throws away the only number that says so."""
        body = "".join(f'<p class="c{i % 5}">Zdanie.</p>' for i in range(10))
        profile = measure(roots(body), "")
        assert 0 < profile.body.share < BODY_TEXT_SHARE

    def test_a_block_with_several_classes_has_no_single_shape(self):
        """Guessing which of three classes is the one that matters is the kind
        of invention this module exists to avoid."""
        body = "".join('<p class="a b c">Zdanie.</p>' for _ in range(5))
        profile = measure(roots(body), "")
        assert profile.body.shape == ("p", "")


class TestTheParagraphParadigm:
    def indented(self, count: int) -> str:
        return "".join(
            f'<p style="text-indent: 1.5em">Zdanie {i}.</p>' for i in range(count)
        )

    def spaced(self, count: int) -> str:
        return "".join(
            f'<p style="margin-bottom: 1em">Zdanie {i}.</p>' for i in range(count)
        )

    def test_an_indented_book(self):
        assert measure(roots(self.indented(10)), "").paragraphs.paradigm == "INDENTED"

    def test_a_spaced_book(self):
        assert measure(roots(self.spaced(10)), "").paragraphs.paradigm == "SPACED"

    def test_a_book_that_mixes_them(self):
        """Nearly always the trace of two sources glued together, which is why
        it is reported from the first version."""
        profile = measure(roots(self.indented(5) + self.spaced(5)), "")
        assert profile.paragraphs.paradigm == "MIXED"

    def test_a_book_that_consistently_does_both_is_not_mixed(self):
        """The first version counted a paragraph that was indented *and* spaced
        on both sides, which made "this publisher indents and leaves a little
        air" indistinguishable from "half this book came from somewhere else".
        Three of the six single-source Gutenberg books read MIXED under that
        rule, which is what said the rule was wrong rather than the books."""
        body = '<p style="text-indent: 1.5em; margin-bottom: 1em">Zdanie.</p>' * 10
        profile = measure(roots(body), "")
        assert profile.paragraphs.paradigm == "BOTH"
        assert profile.paragraphs.both == 10
        assert profile.paragraphs.indented == 0
        assert profile.paragraphs.spaced == 0

    def test_a_hairline_of_air_beside_an_indent_is_still_an_indented_book(self):
        """Project Gutenberg writes `p { text-indent: 1em; margin: 0.25em }`.
        A quarter of an em is four pixels: breathing room, not a paragraph
        break."""
        body = '<p style="text-indent: 1em; margin-bottom: 0.25em">Zdanie.</p>' * 8
        assert measure(roots(body), "").paragraphs.paradigm == "INDENTED"

    def test_a_book_that_does_neither_is_unknown_rather_than_mixed(self):
        assert measure(roots("<p>Zdanie.</p>" * 5), "").paragraphs.paradigm == "UNKNOWN"

    def test_the_threshold_is_high_on_purpose(self):
        """A threshold that swallows MIXED is worth nothing, and MIXED is the
        interesting signal."""
        assert PARADIGM_SHARE >= 0.9
        # Nine indented to one spaced is exactly the boundary and counts as
        # indented; one more spaced tips it.
        assert measure(roots(self.indented(9) + self.spaced(1)), "").paragraphs.paradigm == "INDENTED"
        assert measure(roots(self.indented(8) + self.spaced(2)), "").paragraphs.paradigm == "MIXED"

    def test_a_hairline_indent_is_not_an_indent(self):
        """Publishers who space their paragraphs still sometimes leave a
        near-zero value behind."""
        body = '<p style="text-indent: 0.1em; margin-bottom: 1em">Zdanie.</p>' * 5
        assert measure(roots(body), "").paragraphs.paradigm == "SPACED"

    def test_the_spacing_floor_sits_above_the_indent_floor(self):
        """Not symmetry for its own sake: a quarter-em margin is air and a
        quarter-em indent is still an indent, because the eye reads them
        differently."""
        from epubforge.profile import INDENT_FLOOR_EM, SPACING_FLOOR_EM

        assert SPACING_FLOOR_EM > INDENT_FLOOR_EM

    def test_the_two_kinds_of_mixture_are_told_apart(self):
        """A book that is half indented-only and half spaced-only is MIXED. A
        book where every paragraph does both is BOTH. Only the first is the
        trace of two files."""
        halves = self.indented(5) + self.spaced(5)
        together = '<p style="text-indent: 1.5em; margin-bottom: 1em">Z.</p>' * 10
        assert measure(roots(halves), "").paragraphs.paradigm == "MIXED"
        assert measure(roots(together), "").paragraphs.paradigm == "BOTH"

    def test_a_stylesheet_decides_as_well_as_an_inline_style(self):
        body = '<p class="wciecie">Zdanie.</p>' * 6
        profile = measure(roots(body), ".wciecie { text-indent: 2em; }")
        assert profile.paragraphs.paradigm == "INDENTED"


class TestTheClasses:
    def test_a_class_nobody_uses_is_dead(self):
        profile = measure(roots('<p class="zywa">Zdanie.</p>'), ".zywa{color:red}.martwa{color:blue}")
        assert profile.dead_classes == ("martwa",)

    def test_classes_saying_the_same_thing_are_a_group(self):
        profile = measure(roots("<p>Zdanie.</p>"), ".a{color:red}.b{color: RED;}.c{color:blue}")
        assert profile.duplicate_classes == (("a", "b"),)

    def test_a_selector_that_is_more_than_a_class_says_nothing_about_it(self):
        """`.a p { }` describes paragraphs inside `.a`, not `.a` itself."""
        profile = measure(roots("<p>Zdanie.</p>"), ".a p{color:red}.b{color:red}")
        assert profile.duplicate_classes == ()

    def test_a_shared_selector_lists_both_names(self):
        profile = measure(roots("<p>Zdanie.</p>"), ".a, .b { color: red }")
        assert profile.duplicate_classes == (("a", "b"),)

    def test_an_empty_rule_body_is_not_a_duplicate_of_another_empty_one(self):
        assert measure(roots("<p>x</p>"), ".a{}.b{}").duplicate_classes == ()


class TestTheThingsInTheProse:
    def test_a_row_of_asterisks_is_a_scene_break(self):
        for text in ("* * *", "⁂", "— — —", "***"):
            profile = measure(roots(f"<p>{text}</p>"), "")
            assert profile.separators == 1, text

    def test_a_short_sentence_is_not(self):
        assert measure(roots("<p>Koniec.</p>"), "").separators == 0

    def test_a_long_row_of_asterisks_is_still_prose_to_this_rule(self):
        """Bounded on purpose: a rule that is loose here puts a number in the
        report that nobody can trust later."""
        assert measure(roots("<p>" + "*" * (SEPARATOR_LENGTH + 5) + "</p>"), "").separators == 0

    def test_two_breaks_in_a_row_stand_in_for_a_paragraph(self):
        assert measure(roots("<p>a<br/><br/>b</p>"), "").break_runs == 1

    def test_a_single_break_is_a_line_break_and_nothing_more(self):
        assert measure(roots("<p>a<br/>b</p>"), "").break_runs == 0

    def test_a_run_of_three_is_counted_once(self):
        """Every member but the first has a break immediately before it, so
        counting backwards as well would report a run of three as three."""
        assert measure(roots("<p>a<br/><br/><br/>b</p>"), "").break_runs == 1
        assert BREAK_RUN == 2

    def test_a_bold_short_line_looks_like_a_heading(self):
        assert measure(roots("<p><b>Rozdział pierwszy</b></p>"), "").heading_candidates == 1

    def test_a_sentence_ending_in_a_full_stop_does_not(self):
        assert measure(roots("<p><b>To jest zdanie.</b></p>"), "").heading_candidates == 0

    def test_a_real_heading_is_not_a_candidate_to_become_one(self):
        assert measure(roots("<h2>Rozdział</h2>"), "").heading_candidates == 0


class TestWhatGetsReported:
    def findings(self, tmp_path, **kwargs) -> dict[str, dict]:
        source = book(tmp_path / "r.epub", **kwargs)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        return {
            f.rule: f.values for f in result.report.findings if f.stage == "profile"
        }

    def test_a_mixed_book_is_named_as_such(self, tmp_path):
        body = (
            '<p style="text-indent: 1.5em">A.</p>' * 5
            + '<p style="margin-bottom: 1em">B.</p>' * 5
        )
        assert "profile.paragraphs-mixed" in self.findings(tmp_path, body=body)

    def test_a_handful_of_anything_is_not_yet_a_pattern(self, tmp_path):
        """Two scene breaks is a coincidence; three is a book that uses them."""
        assert INTENT_OCCURRENCES == 3
        few = self.findings(tmp_path, body="<p>* * *</p>" * 2 + "<p>Zdanie.</p>" * 20)
        assert "profile.scene-separators-found" not in few

    def test_three_of_it_is(self, tmp_path):
        many = self.findings(
            tmp_path, body="<p>* * *</p>" * 3 + "<p>Zdanie.</p>" * 20
        )
        assert many["profile.scene-separators-found"]["count"] == 3

    def test_every_profile_finding_is_only_information(self, tmp_path):
        """Nothing here is a fix, a warning or a preserved deviation: the stage
        reports what a book is, and a book is not wrong for being it."""
        from epubforge.report import Level

        source = book(tmp_path / "lvl.epub", body="<p>* * *</p>" * 4 + "<p>A.</p>" * 9)
        result = rebuild(source, str(tmp_path / "o.epub"), Policy.preset("preserve"))
        levels = {f.level for f in result.report.findings if f.stage == "profile"}
        assert levels <= {Level.INFO}


class TestEveryNumberIsFindable:
    """A threshold buried in an expression is one nobody will calibrate."""

    @pytest.mark.parametrize(
        "name",
        [
            "BODY_TEXT_SHARE",
            "PARADIGM_SHARE",
            "INTENT_OCCURRENCES",
            "BREAK_RUN",
            "SEPARATOR_LENGTH",
            "INDENT_FLOOR_EM",
            "SPACING_FLOOR_EM",
        ],
    )
    def test_it_is_a_module_constant(self, name):
        assert isinstance(getattr(book_profile, name), (int, float))

    def test_the_roadmap_numbers_are_the_ones_written_down(self):
        """60% for the body text, 90% for the paradigm, three for intent."""
        assert BODY_TEXT_SHARE == 0.60
        assert PARADIGM_SHARE == 0.90
        assert INTENT_OCCURRENCES == 3

    def test_the_summary_is_counts_and_nothing_else(self):
        """It goes into an inventory that may be sent from a private shelf."""
        summary = measure(roots('<p class="a">Zdanie.</p>' * 4), ".a{text-indent:1em}").to_dict()
        for key, value in summary.items():
            assert isinstance(value, (int, float, bool, str, type(None))), key
        assert "Zdanie" not in repr(summary)


class TestTheInventoryCarriesTheProfile:
    """Where the numbers that will move these thresholds have to arrive.

    A survey says "twelve books came out MIXED", and a threshold needs the
    distribution behind that count, not the count. The inventory is per-book and
    holds only numbers — no titles, no text — which is what makes it the one
    file somebody can send from a private shelf and the right place for a figure
    that only a real shelf can settle.
    """

    def test_a_measured_book_carries_one(self, tmp_path):
        from epubforge.inventory import measure as inventory_measure

        source = book(
            tmp_path / "inv.epub",
            body='<p style="text-indent: 1.5em">Zdanie.</p>' * 8,
        )
        fields = inventory_measure(__import__("pathlib").Path(source)).fields
        assert fields["profile"]["paradigm"] == "INDENTED"
        assert fields["profile"]["body_blocks"] == 8

    def test_it_is_still_numbers_only(self, tmp_path):
        """The inventory may be sent from a shelf nobody else may see."""
        from epubforge.inventory import measure as inventory_measure

        source = book(tmp_path / "priv.epub", body="<p>Tajny tytuł powieści.</p>" * 4)
        fields = inventory_measure(__import__("pathlib").Path(source)).fields
        assert "Tajny" not in repr(fields["profile"])
        for value in fields["profile"].values():
            assert isinstance(value, (int, float, bool, str, type(None)))

    def test_an_unreadable_book_has_no_profile_rather_than_an_empty_one(self, tmp_path):
        from epubforge.inventory import measure as inventory_measure

        broken = tmp_path / "broken.epub"
        broken.write_bytes(b"not an epub at all")
        assert "profile" not in inventory_measure(broken).fields


class TestTheMarginShorthand:
    """`margin: 1em 0` is how most people write it, and it was invisible.

    Twenty-nine books out of ninety-three came back with no paragraph paradigm
    at all — a third of a real shelf — because this measurement looked only for
    `margin-top` and `margin-bottom` in full. It never showed on the six Project
    Gutenberg books it was built against, whose stylesheet happens to write the
    longhand. Six books cannot find a gap that six books do not have.
    """

    def paradigm(self, css: str) -> str:
        return measure(roots('<p class="a">Zdanie.</p>' * 8), css).paragraphs.paradigm

    @pytest.mark.parametrize(
        "css",
        [
            ".a { margin-top: 1em; margin-bottom: 1em }",
            ".a { margin: 1em }",
            ".a { margin: 1em 0 }",
            ".a { margin: 0 0 1em }",
            ".a { margin: 1em 0 1em 0 }",
        ],
    )
    def test_every_spelling_of_a_spaced_paragraph_is_seen(self, css):
        assert self.paradigm(css) == "SPACED"

    @pytest.mark.parametrize(
        "css",
        [
            ".a { margin: 0 1em }",  # horizontal only — not paragraph spacing
            ".a { margin: 0 0 0.25em }",  # under the floor
            ".a { margin: 0 }",
        ],
    )
    def test_a_margin_that_is_not_vertical_space_is_not_spacing(self, css):
        assert self.paradigm(css) == "UNKNOWN"

    def test_the_longhand_wins_where_both_are_given(self):
        """Not a renderer: the specific declaration is the one a publisher
        reached for, and guessing about cascade order would be inventing."""
        assert self.paradigm(".a { margin: 0; margin-bottom: 1em }") == "SPACED"

    def test_an_indent_beside_a_shorthand_margin_is_still_both(self):
        assert self.paradigm(".a { margin: 1em 0; text-indent: 1.5em }") == "BOTH"


class TestAVerdictNeedsMostOfTheBook:
    """Ninety-three real books said `SPACED` on one paragraph out of 3413.

    A ratio over a sample of one is 1.0, and under the first rule it carried
    exactly as much confidence as a book where 2036 paragraphs out of 2036
    agreed. Nine books in that shelf held a verdict on under a tenth of their
    text, and one of the three `MIXED` findings — the signal this measurement
    exists for — rested on 3.5% of its book.

    The shelf also said where the line goes: coverage is sharply bimodal, 38
    books under 10%, nothing at all between 10% and 33%, 41 in the 90–100%
    band. Half sits inside the empty stretch, so nothing hangs on the figure.
    """

    def test_one_paragraph_decides_nothing(self):
        from epubforge.profile import Paragraphs

        assert Paragraphs(spaced=1, neither=3412).paradigm == "UNKNOWN"

    def test_a_thin_mixture_is_not_a_mixed_book(self):
        """The costliest case: `MIXED` claims two files were glued together."""
        from epubforge.profile import Paragraphs

        thin = Paragraphs(indented=49, spaced=161, neither=5754)
        assert thin.coverage < 0.05
        assert thin.paradigm == "UNKNOWN"

    def test_a_book_that_was_read_through_still_gets_its_verdict(self):
        from epubforge.profile import Paragraphs

        assert Paragraphs(indented=6048, spaced=143, both=31, neither=369).paradigm == "INDENTED"
        assert Paragraphs(spaced=2036).paradigm == "SPACED"
        assert Paragraphs(indented=5, spaced=5).paradigm == "MIXED"

    def test_the_coverage_is_reported_beside_the_verdict(self):
        """It is what says whether to believe it, and the number that will move
        this threshold next time."""
        summary = measure(
            roots('<p style="margin-bottom: 1em">A.</p>' * 3 + "<p>B.</p>"), ""
        ).to_dict()
        assert summary["paradigm_coverage"] == 0.75
        assert summary["paradigm"] == "SPACED"

    def test_exactly_half_is_enough(self):
        from epubforge.profile import PARADIGM_COVERAGE, Paragraphs

        assert PARADIGM_COVERAGE == 0.50
        assert Paragraphs(spaced=5, neither=5).paradigm == "SPACED"
        assert Paragraphs(spaced=4, neither=5).paradigm == "UNKNOWN"
