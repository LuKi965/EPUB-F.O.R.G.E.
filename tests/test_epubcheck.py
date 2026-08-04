"""Conformance verified by the reference implementation, when it is installed."""

from __future__ import annotations

import pytest

from epubforge.validate import find_epubcheck, validate

pytestmark = pytest.mark.skipif(
    find_epubcheck() is None,
    reason="EPUBCheck not installed; set EPUBCHECK_JAR or put epubcheck on PATH",
)


def test_strict_rebuild_passes_epubcheck_cleanly(rebuilt_strict):
    result = validate(rebuilt_strict.output_path)
    assert result.available
    assert result.errors == 0 and result.fatal == 0, "\n".join(result.messages)
    assert result.warnings == 0, "\n".join(result.messages)


def test_every_compatibility_profile_still_validates(legacy_epub, tmp_path):
    """The concessions are additive, so enabling all of them must cost nothing.

    This also pins the claim the tool makes about ``<guide>``: EPUB 3.3 dropped
    the element, but EPUBCheck accepts it, so the report says the output stays
    valid. If a future EPUBCheck disagrees, this fails and the wording is wrong.
    """
    from epubforge import compat
    from epubforge.pipeline import rebuild
    from epubforge.policy import Policy

    result = rebuild(
        legacy_epub,
        str(tmp_path / "compat.epub"),
        Policy.preset("strict", compat_profiles=tuple(sorted(compat.PROFILES))),
    )
    assert result.output_path, result.report.to_text()
    check = validate(result.output_path)
    assert check.errors == 0 and check.fatal == 0, "\n".join(check.messages)
    assert check.warnings == 0, "\n".join(check.messages)


def test_preserve_rebuild_only_retains_source_defects(rebuilt):
    """Preserve mode may leave source errors, but must introduce none of its own."""
    result = validate(rebuilt.output_path)
    assert result.available
    assert result.fatal == 0
    # The fixture's one genuine defect is a link to a file that never existed.
    assert result.errors <= 1
    for message in result.messages:
        assert "brakujacy" in message or "could not be found" in message, message
