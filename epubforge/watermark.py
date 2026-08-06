"""Recognising publisher watermarks — the marks stay, the damage goes.

Polish and other European retailers apply "social DRM": a per-purchase token
stamped into the file so a leaked copy can be traced back to the buyer. That is
the publisher's right and this tool never removes it.

What it does remove is the collateral damage. The common implementation is a
``<div style="font-size:1px !important">TOKEN</div>`` repeated at the end of
every single document — 34 copies in one book measured here — which means:

* the token sits in the reading order, so a screen reader spells out
  "N-z-g-x-M-j-I-0…" at the end of every chapter;
* an ``!important`` inline style is duplicated once per document;
* the one-pixel text still generates a line box at the foot of each chapter.

None of that is required for the mark to work. Consolidating the styling and
hiding the token from assistive technology leaves it fully intact and
extractable, while the book stops paying for it.
"""

from __future__ import annotations

import re

#: Class added to every normalised marker so the styling lives in one rule.
MARKER_CLASS = "epubforge-watermark"

#: The rule that replaces the repeated inline styles.
#: Zero rather than one pixel, because publishers hide these at 0pt as often
#: as at 1px and the replacement must never be *more* visible than what it
#: replaces. Collapsing the line height also removes the stray blank line the
#: original left at the foot of every chapter.
MARKER_RULE = (
    f"\n/* Watermark markers, styling consolidated by EPUB-Forge. "
    f"The tokens themselves are untouched. */\n"
    f".{MARKER_CLASS} {{ font-size: 0 !important; line-height: 0 !important; }}\n"
)

#: A watermark payload: one unbroken run of token characters, long enough not
#: to be a word, mixing letters and digits the way an encoded id does.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9+/=_-]{10,120}$")

#: A font-size declaration, captured whole so the value can be compared
#: numerically. Matching the digits loosely is not good enough: an unanchored
#: pattern happily reads "10px" as "1" and "0.9em" as "0", which would drag
#: ordinary small print into the watermark path.
_FONT_SIZE_RE = re.compile(
    r"font-size\s*:\s*(?P<value>\d*\.?\d+)\s*(?P<unit>px|pt|em|rem|%)?\s*"
    r"(?:!\s*important)?\s*(?:;|$)",
    re.IGNORECASE,
)
_HIDDEN_RE = re.compile(
    r"(display\s*:\s*none|visibility\s*:\s*hidden)", re.IGNORECASE
)

#: Absolute sizes at or below this are unreadable by design, not just small.
#: Only absolute units qualify — em and % are how publishers set legitimate
#: small print, and 0.6em is a chapter number, not a hidden token.
_UNREADABLE_ABSOLUTE = {"px": 2.0, "pt": 2.0}

#: Phrases that mark a *visible* watermark notice, which is meant to be seen and
#: is therefore never restyled — only reported.
_NOTICE_PHRASES = (
    "watermark", "znak wodny", "znakiem wodnym", "electronic watermark",
    "order ##", "zamówienie nr", "nr zamówienia", "this document is protected",
    "dokument jest chroniony", "kopia dla", "licensed to",
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def is_token(text: str) -> bool:
    """True when *text* looks like an opaque identifier rather than prose."""
    candidate = text.strip()
    if not _TOKEN_RE.match(candidate):
        return False
    # Prose and filenames fail one of these; encoded ids pass both.
    has_letter = any(c.isalpha() for c in candidate)
    has_digit = any(c.isdigit() for c in candidate)
    return has_letter and has_digit


def is_negligibly_styled(style: str) -> bool:
    """True when an inline style makes the element effectively unreadable."""
    if not style:
        return False
    if _HIDDEN_RE.search(style):
        return True
    for match in _FONT_SIZE_RE.finditer(style):
        unit = (match.group("unit") or "").lower()
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        if value == 0:
            return True
        if unit in _UNREADABLE_ABSOLUTE and value <= _UNREADABLE_ABSOLUTE[unit]:
            return True
    return False


def is_visible_notice(text: str) -> bool:
    """True for a human-readable watermark statement, which must be left alone."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in _NOTICE_PHRASES)


def marks(markup: str) -> tuple[int, int]:
    """How many watermark notices and opaque markers a document carries.

    One definition, used by the pipeline and by the inventory both. The
    inventory had its own, narrower one — it looked for visible notices only
    and recorded the answer in a field called `watermarked`, which said "no"
    about 28 books out of 32 that carried a marker the pipeline could see and
    consolidate. Two implementations of one idea, and the shorter one was
    wrong; measuring a thing twice is how a coverage report comes to disagree
    with the program it is reporting on.

    Text-level rather than parsed, because the inventory has the markup as a
    string and refuses to build a second document tree for a count.
    """
    notices = markers = 0
    for match in _LEAF.finditer(markup):
        text = (match.group("text") or "").strip()
        if not text:
            continue
        # A notice is defined by what it says, so it counts wherever it sits —
        # styled or not. A marker is defined by being unreadable, so it needs
        # the style. Notices are checked first, exactly as the pipeline does:
        # a styled sentence a buyer is meant to read is not an opaque token.
        if is_visible_notice(text):
            notices += 1
            continue
        found = _STYLE.search(match.group("attributes") or "")
        style = found.group(1) if found else ""
        if is_token(text) and is_negligibly_styled(style):
            markers += 1
    return notices, markers


#: An element carrying text and no child elements — the shape both a marker and
#: a notice take. The attributes are captured whole and `style` picked out of
#: them afterwards: an optional group inside the tag pattern matches the empty
#: string against a tag that *does* carry a style, which silently scored every
#: marker as unstyled and therefore as nothing at all.
_LEAF = re.compile(r"<[a-zA-Z][a-zA-Z0-9]*(?P<attributes>[^>]*)>(?P<text>[^<>]{1,400})</")
_STYLE = re.compile(r"\bstyle=\"([^\"]*)\"")


def personal_data(text: str) -> list[str]:
    """Any e-mail addresses carried in a watermark notice."""
    return _EMAIL_RE.findall(text)
