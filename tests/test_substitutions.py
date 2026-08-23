"""One letter standing for another, all through a book.

Filar D, in the shape the measurement gave it rather than the one the plan
assumed. The plan expected per-word corrections; 12 264 unknown words across 25
Polish books said otherwise — a third are capitalised names, a quarter are the
book's own vocabulary, a quarter are rare words with nothing near them, and
correcting any of those would be vandalising somebody's novel. What is left is
dominated by one shape: a single letter written in place of another, the same
letter every time.

So the tests below are about a **pattern**, not about words. The two that matter
most are the ones that refuse: an ordinary book must produce nothing, and a name
the book uses often must survive a pattern that would otherwise rewrite it. On
the shelf this was measured against, one book in a hundred and sixty has such a
pattern — a detector that found them everywhere would be inventing them.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import dictionaries, substitutions
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.decisions import Answer
from tests.test_shelf_refusals import make_book

has_polish = pytest.mark.skipif(
    not dictionaries.available("pl_PL"),
    reason="brak słownika pl_PL — pobierany przy budowaniu wydania",
)

#: Twelve words this book writes both ways: `h` where `r` belongs, and — five
#: times each, elsewhere — correctly. Both halves are what makes each one
#: evidence rather than a guess about somebody's spelling.
PAIRS = [
    ("phawda", "prawda"),
    ("dobhe", "dobre"),
    ("bahdzo", "bardzo"),
    ("wphost", "wprost"),
    ("phoszę", "proszę"),
    ("phaca", "praca"),
    ("zhobić", "zrobić"),
    ("thudno", "trudno"),
    ("tehaz", "teraz"),
    ("dhugi", "drugi"),
    ("hodzaj", "rodzaj"),
    ("khól", "król"),
]

#: One-letter slips that are *not* the pattern, each a different pair of
#: letters. Used only to dilute: a book arguing with itself has no pattern.
NOISE = [
    ("prawdq", "prawda"),
    ("dobrz", "dobre"),
    ("bardzu", "bardzo"),
    ("wprost", "wprost"),
]


def a_book_that_writes(pairs, *, correct_each: int = 5, extra: str = "") -> list:
    """The text of a book that writes each pair both ways."""
    said = []
    for wrong, right in pairs:
        said.append(" ".join([right] * correct_each))
        said.append(f"A tutaj {wrong} stoi w zdaniu.")
    return [" ".join(said) + " " + extra]


class TestThePatternIsFoundOnlyWhenItIsThere:
    @has_polish
    def test_a_book_that_writes_one_letter_for_another(self):
        pattern = substitutions.find(a_book_that_writes(PAIRS))
        assert pattern is not None
        assert (pattern.wrong, pattern.right) == ("h", "r")
        assert set(pattern.words) == {wrong for wrong, _ in PAIRS}

    @has_polish
    def test_an_ordinary_book_produces_nothing(self):
        """The answer for a hundred and fifty-nine books out of a hundred and
        sixty, and the one the detector must get right first."""
        plain = [" ".join(right for _, right in PAIRS) * 6]
        assert substitutions.find(plain) is None

    @has_polish
    def test_nine_words_are_not_a_pattern(self):
        """The threshold sits in a gap the shelf left empty: the affected book's
        pair is 90% of its candidates, the next most concentrated book 2%.
        Nine is below the line and must stay below it."""
        assert substitutions.find(a_book_that_writes(PAIRS[:9])) is None

    @has_polish
    def test_a_book_arguing_with_itself_has_no_pattern(self):
        """Ten of one pair and eleven scattered slips is not a book that makes
        one substitution — it is a book with typos, and correcting typos is not
        what this is for."""
        scattered = [
            (right[:index] + "q" + right[index + 1:], right)
            for _, right in PAIRS
            for index in (1, 2)
        ][:11]
        mixed = a_book_that_writes(PAIRS[:10] + scattered)
        found = substitutions.find(mixed)
        assert found is None, found

    def test_without_a_dictionary_nothing_is_claimed(self, monkeypatch):
        """Half the proof is the dictionary's. Without it the other half —
        this book writes the word another way — would call every rare spelling
        a defect, which is the failure mode the whole design avoids."""
        monkeypatch.setattr(dictionaries, "_load", lambda language: None)
        assert substitutions.find(a_book_that_writes(PAIRS)) is None


class TestWhatTheSpreadMayNotTouch:
    @has_polish
    def test_a_name_the_book_uses_often_survives(self):
        """The first draft of this offered to rename a character — a surname
        beginning with the wrong letter, where undoing the substitution happens
        to produce another dictionary word, so spelling alone cannot tell it
        from a repair. What can is that the book writes it seventeen times —
        measured — while every genuine repair on that book appears once, twice
        or three times."""
        book = a_book_that_writes(PAIRS, extra=" ".join(["Hejs"] * 6))
        pattern = substitutions.find(book)
        assert pattern is not None
        assert "Hejs" not in pattern.repairs
        assert "Hejs" not in pattern.words

    @has_polish
    def test_a_capitalised_word_at_the_start_of_a_sentence_is_repaired(self):
        """The other side of the same rule, and the reason it is a frequency
        test rather than a capital-letter test: `Bahdzo` opening a sentence is
        the same defect as `bahdzo` inside one."""
        book = a_book_that_writes(PAIRS, extra="Bahdzo dobre. Thudno powiedzieć.")
        pattern = substitutions.find(book)
        assert pattern.repairs.get("Bahdzo") == "Bardzo"
        assert pattern.repairs.get("Thudno") == "Trudno"

    @has_polish
    def test_a_word_the_dictionary_knows_is_never_touched(self):
        """`chuda` carries the wrong letter and is a Polish word. A pass that
        repaired it would be correcting the author."""
        book = a_book_that_writes(PAIRS, extra="chuda chata i hak na ścianie")
        pattern = substitutions.find(book)
        assert "chuda" not in pattern.repairs
        assert "hak" not in pattern.repairs

    @has_polish
    def test_the_spread_reaches_further_than_the_evidence(self):
        """The evidence is deliberately narrow; a book repaired only there
        would come out half mended."""
        book = a_book_that_writes(PAIRS, extra="Tehaz phawdziwa hozmowa.")
        pattern = substitutions.find(book)
        assert len(pattern.repairs) > pattern.count
        assert pattern.repairs["phawdziwa"] == "prawdziwa"


class TestRewritingWholeWords:
    def test_only_whole_words_change(self):
        assert substitutions.rewrite("aphawda", {"phawda": "prawda"}) == "aphawda"
        assert substitutions.rewrite("— phawda!", {"phawda": "prawda"}) == "— prawda!"

    def test_nothing_to_do_is_the_text_itself(self):
        assert substitutions.rewrite("cokolwiek", {}) == "cokolwiek"
        assert substitutions.rewrite("", {"a": "b"}) == ""

    def test_capitals_are_kept(self):
        assert substitutions._cases("Phawda", "prawda") == "Prawda"
        assert substitutions._cases("PHAWDA", "prawda") == "PRAWDA"
        assert substitutions._cases("phawda", "prawda") == "prawda"


class TestSayingWhatTheRepairDid:
    """`apart_from` is the repair's own statement about itself: normalise the
    agreed words away on both sides, and what is left has to be identical."""

    REPAIRS = {"phawda": "prawda", "bahdzo": "bardzo"}

    def test_only_the_agreed_words_changing_reads_as_no_change(self):
        before = ["To phawda,", " i to ", "bahdzo prosta."]
        after = ["To prawda,", " i to ", "bardzo prosta."]
        assert substitutions.apart_from(before, self.REPAIRS) == (
            substitutions.apart_from(after, self.REPAIRS)
        )

    def test_a_word_that_went_missing_shows(self):
        before = ["To phawda,", " i to ", "bahdzo prosta."]
        after = ["To prawda,", " i to ", "bardzo."]
        assert substitutions.apart_from(before, self.REPAIRS) != (
            substitutions.apart_from(after, self.REPAIRS)
        )

    def test_a_word_nobody_agreed_to_shows(self):
        before = ["Hejs phawda"]
        after = ["Rejs prawda"]
        assert substitutions.apart_from(before, self.REPAIRS) != (
            substitutions.apart_from(after, self.REPAIRS)
        )

    def test_the_pieces_are_not_joined_first(self):
        """A paragraph ending in a broken word and the next one starting with a
        capital: joined into one string they read as a token on nobody's list,
        and the check would refuse a repair that was exactly right."""
        pieces = ["To bahdzo", "Ważne zdanie"]
        assert substitutions.apart_from(pieces, self.REPAIRS) == "To bardzoWażne zdanie"


#: A page in Polish, with the book's own correct spellings and the broken ones.
PAGE = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title></head><body>{body}</body></html>"
)


def a_broken_book(tmp_path, name: str = "in.epub") -> str:
    text = a_book_that_writes(PAIRS)[0]
    return make_book(
        tmp_path / name,
        {
            "c0.xhtml": PAGE.format(body=f"<p>{text}</p>"),
            "c1.xhtml": PAGE.format(body="<p>Rozdział bez żadnej wady.</p>"),
        },
    )


class Answering:
    """Answers the substitution question one way and remembers being asked."""

    def __init__(self, option: str):
        self.option = option
        self.asked: list = []

    def ask(self, question):
        self.asked.append(question)
        if question.group == "encoding:substitution":
            return Answer(option=self.option, apply_to_group=True)
        return Answer(option=question.recommended or "keep")


def rebuild_with(tmp_path, resolver, **policy) -> object:
    return rebuild(
        a_broken_book(tmp_path),
        str(tmp_path / "out.epub"),
        Policy.preset(
            "preserve", render_gate="off", validate_before_publish="off", **policy
        ),
        resolver=resolver,
    )


def text_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        return " ".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        )


def rules_of(result) -> set:
    return {finding.rule for finding in result.report.findings}


class TestTheStageAsksOnceAndActsOnTheAnswer:
    @has_polish
    def test_one_question_for_the_whole_book(self, tmp_path):
        """A hundred and nineteen words carrying one fact is one question."""
        answering = Answering("keep")
        rebuild_with(tmp_path, answering)
        ours = [q for q in answering.asked if q.group == "encoding:substitution"]
        assert len(ours) == 1
        assert "h" in ours[0].summary and "r" in ours[0].summary

    @has_polish
    def test_the_pattern_is_reported_whether_or_not_it_is_repaired(self, tmp_path):
        result = rebuild_with(tmp_path, Answering("keep"))
        assert "substitutions.pattern-found" in rules_of(result)
        assert "substitutions.left-alone" in rules_of(result)

    @has_polish
    def test_keeping_it_changes_not_one_letter(self, tmp_path):
        result = rebuild_with(tmp_path, Answering("keep"))
        text = text_of(result)
        assert "phawda" in text and "prawda" in text
        assert "substitutions.replaced" not in rules_of(result)

    @has_polish
    def test_repairing_it_puts_the_letter_back(self, tmp_path):
        result = rebuild_with(tmp_path, Answering("repair"))
        text = text_of(result)
        for wrong, right in PAIRS:
            assert wrong not in text, wrong
            assert right in text, right
        assert "substitutions.replaced" in rules_of(result)

    @has_polish
    def test_nobody_answering_leaves_the_book_alone(self, tmp_path):
        """S-05, and it is the default everywhere else in this program: with no
        resolver at all the text comes out as the publisher wrote it."""
        result = rebuild_with(tmp_path, None)
        assert "phawda" in text_of(result)
        assert "substitutions.replaced" not in rules_of(result)


class TestWhenTheStageMustNotEvenAsk:
    @has_polish
    def test_the_container_only_mode_asks_nothing(self, tmp_path):
        """That mode promises the content files come out byte for byte, and a
        promise cannot survive a question whose answer would edit them."""
        answering = Answering("repair")
        rebuild_with(tmp_path, answering, rewrite_content=False)
        assert not [q for q in answering.asked if q.group == "encoding:substitution"]

    @has_polish
    def test_switching_the_detector_off_asks_nothing(self, tmp_path):
        answering = Answering("repair")
        rebuild_with(tmp_path, answering, detect_substitutions=False)
        assert not [q for q in answering.asked if q.group == "encoding:substitution"]


class TestTheDocumentGoesBackIfMoreChangedThanAgreed:
    @has_polish
    def test_a_pass_that_does_anything_else_is_undone(self, tmp_path, monkeypatch):
        """The postcondition, tested by breaking the edit and leaving the proof
        honest — which is the situation it exists for. The edit here also drops
        a word nobody agreed about; the document must come out exactly as it
        went in, broken spellings and all."""
        from epubforge.stages import substitutions as stage

        honest = substitutions.rewrite

        def greedy(text: str, repairs: dict) -> str:
            written = honest(text, repairs)
            return written.replace("zdaniu", "") if repairs else written

        monkeypatch.setattr(stage.substitutions, "rewrite", greedy)
        monkeypatch.setattr(
            stage.substitutions,
            "apart_from",
            lambda pieces, repairs: "".join(honest(piece, repairs) for piece in pieces),
        )
        result = rebuild_with(tmp_path, Answering("repair"))
        assert "substitutions.reverted" in rules_of(result)
        assert "phawda" in text_of(result), "the document did not go back"


class TestTheGateAccountsForIt:
    def test_the_rule_is_named_where_the_subsequence_half_looks(self):
        """K1's first half asks for a subsequence: nothing lost. Putting a
        letter back takes the wrong one out, so the rule has to be named — and
        named in *this* set, because the other half reads the union of both and
        this half reads only this one."""
        from epubforge import pipeline

        assert "substitutions.replaced" in pipeline.REMOVES_TEXT_ON_PURPOSE
        assert (
            "substitutions.replaced"
            in pipeline.REMOVES_TEXT_ON_PURPOSE | pipeline.CHANGES_TEXT_SHAPE_ON_PURPOSE
        )

    @has_polish
    def test_a_repaired_book_is_written_and_says_the_text_changed(self, tmp_path):
        """The whole point of naming it: the book comes out, and the report says
        the invariant no longer holds character for character and why."""
        result = rebuild_with(tmp_path, Answering("repair"))
        assert result.output_path
        assert "package.text-lost" not in rules_of(result)
        assert "package.text-changed-on-request" in rules_of(result)
