"""Pillar A of the 0.4 plan, second slice: rules repeating a selector.

Two rules with one selector tie on specificity, so order is the whole
cascade — which is why every fold here is proved, not assumed. Identical
bodies fold into the **last** occurrence (earlier copies win no conflict);
a different body moves down only when no rule on the road declares any of
its properties and no at-rule stands between. Everything else stays and is
counted. The shelf's material: 149 lint findings, 30 of them made by
D-031's name fold the day slice 1 stripped the `mso-*` that had kept the
bodies different.
"""

from __future__ import annotations

import re
import zipfile

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of
from tests.test_class_translation import PAGE


def sheet_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        for name in archive.namelist():
            if name.endswith(".css"):
                return archive.read(name).decode("utf-8")
    raise AssertionError("no stylesheet in the rebuild")

BODY = (
    '<p class="jeden dwa">Akapit z treścią rozdziału.</p>'
    '<p class="trzy">Drugi akapit.</p>'
)


def build(tmp_path, *, sheet, body=BODY, sweep=None):
    source = make_book(
        tmp_path / "in.epub",
        {"c0.xhtml": PAGE.format(body=body)},
        extra_items='<item id="s" href="s.css" media-type="text/css"/>',
        extra_files={"OEBPS/s.css": sheet.encode()},
    )
    policy = Policy.preset("preserve", render_gate="off")
    if sweep is not None:
        policy.sweep_style_blocks = sweep
    return rebuild(source, str(tmp_path / "out.epub"), policy)


