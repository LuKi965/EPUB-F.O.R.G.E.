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

None of that is required for the mark to work, so there is a choice to make
about where the token lives, and :data:`MODES` is that choice.

The first answer this tool gave was ``consolidate``: one CSS rule instead of
thirty-four inline styles, plus ``aria-hidden`` so assistive software skips the
token. That claim was too confident. ``aria-hidden`` binds a conforming
accessibility tree; it does not bind the text-to-speech engine built into a
reader, which happily reads whatever it finds laid out on the page — and a
token at ``font-size: 0`` is still laid out. The owner said so plainly, and he
is right: a marker that gets spoken aloud at the end of every chapter breaks
the book, whichever pixel size it is set at.

Hence ``gather``: the token moves out of the body altogether and into the
document's own ``<head>`` as a ``<meta>``. Nothing renders it, nothing speaks
it, nothing paginates around it, and it is still there — in the same file, in
the same document, one grep away — which is everything the mark was for. And
hence ``remove``, which does not keep it, for people who have decided that for
themselves.

Neither is the default, and the reason is K1: *no character of the book's text
is lost*. Taking the token out of the reading order loses a character of the
reading order — it is a small and deliberate loss with a good argument behind
it, and it is still a loss, so it is a choice somebody makes rather than one
that is made for them. The default does the most that can be done without
touching the text.
"""

from __future__ import annotations

import re

#: What may be done with an opaque marker, least invasive first.
#:
#: * ``keep`` — the markup comes out as it went in.
#: * ``consolidate`` — the token stays where it is; the repeated inline styling
#:   becomes one rule and the element is hidden from the accessibility tree.
#: * ``gather`` — the token moves to ``<head>`` as document metadata.
#: * ``remove`` — the token is deleted.
#:
#: Only the last one loses anything, and it is never a default anywhere: the
#: owner's standing rule is that whatever the application deletes must be
#: something a person chose, not something that happened to them.
MODES = ("keep", "consolidate", "gather", "remove")

#: Where a gathered token goes. A metadata name of our own rather than one of
#: the registered ones, so nothing else can mistake it for a claim about the
#: document; EPUBCheck accepts it, which was checked before it shipped (on 5.2.1,
#: and again on 5.3.0 when the bundled validator moved).
META_NAME = "epubforge-watermark"

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

#: Phrases that name the *shop's* per-purchase debris, as opposed to anything a
#: publisher put in the book on purpose (WP-17 / D-019).
#:
#: This tuple is the whole feature. Everything else in WP-17 is plumbing; the
#: question that decides whether a book comes out whole or damaged is whether a
#: given sentence is the shop talking about a transaction or the publisher
#: talking about the book, and these phrases are the answer.
#:
#: **What they all have in common:** every one of them names *the sale* — an
#: order, a purchase, a licence, a buyer, a copy made for somebody. That is the
#: line. A publisher's colophon carries an address, a telephone number, an
#: e-mail and an ISBN, and it names *the publisher*, never the transaction, so
#: it matches none of these and must not. That is not a happy accident: it is
#: measured against a real colophon in Book 2, which carries an editorial
#: address, a phone number, `biuro@…` and an ISBN, and is kept.
#:
#: **What is deliberately not here,** and each omission cost a candidate phrase:
#:
#: * bare `"kopia"` / `"copy"` — "kopia redakcyjna", "review copy" are the
#:   publisher's own words, and "copy" appears in "copyright" on every book;
#: * bare `"e-mail"` or an address on its own — the colophon has one;
#: * bare `"licencja"` / `"license"` — a Creative Commons book says it about
#:   itself, and Project Gutenberg says it at length in every volume;
#: * `"wszelkie prawa zastrzeżone"` — that is the publisher's copyright notice
#:   and removing it would be removing the copyright page.
_SHOP_PHRASES = (
    # English — the wording used by the shops on the owner's shelf.
    "this document is protected using an electronic watermark",
    "this document is protected",
    "electronic watermark",
    "order ##",
    "order number",
    "licensed to",
    "purchased by",
    "generated for",
    "sold to",
    "this copy was prepared for",
    # Polish.
    "zamówienie nr",
    "nr zamówienia",
    "numer zamówienia",
    "zakupione dla",
    "zakupione przez",
    # Inflections, because Polish has them and a shop writes whichever fits its
    # sentence. Each one widens the net and therefore the risk, so only the
    # forms that cannot mean anything but a sale are here.
    "zakupiony przez",
    "zakupiona przez",
    "wygenerowane dla",
    "wygenerowano dla",
    "przygotowane dla",
    "egzemplarz dla",
    "kopia dla",
    "znak wodny",
    "znakiem wodnym",
    "dokument jest chroniony",
    "dokument zabezpieczony",
)


def is_shop_notice(text: str) -> bool:
    """True when *text* is the shop talking about a purchase.

    The narrower half of :func:`is_visible_notice`, and the one that is allowed
    to delete something. Both look at the same sentences; this one has to be
    right about a publisher's colophon, because the cost of a false positive
    here is a page of somebody's book.
    """
    lowered = " ".join(text.lower().split())
    return any(phrase in lowered for phrase in _SHOP_PHRASES)


#: How a notice is broken up before being judged. A shop stamps its sentence
#: into the running text — in Book 1 directly in front of the book's first
#: sentence — so judging a whole paragraph at once would either miss it or take
#: the opening line of the novel with it. Line breaks and sentence ends both
#: count, because the stamp arrives as its own line about as often as its own
#: sentence.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

#: What the shop writes *after* its phrase, and what may be swept up with it: an
#: order number, a masked address, a reference in brackets. Recognised by
#: carrying a digit, an `@` or a `#` — the marks of an identifier rather than of
#: prose. Deliberately not "the rest of the line": in Book 1 the rest of the line
#: is the first sentence of the novel.
_STAMP_TAIL = re.compile(r"^[\s.,:;–—-]*(?:\S*[\d@#]\S*[\s.,:;]*)+")

#: Whether what is left of a piece is somebody's writing rather than the tail of
#: a stamp. Three words or more, one of them an ordinary lower-case word — which
#: `Jan Kowalski` is not, and `był chłodny, jasny dzień kwietnia` is.
_PROSE_WORD = re.compile(r"\b[a-ząćęłńóśźż]{3,}\b")


def _looks_like_prose(text: str) -> bool:
    return len(text.split()) >= 3 and bool(_PROSE_WORD.search(text))


def without_shop_notices(text: str) -> "tuple[str, list[str]]":
    """*text* with the shop's sentences taken out, and the list of what went.

    The hard case is the one this was first written wrong for, and the test that
    caught it is the one that matters most in `test_shop_notices.py`. In Book 1
    the stamp is glued to the opening of the novel with no sentence break
    between them:

        Order ##46932 (l***k@…) Był chłodny, jasny dzień kwietnia.

    Splitting on sentence ends leaves that as **one** piece, it matches
    `order ##`, and dropping the piece takes the first line of the book. So a
    matching piece is not dropped wholesale. What goes is the shop's phrase plus
    the identifiers trailing it — the order number, the address in brackets —
    and whatever is left is examined again: prose stays, a leftover that is not
    prose (`Jan Kowalski` after `Zakupione dla:`) goes with the stamp.

    The rule is deliberately conservative in one direction. Leaving a buyer's
    name behind is a blemish somebody can see and report; deleting a sentence of
    the novel is damage they may not notice until they read that page. So where
    it is unsure, text stays.

    Returns the surviving text and the exact fragments removed — because "3
    fragments removed" is not something anybody can check, and this is the one
    feature in the program that deletes a person's book.
    """
    kept: list[str] = []
    removed: list[str] = []
    for piece in _SENTENCE_SPLIT.split(text):
        piece = piece.strip()
        if not piece:
            continue
        if not is_shop_notice(piece):
            kept.append(piece)
            continue

        lowered = " ".join(piece.lower().split())
        starts = [lowered.find(p) for p in _SHOP_PHRASES if p in lowered]
        # Measured on the normalised copy, so the index is only usable when the
        # piece has no runs of whitespace to collapse. It rarely does; where it
        # does, the whole piece is treated as the stamp, which is the same
        # answer the prose check below would reach anyway.
        at = min(starts) if starts and len(lowered) == len(piece) else 0
        head = piece[:at].strip()
        body = piece[at:]

        phrase_text = ""
        for phrase in _SHOP_PHRASES:
            if body.lower().startswith(phrase):
                phrase_text = body[: len(phrase)]
                break
        after = body[len(phrase_text):]
        swept = _STAMP_TAIL.match(after)
        stamp_tail = after[: swept.end()] if swept else ""
        rest = after[len(stamp_tail):].strip()
        keeping = _looks_like_prose(rest)

        # Assembled from what was actually taken rather than measured back from
        # what survived. The first version subtracted the survivor's length from
        # the piece, which reported `Zakupione dla` while `Jan Kowalski` had also
        # gone — an understatement in the one message whose entire job is to let
        # somebody check this feature.
        # The same question asked of the words in front of the phrase. A stamp
        # written mid-sentence — "Ten egzemplarz zakupiony przez …" — leaves a
        # head that is a piece of the shop's own sentence, not of the book, and
        # keeping it strands two words in the middle of a page. Prose in front
        # of the phrase is somebody's writing and stays.
        holding = _looks_like_prose(head)
        taken = (
            ("" if holding else head)
            + (" " if head and not holding else "")
            + phrase_text
            + stamp_tail
            + ("" if keeping else rest)
        ).strip()
        if taken:
            removed.append(taken)
        for survivor in (head if holding else "", rest if keeping else ""):
            if survivor:
                kept.append(survivor)
    return " ".join(kept), removed


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
