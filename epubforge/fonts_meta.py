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

The OS/2 table is not the only place a font speaks. On the shelf, 224 of the
391 stacks left without a generic named faces the book *did* embed — TeX Gyre
Heros, Alegreya Sans, Adagio Serif — whose designers left PANOSE at "any" and
`sFamilyClass` at 0. Two more of the font's own declarations are read then:
the fixed-pitch flag of its `post` table, and the family name it carries in
its own `name` table. `Alegreya Sans` saying *sans* is the designer's word as
much as a PANOSE byte is; the whole-word rule keeps `Sansita` and `Serifa`
from passing for declarations. The name written in the CSS is never read for
this — that would be the guess again.
"""

from __future__ import annotations

import re
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


def _table(data: bytes, tag: bytes) -> bytes | None:
    """One raw table of an sfnt by its tag, or None when the file is not a
    readable sfnt or carries no such table."""
    if len(data) < 12 or data[:4] not in _SFNT_MAGIC:
        return None
    try:
        count = struct.unpack(">H", data[4:6])[0]
        for index in range(count):
            record = 12 + index * 16
            if data[record:record + 4] != tag:
                continue
            offset, length = struct.unpack(">II", data[record + 8:record + 16])
            return data[offset:offset + length]
    except (struct.error, IndexError):
        return None
    return None


def _os2_table(data: bytes) -> bytes | None:
    """The raw OS/2 table, or None when the file is not a readable sfnt."""
    table = _table(data, b"OS/2")
    return table if table is not None and len(table) >= 42 else None


def _fixed_pitch(data: bytes) -> bool:
    """`post.isFixedPitch` — non-zero means monospaced, by the font's own word."""
    post = _table(data, b"post")
    if post is None or len(post) < 16:
        return False
    return struct.unpack(">I", post[12:16])[0] != 0


#: `name` table ids: the plain family name, and the typographic family the
#: designer sets when the plain one is a style-split fragment ("Alegreya Sans
#: Medium" is family 1; "Alegreya Sans" is family 16).
_NAME_FAMILY = 1
_NAME_TYPOGRAPHIC_FAMILY = 16


def _family_name(data: bytes) -> str | None:
    """The family name the font carries in its own `name` table.

    The typographic family wins when set, the plain family otherwise. Windows
    and Unicode records are UTF-16; Macintosh ones are read as Latin-1, which
    is exact for every ASCII name and harmless for the rest, since only whole
    ASCII words are looked for in it.
    """
    table = _table(data, b"name")
    if table is None or len(table) < 6:
        return None
    found: dict[int, str] = {}
    try:
        count, storage = struct.unpack(">HH", table[2:6])
        for index in range(count):
            record = table[6 + index * 12:18 + index * 12]
            if len(record) < 12:
                break
            platform, _, _, name_id, length, offset = struct.unpack(">HHHHHH", record)
            if name_id not in (_NAME_FAMILY, _NAME_TYPOGRAPHIC_FAMILY) or name_id in found:
                continue
            raw = table[storage + offset:storage + offset + length]
            if len(raw) < length:
                continue
            try:
                text = raw.decode("utf-16-be") if platform in (0, 3) else raw.decode("latin-1")
            except UnicodeDecodeError:
                continue
            if text.strip():
                found[name_id] = text.strip()
    except struct.error:
        return None
    return found.get(_NAME_TYPOGRAPHIC_FAMILY) or found.get(_NAME_FAMILY)


#: What a family name says in words, when the OS/2 table says nothing in
#: numbers. Whole words only — `Sansita` is not `Sans` and `Serifa` is not
#: `Serif` — and in this order: a monospaced face is monospaced whatever its
#: serifs do (the same precedence PANOSE gets above), and "Sans Serif" is a
#: sans-serif.
_KINDS_BY_WORD: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"mono", "monospace", "monospaced"}), "monospace"),
    (frozenset({"sans"}), "sans-serif"),
    (frozenset({"serif", "slab"}), "serif"),
    (frozenset({"script", "handwriting"}), "cursive"),
)
_WORDS = re.compile(r"[A-Za-z]+")
_CAMEL_SEAM = re.compile(r"(?<=[a-z])(?=[A-Z])")


def _kind_in_name(name: str) -> str | None:
    """The generic a family name declares in words, or None when it declines.

    `AlegreyaSans` is split at its camel-case seam first — a designer who
    wrote the name without a space still wrote *Sans*.
    """
    words = {word.lower() for word in _WORDS.findall(_CAMEL_SEAM.sub(" ", name))}
    for saying, generic in _KINDS_BY_WORD:
        if words & saying:
            return generic
    return None


def _from_os2(data: bytes) -> str | None:
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


def classify(data: bytes) -> str | None:
    """The CSS generic family this font belongs to, or None if it will not say.

    Three of the font's own declarations, in order of precision: the OS/2
    table (PANOSE, then `sFamilyClass`), the `post` table's fixed-pitch flag,
    and the family name in the `name` table. None is a real answer and has to
    stay one. A font whose designer left PANOSE at "any" *and* named it
    nothing that says what it is has declared nothing, and inventing a family
    for it would be exactly the guess this module exists to avoid.
    """
    generic = _from_os2(data)
    if generic:
        return generic
    if _fixed_pitch(data):
        return "monospace"
    name = _family_name(data)
    return _kind_in_name(name) if name else None


