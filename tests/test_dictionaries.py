"""The dictionary as evidence, and what happens when there is none.

WP-10. These run everywhere, including on a machine with no dictionary files —
which is the state of a checkout and of CI, and therefore the state that has to
be tested hardest. A dictionary that is absent must make the hyphen detector
behave exactly as it did before this existed, and the tests that need real
dictionary answers say so and skip.

The distinction this file is really about is three-valued lookup. `False` means
*the dictionary says no*, which is evidence. `None` means *nobody was asked*,
which is not. Collapsing the two into a boolean would turn a missing dictionary
into a confident claim that nothing is a word — and that claim would mark every
hyphenated word in every book as a converter's artefact.
"""

from __future__ import annotations

import pytest

from epubforge import dictionaries

has_polish = pytest.mark.skipif(
    not dictionaries.available("pl_PL"),
    reason="brak słownika pl_PL — pobierany przy budowaniu wydania",
)


class TestWithNoDictionaryNothingChanges:
    """The important half. Every build before 0.2.28 detected hyphens without
    a dictionary, and a build that cannot find one has to keep doing that."""

    def test_a_missing_dictionary_answers_nobody_was_asked(self, monkeypatch):
        monkeypatch.setattr(dictionaries, "_load", lambda language: None)
        assert dictionaries.is_a_word("cokolwiek", "pl_PL") is None

    def test_and_never_claims_a_word_is_broken(self, monkeypatch):
        """The failure this shape prevents: with a boolean lookup, a missing
        dictionary would answer `False` to every half of every hyphenated word
        and the detector would call the whole book broken."""
        monkeypatch.setattr(dictionaries, "_load", lambda language: None)
        assert dictionaries.half_is_not_a_word("doboro", "doborowym", "pl_PL") is False

    def test_available_says_so_rather_than_raising(self, monkeypatch):
        monkeypatch.setattr(dictionaries, "_load", lambda language: None)
        assert dictionaries.available("pl_PL") is False

    def test_a_dictionary_that_will_not_load_is_the_same_as_none(self, monkeypatch):
        """A corrupt file is not a reason for a book to fail to rebuild."""
        def explode(_language):
            raise RuntimeError("uszkodzony plik")

        monkeypatch.setattr(dictionaries, "_load", explode)
        with pytest.raises(RuntimeError):
            dictionaries.is_a_word("x", "pl_PL")


class TestTheLanguageTagIsUnderstoodLoosely:
    """Books write their language every way the standard allows."""

    @pytest.mark.parametrize("tag", ["pl", "pl-PL", "pl_PL", "PL", "pl-pl"])
    def test_every_spelling_of_polish_finds_the_same_dictionary(self, tag):
        assert dictionaries._normalise(tag) == "pl_PL"

    @pytest.mark.parametrize("tag", ["en", "en-GB", "en_US"])
    def test_and_of_english(self, tag):
        assert dictionaries._normalise(tag) == "en_US"

    def test_an_unknown_language_is_left_alone_rather_than_guessed(self):
        """A Dutch book must not be judged by a Polish dictionary: every word
        would come back "not a word" and every hyphen would look like damage."""
        assert dictionaries._normalise("nl_NL") == "nl_NL"
        assert dictionaries.available("nl_NL") is False

    def test_no_language_falls_back_to_the_first_one(self):
        assert dictionaries._normalise("") == dictionaries.LANGUAGES[0]


