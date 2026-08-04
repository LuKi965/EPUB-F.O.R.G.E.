"""The library survey: what breaks across many books, ranked."""

from __future__ import annotations

import json

import pytest

from epubforge.report import Level
from epubforge.survey import normalise, survey_library, to_json

from .factory import make_legacy_epub, make_modern_epub


@pytest.fixture
def library(tmp_path):
    """A handful of books, one of them not a book at all."""
    folder = tmp_path / "lib"
    folder.mkdir()
    for index in range(3):
        make_legacy_epub(str(folder / f"legacy{index}.epub"))
    make_modern_epub(str(folder / "modern.epub"))
    (folder / "broken.epub").write_bytes(b"this is not a zip")
    return [str(p) for p in sorted(folder.glob("*.epub"))]


class TestNormalisation:
    """Counting raw messages would scatter one defect across a dozen rows."""

    def test_numbers_are_folded(self):
        assert normalise("corrected 5 declarations") == normalise("corrected 12 declarations")

    def test_decimals_are_folded_too(self):
        assert normalise("entry declares 1.5 MiB") == normalise("entry declares 300.25 MiB")

    def test_quoted_fragments_are_folded(self):
        assert normalise("declared 'text/html'") == normalise("declared 'application/xml'")

    def test_the_sentence_itself_still_distinguishes_findings(self):
        assert normalise("removed 3 rules") != normalise("kept 3 rules")


class TestSurvey:
    def test_every_book_is_counted(self, library):
        assert survey_library(library, deep=False).books == len(library)

    def test_an_unreadable_file_is_separated_from_findings(self, library):
        survey = survey_library(library, deep=True)
        assert len(survey.unreadable) == 1

    def test_source_versions_are_tallied(self, library):
        survey = survey_library(library, deep=True)
        assert survey.source_versions["2.0"] == 3
        assert survey.source_versions["3.0"] == 1

    def test_a_shared_defect_is_reported_once_with_a_book_count(self, library):
        survey = survey_library(library, deep=True)
        shared = [f for f in survey.ranked() if f.books == 3 and f.stage == "package"]
        assert shared, [f"{f.books} {f.stage}: {f.message}" for f in survey.ranked()]

    def test_findings_are_ranked_by_how_many_books_show_them(self, library):
        counts = [f.books for f in survey_library(library, deep=True).ranked()]
        assert counts == sorted(counts, reverse=True)

    def test_nothing_crashes_on_a_mixed_library(self, library):
        assert survey_library(library, deep=True).crashed == []

    def test_the_deep_survey_sees_more_than_the_shallow_one(self, library):
        """Shallow reads the books; deep runs the pipeline that repairs them."""
        shallow = survey_library(library, deep=False)
        deep = survey_library(library, deep=True)
        assert len(deep.findings) > len(shallow.findings)

    def test_no_output_is_written_beside_the_books(self, library, tmp_path):
        before = set((tmp_path / "lib").iterdir())
        survey_library(library, deep=True)
        assert set((tmp_path / "lib").iterdir()) == before


class TestPrivacy:
    """A survey is meant to be shareable; a list of titles is not."""

    def test_names_are_absent_by_default(self, library):
        payload = to_json(survey_library(library, deep=True))
        assert "legacy0.epub" not in payload
        assert "modern.epub" not in payload

    def test_names_appear_only_when_asked_for(self, library):
        survey = survey_library(library, deep=True, with_names=True)
        payload = to_json(survey, with_names=True)
        assert "legacy0.epub" in payload

    def test_asking_for_names_while_writing_without_them_still_omits_them(self, library):
        """The flag on the writer is what decides, so one cannot leak the other."""
        survey = survey_library(library, deep=True, with_names=True)
        assert "legacy0.epub" not in to_json(survey, with_names=False)

    def test_the_json_declares_its_schema(self, library):
        payload = json.loads(to_json(survey_library(library, deep=False)))
        assert payload["schema"] == 2
        assert set(payload) >= {"books", "unreadable", "findings", "source_versions"}


class TestFailuresExplainThemselves:
    """A survey came back with `crashed: 3` and no way to learn anything more.

    The count is the alarm; the reason is the only part anybody can act on. It
    travels because a stack trace says nothing about a shelf — but the filename
    it happened on does, so that stays behind unless it was asked for.
    """

    def test_the_reason_is_recorded_not_just_the_count(self, library):
        payload = json.loads(to_json(survey_library(library, deep=False)))
        assert payload["unreadable"] == 1
        reasons = payload["unreadable_reasons"]
        assert reasons and reasons[0]["books"] == 1
        assert reasons[0]["reason"]

    def test_identical_failures_are_grouped(self, tmp_path):
        folder = tmp_path / "bad"
        folder.mkdir()
        for index in range(3):
            (folder / f"broken{index}.epub").write_bytes(b"this is not a zip")
        payload = json.loads(
            to_json(survey_library([str(p) for p in sorted(folder.glob("*.epub"))]))
        )
        assert len(payload["unreadable_reasons"]) == 1
        assert payload["unreadable_reasons"][0]["books"] == 3

    def test_a_path_inside_the_message_is_taken_out(self):
        from epubforge.survey import redact

        redacted = redact("failed on C:\\Users\\Ktos\\Ebooki\\Tytul.epub while parsing")
        assert "Tytul" not in redacted
        assert "while parsing" in redacted

    def test_the_names_still_need_asking_for(self, library):
        payload = json.loads(to_json(survey_library(library, deep=False)))
        assert "broken.epub" not in json.dumps(payload)
        with_names = json.loads(
            to_json(survey_library(library, deep=False, with_names=True), with_names=True)
        )
        assert "broken.epub" in json.dumps(with_names)


def test_levels_survive_into_the_summary(library):
    survey = survey_library(library, deep=True)
    levels = {finding.level for finding in survey.ranked()}
    assert Level.FIX in levels
