"""Print-era formatting: naming it, and freeing it only when asked.

WP-13, covering two findings that turn out to be the same mistake seen twice —
a rewrite of somebody's stylesheet justified by what the publisher *probably*
meant rather than by what the page *actually* shows.

**EF-029.** `absolute_font_sizes` has been counted in the inventory since the
survey existed and never reached a report or a repair. So the most common piece
of print-era formatting on a real shelf was being measured and never mentioned.

**EF-033.** `font-style: regular` is not CSS, so every parser drops the whole
declaration and the element inherits. Replacing it with `normal` does not
restore the publisher's intent — it *overrides*, and those two are the same
thing only while the inherited value is already normal.

The unit conversion is `rem` and not `em`, and the test that matters most in
this file is the nesting one: `em` resolves against the parent, so a converted
sheet would compound and the same declaration would mean different sizes in
different places. That is not a smaller version of the right answer, it is a
wrong one, and no care with the arithmetic fixes it because a regex cannot see
which rule ends up inside which.
"""

from __future__ import annotations

import zipfile

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .test_dead_css_urls import book, rules_of, stylesheet_of


def relative() -> Policy:
    policy = Policy.preset("preserve")
    policy.relative_units = True
    return policy


class TestTheSizesAreNamedWhetherOrNotAnythingIsDone:
    """The half of EF-029 that is true in every mode. A number counted in the
    inventory and never said is a measurement nobody can act on."""

    CSS = "p { font-size: 12px; } h1 { font-size: 24px; } .note { font-size: 9pt; }"

    def test_the_count_is_reported_per_file(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        found = [
            f for f in result.report.findings if f.rule == "css.absolute-units"
        ]
        assert len(found) == 1, "one message per stylesheet, not one per book"
        assert found[0].values["count"] == 3
        assert found[0].location.endswith("style.css")

    def test_the_count_is_the_one_grep_gives(self, tmp_path):
        """The acceptance condition, written as a test rather than as a promise
        to check by hand: the reported figure is the number of absolute font
        sizes in the file, counted independently of the code that reports it."""
        import re

        expected = len(re.findall(r"font-size\s*:\s*[\d.]+\s*(?:px|pt)", self.CSS))
        result = rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        said = next(f for f in result.report.findings if f.rule == "css.absolute-units")
        assert said.values["count"] == expected == 3

    def test_a_sheet_with_none_says_nothing(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", "p { font-size: 1.2em; }"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "css.absolute-units" not in rules_of(result)

    def test_nothing_is_rewritten_without_being_asked(self, tmp_path):
        """Off by default is the whole safety of this feature, so it is asserted
        against the file rather than against the flag."""
        result = rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "12px" in stylesheet_of(result)
        assert "rem" not in stylesheet_of(result)


class TestWhenAsked:
    def test_pixels_become_rem_against_the_initial_size(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", "p { font-size: 12px; }"),
            str(tmp_path / "out.epub"),
            relative(),
        )
        assert "font-size: 0.75rem" in stylesheet_of(result)

    def test_points_are_converted_through_their_own_definition(self, tmp_path):
        """9pt is 12px by the specification — not by the device — so it lands on
        the same number as the case above."""
        result = rebuild(
            book(tmp_path / "in.epub", ".note { font-size: 9pt; }"),
            str(tmp_path / "out.epub"),
            relative(),
        )
        assert "font-size: 0.75rem" in stylesheet_of(result)

    def test_nesting_does_not_compound(self, tmp_path):
        """The reason this is rem and not em, and the test the whole design
        hangs on.

        With `em` the paragraph below would resolve against a 20px body and come
        out at 20px instead of 16 — a quarter larger, on every nested rule in
        the book, differently depending on how deep it sits. `rem` is measured
        from the root, so both declarations come out at exactly size/16 and the
        page is unchanged.
        """
        css = "body { font-size: 20px; } p { font-size: 16px; }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            relative(),
        )
        sheet = stylesheet_of(result)
        assert "font-size: 1.25rem" in sheet, "20/16, measured from the root"
        assert "font-size: 1rem" in sheet, "16/16, and not 0.8 of a 20px parent"
        assert "em" not in sheet.replace("rem", ""), "em would compound"

    def test_the_proportions_the_publisher_chose_are_kept(self, tmp_path):
        """Everything moves by one factor, so a sheet whose sizes were picked
        against each other still reads as it was designed."""
        css = "p { font-size: 12px; } h1 { font-size: 24px; }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            relative(),
        )
        sheet = stylesheet_of(result)
        assert "font-size: 0.75rem" in sheet and "font-size: 1.5rem" in sheet

    def test_it_says_what_it_did(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", "p { font-size: 12px; }"),
            str(tmp_path / "out.epub"),
            relative(),
        )
        said = next(
            f for f in result.report.findings
            if f.rule == "css.absolute-units-relativised"
        )
        assert said.values["count"] == 1
        assert "css.absolute-units" not in rules_of(result), (
            "one sheet gets one verdict: reporting and converting is two"
        )

    def test_a_size_outside_a_font_size_is_not_touched(self, tmp_path):
        """Margins, borders and widths in pixels are layout the publisher drew,
        and the reader's font control was never going to reach them anyway."""
        css = "p { font-size: 12px; margin-left: 40px; border: 1px solid; }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            relative(),
        )
        sheet = stylesheet_of(result)
        assert "margin-left: 40px" in sheet and "1px solid" in sheet


