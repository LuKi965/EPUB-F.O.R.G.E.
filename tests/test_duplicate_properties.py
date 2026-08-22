"""Pillar A of the 0.4 plan, fourth slice: duplicates of a property in a block.

Within one block importance beats order and order beats nothing else, so a
duplicate is dead under exactly two proofs: every occurrence says the same
thing (the winner stays — the last important one when importance is in
play, the last occurrence otherwise), or the last value is one no validator
since CSS1 rejects, which is what disarms the fallback idiom. A pair like
`display: block; display: flex` stays: an old reader can reject `flex` and
fall back, and cutting the earlier line would take the book away from it.
The shelf's material: 1 288 lint findings, 87% of them Word's
`margin-bottom: 0cm` … `margin-bottom: .0001pt` with a line between.
"""

from __future__ import annotations

from epubforge.stages import style

from tests.test_shelf_refusals import rules_of
from tests.test_duplicate_selectors import build, sheet_of


class TestTheProvableCuts:
    def test_the_word_artifact_loses_its_dead_line(self, tmp_path):
        """The shelf's mass: `margin-bottom` twice with `margin-left`
        between. Both values are CSS1 lengths, so no reader anywhere could
        reject the later one — the earlier never won and goes."""
        sheet = (
            "p.jeden { margin-bottom: 0cm; margin-left: 0cm; "
            "margin-bottom: .0001pt; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("margin-bottom") == 1
        assert ".0001pt" in out and "0cm" in out  # margin-left's 0cm stays
        assert "css.duplicate-properties-removed" in rules_of(result)

    def test_identical_twins_keep_the_last_occurrence(self, tmp_path):
        """Same value twice — any parser picks some occurrence and both say
        the same thing. The last stays where the cascade already read it;
        the mutation that keeps the first fails on the position check."""
        sheet = "p.jeden { color: black; text-indent: 1em; color: black; }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("color") == 1
        assert out.index("text-indent") < out.index("color")
        assert "css.duplicate-properties-removed" in rules_of(result)

    def test_the_plain_twin_of_an_important_wins_nothing(self, tmp_path):
        """`line-height: 100% !important; line-height: 100%` — the shelf's
        eight. In-block the important one wins; against later rules only
        the important one holds. The plain twin does neither and goes; the
        mutation that keeps the last occurrence regardless drops the
        `!important` and fails here."""
        sheet = "p.jeden { line-height: 100% !important; line-height: 100%; }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("line-height") == 1
        assert "!important" in out
        assert "css.duplicate-properties-removed" in rules_of(result)

    def test_auto_is_a_css1_value_for_margin(self, tmp_path):
        sheet = "p.jeden { margin-left: 10px; margin-left: auto; }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("margin-left") == 1
        assert "margin-left: auto" in out


class TestFallbacksAreSomebodys:
    def test_a_value_a_reader_can_reject_keeps_its_fallback(self, tmp_path):
        """`display: block; display: flex` — an old reader rejects `flex`
        at validation and uses `block`. The earlier line is that reader's
        whole layout; it stays and is counted. The mutation that cuts
        without the CSS1 proof fails here."""
        sheet = "p.jeden { display: block; display: flex; }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "display: block" in out and "display: flex" in out
        assert "css.duplicate-properties-kept" in rules_of(result)
        assert "css.duplicate-properties-removed" not in rules_of(result)

    def test_a_function_value_keeps_its_fallback(self, tmp_path):
        sheet = "p.jeden { color: #000000; color: rgba(0, 0, 0, 0.8); }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "#000000" in out and "rgba" in out
        assert "css.duplicate-properties-removed" not in rules_of(result)

    def test_a_bare_number_is_not_a_css1_length(self, tmp_path):
        """CSS1 requires the unit, so a strict validator may reject
        `margin-bottom: 12` — and then the earlier line is live. The
        mutation that lets a unitless non-zero through the length pattern
        fails here."""
        sheet = "p.jeden { margin-bottom: 1em; margin-bottom: 12; }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "1em" in out and "margin-bottom: 12" in out
        assert "css.duplicate-properties-removed" not in rules_of(result)

    def test_mixed_importance_with_different_values_stays(self, tmp_path):
        """`text-indent: 2em !important; text-indent: 1em` — which one a
        reader uses depends on how much of importance it implements, and
        that is not a thing to bet a book's layout on."""
        sheet = "p.jeden { text-indent: 2em !important; text-indent: 1em; }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "2em" in out and "1em" in out
        assert "css.duplicate-properties-removed" not in rules_of(result)


class TestTheReachOfTheCut:
    def test_a_duplicate_inside_an_at_rule_is_cut_too(self, tmp_path):
        """Whatever condition turns a block on turns all of it on, so the
        in-block winner is the same under any `@media`. The walk goes to
        the leaves; the identical twin inside goes like any other."""
        sheet = (
            "p.jeden { margin: 0; } "
            "@media print { p.jeden { color: black; color: black; } }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("color") == 1
        assert "@media print" in out
        assert "css.duplicate-properties-removed" in rules_of(result)

    def test_strings_do_not_confuse_the_walk(self, tmp_path):
        """A brace and a semicolon inside a string are somebody's content,
        not structure — the twin is still recognised and still cut whole,
        and the surviving string is intact."""
        sheet = (
            "p.jeden { margin: 0; } "
            'p.jeden::before { content: "a;b{c}"; content: "a;b{c}"; }'
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count('content: "a;b{c}"') == 1
        assert "css.duplicate-properties-removed" in rules_of(result)

    def test_the_opt_out_counts_instead(self, tmp_path):
        sheet = (
            "p.jeden { margin-bottom: 0cm; margin-left: 0cm; "
            "margin-bottom: .0001pt; }"
        )
        result = build(tmp_path, sheet=sheet, sweep=False)
        out = sheet_of(result)
        assert out.count("margin-bottom") == 2
        assert "css.duplicate-properties-found" in rules_of(result)


class TestTheGuard:
    def test_a_failed_verification_hands_the_sheet_back(self, tmp_path, monkeypatch):
        """The structural check is the cheap half of the two-part guard; a
        cut whose product fails it never replaces the publisher's text.
        The mutation that returns the cut text anyway fails here."""
        monkeypatch.setattr(style, "_structurally_sound", lambda text: False)
        sheet = (
            "p.jeden { margin-bottom: 0cm; margin-left: 0cm; "
            "margin-bottom: .0001pt; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("margin-bottom") == 2
        assert "css.duplicate-properties-unverified" in rules_of(result)


class TestTheMixedImportanceQuestion:
    """D-037: mixed `!important` over different values is a real divergence
    between readers, and which version the book means is a person's call.
    Unanswered, nothing changes (S-05); answered, the modern cascade's
    winner stands alone and every reader computes the same thing."""

    def _build(self, tmp_path, sheet, option=None):
        from epubforge.decisions import Answer
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy
        from tests.test_shelf_refusals import make_book
        from tests.test_class_translation import PAGE

        class Chooser:
            def __init__(self, picked):
                self.picked = picked
                self.asked = []

            def ask(self, question):
                self.asked.append(question)
                return Answer(option=self.picked)

        source = make_book(
            tmp_path / "in.epub",
            {"c0.xhtml": PAGE.format(body='<p class="jeden">Akapit.</p>')},
            extra_items='<item id="s" href="s.css" media-type="text/css"/>',
            extra_files={"OEBPS/s.css": sheet.encode()},
        )
        chooser = Chooser(option) if option else None
        result = rebuild(
            source, str(tmp_path / "out.epub"),
            Policy.preset("preserve", render_gate="off"), resolver=chooser,
        )
        return result, chooser

    def test_nobody_answers_nothing_changes(self, tmp_path):
        sheet = "p.jeden { text-indent: 2em !important; text-indent: 1em; }"
        result, _ = self._build(tmp_path, sheet)
        out = sheet_of(result)
        assert "2em" in out and "1em" in out
        assert "css.duplicate-properties-resolved" not in rules_of(result)

    def test_an_answer_leaves_the_modern_winner_alone(self, tmp_path):
        """The shelf's own shape — a triple with mixed importance. The
        mutation that keeps the last plain occurrence instead of the last
        important one fails here."""
        sheet = (
            "p.jeden { line-height: 0.8; line-height: 100% !important; "
            "line-height: 100%; }"
        )
        result, chooser = self._build(tmp_path, sheet, option="resolve")
        out = sheet_of(result)
        assert out.count("line-height") == 1
        assert "line-height: 100% !important" in out
        assert "css.duplicate-properties-resolved" in rules_of(result)
        assert [q for q in chooser.asked if q.group == "style:important"]
