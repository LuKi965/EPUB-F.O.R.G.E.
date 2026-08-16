"""The questions speak the language the interface speaks.

EF-032. Every question this program puts to a person was a Polish literal in
whichever module happened to raise it. The report has had a two-language
catalogue since 0.2.4 and renders from `rule` + `values` at display time; the
questions — the one place the program actually *talks* to somebody — had
neither. An English user got the window in English and then, at the moment of
being asked to decide something irreversible about their book, a paragraph of
Polish.

The test that matters most here is the last one: a key present in one catalogue
and missing from the other is how a half-finished translation looks from the
outside, and it fails silently — the fallback quietly serves Polish and nobody
finds out until somebody is staring at it.
"""

from __future__ import annotations

import pytest

from epubforge import question_texts
from epubforge.question_texts import say, set_language


@pytest.fixture(autouse=True)
def restore_language():
    """The setting is module-level, so a test that changes it and leaves would
    hand the next one a different program."""
    before = question_texts.language()
    yield
    set_language(before)


class TestBothLanguagesAreThere:
    def test_polish_is_what_it_was(self):
        set_language("pl")
        assert say("hyphen.one.summary", word="obo-jętna") == (
            "„obo-jętna” — łącznik w środku słowa"
        )

    def test_english_is_english(self):
        set_language("en")
        assert say("hyphen.one.summary", word="obo-jętna") == (
            "“obo-jętna” — a hyphen inside a word"
        )

    def test_the_default_is_polish(self):
        """The owner's language, and the window's default. This module must not
        change what he sees by existing."""
        assert question_texts._initial() == "pl"

    def test_the_command_line_setting_is_honoured(self, monkeypatch):
        """`cli.py` already reads EPUBFORGE_LANG for its closing remark, so a
        batch configured for English asks in English without a second setting
        nobody would think to change."""
        monkeypatch.setenv(question_texts.ENV_LANGUAGE, "en")
        assert question_texts._initial() == "en"

    def test_a_language_nobody_wrote_leaves_the_setting_alone(self):
        set_language("pl")
        set_language("de")
        assert question_texts.language() == "pl"


class TestItNeverRefusesToRender:
    """Same rule as `rules.describe`: a question in the wrong language is still
    a question somebody can answer, and one that raises leaves a person looking
    at a traceback instead of at their book."""

    def test_an_unknown_key_comes_back_as_itself(self):
        assert say("nie.ma.takiego.klucza") == "nie.ma.takiego.klucza"

    def test_a_missing_value_does_not_raise(self):
        assert "{" in say("hyphen.one.summary")

    def test_a_key_only_polish_has_falls_back_rather_than_vanishing(self):
        set_language("en")
        question_texts.TEXTS_PL["test.only-polish"] = "tylko po polsku"
        try:
            assert say("test.only-polish") == "tylko po polsku"
        finally:
            del question_texts.TEXTS_PL["test.only-polish"]


class TestTheTranslationIsWholeRatherThanStarted:
    def test_neither_catalogue_has_a_key_the_other_lacks(self):
        """The failure this prevents is invisible: the fallback serves Polish
        for a missing English key, so a half-translated catalogue looks like a
        working one until somebody is reading it."""
        missing_en = set(question_texts.TEXTS_PL) - set(question_texts.TEXTS_EN)
        missing_pl = set(question_texts.TEXTS_EN) - set(question_texts.TEXTS_PL)
        assert not missing_en, f"bez angielskiego: {sorted(missing_en)}"
        assert not missing_pl, f"bez polskiego: {sorted(missing_pl)}"

    def test_a_template_expects_the_same_values_in_both_languages(self):
        """A placeholder present in one and absent in the other means one of the
        two renders with a brace in it, and only for the users of that language."""
        import re

        holes = re.compile(r"\{(\w+)\}")
        for key, polish in question_texts.TEXTS_PL.items():
            english = question_texts.TEXTS_EN[key]
            assert set(holes.findall(polish)) == set(holes.findall(english)), key


class TestTheCoreNoLongerCarriesQuestionProse:
    """The point of the catalogue is that there is one place to edit. These two
    modules raised every question in the program, in Polish, inline."""

    @pytest.mark.parametrize("module", ["hyphens.py", "pipeline.py"])
    def test_no_question_is_written_in_place(self, module):
        import pathlib
        import re

        source = (
            pathlib.Path(__file__).parent.parent / "epubforge" / module
        ).read_text(encoding="utf-8")
        # Only the arguments a person reads. `detail=` also carries assembled
        # data — a list of changed fields, a quoted line of the book — and that
        # is not prose to translate.
        prose = re.findall(r"summary=(?:f?\")([^\"]*)\"", source)
        for line in prose:
            assert not re.search(r"[ąćęłńóśźż]", line), f"{module}: {line}"


class TestTheWindowKeepsTheTwoInStep:
    def test_switching_the_window_switches_the_questions(self):
        """One call, both settings. Two calls would eventually become one call
        and a bug that only English users see."""
        from epubforge.gui import strings

        before = strings.language()
        try:
            strings.set_language("en")
            assert question_texts.language() == "en"
            strings.set_language("pl")
            assert question_texts.language() == "pl"
        finally:
            strings.set_language(before)