class TestTheSheetThatPinsTheRoot:
    """`rem` is measured from the root element. A sheet that fixes the root in
    pixels has already fixed every `rem` beneath it, so converting would rewrite
    somebody's stylesheet and free nothing."""

    CSS = "html { font-size: 16px; } p { font-size: 12px; }"

    def test_it_is_left_alone(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            relative(),
        )
        assert "rem" not in stylesheet_of(result)
        assert "12px" in stylesheet_of(result)

    def test_and_says_why(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", self.CSS),
            str(tmp_path / "out.epub"),
            relative(),
        )
        assert "css.absolute-units-rooted" in rules_of(result)


class TestCorrectingRegularDependsOnWhatIsInherited:
    """EF-033. The correction and the current page agree only while the
    inherited value is normal, and this is the sheet where they do not."""

    def test_a_plain_sheet_is_corrected_as_before(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", ".name { font-style: regular; }"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "font-style: normal" in stylesheet_of(result)
        assert "css.invalid-value-corrected" in rules_of(result)

    def test_a_sheet_that_sets_italic_is_left_alone(self, tmp_path):
        """The failure: `.list` is italic, `.list .name` says `regular` and is
        therefore ignored, so the names have been italic since the book was
        published. Correcting the value turns them upright — a rebuild changing
        the page to what the publisher probably meant."""
        css = ".list { font-style: italic; } .list .name { font-style: regular; }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        sheet = stylesheet_of(result)
        assert "font-style: regular" in sheet
        assert "font-style: normal" not in sheet
        assert "css.invalid-value-inherited" in rules_of(result)
        assert "css.invalid-value-corrected" not in rules_of(result)

    def test_bold_counts_the_same_way(self, tmp_path):
        css = ".head { font-weight: bold; } .head em { font-weight: regular; }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "css.invalid-value-inherited" in rules_of(result)

    def test_and_so_does_the_shorthand(self, tmp_path):
        """`font: italic 12px serif` sets the same thing by another spelling,
        and a check that only looked for `font-style` would miss it."""
        css = ".q { font: italic 1em serif; } .q b { font-style: regular; }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "css.invalid-value-inherited" in rules_of(result)

    def test_a_numeric_weight_below_bold_does_not_block_it(self, tmp_path):
        """`font-weight: 400` *is* normal, so it cannot make the correction
        visible. Treating every numeric weight as emphasis would leave the
        invalid value in most of the sheets that carry it."""
        css = ".body { font-weight: 400; } .body b { font-weight: regular; }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "css.invalid-value-corrected" in rules_of(result)


class TestTheTextIsNeverAtRisk:
    def test_no_content_document_is_touched_by_any_of_this(self, tmp_path):
        """A stylesheet pass reaching into the documents would be a defect of a
        different order, and the balance would be right to block it."""
        css = "p { font-size: 12px; font-style: regular; }"
        result = rebuild(
            book(tmp_path / "in.epub", css),
            str(tmp_path / "out.epub"),
            relative(),
        )
        with zipfile.ZipFile(result.output_path) as archive:
            # By suffix rather than by path: a rebuild relays the container out,
            # which is its job, and a test pinned to the source layout would be
            # testing the layout instead of the text.
            name = next(n for n in archive.namelist() if n.endswith("chapter.xhtml"))
            page = archive.read(name).decode("utf-8")
        assert "Tekst rozdziału." in page
