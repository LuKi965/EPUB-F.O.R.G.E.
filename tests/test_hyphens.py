"""BA-2026-001: hyphens a conversion left inside words.

The audit's three synthetic examples — `obo-jętna`, `doboro-wym`, `po-klepała` —
produced no candidates and no decisions, because the typography stage only knew
about ellipses, conjunctions and quotes.

The difficulty is not finding hyphens. It is that Polish is full of hyphens that
are the author's, and a rule that joined hyphenated words would destroy every one
of them silently. So the detector answers one question — *what evidence is there
that this hyphen is not the author's* — and inside a single file only one strong
kind exists: the same book spells the word without it.

Measured across the owner's thirty-two books while this was written: 67 confirmed
candidates, 101 "likely" and 88 "uncertain". Reading the last two lists, almost
every entry is a real word. That measurement is why only confirmed candidates
become questions, and it is pinned as a test at the bottom of this file.
"""

from __future__ import annotations

import pytest

from epubforge import hyphens
from epubforge.decisions import KEEP, Answer, Queue
from epubforge.hyphens import CONFIRMED, LIKELY, UNCERTAIN, find, vocabulary


def candidates(*sentences, where="r.xhtml"):
    words = vocabulary(sentences)
    found = []
    for text in sentences:
        found.extend(find(text, where=where, words=words))
    return found


def by_word(*sentences) -> dict:
    return {candidate.word: candidate for candidate in candidates(*sentences)}


class TestTheThreeExamplesTheAuditGave:
    """`obo-jętna`, `doboro-wym`, `po-klepała` — none of them detected before."""

    @pytest.mark.parametrize(
        "broken, whole",
        [
            ("obo-jętna", "obojętna"),
            ("doboro-wym", "doborowym"),
            ("po-klepała", "poklepała"),
        ],
    )
    def test_it_is_found_when_the_book_spells_it_out(self, broken, whole):
        found = by_word(f"Była {broken} wobec wszystkiego.", f"{whole} i jeszcze raz {whole}.")
        assert broken in found
        assert found[broken].confidence == CONFIRMED
        assert found[broken].joined == whole

    def test_the_reason_is_a_fact_somebody_can_check(self):
        """Not a score. "0.82" says nothing anybody can go and verify; "this
        book writes it without a hyphen fourteen times" does."""
        found = by_word("Była obo-jętna.", "obojętna, obojętna, obojętna")
        assert "3" in found["obo-jętna"].reason


class TestWordsThisMustNeverTouch:
    """Every one of these is a shape of real Polish that a naive rule eats."""

    @pytest.mark.parametrize(
        "word",
        [
            "1939-1945",          # a range
            "Bielsko-Biała",      # a proper name
            "SMS-a",              # an abbreviation with an ending
            "e-mail",             # a one-letter particle
            "dum-dum",            # a reduplication
            "biało-czerwona",     # the linking vowel
            "polsko-niemiecki",
            "słodko-gorzki",
            "czarno-biały",
            "pseudo-naukowy",     # a bound particle
            "eks-mąż",
        ],
    )
    def test_it_is_not_even_a_candidate(self, word):
        assert not candidates(f"Zdanie zawierające {word} i nic więcej.")

    def test_a_repeated_hyphenation_is_this_book_s_spelling(self):
        """Four occurrences of the same hyphenation is a spelling. A line break
        does not fall in the same place four times."""
        text = "wolno-stojący " * 5
        assert not candidates(text)


class TestTheBookOutranksTheHeuristic:
    """The ordering that took two attempts to get right.

    The first version checked the linking vowel *before* weighing evidence and
    therefore found neither `obo-jętna` nor `doboro-wym` — both end in `-o`. A
    structural fact settles the matter; a tendency does not.
    """

    def test_evidence_beats_the_linking_vowel(self):
        found = by_word("Była obo-jętna.", "obojętna i znowu obojętna")
        assert found["obo-jętna"].confidence == CONFIRMED

    def test_evidence_beats_a_bound_particle(self):
        """`pół-` is a particle and `Pół-nocy` in a book that writes `Północy`
        twenty-two times is a broken line. Measured on the owner's shelf."""
        found = by_word("O Pół-nocy wyszedł.", "Północy, Północy, o Północy")
        assert "Pół-nocy" in found

    def test_no_evidence_leaves_the_compound_alone(self):
        assert not candidates("Flaga biało-czerwona wisiała nad wejściem.")

    def test_one_occurrence_is_not_enough_for_a_compound_shape(self):
        """Measured: `czerwonawo-złote` against a single `czerwonawozłote`, and
        `złocisto-brązowe` against a single `złocistobrązowe`. Both are compounds
        a writer may set either way, and both were being called confirmed on a
        count of one."""
        found = by_word("Miała czerwonawo-złote włosy.", "czerwonawozłote światło")
        assert "czerwonawo-złote" not in found

    def test_two_occurrences_are(self):
        found = by_word(
            "Miała czerwonawo-złote włosy.",
            "czerwonawozłote światło i czerwonawozłote liście",
        )
        assert found["czerwonawo-złote"].confidence == CONFIRMED

    def test_a_shape_that_is_not_a_compound_needs_only_one(self):
        """`trzyna-ście` is not a compound by any reading, so a single
        `trzynaście` settles it. Measured on the owner's shelf."""
        found = by_word("Miał trzyna-ście lat.", "trzynaście lat minęło")
        assert found["trzyna-ście"].confidence == CONFIRMED


