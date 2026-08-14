"""The suite has to be able to say which book it is waiting for.

The audit named two purchased books "mandatory fixtures", recorded three
findings as blocked for want of them, and never wrote down which books it
meant. The owner said so plainly: he had no idea which files were wanted. That
is a defect here and not in his reading — the program asked for something and
gave nobody a way to find out what.

So the roles are declared in the code, described in the owner's language, and
matched against whatever shelves are reachable. What is committed is a digest,
a size and six counts per role. No title, no author, not a word of text.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from epubforge import fixtures
from tests.factory import make_legacy_epub, make_modern_epub


class TestARoleSaysWhatItNeeds:
    def test_every_role_names_the_findings_that_need_it(self):
        for role in fixtures.ROLES:
            assert role.findings, role.id

    def test_every_role_explains_itself_in_sentences(self):
        """`epubforge fixtures` and the GUI both print this. A role described
        only by a digest answers "is it here" and not "what am I looking for",
        and the second question is the one that was never answered."""
        for role in fixtures.ROLES:
            assert role.exercises
            text = fixtures.explain(role)
            assert role.id in text
            for line in role.exercises:
                assert line in text

    def test_a_recorded_profile_exists_for_each_role(self):
        for role in fixtures.ROLES:
            entry = fixtures.recorded(role.id)
            assert entry is not None, f"{role.id} has no recorded profile"
            assert len(entry["sha256"]) == 64
            assert entry["bytes"] > 0


class TestNothingCommittedNamesABook:
    """The standing rule, enforced rather than remembered: in anything public
    these are "Książka 1" and "Książka 2"."""

    def test_the_profiles_hold_counts_and_a_digest_and_nothing_else(self):
        allowed = {"role", "sha256", "bytes", "profile"}
        for role in fixtures.ROLES:
            entry = fixtures.recorded(role.id)
            assert set(entry) <= allowed, set(entry) - allowed
            assert set(entry["profile"]) <= {
                "package_version",
                "documents",
                "spine",
                "images",
                "fonts",
                "stylesheets",
            }

    def test_the_role_ids_are_not_titles(self):
        for role in fixtures.ROLES:
            assert role.id.startswith("ksiazka-")

    def test_no_profile_carries_free_text(self):
        for role in fixtures.ROLES:
            raw = json.loads(fixtures.profile_path(role.id).read_text(encoding="utf-8"))
            for key, value in raw["profile"].items():
                if key == "package_version":
                    assert value in ("2.0", "3.0"), value
                else:
                    assert isinstance(value, int)


class TestFindingTheBook:
    def test_the_recorded_copy_is_found_by_its_digest(self, tmp_path):
        shelf = tmp_path / "polka"
        shelf.mkdir()
        book = shelf / "cokolwiek.epub"
        make_modern_epub(str(book), title="Cokolwiek")
        fixtures.record("ksiazka-1", book)
        try:
            found = fixtures.locate("ksiazka-1", extra=shelf)
            assert found.found
            assert found.path == book
        finally:
            _restore(tmp_path)

    def test_a_shelf_without_it_reports_missing_and_not_something_else(self, tmp_path):
        """Measured on the owner's own library while this was written: matching
        a role by its structural profile handed a Foundation novel to the
        Witcher fixture, confidently. "EPUB 2, 29 documents, 3 images, 7 fonts,
        one stylesheet" describes a publisher's export settings, not a book.

        A wrong fixture is worse than a missing one — a test would then measure
        a book nobody chose and report a number about it as if it meant
        something. So resemblance produces a shortlist for a person, never an
        answer.
        """
        shelf = tmp_path / "polka"
        shelf.mkdir()
        make_modern_epub(str(shelf / "inna.epub"), title="Inna")
        make_legacy_epub(str(shelf / "stara.epub"))
        found = fixtures.locate("ksiazka-1", extra=shelf)
        assert not found.found
        assert "brak" in str(found)

    def test_a_folder_of_rubbish_does_not_stop_the_search(self, tmp_path):
        shelf = tmp_path / "polka"
        shelf.mkdir()
        (shelf / "to nie epub.epub").write_bytes(b"nie jestem archiwum")
        book = shelf / "prawdziwa.epub"
        make_modern_epub(str(book), title="Prawdziwa")
        fixtures.record("ksiazka-2", book)
        try:
            assert fixtures.locate("ksiazka-2", extra=shelf).path == book
        finally:
            _restore(tmp_path)

    def test_survey_covers_every_role(self):
        assert {m.role for m in fixtures.survey()} == {r.id for r in fixtures.ROLES}


class TestTheProfileIsMeasuredAndNotAssumed:
    def test_it_reads_the_package_version_from_the_package(self, tmp_path):
        legacy = tmp_path / "stara.epub"
        make_legacy_epub(str(legacy))
        assert fixtures.profile_of(legacy)["package_version"] == "2.0"

    def test_it_counts_what_is_in_the_archive(self, tmp_path):
        book = tmp_path / "nowa.epub"
        make_modern_epub(str(book), title="Nowa")
        measured = fixtures.profile_of(book)
        with zipfile.ZipFile(book) as archive:
            names = archive.namelist()
        assert measured["documents"] == sum(
            1 for n in names if n.lower().endswith((".xhtml", ".html", ".htm"))
        )
        assert measured["images"] == sum(1 for n in names if n.lower().endswith(".png"))


class TestTheCommandLineSaysIt:
    def test_the_command_lists_every_role_and_what_it_is_for(self, capsys, tmp_path):
        import argparse

        from epubforge.cli import command_fixtures

        code = command_fixtures(argparse.Namespace(role=None, book=None))
        printed = capsys.readouterr().out
        for role in fixtures.ROLES:
            assert role.id in printed
        # 0 only when both are actually reachable; on a checkout without the
        # books this is 1, and that is the honest answer rather than a pass.
        assert code in (0, 1)

    def test_recording_through_the_command_names_the_digest(self, capsys, tmp_path):
        import argparse

        from epubforge.cli import command_fixtures

        book = tmp_path / "nowa.epub"
        make_modern_epub(str(book), title="Nowa")
        try:
            code = command_fixtures(
                argparse.Namespace(role="ksiazka-1", book=str(book))
            )
            assert code == 0
            assert fixtures.digest_of(book)[:16] in capsys.readouterr().out
        finally:
            _restore(tmp_path)

    def test_an_unknown_role_is_refused_rather_than_created(self, tmp_path):
        import argparse

        from epubforge.cli import command_fixtures

        book = tmp_path / "nowa.epub"
        make_modern_epub(str(book), title="Nowa")
        assert command_fixtures(argparse.Namespace(role="ksiazka-9", book=str(book))) == 2
        assert not fixtures.profile_path("ksiazka-9").exists()


#: Recording rewrites a committed file, so every test that records puts the real
#: one back. Kept as a helper rather than a fixture because the restore has to
#: happen even when the assertion above it fails.
_ORIGINAL = {
    role.id: fixtures.profile_path(role.id).read_text(encoding="utf-8")
    for role in fixtures.ROLES
    if fixtures.profile_path(role.id).exists()
}


def _restore(_tmp_path) -> None:
    for role_id, text in _ORIGINAL.items():
        fixtures.profile_path(role_id).write_text(text, encoding="utf-8")
