"""The remark is rare by design; it must never intrude on real work."""

from __future__ import annotations

from epubforge.quips import quip_for
from epubforge.report import Level, Report


def report_with(fixes: int = 0, warnings: int = 0, errors: int = 0) -> Report:
    report = Report()
    for _ in range(fixes):
        report.add("test", Level.FIX, "did a thing")
    for _ in range(warnings):
        report.add("test", Level.WARN, "worth a look")
    for _ in range(errors):
        report.add("test", Level.ERROR, "something broke")
    return report


def test_speaks_only_for_a_book_that_needed_nothing():
    remark = quip_for(report_with())
    assert remark and len(remark) > 10


def test_silent_for_an_ordinary_rebuild():
    """A wisecrack after every book stops being funny by the third one."""
    assert quip_for(report_with(fixes=8)) is None


def test_silent_when_anything_needs_attention():
    assert quip_for(report_with(warnings=1)) is None
    assert quip_for(report_with(errors=1)) is None


def test_the_same_book_always_gets_the_same_line():
    assert quip_for(report_with()) == quip_for(report_with())


def test_both_languages_are_available():
    assert quip_for(report_with(), "pl") != quip_for(report_with(), "en")


def test_unknown_language_falls_back_to_english():
    assert quip_for(report_with(), "de") == quip_for(report_with(), "en")
