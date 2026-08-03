"""The remark is decoration; it must never intrude on a real problem."""

from __future__ import annotations

from epubforge.quips import quip_for
from epubforge.report import Level, Report


def report_with(fixes: int = 0, errors: int = 0, message: str = "did a thing") -> Report:
    report = Report()
    for _ in range(fixes):
        report.add("test", Level.FIX, message)
    for _ in range(errors):
        report.add("test", Level.ERROR, "something broke")
    return report


def test_silent_when_anything_failed():
    """A wisecrack next to an error the user must act on is just noise."""
    assert quip_for(report_with(fixes=20, errors=1)) is None


def test_speaks_for_a_clean_book():
    remark = quip_for(report_with(fixes=0))
    assert remark and len(remark) > 10


def test_scales_with_how_broken_the_book_was():
    light = quip_for(report_with(fixes=2))
    carnage = quip_for(report_with(fixes=40))
    assert light and carnage and light != carnage


def test_watermarks_get_their_own_line():
    remark = quip_for(report_with(fixes=6, message="consolidated 34 watermark marker(s)"))
    assert remark and ("watermark" in remark.lower() or "znak wodny" in remark.lower())


def test_the_same_book_always_gets_the_same_line():
    """Deterministic, so re-running does not spin a slot machine."""
    first = quip_for(report_with(fixes=7))
    second = quip_for(report_with(fixes=7))
    assert first == second


def test_both_languages_are_available():
    assert quip_for(report_with(fixes=7), "pl") != quip_for(report_with(fixes=7), "en")


def test_unknown_language_falls_back_to_english():
    assert quip_for(report_with(fixes=7), "de") == quip_for(report_with(fixes=7), "en")
