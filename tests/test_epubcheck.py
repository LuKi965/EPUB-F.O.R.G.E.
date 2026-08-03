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


def test_preserve_rebuild_only_retains_source_defects(rebuilt):
    """Preserve mode may leave source errors, but must introduce none of its own."""
    result = validate(rebuilt.output_path)
    assert result.available
    assert result.fatal == 0
    # The fixture's one genuine defect is a link to a file that never existed.
    assert result.errors <= 1
    for message in result.messages:
        assert "brakujacy" in message or "could not be found" in message, message