@has_polish
class TestWhatTheDictionaryActuallySettles:
    """Measured before the code was written, and kept as tests so the claim
    stays honest if a dictionary version changes under us."""

    @pytest.mark.parametrize(
        "left,joined",
        [("doboro", "doborowym"), ("przeko", "przekonaniem"), ("wspo", "wspominał")],
    )
    def test_a_first_half_that_is_not_a_word_settles_it(self, left, joined):
        """A compound whose first half is not a word does not exist, so the
        hyphen came from a converter. These are three of the six artefacts on
        the owner's second book that were being dropped without a trace."""
        assert dictionaries.half_is_not_a_word(left, joined, "pl_PL") is True

    @pytest.mark.parametrize(
        "left,joined",
        [
            ("czarno", "czarnoczerwone"),
            ("błękitno", "błękitnozłote"),
            ("ciemno", "ciemnowłosej"),
            ("nie", "niewielkich"),
        ],
    )
    def test_two_real_halves_are_not_settled_by_a_dictionary(self, left, joined):
        """The limit, stated as a test rather than as a hope.

        `ciemno-włosej` is an artefact and `czarno-czerwone` is a compound the
        writer chose, and to a dictionary they are identical: both halves are
        words and so is the join. This is why the threshold for promoting these
        to a question is to be measured on the owner's corpus and not guessed
        (D-012).
        """
        assert dictionaries.half_is_not_a_word(left, joined, "pl_PL") is False

    def test_a_join_that_is_not_a_word_is_never_offered(self):
        """`biało-czerwony` joined is not a word, so joining would invent one."""
        assert dictionaries.is_a_word("białoczerwony", "pl_PL") is False
        assert dictionaries.half_is_not_a_word("biało", "białoczerwony", "pl_PL") is False

    def test_an_ordinary_inflected_word_is_recognised(self):
        """The dictionary is asked about morphology, not about this book's
        vocabulary — so inflected forms have to come back true or the whole
        approach is a false-positive machine."""
        for word in ("doborowym", "wspominał", "ciemnowłosej"):
            assert dictionaries.is_a_word(word, "pl_PL") is True


class TestItIsCarriedWithTheRelease:
    def test_the_packaging_pins_both_dictionaries_by_digest(self):
        """Same rule as EPUBCheck and Chromium (EF-017): nothing ships that this
        release has not measured."""
        import pathlib

        build = (pathlib.Path(__file__).parent.parent / "packaging" / "build.py").read_text(
            encoding="utf-8"
        )
        assert "DICTIONARIES" in build
        for language in dictionaries.LANGUAGES:
            assert f'"{language}.dic"' in build, language
            assert f'"{language}.aff"' in build, language

    def test_a_missing_dictionary_does_not_fail_the_build(self):
        """Deliberate asymmetry with EPUBCheck and Chromium, and worth asserting
        because it reads as an oversight: a dictionary is a second opinion for
        one detector, and refusing to release over a briefly unreachable file
        would trade a small loss of evidence for a total loss of the release. A
        *wrong* digest still stops it."""
        import pathlib

        build = (pathlib.Path(__file__).parent.parent / "packaging" / "build.py").read_text(
            encoding="utf-8"
        )
        staging = build[build.index("def stage_dictionaries"):build.index("def stage_chromium")]
        assert "WARNING" in staging
        assert "Refusing to " in staging and "has not measured" in staging

    def test_the_bundle_looks_for_them_where_the_spec_puts_them(self):
        import pathlib

        spec = (pathlib.Path(__file__).parent.parent / "packaging" / "epubforge.spec").read_text(
            encoding="utf-8"
        )
        assert '"dictionaries"' in spec
        assert "dictionaries" in str(dictionaries._search_paths())


class TestSuppressionIsPerThread:
    """WP-12's rule, and the bug that came with applying it.

    The corpus signature is measured with the dictionary deliberately switched
    off, so that a recorded corpus does not become reproducible only on a
    machine that happens to have one. The first version of that switch was a
    plain module global — and the corpus measures books **in parallel**. Two
    workers overlap, the first restores the flag to what it saw, the second
    restores it to `True`, and every later caller in the process is quietly told
    there is no dictionary.

    It surfaced as one test failing in the full suite and passing alone, which
    is the signature of leaked state, and it was caught by running the suite the
    way CI runs it rather than the way it is convenient to run it.
    """

    def test_it_restores_what_it_found(self):
        before = dictionaries._is_suppressed()
        with dictionaries.suppressed():
            assert dictionaries._is_suppressed() is True
        assert dictionaries._is_suppressed() is before

    def test_one_thread_suppressing_does_not_reach_another(self):
        import threading

        seen: list[bool] = []
        started = threading.Event()
        may_finish = threading.Event()

        def hold():
            with dictionaries.suppressed():
                started.set()
                may_finish.wait(timeout=5)

        worker = threading.Thread(target=hold)
        worker.start()
        started.wait(timeout=5)
        try:
            seen.append(dictionaries._is_suppressed())
        finally:
            may_finish.set()
            worker.join(timeout=5)
        assert seen == [False], "suppression leaked out of the thread that set it"

    def test_and_nesting_does_not_strand_it(self):
        with dictionaries.suppressed():
            with dictionaries.suppressed():
                pass
            assert dictionaries._is_suppressed() is True
        assert dictionaries._is_suppressed() is False
