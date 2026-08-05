"""What the command line promises the shell, and what it refuses to do.

There were no tests here at all, and that is exactly where two defects lived:
a book that produced an error exited 0 while printing "written" in green, and
pointing `-o` at an existing file replaced it without a word. Neither is visible
from inside the library — both are contracts between this program and whoever
runs it.

The exit code is the part a script reads. Getting it wrong means an automated
pipeline treats a damaged book as a finished one.
"""

from __future__ import annotations


import zipfile

import pytest

from epubforge.cli import EXIT_NOT_WRITTEN, EXIT_OK, EXIT_WRITTEN_WITH_PROBLEMS, main

from .factory import make_legacy_epub, make_modern_epub, png_bytes


def run(*args: str) -> int:
    """The CLI in-process, so a failure shows a traceback and not just a code."""
    return main(list(args))


@pytest.fixture
def book(tmp_path) -> str:
    return make_modern_epub(str(tmp_path / "book.epub"))


@pytest.fixture
def book_with_an_error(tmp_path) -> str:
    """An unreadable image: reported as an error, and the book is still written.

    Whether the book *should* be written in that case is a separate question
    (the stage failed on one resource, not on the book). What must not happen is
    calling that outcome a success.
    """
    source = str(tmp_path / "broken-image.epub")
    make_modern_epub(source)
    # Rewritten rather than appended: a second entry of the same name is itself
    # one of the defects under investigation, and it has no place in a fixture
    # meant to isolate a different one.
    with zipfile.ZipFile(source) as original:
        entries = {name: original.read(name) for name in original.namelist()}
    entries["OEBPS/picture.png"] = b"THIS IS NOT A PNG"
    with zipfile.ZipFile(source, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, entries.pop("mimetype"))
        for name, data in entries.items():
            archive.writestr(name, data)
    return source


class TestExitCodes:
    def test_a_clean_book_exits_zero(self, book, tmp_path):
        assert run("build", book, "-o", str(tmp_path / "out.epub")) == EXIT_OK

    def test_an_unreadable_source_exits_not_written(self, tmp_path):
        broken = tmp_path / "not-a-zip.epub"
        broken.write_bytes(b"this is not a zip at all")
        assert run("build", str(broken), "-o", str(tmp_path / "out.epub")) == EXIT_NOT_WRITTEN

    def test_a_written_book_carrying_errors_does_not_exit_zero(
        self, book_with_an_error, tmp_path
    ):
        """The defect: this used to be 0 unless --strict-exit was passed."""
        code = run("build", book_with_an_error, "-o", str(tmp_path / "out.epub"))
        assert code == EXIT_WRITTEN_WITH_PROBLEMS

    def test_warnings_alone_are_not_a_failure(self, tmp_path):
        """A legacy book produces warnings by design. Treating those as failure
        would make the exit code useless, which is the opposite defect."""
        source = make_legacy_epub(str(tmp_path / "legacy.epub"))
        assert run("build", source, "-o", str(tmp_path / "out.epub")) == EXIT_OK

    def test_strict_exit_promotes_warnings(self, tmp_path):
        source = make_legacy_epub(str(tmp_path / "legacy.epub"))
        code = run("build", source, "--strict-exit", "-o", str(tmp_path / "out.epub"))
        assert code == EXIT_WRITTEN_WITH_PROBLEMS


class TestNothingIsOverwrittenByAccident:
    def test_the_source_is_still_refused(self, book):
        """This guard already existed and must keep existing."""
        assert run("build", book, "-o", book) == EXIT_NOT_WRITTEN

    def test_an_existing_destination_is_refused(self, book, tmp_path):
        victim = tmp_path / "already-here.epub"
        victim.write_bytes(b"SOMEBODY ELSE'S WORK")

        code = run("build", book, "-o", str(victim))

        assert code == EXIT_NOT_WRITTEN
        assert victim.read_bytes() == b"SOMEBODY ELSE'S WORK"

    def test_force_allows_it(self, book, tmp_path):
        victim = tmp_path / "already-here.epub"
        victim.write_bytes(b"SOMEBODY ELSE'S WORK")

        assert run("build", book, "--force", "-o", str(victim)) == EXIT_OK
        assert zipfile.is_zipfile(victim)

    def test_a_batch_does_not_quietly_replace_earlier_results(self, tmp_path):
        """Two runs into the same folder: the second must not clobber the first
        without being told to."""
        folder = tmp_path / "books"
        folder.mkdir()
        make_modern_epub(str(folder / "one.epub"), title="One")
        out = tmp_path / "out"
        out.mkdir()

        assert run("build", str(folder), "-o", str(out)) == EXIT_OK
        assert run("build", str(folder), "-o", str(out)) == EXIT_NOT_WRITTEN
        assert run("build", str(folder), "--force", "-o", str(out)) == EXIT_OK


class TestOrphansAreKeptUnlessAsked:
    """0.1.7 turned this off by default. The reference graph does not yet see
    `srcset`, `<picture>` or links made from inside an SVG, so a file it calls
    unreferenced may still be on the page."""

    def build_with_a_lone_file(self, tmp_path) -> str:
        source = make_modern_epub(str(tmp_path / "lonely.epub"))
        with zipfile.ZipFile(source, "a") as archive:
            archive.writestr("OEBPS/nobody-points-here.png", png_bytes())
        return source

    def test_kept_by_default(self, tmp_path):
        source = self.build_with_a_lone_file(tmp_path)
        out = tmp_path / "kept.epub"
        assert run("build", source, "-o", str(out)) == EXIT_OK
        with zipfile.ZipFile(out) as archive:
            assert any("nobody-points-here" in n for n in archive.namelist())

    def test_removed_when_asked(self, tmp_path):
        source = self.build_with_a_lone_file(tmp_path)
        out = tmp_path / "swept.epub"
        assert run("build", source, "--drop-orphans", "-o", str(out)) == EXIT_OK
        with zipfile.ZipFile(out) as archive:
            assert not any("nobody-points-here" in n for n in archive.namelist())

    def test_the_old_flag_name_is_gone(self):
        """`--keep-orphans` described the non-default. Leaving it as a silent
        no-op would be worse than an error, because a script passing it would
        believe it had changed something."""
        with pytest.raises(SystemExit):
            run("build", "--keep-orphans", "nothing.epub")
