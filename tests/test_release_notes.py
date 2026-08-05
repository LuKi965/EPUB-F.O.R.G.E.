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

from release_notes import CHANGELOG, section_for  # noqa: E402

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
