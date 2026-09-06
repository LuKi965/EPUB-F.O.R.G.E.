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


class TestAWordWithAHyphenOfItsOwnBrokenASecondTime:
    """DROGA 6.4. `fellow-creature` is the writer's; a converter that wraps
    lines broke it again into `fel-low-creature`, and a detector that saw
    only `(\\w+)-(\\w+)` between non-word characters could not see the run at
    all — neither hyphen was a candidate, and the word stayed broken in every
    book measured on 2026-09-06 that had one.

    A run yields one candidate per hyphen. Each is judged by the two parts
    beside it, exactly as a plain candidate's halves are, and joins that
    hyphen alone: the candidate's `word` is the whole run and its `joined`
    is the run with one hyphen fewer.
    """

    def test_the_book_s_own_spelling_confirms_the_converter_s_hyphen(self):
        found = candidates(
            "He was a fel-low-creature after all.",
            "A fellow-creature, and a fellow-creature again.",
        )
        confirmed = [c for c in found if c.confidence == CONFIRMED]
        assert len(confirmed) == 1, [(c.word, c.left, c.right, c.confidence) for c in found]
        assert confirmed[0].word == "fel-low-creature"
        assert confirmed[0].joined == "fellow-creature"
        assert "fellow-creature" in confirmed[0].reason

    def test_the_break_may_sit_at_the_second_hyphen(self):
        found = candidates(
            "The bedroom-win-dow was open.",
            "The bedroom-window faced the yard; the bedroom-window was old.",
        )
        confirmed = [c for c in found if c.confidence == CONFIRMED]
        assert [(c.word, c.joined) for c in confirmed] == [("bedroom-win-dow", "bedroom-window")]

    def test_the_book_s_own_opposite_damage_is_not_evidence(self):
        """Measured on the owner's shelf: `face-toface` four times in a book
        that writes `face-to-face` — a converter dropped the writer's hyphen
        at a line end. That is not the book spelling the run's join; it is
        the same damage the other way round. The joined form has to
        outnumber the hyphenated run."""
        found = candidates(
            "They met face-to-face at last, face-to-face and face-to-face.",
            "Once more we meet face-toface, the man said.",
        )
        assert all(c.confidence != CONFIRMED for c in found), [(c.joined, c.confidence) for c in found]

    def test_a_run_with_a_one_letter_piece_is_nobody_s_candidate(self):
        """`O-li-ver!` shouted syllable by syllable, `s-s-spo-tkamy` stammered:
        somebody spelling a word out, and the dictionary knowing `liver` does
        not make the second hyphen a converter's."""
        found = candidates("„O-li-ver!” he cried; s-s-spo-tkamy się.", "Oliver came; spotkamy się.")
        assert not [c for c in found if c.word in ("O-li-ver", "s-s-spo-tkamy")], [c.word for c in found]

    def test_the_writer_s_hyphen_in_the_same_run_is_not_confirmed(self):
        """The other hyphen of `fel-low-creature` is the writer's, and nothing
        in the book says otherwise: it may be counted, never recommended."""
        found = candidates(
            "He was a fel-low-creature after all.",
            "A fellow-creature, and a fellow-creature again.",
        )
        others = [c for c in found if c.joined != "fellow-creature"]
        assert all(c.confidence != CONFIRMED for c in others), [(c.joined, c.confidence) for c in others]

    def test_a_run_is_not_a_plain_candidate_as_well(self):
        """`_CANDIDATE` must not also match the tail of a run — `low-creature`
        inside `fel-low-creature` — because a join of that would write into
        the middle of a longer word, which is the EF-088 shape exactly."""
        found = candidates("He was a fel-low-creature after all.", "fellow-creature twice: fellow-creature.")
        assert not {c.word for c in found} & {"low-creature", "fel-low"}, [c.word for c in found]

    @pytest.mark.parametrize("run", ["1939-1945-1950", "pkt-1-a", "A-b-c"])
    def test_the_structural_guards_hold_for_every_hyphen_of_a_run(self, run):
        """A digit anywhere in the run, a single letter beside the hyphen: the
        same shapes that keep a plain candidate out keep every hyphen of a run
        out, whatever the book writes elsewhere."""
        found = candidates(f"Zapis {run} i tyle.", f"{run.replace('-', '', 1)} raz.")
        assert not [c for c in found if c.word == run], [(c.word, c.confidence) for c in found]

    def test_the_writer_s_abbreviation_stays_when_the_converter_s_hyphen_goes(self):
        """`ul-tra-HD`: the join removes the converter's hyphen and nothing
        else, so `ultra-HD` keeps the hyphen before the abbreviation — the
        guard on capitals is asked of the parts beside *this* hyphen."""
        found = candidates("Film w ul-tra-HD.", "Nagranie ultra-HD i ultra-HD.")
        confirmed = [c for c in found if c.confidence == CONFIRMED]
        assert [(c.word, c.joined) for c in confirmed] == [("ul-tra-HD", "ultra-HD")]

    def test_two_breaks_in_one_run_are_two_candidates_with_the_same_word(self):
        """`to-mor-row`: both hyphens are the converter's. Each is its own
        candidate on the same `word`, judged by its own neighbours; the stage
        joins one per pass (a run is changed at most once by one answer)
        and meets the other next time."""
        found = candidates("See you to-mor-row.", "tomorrow and tomorrow and tomorrow.")
        for candidate in found:
            assert candidate.word == "to-mor-row"
        assert {c.joined for c in found} == {"tomor-row", "to-morrow"}

    def test_the_run_written_whole_elsewhere_is_not_evidence_for_any_one_hyphen(self):
        """`O-li-ver` on the public corpus: a name shouted syllable by
        syllable, in a book that writes `Oliver` 260 times. The same shape
        as a word broken twice, and the book cannot tell them apart — so
        the whole is not evidence, and nothing here is confirmed."""
        found = candidates("See you to-mor-row.", "Tomorrow, tomorrow, tomorrow and tomorrow.")
        assert found, "the run is still a candidate, only not a confirmed one"
        assert all(c.confidence != CONFIRMED for c in found), [(c.joined, c.confidence) for c in found]


