"""What happens when a stage raises.

Until 0.1.7 the answer was: the exception became an ERROR line, the remaining
stages ran on a half-modified model, and the writer produced a file. The file
looked finished. Nothing about it said otherwise — not its size, not its
structure, not EPUBCheck.

That made this the worst defect in the program rather than merely one of them:
every other failure could leave the building through it. A crash in the image
stage, in navigation, in metadata — all of them ended as a book on somebody's
disk.

These tests are parameterised over every stage in the real pipeline, so a stage
added later is covered the day it is added.
"""

from __future__ import annotations

import os

import pytest

from epubforge.pipeline import DEFAULT_STAGES, Result, Status, rebuild
from epubforge.policy import Policy
from epubforge.report import Level

from .factory import make_legacy_epub, make_modern_epub


@pytest.fixture
def book(tmp_path) -> str:
    return make_modern_epub(str(tmp_path / "book.epub"))


def explode_in(monkeypatch, stage_class, message="injected failure"):
    """Make one real stage raise, leaving the rest of the pipeline alone."""

    def boom(self, ctx):
        raise RuntimeError(message)

    monkeypatch.setattr(stage_class, "run", boom)


@pytest.mark.parametrize("stage_class", DEFAULT_STAGES, ids=lambda s: s.name)
class TestAStageThatRaises:
    def test_no_file_is_written(self, stage_class, book, tmp_path, monkeypatch):
        destination = tmp_path / "out.epub"
        explode_in(monkeypatch, stage_class)

        result = rebuild(book, str(destination), Policy.preset("preserve"))

        assert result.status is Status.FAILED
        assert result.output_path is None
        assert not destination.exists(), "a half-processed book was left on disk"

    def test_an_existing_destination_is_untouched(
        self, stage_class, book, tmp_path, monkeypatch
    ):
        """The earlier run's output is somebody's work. A crash must not eat it."""
        destination = tmp_path / "out.epub"
        good = rebuild(book, str(destination), Policy.preset("preserve"))
        assert good.status is Status.SUCCEEDED
        before = destination.read_bytes()

        explode_in(monkeypatch, stage_class)
        rebuild(book, str(destination), Policy.preset("preserve"))

        assert destination.read_bytes() == before

    def test_the_failure_names_the_stage(self, stage_class, book, tmp_path, monkeypatch):
        explode_in(monkeypatch, stage_class, "injected failure")

        result = rebuild(book, str(tmp_path / "out.epub"), Policy.preset("preserve"))

        errors = [f for f in result.report.findings if f.level is Level.ERROR]
        assert any("injected failure" in f.message for f in errors)
        assert any(f.stage == stage_class.name for f in errors)

    def test_the_report_says_nothing_was_written(
        self, stage_class, book, tmp_path, monkeypatch
    ):
        """A user reading the report must not be left to infer it from silence."""
        explode_in(monkeypatch, stage_class)

        result = rebuild(book, str(tmp_path / "out.epub"), Policy.preset("preserve"))

        details = " ".join(f.detail or "" for f in result.report.findings)
        assert "Nothing was written" in details


class TestStatusIsReportedNotInferred:
    def test_a_clean_rebuild_succeeds(self, book, tmp_path):
        result = rebuild(book, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status is Status.SUCCEEDED
        assert result.status.wrote_a_file

    def test_a_book_with_errors_is_marked_as_such(self, tmp_path):
        """An unreadable image is an error the rebuild survives — the file is
        written, and the status refuses to call that a clean success."""
        import zipfile

        source = str(tmp_path / "broken-image.epub")
        make_modern_epub(source)
        with zipfile.ZipFile(source) as original:
            entries = {n: original.read(n) for n in original.namelist()}
        entries["OEBPS/picture.png"] = b"NOT A PNG"
        with zipfile.ZipFile(source, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, entries.pop("mimetype"))
            for name, data in entries.items():
                archive.writestr(name, data)

        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))

        assert result.status is Status.SUCCEEDED_WITH_PROBLEMS
        assert result.status.wrote_a_file

    def test_an_unreadable_source_fails(self, tmp_path):
        broken = tmp_path / "not-a-zip.epub"
        broken.write_bytes(b"nope")
        result = rebuild(str(broken), str(tmp_path / "out.epub"))
        assert result.status is Status.FAILED
        assert not result.status.wrote_a_file

    def test_writing_over_the_source_is_blocked_not_failed(self, book):
        """A refusal is not a malfunction, and the two should not read alike."""
        result = rebuild(book, book, Policy.preset("preserve"))
        assert result.status is Status.BLOCKED
        assert not result.status.wrote_a_file

    def test_a_legacy_book_full_of_fixes_is_still_a_success(self, tmp_path):
        source = make_legacy_epub(str(tmp_path / "legacy.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status is Status.SUCCEEDED, [
            f.message for f in result.report.findings if f.level is Level.ERROR
        ]


def test_the_default_result_status_is_not_a_lie():
    """`Result` has a default so old call sites keep working. It must default to
    the harmless value, not to a claim of success on an empty result."""
    from epubforge.report import Report

    empty = Result(Report(), None, None, Status.FAILED)
    assert not empty.status.wrote_a_file