class TestTheFoldingIsUsedForCountingAndNeverForWriting:
    def test_case_does_not_hide_the_evidence(self):
        found = by_word("była obo-jętna", "Obojętna mina. Obojętna twarz.")
        assert found["obo-jętna"].confidence == CONFIRMED

    def test_the_replacement_keeps_the_original_case(self):
        found = by_word("Po-klepała go.", "poklepała raz, poklepała drugi")
        assert found["Po-klepała"].joined == "Poklepała"

    def test_the_particle_list_is_folded_and_therefore_matches(self):
        """It held `pol` and was looked up with `poł`, so `pół-` never fired.
        A list written in the unfolded spelling matches nothing and says
        nothing about it."""
        assert hyphens._fold("pół") in hyphens._BOUND_PARTICLES


class TestWhatAPersonIsShown:
    def test_the_surrounding_words_come_with_it(self):
        found = by_word(
            "Stała przy oknie zupełnie obo-jętna na wszystko dookoła.",
            "obojętna, obojętna",
        )
        assert "oknie" in found["obo-jętna"].context

    def test_a_question_offers_keep_join_and_write_your_own(self):
        found = by_word("Była obo-jętna.", "obojętna, obojętna")
        question = hyphens.question_for(found["obo-jętna"])
        assert {option.id for option in question.options} == {KEEP, "join", "write"}

    def test_only_a_confirmed_candidate_is_recommended_for_joining(self):
        confirmed = by_word("Była obo-jętna.", "obojętna, obojętna")["obo-jętna"]
        assert hyphens.question_for(confirmed).recommended == "join"

    def test_the_question_says_it_cannot_be_undone(self):
        confirmed = by_word("Była obo-jętna.", "obojętna, obojętna")["obo-jętna"]
        question = hyphens.question_for(confirmed)
        assert not question.reversible
        assert question.risk.value == "content"

    def test_the_same_word_in_two_places_is_two_questions(self):
        """Two hyphens in two chapters are two decisions, and answering one is
        not answering the other — the group is how "all of them" is said."""
        words = vocabulary(["obo-jętna obojętna obojętna"])
        one = find("Była obo-jętna.", where="a.xhtml", words=words)[0]
        two = find("Była obo-jętna.", where="b.xhtml", words=words)[0]
        assert hyphens.question_for(one).id != hyphens.question_for(two).id
        assert hyphens.question_for(one).group == hyphens.question_for(two).group


class TestNothingHappensWithoutAnAnswer:
    def test_a_recommendation_is_not_an_action(self):
        confirmed = by_word("Była obo-jętna.", "obojętna, obojętna")["obo-jętna"]
        question = hyphens.question_for(confirmed)
        assert Queue().ask(question).option == KEEP

    def test_an_answer_of_join_says_so(self):
        class Person:
            def ask(self, _question):
                return Answer(option="join")

        confirmed = by_word("Była obo-jętna.", "obojętna, obojętna")["obo-jętna"]
        assert Queue(asker=Person()).ask(hyphens.question_for(confirmed)).option == "join"


class TestTheConfidenceBucketsAreHonest:
    """`LIKELY` and `UNCERTAIN` exist to be counted and not to be asked about.

    Measured across the owner's thirty-two books: 67 confirmed, 101 likely, 88
    uncertain — and reading the last two lists, `marksizm-leninizm`,
    `savoir-vivre`, `ping-pong`, `Karol-wybawca`, `hrabią-kasiarzem`. A queue of
    a hundred and eighty-nine questions that are mostly not defects is a queue
    nobody finishes, which is exactly the over-eager heuristic the finding warns
    about.
    """

    def test_a_word_with_no_evidence_either_way_is_not_confirmed(self):
        found = by_word("Znał savoir-vivre doskonale.")
        assert found["savoir-vivre"].confidence in (LIKELY, UNCERTAIN)

    @pytest.mark.parametrize("word", ["marksizm-leninizm", "jazz-band", "granat-pułapka"])
    def test_the_real_ones_from_the_shelf_are_never_confirmed(self, word):
        found = by_word(f"Zdanie o {word} i tyle.")
        assert all(c.confidence != CONFIRMED for c in found.values()), word