#: What everybody already knows about fonts nobody embedded. The shelf's
#: 50 173 stacks without a generic name mostly one font: `"Times New Roman"`
#: alone accounts for 41 913 of them, written by Word into books that embed
#: nothing — so there is no OS/2 table to read, and the module's own rule
#: ("ask the font, don't guess") has nothing to ask. This table is the middle
#: ground the owner delegated: not a guess, but common knowledge — the kind a
#: person answering the question would apply anyway — offered *through* the
#: question queue, never on the program's own authority. Only names the shelf
#: actually showed or their obvious kin. Looked up with spaces, hyphens and
#: underscores ignored, since `TexGyreHeros` in a stylesheet and `TeX Gyre
#: Heros` in a font are the one face and a converter writes it either way.
#:
#: The second wave of names came from the 391 stacks the first wave left: the
#: TeX Gyre family (the Ghostscript clones of Helvetica, Times, Palatino,
#: Bookman, Century Schoolbook, Avant Garde, Courier and Zapf Chancery),
#: Alegreya and Alegreya Sans, Charis SIL, Judson, Aharoni, Berthold's
#: Garamond BE, Adobe's Ex Ponto, and Lucida Handwriting.
WELL_KNOWN_GENERICS: dict[str, str] = {
    # serif
    "times new roman": "serif", "times": "serif", "tms rmn": "serif",
    "georgia": "serif", "garamond": "serif", "book antiqua": "serif",
    "palatino": "serif", "palatino linotype": "serif", "cambria": "serif",
    "cambria math": "serif", "constantia": "serif", "century schoolbook": "serif",
    "new york": "serif", "liberation serif": "serif", "dejavu serif": "serif",
    "minion pro": "serif", "adobe garamond pro": "serif", "baskerville": "serif",
    "bookman old style": "serif", "goudy old style": "serif",
    "garamond be": "serif", "alegreya": "serif", "charis sil": "serif",
    "charis": "serif", "judson": "serif", "tex gyre termes": "serif",
    "tex gyre pagella": "serif", "tex gyre bonum": "serif",
    "tex gyre schola": "serif",
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
    "alegreya sans": "sans-serif", "aharoni": "sans-serif",
    "tex gyre heros": "sans-serif", "tex gyre adventor": "sans-serif",
    # monospace
    "courier": "monospace", "courier new": "monospace",
    "consolas": "monospace", "lucida console": "monospace",
    "monaco": "monospace", "dejavu sans mono": "monospace",
    "liberation mono": "monospace", "tex gyre cursor": "monospace",
    # cursive
    "lucida handwriting": "cursive", "ex ponto": "cursive",
    "ex ponto pro": "cursive", "tex gyre chorus": "cursive",
}

_SPACING = re.compile(r"[\s_-]+")


def _normalized(family: str) -> str:
    return _SPACING.sub("", family.strip().strip("\"'").lower())


_WELL_KNOWN_NORMALIZED = {
    _normalized(family): generic for family, generic in WELL_KNOWN_GENERICS.items()
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
    return _WELL_KNOWN_NORMALIZED.get(_normalized(family))


#: `OS/2.fsType`, the one place a font file states what may be done with it.
#: The bits this program reads, and what each of them costs:
#:
#: * `0x0002` **restricted licence** — the font may not be embedded at all,
#:   so it may certainly not be embedded in a cut-down form;
#: * `0x0004` **preview and print only** — embedding is for looking at and
#:   printing, not for carrying the font onward;
#: * `0x0100` **no subsetting** — the one bit that names *exactly* the
#:   operation this program would perform. It was absent from the shelf
#:   measurement (fsType 0, 8, 12, 4 and 2 were all that appeared), which is
#:   a fact about 491 files and not a licence to skip the check.
#:
#: `0x0008` (editable embedding) and `0x0000` (installable) say nothing
#: against it. None of this makes subsetting *lawful* — fsType speaks about
#: embedding, and the right to modify lives in a text licence no bit
#: carries — which is why the switch is off until a person turns it on.
FSTYPE_RESTRICTED = 0x0002
FSTYPE_PREVIEW_PRINT = 0x0004
FSTYPE_NO_SUBSETTING = 0x0100

#: Offset of `fsType` inside the OS/2 table: version (2) + xAvgCharWidth (2)
#: + usWeightClass (2) + usWidthClass (2).
_FSTYPE_OFFSET = 8


def embedding_flags(data: bytes) -> "int | None":
    """`OS/2.fsType`, or None when the file will not say.

    None is a real answer and stays one: a file this program cannot read is
    a file whose licence it cannot read either, and the caller must treat
    that as a refusal rather than as a zero.
    """
    table = _os2_table(data)
    if table is None or len(table) < _FSTYPE_OFFSET + 2:
        return None
    try:
        return struct.unpack(">H", table[_FSTYPE_OFFSET:_FSTYPE_OFFSET + 2])[0]
    except struct.error:
        return None


def may_be_subset(data: bytes) -> "tuple[bool, str]":
    """Whether this font's own file permits cutting it down, and why not.

    The reason is returned rather than logged because it belongs in the
    report: a font left at full weight in a run that asked for subsetting is
    a decision the person needs to see explained, not a silent omission.
    """
    flags = embedding_flags(data)
    if flags is None:
        return False, "unreadable"
    if flags & FSTYPE_NO_SUBSETTING:
        return False, "no-subsetting"
    if flags & FSTYPE_RESTRICTED:
        return False, "restricted"
    if flags & FSTYPE_PREVIEW_PRINT:
        return False, "preview-print"
    return True, ""