class TestTheProvableFolds:
    def test_identical_bodies_keep_the_last_occurrence(self, tmp_path):
        """`p.jeden` twice with one body, `p.dwa` between them fighting over
        `color`. An element carrying both classes reads the LAST `p.jeden`
        as the winner today; keeping the first copy instead would hand the
        win to `p.dwa`. The mutation that keeps the first occurrence fails
        here."""
        sheet = (
            "p.jeden { color: green; text-indent: 1em; } "
            "p.dwa { color: blue; } "
            "p.jeden { color: green; text-indent: 1em; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("p.jeden") == 1
        # the surviving p.jeden stands AFTER p.dwa, where the cascade put it
        assert out.index("p.dwa") < out.index("p.jeden")
        assert "css.duplicate-selectors-merged" in rules_of(result)

    def test_a_clear_road_lets_a_body_move_down(self, tmp_path):
        """Different bodies, and the rule between fights over none of the
        moved properties — the earlier body may ride down, prepended so the
        later body still wins inside the block as it won across blocks."""
        sheet = (
            "p.jeden { text-indent: 1em; } "
            "p.trzy { color: black; } "
            "p.jeden { margin: 0; line-height: 1.3; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("p.jeden") == 1
        merged = re.search(r"p\.jeden\s*\{([^}]*)\}", out).group(1)
        assert "text-indent" in merged and "margin" in merged
        assert "css.duplicate-selectors-merged" in rules_of(result)

    def test_a_contested_road_blocks_the_move(self, tmp_path):
        """`p.dwa` between the copies declares `color` too, and an element
        carrying both classes would flip its winner if the earlier `color`
        moved past it. No proof, no fold: both rules stay where the
        publisher put them. The mutation that moves regardless fails
        here."""
        sheet = (
            "p.jeden { color: green; } "
            "p.dwa { color: blue; } "
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("p.jeden") == 2
        assert "css.duplicate-selectors-kept" in rules_of(result)
        assert "css.duplicate-selectors-merged" not in rules_of(result)

    def test_an_at_rule_on_the_road_blocks_the_move_too(self, tmp_path):
        """The `@media` on the road holds a `p.jeden` colour that fights
        the moved colour — read, not cut, and a real conflict under any
        condition, so the move is blocked. The identical-bodies fold is
        unaffected: it never moves anything forward past the at-rule."""
        sheet = (
            "p.jeden { color: green; } "
            "@media screen { p.jeden { color: red; } } "
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet)
        assert sheet_of(result).count("p.jeden") == 3  # both + the media copy
        assert "css.duplicate-selectors-kept" in rules_of(result)

    def test_the_opt_out_counts_instead(self, tmp_path):
        sheet = (
            "p.jeden { color: green; } p.jeden { color: green; }"
        )
        result = build(tmp_path, sheet=sheet, sweep=False)
        assert sheet_of(result).count("p.jeden") == 2
        assert "css.duplicate-selectors-found" in rules_of(result)


class TestTheRenameMadeDuplicates:
    def test_the_name_folds_duplicates_are_folded_in_the_sheet_too(self, tmp_path):
        """D-031 gives two generator classes with one body one name — and
        until this slice the sheet kept both rules under that one name,
        which is where the shelf's +30 lint findings came from. After the
        fold there is one rule, one selector, one body."""
        body = (
            '<p class="calibre7">Akapit raz.</p><p class="calibre8">Akapit dwa.</p>'
        )
        sheet = (
            "p.calibre7 { margin: 1em 0; text-indent: 2em; line-height: 1.3; text-align: justify; } "
            "p.calibre8 { margin: 1em 0; text-indent: 2em; line-height: 1.3; text-align: justify; }"
        )
        result = build(tmp_path, sheet=sheet, body=body)
        out = sheet_of(result)
        assert out.count("ef-paragraph-1") == 1
        assert "css.duplicate-selectors-merged" in rules_of(result)


class TestOpaqueBodiesTakeNoPart:
    def test_an_equals_declaration_is_not_merge_food(self, tmp_path):
        """The measured collision with the `=` question (EF-059's fixture
        shape): `p.sgc-1 {text-align="center"}` parses as zero declarations,
        and a merge that believed that would quietly drop the very line
        `_malformed_declarations` just asked a person about — bypassing the
        whole question machinery. An opaque body takes no part in any fold.
        The mutation that trusts a partial parse fails here."""
        sheet = 'p.jeden {text-align="center"} p.jeden { color: black; }'
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert 'text-align="center"' in out       # kept, unasked → unchanged
        assert out.count("p.jeden") == 2
        assert "css.duplicate-selectors-merged" not in rules_of(result)


class TestEmptyNoise:
    """Third slice: what says nothing goes — empty comments, empty rules,
    empty at-rules. 1 982 `/**/` and 71 empty blocks on the lint baseline."""

    def test_empty_things_go_and_full_things_stay(self, tmp_path):
        sheet = (
            "/**/ /* Sekcja wstępu */ p.jeden { margin: 0; } "
            "p.pusty {} @media print {} /*  */"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "/**/" not in out and "/*  */" not in out
        assert "Sekcja wstępu" in out          # a comment with words is a note
        assert "p.pusty" not in out and "@media print" not in out
        assert "margin: 0" in out
        assert "css.empty-noise-removed" in rules_of(result)

    def test_an_empty_comment_inside_content_is_content(self, tmp_path):
        """`content: "/**/"` is somebody's text on the page. The mutation
        that swaps the walk for a regex fails here."""
        sheet = 'p.jeden { margin: 0; } p.jeden::before { content: "/**/"; }'
        result = build(tmp_path, sheet=sheet)
        assert 'content: "/**/"' in sheet_of(result)

    def test_the_opt_out_counts_the_emptiness_too(self, tmp_path):
        sheet = "p.jeden { margin: 0; } /**/ p.pusty {}"
        result = build(tmp_path, sheet=sheet, sweep=False)
        out = sheet_of(result)
        assert "/**/" in out and "p.pusty" in out
        assert "css.empty-noise-found" in rules_of(result)


class TestTheBookProvedRoads:
    """Slice 8, at the owner's own prompting („masz całe książki do
    dyspozycji"): the road test upgraded from grammar to the full prover —
    specificity, values, and this book's documents."""

    def test_a_contest_with_the_same_value_merges(self, tmp_path):
        """`p.dwa` on the road declares the same `color: green` the moved
        body carries — whichever wins, the page computes the same thing,
        so there is no contest. The mutation that compares names without
        values fails here."""
        sheet = (
            "p.jeden { color: green; } "
            "p.dwa { color: green; } "
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("p.jeden") == 1
        assert "css.duplicate-selectors-merged" in rules_of(result)

    def test_a_contest_of_different_specificity_merges(self, tmp_path):
        """`body p.dwa` outguns the moved branch on specificity, so their
        order never decided anything — the move cannot flip a winner
        specificity already picked."""
        sheet = (
            "p.jeden { color: green; } "
            "body p.dwa { color: blue; } "
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("p.jeden") == 1
        assert "css.duplicate-selectors-merged" in rules_of(result)

    def test_a_contest_these_documents_disprove_merges(self, tmp_path):
        """`p.trzy` ties and fights over `color` — but no element in this
        book is both `.jeden` and `.trzy`, so the pair never meets. The
        mutation that skips the document check fails here."""
        sheet = (
            "p.jeden { color: green; } "
            "p.trzy { color: blue; } "
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("p.jeden") == 1
        assert "css.duplicate-selectors-merged" in rules_of(result)

    def test_an_at_rule_holding_no_conflict_is_crossed(self, tmp_path):
        """The `@media` on the road holds only a colour; the moved body
        carries indentation. Read, not cut — and nothing in it can flip."""
        sheet = (
            "p.jeden { text-indent: 1em; } "
            "@media print { p.jeden { color: black; } } "
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("p.jeden") == 2  # the media copy and the merged rule
        assert "css.duplicate-selectors-merged" in rules_of(result)

    def test_a_stuck_sibling_blocks_everything_above_it(self, tmp_path):
        """The middle copy is opaque (`=` for a colon) and stays; the
        first copy must not jump it — same selector means every tie, and
        an unreadable body means an unknowable conflict. The mutation
        that lets copies above a refused sibling move fails here."""
        sheet = (
            "p.jeden { color: green; } "
            'p.jeden {text-align="center"} '
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("p.jeden") == 3
        assert "css.duplicate-selectors-merged" not in rules_of(result)
