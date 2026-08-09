"""The safety apparatus for roadmap [7], tested before anything uses it.

Typography is the only stage that changes text on purpose, so it is the only
stage K1 cannot police as written. These tests are about the replacement: a
folding that still catches a lost word, and one iterator that decides where a
rule may reach.
"""

from __future__ import annotations

import pytest
from lxml import etree

from epubforge import typography
from epubforge.cascade import Cascade

XHTML = "http://www.w3.org/1999/xhtml"


def parse(markup: str):
    return etree.fromstring(markup.encode("utf-8"))


def editable(root, **kwargs) -> str:
    return "|".join(
        (getattr(element, attribute) or "").strip()
        for element, attribute in typography.text_nodes(root, **kwargs)
        if (getattr(element, attribute) or "").strip()
    )


class TestWhereARuleMayReach:
    """One iterator, not a condition inside every rule. "Did you remember to
    skip <code>" is a question that gets the right answer nine times."""

    def test_ordinary_prose_is_editable(self):
        root = parse(f'<div xmlns="{XHTML}"><p>Zwykły akapit.</p></div>')
        assert editable(root) == "Zwykły akapit."

    @pytest.mark.parametrize("tag", ["pre", "code", "kbd", "samp", "script", "style", "ruby"])
    def test_protected_elements_are_skipped(self, tag):
        root = parse(f'<div xmlns="{XHTML}"><{tag}>nietykalne</{tag}></div>')
        assert editable(root) == ""

    def test_everything_inside_a_protected_element_is_skipped_too(self):
        """A <span> inside <code> is protected, and the span itself says
        nothing about that — only its ancestry does."""
        root = parse(f'<div xmlns="{XHTML}"><code>a<span>b</span>c</code></div>')
        assert editable(root) == ""

    def test_the_text_after_a_protected_element_is_still_prose(self):
        """A tail belongs to the parent's flow. Skipping it would leave a
        sentence half retyped, which is worse than not touching it."""
        root = parse(f'<div xmlns="{XHTML}"><p>przed <code>x</code> po</p></div>')
        assert editable(root) == "przed|po"

    def test_mathml_and_svg_are_left_alone(self):
        root = parse(
            f'<div xmlns="{XHTML}">'
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>'
            '<svg xmlns="http://www.w3.org/2000/svg"><text>etykieta</text></svg>'
            "</div>"
        )
        assert editable(root) == ""

    def test_another_language_is_left_alone(self):
        """Quoting conventions belong to a language. Applying Polish rules to a
        French epigraph is not a repair."""
        root = parse(
            f'<div xmlns="{XHTML}"><p>polski</p>'
            '<p xml:lang="fr">une citation</p></div>'
        )
        assert editable(root, language="pl") == "polski"

    def test_the_same_language_in_another_region_is_not_foreign(self):
        root = parse(f'<div xmlns="{XHTML}"><p xml:lang="pl-PL">polski</p></div>')
        assert editable(root, language="pl") == "polski"

    def test_without_a_declared_language_nothing_is_foreign(self):
        root = parse(f'<div xmlns="{XHTML}"><p xml:lang="fr">une citation</p></div>')
        assert editable(root) == "une citation"

    def test_preserved_whitespace_is_left_alone(self):
        """A publisher who sets white-space: pre has said "print this exactly",
        and collapsing two spaces there is not a repair."""
        root = parse(f'<div xmlns="{XHTML}"><p class="wiersz">a  b</p></div>')
        cascade = Cascade.parse([".wiersz { white-space: pre-wrap; }"])
        assert editable(root, cascade=cascade) == ""
        assert editable(root) == "a  b"

    def test_an_inline_style_preserves_it_too(self):
        root = parse(
            f'<div xmlns="{XHTML}"><p style="white-space: pre">a  b</p></div>'
        )
        assert editable(root, cascade=Cascade.parse([])) == ""

    def test_comments_are_not_text(self):
        root = parse(f'<div xmlns="{XHTML}"><!-- uwaga --><p>tekst</p></div>')
        assert editable(root) == "tekst"


