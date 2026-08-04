"""Optional concessions to particular reader families.

The rebuild targets the specification. Some devices do not, and the gap is not
symmetric: a reader that predates a feature does not fail loudly, it silently
renders the book wrong — a table of contents that is empty, a cover that never
appears, chapters that run together because ``<section>`` meant nothing to it.

Everything in this module is therefore **opt-in and additive**. A measure may
add a file, a declaration or a legacy element; none of them removes or rewrites
anything the book already had, and none of them changes how a conforming
reader renders the result. That is the price of admission: a concession that
could damage the book on correct software is not a concession, it is a
regression, and it does not belong here.

Two consequences follow, and both are stated to the user rather than hidden:

* A measure may leave the book outside the current specification even when no
  validator says so. ``<guide>`` was removed from EPUB 3.3; EPUBCheck 5.x still
  accepts it silently, which makes it a quiet deviation rather than a free one,
  and the person enabling it should know which of the two they are getting.
* A measure is applied only when the book gives it something to do. Declaring
  ``specified-fonts`` for a book that embeds no fonts states a fact that is not
  true, and this tool does not write claims it cannot support — the same rule
  that governs the accessibility metadata.

Nothing here is a fix for a device that refuses a book outright. If a reader
will not open a file at all, the cause is upstream of anything in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

#: Injected as its own stylesheet, linked ahead of the book's own so that any
#: rule the publisher wrote still wins.
HTML5_BLOCK_CSS = """/* Added by EPUB F.O.R.G.E. for readers that predate HTML5.
   Renderers built on Adobe's RMSDK treat an element they do not know as
   inline, which collapses a book built out of <section> and <figure> into one
   running paragraph. Declaring the defaults costs nothing on a modern reader,
   which applies exactly the same values. */
article, aside, details, figcaption, figure, footer, header, hgroup,
main, nav, section, summary { display: block; }
"""

#: Apple Books ignores embedded fonts unless the container says the book has
#: chosen its own. There is no in-package equivalent; it has to be this file.
APPLE_DISPLAY_OPTIONS = """<?xml version="1.0" encoding="UTF-8"?>
<display_options>
  <platform name="*">
    <option name="specified-fonts">true</option>
  </platform>
