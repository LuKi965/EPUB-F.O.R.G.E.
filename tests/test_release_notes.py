"""The notes a release goes out with come from the changelog, or it does not go.

The release step reads `packaging/release_notes.py`, so an empty or wrong
section here means a release published with empty notes — which nobody notices
until it is on the download page. The extractor failing loudly is the whole
point of it existing.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "packaging"))

from release_notes import CHANGELOG, main, section_for  # noqa: E402

SAMPLE = """# Changelog

## 0.3.0 — alpha

Nowsze.

## 0.2.0 — alpha

Pierwsza linia.

More.

## 0.1.0 — pre-alpha

Najstarsze.
"""


def test_a_section_stops_at_the_next_version():
    body = section_for("0.2.0", SAMPLE)
    assert body.startswith("Pierwsza linia.")
    assert body.endswith("More.")
    assert "Najstarsze" not in body
    assert "Nowsze" not in body


def test_the_last_section_runs_to_the_end():
    assert section_for("0.1.0", SAMPLE) == "Najstarsze."


def test_the_heading_itself_is_not_part_of_the_body():
    """The release page prints its own heading; repeating it reads as a mistake."""
    assert not section_for("0.2.0", SAMPLE).startswith("##")


def test_an_absent_version_is_empty_rather_than_the_nearest_one():
    assert section_for("9.9.9", SAMPLE) == ""


def test_the_current_version_has_notes_to_release():
    """The one that would actually stop a bad release: whatever `__version__`
    says, the changelog has a section for it."""
    from epubforge import __version__

    body = section_for(__version__, CHANGELOG.read_text(encoding="utf-8"))
    assert body, f"CHANGELOG.md has no section for {__version__}"


@pytest.mark.parametrize("version", ["0.1.8", "0.1.7", "0.1.6"])
def test_earlier_versions_are_still_extractable(version):
    """Cheap protection for the heading format, which the regex depends on."""
    assert section_for(version, CHANGELOG.read_text(encoding="utf-8"))


class TestWritingThemOut:
    """The release step calls this as a program, not as a function.

    It first did it by printing and letting PowerShell redirect, and that died
    on the runner after a full build: Windows hands Python a cp1252 console,
    and this changelog is Polish with em dashes and arrows in it. Everything
    downstream — tag, release, both downloads — was lost to an encoding.
    """

    def test_the_file_it_writes_is_utf_8(self, tmp_path):
        from epubforge import __version__

        target = tmp_path / "notes.md"
        assert main(["release_notes.py", __version__, "--output", str(target)]) == 0
        raw = target.read_bytes()
        assert raw.decode("utf-8").strip()

    def test_the_bytes_do_not_depend_on_the_runner(self, tmp_path):
        """Text mode turns "\\n" into "\\r\\n" on Windows, so the same release
        published from a Windows runner and a Linux one would have differently
        encoded notes. This caught it — on Windows, after everything else had
        already been built."""
        from epubforge import __version__

        target = tmp_path / "notes.md"
        main(["release_notes.py", __version__, "--output", str(target)])
        assert b"\r" not in target.read_bytes()

    def test_a_leading_v_is_accepted(self, tmp_path):
        """The workflow passes whatever the tag said."""
        from epubforge import __version__

        target = tmp_path / "notes.md"
        assert main(["release_notes.py", f"v{__version__}", "--output", str(target)]) == 0
        assert target.read_text(encoding="utf-8").strip()

    def test_an_unknown_version_writes_nothing_and_fails(self, tmp_path):
        target = tmp_path / "notes.md"
        assert main(["release_notes.py", "9.9.9", "--output", str(target)]) == 1
        assert not target.exists()

    def test_printing_survives_a_console_that_cannot_hold_the_text(self):
        """Exactly the runner's failure, reproduced: a stdout that is cp1252."""
        import io

        from epubforge import __version__

        buffer = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        stdout, sys.stdout = sys.stdout, buffer
        try:
            assert main(["release_notes.py", __version__]) == 0
        finally:
            sys.stdout = stdout
        buffer.flush()
        assert buffer.buffer.getvalue().decode("utf-8").strip()
