"""Ask an embedded font what kind of font it is, instead of guessing.

A stack ending in a named font and no generic family is a real weakness: when
the named font fails to load — and on an e-reader it often does — the reader
falls back to whatever it feels like. Calibre calls it an error; this tool
reported it and left it alone, on the ground that choosing between `serif` and
`sans-serif` from a font's *name* is guesswork, and guessing at somebody's
typography is how a tool that means well ruins a book.

The premise was wrong. When the book embeds the font, the answer is not a guess
and never was: it is written in the font's own OS/2 table, which every
TrueType and OpenType file carries because Windows needs it for font
substitution. PANOSE — ten bytes the type designer filled in — says whether the
letters have serifs and whether the font is monospaced, and `sFamilyClass` says
the same thing again in a coarser way.

So the stack gains the generic family **the font declares about itself**. Where
the font is not embedded, nothing is added, because then it really would be a
guess.

Only bare sfnt files are read — `.ttf` and `.otf`. WOFF wraps the same tables
in per-table compression, and decompressing a font to answer a styling question
is more machinery than the answer is worth.
"""

from __future__ import annotations

import struct

#: PANOSE byte 1, the serif style, for a Latin text font. 11, 12 and 13 are the
#: three sans-serif entries; everything else in the range describes a shape of
#: serif. 0 ("any") and 1 ("no fit") mean the designer declined to say.
_SANS_SERIF_STYLES = frozenset({11, 12, 13})
_SERIF_STYLES = frozenset({2, 3, 4, 5, 6, 7, 8, 9, 10})

#: 14 (Flared) and 15 (Rounded) are deliberately in neither set. They describe
#: how a stem *ends*, not whether the letter has a serif, and sans-serif
#: families use them: Lato is 15 and is as sans-serif as a font gets. Reading
#: them as serifs is the first thing this module got wrong, on the first real
#: font it was pointed at. They fall through to `sFamilyClass`, which says 8 —
#: sans-serif — and is right.
_AMBIGUOUS_STYLES = frozenset({14, 15})

#: PANOSE byte 3, the proportion. 9 is monospaced, and a monospaced font is
#: monospaced whatever its serifs do.
_MONOSPACED = 9

#: The high byte of `sFamilyClass`, used when PANOSE says nothing. 8 is the
#: sans-serif class; 1 through 7 are the serif classes; 10 is script.
_CLASS_SANS = 8
_CLASS_SERIF = frozenset({1, 2, 3, 4, 5, 6, 7})
_CLASS_SCRIPT = 10

_SFNT_MAGIC = (b"\x00\x01\x00\x00", b"true", b"ttcf", b"OTTO")


def _os2_table(data: bytes) -> bytes | None:
    """The raw OS/2 table, or None when the file is not a readable sfnt."""
    if len(data) < 12 or data[:4] not in _SFNT_MAGIC:
        return None
    try:
        count = struct.unpack(">H", data[4:6])[0]
        for index in range(count):
            record = 12 + index * 16
            tag = data[record:record + 4]
            if tag != b"OS/2":
                continue
            offset, length = struct.unpack(">II", data[record + 8:record + 16])
            table = data[offset:offset + length]
            return table if len(table) >= 42 else None
    except (struct.error, IndexError):
        return None
    return None


def classify(data: bytes) -> str | None:
    """The CSS generic family this font belongs to, or None if it will not say.

    None is a real answer and has to stay one. A font whose designer left
    PANOSE at "any" has declared nothing, and inventing a family for it would
    be exactly the guess this module exists to avoid.
    """
    table = _os2_table(data)
    if table is None:
        return None
    family_class = table[30]  # high byte of sFamilyClass
    panose = table[32:42]

    if panose[3] == _MONOSPACED:
        return "monospace"
    if panose[0] == 3:  # Latin Hand Written
        return "cursive"
    if panose[0] in (2, 4):  # Latin Text, Latin Decorative
        if panose[1] in _SANS_SERIF_STYLES:
            return "sans-serif"
        if panose[1] in _SERIF_STYLES:
            return "serif"

    if family_class == _CLASS_SANS:
        return "sans-serif"
    if family_class in _CLASS_SERIF:
        return "serif"
    if family_class == _CLASS_SCRIPT:
        return "cursive"
    return None


#: What everybody already knows about fonts nobody embedded. The shelf's
#: 50 173 stacks without a generic name mostly one font: `"Times New Roman"`
#: alone accounts for 41 913 of them, written by Word into books that embed
#: nothing — so there is no OS/2 table to read, and the module's own rule
#: ("ask the font, don't guess") has nothing to ask. This table is the middle
#: ground the owner delegated: not a guess, but common knowledge — the kind a
#: person answering the question would apply anyway — offered *through* the
#: question queue, never on the program's own authority. Names normalized to
#: lower case; only names the shelf actually showed or their obvious kin.
WELL_KNOWN_GENERICS: dict[str, str] = {
    # serif
    "times new roman": "serif", "times": "serif", "tms rmn": "serif",
    "georgia": "serif", "garamond": "serif", "book antiqua": "serif",
    "palatino": "serif", "palatino linotype": "serif", "cambria": "serif",
    "cambria math": "serif", "constantia": "serif", "century schoolbook": "serif",
    "new york": "serif", "liberation serif": "serif", "dejavu serif": "serif",
    "minion pro": "serif", "adobe garamond pro": "serif", "baskerville": "serif",
    "bookman old style": "serif", "goudy old style": "serif",
    # sans-serif
    "arial": "sans-serif", "arial unicode ms": "sans-serif",
    "helvetica": "sans-serif", "helv": "sans-serif", "verdana": "sans-serif",
    "tahoma": "sans-serif", "calibri": "sans-serif", "segoe ui": "sans-serif",
    "trebuchet ms": "sans-serif", "franklin gothic": "sans-serif",
    "franklin gothic medium": "sans-serif", "futura": "sans-serif",
    "geneva": "sans-serif", "lucida sans": "sans-serif",
    "lucida sans unicode": "sans-serif", "liberation sans": "sans-serif",
    "dejavu sans": "sans-serif", "corbel": "sans-serif", "candara": "sans-serif",
    "optima": "sans-serif", "gill sans": "sans-serif",
    # monospace
    "courier": "monospace", "courier new": "monospace",
    "consolas": "monospace", "lucida console": "monospace",
    "monaco": "monospace", "dejavu sans mono": "monospace",
    "liberation mono": "monospace",
}

#: Symbol and dingbat faces get no question at all: appending `fantasy` to
#: Wingdings would promise readers a substitute that draws pictures, and no
#: generic family does. Left alone, counted, named in the report.
SYMBOL_FAMILIES: frozenset = frozenset({
    "wingdings", "wingdings 2", "wingdings 3", "webdings", "symbol",
    "marlett", "zapf dingbats", "zapfdingbats", "system",
})


def well_known(family: str) -> "str | None":
    """The generic common knowledge assigns to *family*, or None."""
    return WELL_KNOWN_GENERICS.get(family.strip().strip("\"'").lower())
