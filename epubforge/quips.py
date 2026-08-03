"""A closing remark on each rebuilt book.

The tool's personality lives in its documentation and in the fixed text of the
interface. Here there is exactly one running remark, and it is deliberately
rare: it appears only when a book arrives with nothing at all to fix, which is
unusual enough to be worth a raised eyebrow.

Everything else stays quiet. A wisecrack after every single book stops being
funny by the third one and gets in the way of reading the counts, and one next
to an error the user has to act on is simply rude.

The line is picked deterministically from the report, so the same book always
gets the same remark rather than a slot machine on every run.
"""

from __future__ import annotations

from .report import Level, Report

#: Keyed by situation, then by language. Ordered from mildest to most pointed.
QUIPS: dict[str, dict[str, list[str]]] = {
    "spotless": {
        "pl": [
            "Ani jednej usterki. Sprawdź, czy to na pewno EPUB.",
            "Nie znalazłem nic do naprawienia. Zapisz sobie tę datę.",
            "Plik poprawny od pierwszego wejrzenia. Zdarza się raz na jakiś czas.",
        ],
        "en": [
            "Not a single defect. Check that this is actually an EPUB.",
            "Nothing to fix. Note the date somewhere.",
            "Correct on arrival. It happens, apparently.",
        ],
    },
}


def _situation(report: Report) -> str | None:
    """Pick the category, or ``None`` when the tool should stay quiet."""
    if report.count(Level.ERROR) or report.count(Level.WARN):
        # Something needs the user's attention; do not be cute about it.
        return None
    if report.count(Level.FIX) == 0:
        return "spotless"
    # Every other outcome is ordinary work and speaks for itself.
    return None


def quip_for(report: Report, language: str = "pl") -> str | None:
    """One remark for this book, or ``None`` if it should stay quiet."""
    situation = _situation(report)
    if situation is None:
        return None
    options = QUIPS[situation].get(language) or QUIPS[situation]["en"]
    # Deterministic: the same book always gets the same line.
    seed = len(report.findings) * 31 + report.count(Level.PRESERVED)
    return options[seed % len(options)]