@pytest.mark.skipif(
    not hyphens.dictionaries.available("en_US"),
    reason="ten test mierzy, co słownik dokłada — bez słownika nie ma czego mierzyć",
)
class TestTheTypesetterSLineEndIsEvidenceOfItsOwn:
    """From a PDF the reader knows which hyphens stood at a line end. With the
    joined form in the dictionary that settles the hyphen (D-052). Without it
    — a spelling before the reform, a name, a word the list lacks — the
    acceptance measurement of 2026-09-06 lost thirty-eight of ninety-nine
    words to silence. Now the break is `LIKELY` with a reason that names the
    line end, so the class is put to a person once and not dropped.
    """

    def test_a_line_end_break_the_dictionary_knows_is_confirmed(self):
        found = find(
            "The win-dow was open.", where="r.xhtml", words=vocabulary(["The win-dow was open."]),
            language="en_US", line_end={"win-dow"},
        )
        assert [c.confidence for c in found] == [CONFIRMED]
        assert "końcu wiersza" in found[0].reason

    def test_a_line_end_break_the_dictionary_does_not_know_is_likely_not_silent(self):
        text = "Old xylo-brandt stood there."
        found = find(
            text, where="r.xhtml", words=vocabulary([text]), language="en_US",
            line_end={"xylo-brandt"},
        )
        assert [c.confidence for c in found] == [LIKELY], [(c.word, c.confidence, c.reason) for c in found]
        assert "końcu wiersza" in found[0].reason
        assert "słownik nie zna" in found[0].reason

    def test_the_same_word_away_from_a_line_end_is_judged_as_before(self):
        text = "Old xylo-brandt stood there."
        found = find(text, where="r.xhtml", words=vocabulary([text]), language="en_US")
        assert not any("końcu wiersza" in c.reason for c in found)

    def test_a_run_broken_at_its_second_hyphen_matches_what_the_reader_recorded(self):
        """The reader records the last token before the break with the first
        word after it: `bedroom-win-` + `dow` → `bedroom-win-dow`. That is the
        run up to the break, and it is one of the two shapes looked up."""
        text = "The bedroom-win-dow was open."
        found = find(
            text, where="r.xhtml", words=vocabulary([text]), language="en_US",
            line_end={"bedroom-win-dow"},
        )
        confirmed = [c for c in found if c.confidence == CONFIRMED]
        assert [(c.word, c.joined) for c in confirmed] == [("bedroom-win-dow", "bedroom-window")]