</display_options>
"""

APPLE_DISPLAY_OPTIONS_PATH = "META-INF/com.apple.ibooks.display-options.xml"

COMPAT_STYLESHEET_NAME = "reader-compat.css"


@dataclass(frozen=True)
class Measure:
    """One concession, and the honest accounting for it."""

    key: str
    #: What is added to the book.
    what: str
    #: Why a device needs it — the failure it prevents.
    why: str
    #: What enabling it costs, or ``None`` when it costs nothing.
    cost: str | None = None


MEASURES: dict[str, Measure] = {
    "ncx": Measure(
        key="ncx",
        what="keeps the EPUB 2 NCX alongside the EPUB 3 navigation document",
        why=(
            "readers that predate EPUB 3 build their chapter list from the NCX and "
            "ignore the navigation document entirely"
        ),
    ),
    "guide": Measure(
        key="guide",
        what="adds the EPUB 2 <guide> element to the package document",
        why=(
            "Amazon's converter and RMSDK-based readers locate the cover and the "
            "start-reading position through <guide>, not through the landmarks nav"
        ),
        cost=(
            "the element is no longer part of EPUB 3.3; EPUBCheck 5.x still accepts it "
            "without complaint, but it is a deviation from the current specification "
            "rather than a feature of it"
        ),
    ),
    "html5-blocks": Measure(
        key="html5-blocks",
        what=f"adds {COMPAT_STYLESHEET_NAME}, declaring the HTML5 sectioning elements as blocks",
        why=(
            "RMSDK-based readers render an unknown element inline, which runs "
            "sections and figures together into one paragraph"
        ),
    ),
    "page-break": Measure(
        key="page-break",
        what="mirrors every break-before/after/inside declaration into its page-break-* equivalent",
        why=(
            "the modern fragmentation properties postdate these renderers, which "
            "understand only the page-break-* spellings and drop the rest"
        ),
    ),
    "apple-fonts": Measure(
        key="apple-fonts",
        what=f"adds {APPLE_DISPLAY_OPTIONS_PATH} declaring specified-fonts",
        why="Apple Books substitutes its own font for every embedded face without it",
    ),
}


@dataclass(frozen=True)
class Profile:
    """A named set of measures, aimed at one family of devices."""

    key: str
    #: The devices this is for, in plain words.
    devices: str
    measures: tuple[str, ...]


PROFILES: dict[str, Profile] = {
    "kindle": Profile(
        key="kindle",
        devices="Amazon Kindle, via Send-to-Kindle or any KFX/KF8 conversion",
        measures=("guide", "html5-blocks", "page-break"),
    ),
    "kobo": Profile(
        key="kobo",
        devices="Rakuten Kobo, reading the EPUB directly rather than a converted KEPUB",
        measures=("ncx", "guide", "html5-blocks"),
    ),
    "apple": Profile(
        key="apple",
        devices="Apple Books on iOS and macOS",
        measures=("apple-fonts",),
    ),
    "legacy": Profile(
        key="legacy",
        devices="Adobe RMSDK readers — PocketBook, Nook, Sony, older Kobo and Onyx",
        measures=("ncx", "guide", "html5-blocks", "page-break"),
    ),
}


def resolve(names: Iterable[str]) -> tuple[set[str], list[str]]:
    """Expand profile names into measures, reporting any that are not known."""
    measures: set[str] = set()
    unknown: list[str] = []
    for raw in names:
        name = raw.strip().lower()
        if not name:
            continue
        profile = PROFILES.get(name)
        if profile is None:
            unknown.append(raw)
            continue
        measures.update(profile.measures)
    return measures, unknown


def profiles_needing(measure: str) -> list[str]:
    """Which profiles ask for *measure*. Used when explaining a report entry."""
    return sorted(key for key, profile in PROFILES.items() if measure in profile.measures)


#: ``epub:type`` → the OPF 2 ``guide`` reference type that matches it. Only the
#: OPF 2.0.1 vocabulary is emitted: a type outside it would be as meaningless to
#: a legacy reader as the landmark it came from.
GUIDE_TYPES = {
    "cover": "cover",
    "titlepage": "title-page",
    "toc": "toc",
    "bodymatter": "text",
    "acknowledgments": "acknowledgements",
    "acknowledgements": "acknowledgements",
    "bibliography": "bibliography",
    "colophon": "colophon",
    "copyright-page": "copyright-page",
    "dedication": "dedication",
    "epigraph": "epigraph",
    "foreword": "foreword",
    "glossary": "glossary",
    "index": "index",
    "loi": "loi",
    "lot": "lot",
    "preface": "preface",
}

_DEFAULT_GUIDE_TITLES = {
    "cover": "Cover",
    "title-page": "Title Page",
    "toc": "Table of Contents",
    "text": "Beginning",
}


def guide_references(book) -> list[tuple[str, str, str]]:
    """``(type, title, target)`` triples for a legacy ``<guide>``.

    Derived from the landmarks the navigation stage already established, so the
    legacy element and the EPUB 3 one can never disagree about where the cover
    or the start of the text is.
    """
    references: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for landmark in book.landmarks:
        guide_type = GUIDE_TYPES.get(landmark.epub_type)
        if guide_type is None or guide_type in seen:
            continue
        target = landmark.target
        if not target or target.split("#")[0] not in book.resources:
            continue
        title = landmark.label or _DEFAULT_GUIDE_TITLES.get(
            guide_type, guide_type.replace("-", " ").title()
        )
        references.append((guide_type, title, target))
        seen.add(guide_type)

    if "toc" not in seen and book.nav_path:
        references.append(("toc", _DEFAULT_GUIDE_TITLES["toc"], book.nav_path))
    return references


__all__ = [
    "APPLE_DISPLAY_OPTIONS",
    "APPLE_DISPLAY_OPTIONS_PATH",
    "COMPAT_STYLESHEET_NAME",
    "GUIDE_TYPES",
    "HTML5_BLOCK_CSS",
    "MEASURES",
    "PROFILES",
    "Measure",
    "Profile",
    "guide_references",
    "profiles_needing",
    "resolve",
]
