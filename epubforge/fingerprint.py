"""What made this book, and how sure of each answer we are.

`model.py` has carried a `generator` field nobody filled in since the first
week, and the inventory has carried its own detector — a flat dictionary of
regular expressions producing a flat sorted list of names. Both say the same
kind of thing and neither says how strongly, which is the part that matters:

* `_idGenParaOverride` is a class name InDesign invents. Nothing else writes it
  and no human types it. Seeing it *is* the answer.
* `vellum` is the name of a typesetting program and also the word for
  parchment. Seeing it in a book about bookbinding says nothing at all.

The old detector scored those identically, and the whole file was searched as
one string, so a `<meta name="generator">` in the package document counted for
exactly as much as the same word appearing in a chapter. This module keeps the
signatures as **data**, gives each one a weight and a place it has to appear
in, and returns a **list with confidences** rather than a single name.

The list is the point, not a compromise. Files are layered — exported from
InDesign, converted by Calibre, patched in Sigil — and each of those left a
different kind of damage behind. A book that is 90% Calibre and 40% InDesign is
not an uncertain answer; it is an accurate description of a real file, and
roadmap [7] needs it that way, because the care a paragraph deserves depends on
what handled it last.

Nothing here changes a book. It answers a question and the answer goes in the
report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Where a trace may count. The package document is the strongest ground: a
#: generator writes its own name there deliberately, and prose does not reach
#: it. `any` is for traces distinctive enough that where they turn up does not
#: change what they mean.
PLACES = ("package", "markup", "css", "any")

#: Below this a trace is noise and is not reported. One weak signal on its own
#: never clears it; two do, which is the behaviour wanted — the word "calibre"
#: in a chapter is nothing, the word plus a `calibre3` class is an answer.
FLOOR = 0.5


@dataclass(frozen=True)
class Signal:
    """One trace, what it is worth, and where it has to appear to be worth it."""

    pattern: str
    weight: float
    place: str = "any"
    #: The trace itself, as it appears in the file — `calibre:series`,
    #: `MsoNormal`, `class=ftN`. Written as the literal thing found rather than
    #: as a sentence about it, for two reasons: a confidence with no evidence
    #: behind it is a number nobody can check, and a report reader who wants to
    #: verify the claim can search the book for exactly this. It is also the
    #: same string in every language, which a sentence would not have been.
    #: `@package` marks a trace that only counted because it was in the package
    #: document.
    note: str = ""
    #: Plain lowercase substrings, any one of which must be present for the
    #: pattern to have a chance of matching. A `in` test on a string is a
    #: C-level scan; a regular expression with a character class and a
    #: backtracking point is not, and this module runs thirty-five of them over
    #: every book. On a two-megabyte book that was **0.31 seconds each**, which
    #: nobody notices on one book and everybody notices on two thousand.
    #:
    #: Empty means "no cheap test exists" — `class="[^"]*\bft\d+\b` cannot have
    #: one, because `ft` occurs in *left* and *after* and would filter nothing.
    needles: tuple[str, ...] = ()


@dataclass(frozen=True)
class Trace:
    """One tool that appears to have touched this book."""

    name: str
    confidence: float
    evidence: tuple[str, ...]


#: The signatures, as data. Weights are a judgement and they are written down
#: here so the judgement can be argued with rather than reverse-engineered from
#: behaviour.
#:
#: A weight is roughly "if I saw only this, how sure would I be" — 0.9 for a
#: string only one program writes, 0.6 for a habit shared by a family of tools,
#: 0.3 for a word that also occurs in ordinary language.
SIGNATURES: dict[str, tuple[Signal, ...]] = {
    "calibre": (
        Signal(r"calibre:series", 0.9, "package", "calibre:series", needles=('calibre:series',)),
        Signal(r'class="[^"]*\bcalibre\d+\b', 0.85, "markup", "class=calibreN", needles=('calibre',)),
        Signal(r"\.calibre\d+\b", 0.85, "css", ".calibreN", needles=('calibre',)),
        # `(?!:)` keeps this off `calibre:series` above. The two would otherwise
        # be the same bytes counted as two independent traces, which is how a
        # confidence climbs past what the evidence supports.
        Signal(r"(?i)\bcalibre\b(?!:)", 0.8, "package", "calibre@package", needles=('calibre',)),
        # The bare word anywhere else is weak on purpose: it is a real word and
        # it turns up in books about typesetting.
        Signal(r"(?i)\bcalibre\b(?!:)", 0.3, "any", "calibre", needles=('calibre',)),
    ),
    "indesign": (
        Signal(r"_idGenParaOverride", 0.95, "any", "_idGenParaOverride", needles=('_idgenparaoverride',)),
        Signal(r"_idGenObjectStyle", 0.95, "any", "_idGenObjectStyle", needles=('_idgenobjectstyle',)),
        Signal(r"(?i)InDesign", 0.8, "package", "InDesign@package", needles=('indesign',)),
        Signal(r"(?i)InDesign", 0.35, "any", "InDesign", needles=('indesign',)),
    ),
    "word": (
        Signal(r"\bMsoNormal\b", 0.9, "any", "MsoNormal", needles=('msonormal',)),
        Signal(r"\bmso-[a-z-]+\s*:", 0.85, "any", "mso-*", needles=('mso-',)),
        Signal(r"<o:p>", 0.8, "markup", "<o:p>", needles=('<o:p>',)),
        # Google Docs, which the roadmap puts in this family and which leaves a
        # different trace: `kix` is the name of the editor inside Google.
        Signal(r"\blst-kix_", 0.9, "any", "lst-kix_", needles=('lst-kix_',)),
        Signal(r"\bdocs-internal-guid", 0.9, "any", "docs-internal-guid", needles=('docs-internal-guid',)),
        Signal(r"themes\.googleusercontent\.com", 0.85, "any", "themes.googleusercontent.com", needles=('themes.googleusercontent.com',)),
    ),
    "sigil": (
        Signal(r"(?i)Sigil version", 0.95, "any", "Sigil version", needles=('sigil version',)),
        Signal(r'class="[^"]*\bsgc-', 0.8, "markup", "class=sgc-*", needles=('sgc-',)),
    ),
    "vellum": (
        Signal(r"(?i)\bvellum\b", 0.9, "package", "Vellum@package", needles=('vellum',)),
        # The word for parchment. In a chapter it is prose, not provenance, and
        # scoring it like a generator stamp is how a book about bookbinding
        # comes out of a typesetting program it never went near.
        Signal(r"(?i)\bvellum\b", 0.25, "any", "vellum", needles=('vellum',)),
    ),
    "pressbooks": (
        Signal(r"(?i)pressbooks", 0.9, "any", "pressbooks", needles=('pressbooks',)),
        Signal(r'class="[^"]*\bwp-', 0.4, "markup", "class=wp-*", needles=('wp-',)),
    ),
    "pdf-or-ocr": (
        Signal(r"(?i)ABBYY", 0.9, "any", "ABBYY", needles=('abbyy',)),
        Signal(r"(?i)pdftohtml", 0.9, "any", "pdftohtml", needles=('pdftohtml',)),
        Signal(r"(?i)PDF Reflow conversion", 0.9, "any", "PDF Reflow conversion", needles=('pdf reflow',)),
        Signal(r'class="[^"]*\bft\d+\b', 0.6, "markup", "class=ftN"),
        # What calibre's PDF plugin names the pictures it lifts out — the only
        # trace left once it has rewritten the class names to its own.
        Signal(r"\bindex-\d+_\d+\.(?:png|jpe?g)\b", 0.7, "any", "index-P_N.png", needles=('index-',)),
    ),
    "from-mobi": (
        Signal(r"\bfilepos\d+", 0.9, "any", "filepos", needles=('filepos',)),
        Signal(r"kindle:pos", 0.9, "any", "kindle:pos", needles=('kindle:pos',)),
    ),
    "gutenberg": (
        Signal(r"x-ebookmaker", 0.95, "any", "x-ebookmaker", needles=('x-ebookmaker',)),
        Signal(r"(?i)Project Gutenberg", 0.85, "any", "Project Gutenberg", needles=('project gutenberg',)),
    ),
    "self-publishing": (
        Signal(r"(?i)\b(epubli|lulu\.com|blurb|draft2digital)\b", 0.8, "any",
               "epubli|lulu|blurb|draft2digital", needles=('epubli', 'lulu.com', 'blurb', 'draft2digital')),
    ),
}

_compiled: dict[str, tuple[tuple[re.Pattern, Signal], ...]] = {}


def _patterns(name: str):
    ready = _compiled.get(name)
    if ready is None:
        ready = tuple((re.compile(s.pattern), s) for s in SIGNATURES[name])
        _compiled[name] = ready
    return ready


def _combine(weights: list[float]) -> float:
    """Confidence from several independent traces.

    ``1 - Π(1 - w)``: two weak signals corroborate into something stronger than
    either, and nothing ever reaches certainty from evidence that was not
    certain to begin with. Adding weights would let three guesses outvote a
    fact, and taking the maximum would make corroboration worth nothing.
    """
    survives = 1.0
    for weight in weights:
        survives *= 1.0 - max(0.0, min(1.0, weight))
    # Capped below 1, and not only as arithmetic hygiene. Four strong traces
    # multiply out to 0.9997, which rounds to a flat `1.0` — a report claiming
    # certainty about something that was inferred from regular expressions.
    # Nothing in this module is ever certain and the number should not say it is.
    return min(0.999, round(1.0 - survives, 3))


def identify(*, package: str = "", markup: str = "", css: str = "") -> list[Trace]:
    """Which tools touched this book, most confident first.

    The three texts are kept apart rather than concatenated, because half of
    what a weight means is *where* the trace was allowed to count.
    """
    everything = f"{package}\n{markup}\n{css}"
    haystacks = {"package": package, "markup": markup, "css": css, "any": everything}
    # Lowercased once per place, so the cheap test below is a C-level scan and
    # not thirty-five regular expressions over two megabytes.
    lowered = {place: text.lower() for place, text in haystacks.items()}

    traces: list[Trace] = []
    for name in SIGNATURES:
        # Best weight per *pattern*, not per signal. A pattern usually appears
        # twice — once tied to the package document and once to anywhere — and
        # a package match satisfies both. Counting them separately would treat
        # one trace as two independent ones and make the weakened `any` variant
        # push the confidence back up, which is precisely what writing it down
        # separately was meant to prevent.
        best: dict[str, tuple[float, str]] = {}
        for pattern, signal in _patterns(name):
            haystack = haystacks.get(signal.place, "")
            if signal.needles and not any(
                needle in lowered[signal.place] for needle in signal.needles
            ):
                continue
            if not pattern.search(haystack):
                continue
            current = best.get(signal.pattern)
            if current is None or signal.weight > current[0]:
                best[signal.pattern] = (signal.weight, signal.note)
        if not best:
            continue
        weights = [weight for weight, _ in best.values()]
        evidence = [note for _, note in best.values() if note]
        confidence = _combine(weights)
        if confidence < FLOOR:
            continue
        traces.append(Trace(name, confidence, tuple(evidence)))

    # Confidence first, then name, so two equal answers come out in a stable
    # order and a signature file can be compared between runs.
    traces.sort(key=lambda trace: (-trace.confidence, trace.name))
    return traces


def names(traces: list[Trace]) -> list[str]:
    """Just the names, sorted — what the inventory's `generators` field is."""
    return sorted(trace.name for trace in traces)


def describe(traces: list[Trace]) -> str:
    """One line for a report: ``calibre (0.895), indesign (0.95)``."""
    return ", ".join(f"{trace.name} ({trace.confidence:g})" for trace in traces)
