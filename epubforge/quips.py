"""A closing remark on each rebuilt book.

The tool spends its life reading files that nobody proofread, so it is allowed
one dry observation per book. Two rules keep this from becoming annoying:

* **The joke is never at the user's expense.** They did not write the file; they
  bought it. The target is always the file, the converter or the publisher.
* **It never replaces information.** The quip is decoration printed after the
  counts, never instead of them, and it is silent when something actually went
  wrong — nobody wants a wisecrack next to an error they have to deal with.

The line is picked deterministically from the report, so the same book always
gets the same remark rather than a slot machine on every run.
"""

from __future__ import annotations

from .report import Level, Report

#: Keyed by situation, then by language. Ordered from mildest to most pointed.
QUIPS: dict[str, dict[str, list[str]]] = {
    "spotless": {
        "pl": [
            "Ani jednej usterki. Sprawdź, czy to na pewno ebook.",
            "Nie znalazłem nic do naprawienia. Zapisz sobie tę datę.",
            "Plik poprawny od pierwszego wejrzenia. Zdarza się raz na jakiś czas.",
        ],
        "en": [
            "Not a single defect. Check that this is actually an e-book.",
            "Nothing to fix. Note the date somewhere.",
            "Correct on arrival. It happens, apparently.",
        ],
    },
    "light": {
        "pl": [
            "Kilka drobiazgów. Wydawca prawie się postarał.",
            "Lekkie zadrapania, nic poważnego.",
            "Dało się to naprawić bez wzywania karetki.",
        ],
        "en": [
            "A few odds and ends. The publisher nearly tried.",
            "Light scratches, nothing structural.",
            "Fixed without having to call anyone.",
        ],
    },
    "moderate": {
        "pl": [
            "Wydawca się postarał. W złym kierunku.",
            "Ktoś tu eksportował z Worda i nie poczuł nic.",
            "Standard był w pobliżu. Nikt go nie zaczepił.",
        ],
        "en": [
            "The publisher tried. In the wrong direction.",
            "Someone exported this from Word and felt nothing.",
            "The specification was nearby. Nobody spoke to it.",
        ],
    },
    "carnage": {
        "pl": [
            "Ten plik nie został złożony. On się po prostu wydarzył.",
            "Podejrzewam, że konwerter płakał, ale robił swoje.",
            "Więcej tu było napraw niż akapitów w niejednym wstępie.",
        ],
        "en": [
            "This file was not authored. It simply happened.",
            "The converter was crying, but it kept going.",
            "More repairs here than some books have paragraphs.",
        ],
    },
    "watermarks": {
        "pl": [
            "Znak wodny w każdym rozdziale. Ktoś płacił od sztuki?",
            "Ten sam token powtórzony do znudzenia. Zostaje, ale już nie krzyczy.",
        ],
        "en": [
            "A watermark in every chapter. Was somebody paid per copy?",
            "The same token, over and over. It stays — it just stops shouting.",
        ],
    },
    "legacy": {
        "pl": [
            "EPUB 2 w tym roku. Klasyka gatunku.",
            "Ten plik pamięta czasy, gdy `<center>` był dobrym pomysłem.",
        ],
        "en": [
            "EPUB 2, this year. A classic of the genre.",
            "This file remembers when `<center>` was a good idea.",
        ],
    },
}


def _situation(report: Report) -> str | None:
    """Pick the category, or ``None`` when a joke would be out of place."""
    if report.count(Level.ERROR):
        # Something needs the user's attention; do not be cute about it.
        return None

    fixes = report.count(Level.FIX)
    messages = " ".join(f.message for f in report.findings)

    if "watermark marker" in messages and fixes >= 5:
        return "watermarks"
    if "EPUB 2" in messages and fixes >= 5:
        return "legacy"
    if fixes == 0:
        return "spotless"
    if fixes <= 4:
        return "light"
    if fixes <= 12:
        return "moderate"
    return "carnage"


def quip_for(report: Report, language: str = "pl") -> str | None:
    """One remark for this book, or ``None`` if it should stay quiet."""
    situation = _situation(report)
    if situation is None:
        return None
    options = QUIPS[situation].get(language) or QUIPS[situation]["en"]
    # Deterministic: the same book always gets the same line.
    seed = len(report.findings) * 31 + report.count(Level.PRESERVED)
    return options[seed % len(options)]