class TestTheFoldingStillCatchesLostText:
    """The whole argument for folding rather than switching K1 off."""

    def test_a_quote_may_change_shape(self):
        assert typography.unchanged('"tak"', "„tak”")

    def test_a_dash_may_change_shape(self):
        assert typography.unchanged("a - b", "a — b")

    def test_three_dots_may_become_an_ellipsis(self):
        assert typography.unchanged("czekaj...", "czekaj…")

    def test_a_hard_space_may_appear(self):
        assert typography.unchanged("w lesie", "w lesie")

    def test_a_lost_word_is_still_caught(self):
        assert not typography.unchanged("szedł przez las", "szedł las")

    def test_a_swallowed_letter_is_still_caught(self):
        assert not typography.unchanged("szedł", "szed")

    def test_two_words_run_together_are_still_caught(self):
        """The failure mode of every hyphenation repair ever written:
        `biało-czerwony` glued into `białoczerwony`."""
        assert not typography.unchanged("biało-czerwony", "białoczerwony")

    def test_reordered_text_is_still_caught(self):
        assert not typography.unchanged("a potem b", "b potem a")

    def test_the_strict_form_allows_nothing_but_whitespace_and_nfc(self):
        assert typography.unchanged("czekaj  tu", "czekaj tu", relaxed=False)
        assert not typography.unchanged("czekaj...", "czekaj…", relaxed=False)

    def test_decomposed_and_composed_polish_are_the_same_text(self):
        """`ó` written as one character and as `o` plus a combining acute are
        the same word, and a book can contain both."""
        composed = "\u00f3"          # ó
        decomposed = "o\u0301"       # o + combining acute
        assert composed != decomposed
        assert typography.unchanged(f"m{composed}j", f"m{decomposed}j", relaxed=False)

    def test_invisible_characters_fold_away(self):
        assert typography.unchanged("sło­wo", "słowo")
        assert typography.unchanged("sło​wo", "słowo")


class TestWhatTheBookAlreadyDoes:
    """K5: a book that consistently uses «…» has made a decision. The job is to
    repair inconsistency, not taste."""

    def test_a_clear_convention_is_named(self):
        assert typography.dominant({"pl-open": 400, "straight": 3}) == "pl-open"

    def test_an_argument_with_itself_is_left_alone(self):
        """At 51% a book is not consistent, and picking the winner would
        impose an opinion on nearly half the text."""
        assert typography.dominant({"pl-open": 260, "guillemet-open": 240}) is None

    def test_too_little_evidence_is_not_a_convention(self):
        assert typography.dominant({"straight": 4}) is None

    def test_nothing_at_all_is_not_a_convention(self):
        assert typography.dominant({}) is None

    def test_the_threshold_is_two_thirds_not_a_majority(self):
        assert typography.dominant({"a": 67, "b": 33}) == "a"
        assert typography.dominant({"a": 60, "b": 40}) is None


class TestQuotesAreShapesAndConventionsArePairs:
    """The inventory named quote marks by nationality and its table had seven
    entries and six keys: `”` was written twice, as `pl-close` and as
    `en-close`, and the second won. `pl-close` was a label nothing could
    produce, and every Polish closing quote counted as English — so a book set
    in ordinary Polish `„…”` measured as *mixing two conventions*. Roadmap [7]
    was about to set its thresholds from that number.
    """

    def test_no_mark_is_declared_twice(self):
        """The defect itself, in the form that would have caught it: a dict
        literal with a repeated key loses one silently."""
        assert len(typography.QUOTE_MARKS) == len(set(typography.QUOTE_MARKS))
        assert len(set(typography.QUOTE_MARKS.values())) == len(typography.QUOTE_MARKS)

    def test_every_convention_names_marks_that_exist(self):
        shapes = set(typography.QUOTE_MARKS.values())
        for name, pair in typography.CONVENTIONS.items():
            assert set(pair) <= shapes, name

    def test_polish_quotes_read_as_one_convention_not_two(self):
        assert typography.convention({"low-double": 400, "right-double": 400}) == "polish"

    def test_german_and_polish_share_an_opening_mark_and_are_told_apart(self):
        assert typography.convention({"low-double": 400, "left-double": 400}) == "german"

    def test_english_is_not_undecided(self):
        """`“` is the English opening mark and the German closing one. Sorted
        into an "openings" bucket and a "closings" bucket it beats itself, and
        an ordinary English book came out as undecided."""
        assert typography.convention({"left-double": 400, "right-double": 400}) == "english"

    def test_guillemets_are_french(self):
        assert typography.convention({"guillemet-left": 50, "guillemet-right": 50}) == "french"

    def test_a_book_using_two_conventions_equally_gets_no_answer(self):
        counts = {"low-double": 200, "right-double": 200,
                  "guillemet-left": 200, "guillemet-right": 200}
        assert typography.convention(counts) is None

    def test_too_few_quotes_is_not_a_convention(self):
        assert typography.convention({"low-double": 5, "right-double": 5}) is None


class TestADeclaredLanguageIsNotAFact:
    """K11. A real library: 2 200 books, 2 187 declaring `en`, and 1 815 of
    those carrying `„` — a mark English typesetting does not use at all."""

    def test_polish_prose_scores_far_above_the_floor(self):
        assert typography.polish_share("Zażółć gęślą jaźń") > typography.POLISH_FLOOR

    def test_english_prose_scores_zero(self):
        assert typography.polish_share("The quick brown fox jumps over") == 0

    def test_an_english_book_naming_one_pole_is_not_polish(self):
        """The gap is two orders of magnitude, so the floor does not have to be
        delicate — but it does have to survive a surname."""
        text = "He met Wałęsa in Gdańsk. " + "Ordinary English prose. " * 40
        assert typography.polish_share(text) < typography.POLISH_FLOOR

    def test_empty_text_is_not_a_claim(self):
        assert typography.polish_share("") == 0
