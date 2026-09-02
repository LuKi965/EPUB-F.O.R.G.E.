"""What kind of font is this — asked of the font, not of its name.

A stack ending in a named font and no generic family is a real weakness, and
the tool reported it and left it alone because picking `serif` or `sans-serif`
from a name is guesswork. Wherever the book embeds the font it is not: the
answer is in the font's own OS/2 table.
"""

from __future__ import annotations

import glob
import pathlib

import pytest

from epubforge import fonts_meta


def system_font(*names) -> bytes | None:
    found = {
        pathlib.Path(path).name: path
        for path in glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
    }
    for name in names:
        if name in found:
            return pathlib.Path(found[name]).read_bytes()
    return None


def what_the_font_declares(data: bytes) -> "tuple[int, int, int] | None":
    """`(panose family kind, panose serif style, sFamilyClass)` — the classifier's
    whole input, read straight out of the font.

    DELTA-2026-08-15-001 measured this file at 23 passed and **1 failed** on its
    own container, while it was 23 passed and 1 skipped here. Both numbers are
    the same defect: a test that reaches into `/usr/share/fonts` for "Lato" is
    asserting something about whatever file the host happens to have under that
    name. Absent, it asserted nothing and reported a pass; different, it failed
    and looked like a defect in this program.

    A test may not decide whether the case it is about is even present by
    trusting a filename. It reads the two fields the classifier reads, and
    asserts only when the host's font really is an example of the case.
    """
    table = fonts_meta._os2_table(data)
    if table is None:
        return None
    return table[32], table[33], table[30]


class TestItReadsTheFontRatherThanTheName:
    @pytest.mark.parametrize(
        "names, expected",
        [
            (("DejaVuSerif.ttf",), "serif"),
            (("DejaVuSans.ttf",), "sans-serif"),
            (("DejaVuSansMono.ttf", "SourceCodePro-Regular.ttf"), "monospace"),
        ],
    )
    def test_a_real_font_says_what_it_is(self, names, expected):
        """Same reasoning as the Lato case below: the host supplies an example
        or it does not, and a font that declares something other than the case
        under test is not evidence about this program either way."""
        data = system_font(*names)
        if data is None:
            pytest.skip(f"none of {names} installed here")
        declared = what_the_font_declares(data)
        if declared is None:
            pytest.skip(f"{names[0]} here carries no readable OS/2 table")
        assert fonts_meta.classify(data) == expected, (
            f"{names[0]} on this host declares PANOSE {declared[0]}/{declared[1]} "
            f"and sFamilyClass {declared[2]}"
        )

    def test_a_rounded_sans_is_not_a_serif(self):
        """The first thing this got wrong, on the first real font it met. PANOSE
        serif styles 14 (Flared) and 15 (Rounded) describe how a stem *ends*,
        not whether the letter has a serif, and sans-serif families use them —
        Lato is 15 and is as sans-serif as a font gets. They fall through to
        `sFamilyClass`, which says 8, and is right.

        The rule itself is asserted on built bytes further down this file, where
        it holds on every machine. What this adds is the only thing a real font
        can add and a built one cannot: that the combination occurs *in the
        wild*. So it checks that the host's font is genuinely an example before
        asserting anything about it — a file called `Lato-Regular.ttf` that
        declares something else is a different font, not a failure here.
        """
        data = system_font("Lato-Regular.ttf", "Lato-Light.ttf")
        if data is None:
            pytest.skip("no Lato installed here; the rule is asserted on built bytes")
        declared = what_the_font_declares(data)
        if declared is None:
            pytest.skip("the Lato installed here carries no readable OS/2 table")
        kind, serif_style, family_class = declared
        if not (kind in (2, 4) and serif_style in (14, 15) and family_class == 8):
            pytest.skip(
                "the Lato installed here is not an example of this case: it "
                f"declares PANOSE {kind}/{serif_style} and sFamilyClass "
                f"{family_class}"
            )
        assert fonts_meta.classify(data) == "sans-serif"


def _sfnt_of(tables: "dict[bytes, bytes]") -> bytes:
    """An sfnt made of exactly these tables, in this order."""
    import struct

    header = struct.pack(">4sHHHH", b"\x00\x01\x00\x00", len(tables), 16, 0, 0)
    offset = 12 + 16 * len(tables)
    records = b""
    body = b""
    for tag, table in tables.items():
        # tag, checksum, offset, length — the sixteen bytes of a table record.
        records += struct.pack(">4sIII", tag, 0, offset + len(body), len(table))
        body += table
    return header + records + body


def name_table(*families: "tuple[int, str]", platform: int = 3) -> bytes:
    """A `name` table with these `(name id, text)` records. Platform 3 is
    Windows, stored as UTF-16; platform 1 is Macintosh, stored as Latin-1."""
    import struct

    strings = b""
    records = b""
    for name_id, text in families:
        encoded = text.encode("utf-16-be" if platform in (0, 3) else "latin-1")
        records += struct.pack(">HHHHHH", platform, 1, 0x409, name_id, len(encoded), len(strings))
        strings += encoded
    header = struct.pack(">HHH", 0, len(families), 6 + len(records))
    return header + records + strings


def post_table(*, fixed_pitch: bool) -> bytes:
    import struct

    table = bytearray(32)
    struct.pack_into(">I", table, 12, 1 if fixed_pitch else 0)
    return bytes(table)


def sfnt(
    *,
    panose: "tuple[int, ...] | None",
    family_class: int = 0,
    family: "str | None" = None,
    typographic_family: "str | None" = None,
    fixed_pitch: "bool | None" = None,
    name_platform: int = 3,
) -> bytes:
    """A minimal sfnt carrying an OS/2 table and the two fields read from it —
    and, when asked, a `name` table and a `post` table, the two other places
    the classifier reads once OS/2 has declined. `panose=None` leaves the
    OS/2 table out altogether.

    The tests above are the ones worth having and the ones that cannot be
    relied on: they need a font the machine may not have, and on a machine
    without it they skip. Measured on the audit's own container, that is every
    case in this file except three — so `classify` shipped with the branch
    coverage of a comment.

    A synthetic font is not a substitute for a real one and is not offered as
    one; the real fonts stay. It is the difference between "this ran nowhere"
    and "this ran everywhere, and on real Lato as well where Lato exists".
    """
    import struct

    tables: dict[bytes, bytes] = {}
    if panose is not None:
        table = bytearray(96)
        struct.pack_into(">h", table, 30, family_class << 8)
        table[32:32 + len(panose)] = bytes(panose)
        tables[b"OS/2"] = bytes(table)
    names = []
    if family is not None:
        names.append((1, family))
    if typographic_family is not None:
        names.append((16, typographic_family))
    if names:
        tables[b"name"] = name_table(*names, platform=name_platform)
    if fixed_pitch is not None:
        tables[b"post"] = post_table(fixed_pitch=fixed_pitch)
    return _sfnt_of(tables)


#: PANOSE for a Latin text font, with the serif style left to the caller.
def text_panose(serif_style: int, proportion: int = 4) -> "tuple[int, ...]":
    return (2, serif_style, 5, proportion, 0, 0, 0, 0, 0, 0)


class TestItClassifiesWithoutAskingTheMachineForFonts:
    """Every branch of `classify`, on fonts this file builds.

    BA-2026-004: two tests depended on host state. This is the font half. The
    finding said the test picks a system Lato and assumes its metadata; the
    sharper version is that on a host with no Lato it asserts nothing at all and
    reports a pass, which is how a classifier keeps its coverage while losing
    it.
    """

    @pytest.mark.parametrize(
        "serif_style, expected",
        [(11, "sans-serif"), (12, "sans-serif"), (13, "sans-serif"),
         (2, "serif"), (5, "serif"), (10, "serif")],
    )
    def test_the_panose_serif_style_decides(self, serif_style, expected):
        assert fonts_meta.classify(sfnt(panose=text_panose(serif_style))) == expected

    @pytest.mark.parametrize("serif_style", [14, 15])
    def test_flared_and_rounded_fall_through_to_the_family_class(self, serif_style):
        """The defect this module was written around, now testable without
        owning Lato. 14 and 15 describe how a stem ends, not whether there is a
        serif, and a sans-serif family may declare either."""
        font = sfnt(panose=text_panose(serif_style), family_class=8)
        assert fonts_meta.classify(font) == "sans-serif"
        assert fonts_meta.classify(sfnt(panose=text_panose(serif_style), family_class=3)) == "serif"

    def test_monospaced_beats_the_serifs(self):
        """Proportion 9 with a serif style set: a monospaced font is monospaced
        whatever its serifs are doing."""
        assert fonts_meta.classify(sfnt(panose=text_panose(2, proportion=9))) == "monospace"

    def test_hand_written_is_cursive(self):
        assert fonts_meta.classify(sfnt(panose=(3, 0, 0, 0, 0, 0, 0, 0, 0, 0))) == "cursive"

    @pytest.mark.parametrize(
        "family_class, expected",
        [(8, "sans-serif"), (1, "serif"), (7, "serif"), (10, "cursive")],
    )
    def test_the_family_class_answers_when_panose_says_nothing(self, family_class, expected):
        font = sfnt(panose=(0,) * 10, family_class=family_class)
        assert fonts_meta.classify(font) == expected

    def test_a_font_that_declares_nothing_gets_no_family_invented_for_it(self):
        assert fonts_meta.classify(sfnt(panose=(0,) * 10, family_class=0)) is None

    def test_a_decorative_face_is_read_the_same_way_as_a_text_face(self):
        assert fonts_meta.classify(sfnt(panose=(4, 11, 5, 4, 0, 0, 0, 0, 0, 0))) == "sans-serif"


SILENT = (0,) * 10  # PANOSE "any" throughout: the designer declined to say


class TestTheNameIsAlsoTheFontsWord:
    """The shelf's second wave: 224 of 391 leftover stacks named faces the book
    embedded whose OS/2 table was blank. Two more of the font's own
    declarations are read then — the `post` fixed-pitch flag and the family
    name in the `name` table — and the name written in the CSS still never
    is."""

    @pytest.mark.parametrize(
        "family, expected",
        [
            ("Alegreya Sans", "sans-serif"),
            ("Adagio_Serif", "serif"),
            ("Roboto Slab", "serif"),
            ("Liberation Mono", "monospace"),
            ("Lucida Handwriting", "cursive"),
            ("Brush Script", "cursive"),
        ],
    )
    def test_a_blank_os2_falls_through_to_the_family_name(self, family, expected):
        assert fonts_meta.classify(sfnt(panose=SILENT, family=family)) == expected

    def test_a_camel_cased_name_still_says_sans(self):
        """A designer who wrote `AlegreyaSans` without the space still wrote
        *Sans*. The mutation that matches only space-separated words fails
        here."""
        assert fonts_meta.classify(sfnt(panose=SILENT, family="AlegreyaSans")) == "sans-serif"

    @pytest.mark.parametrize("family", ["Sansita", "Serifa", "Monoton", "Scriptina"])
    def test_only_whole_words_count(self, family):
        """`Sansita` is not `Sans` and `Serifa` is not `Serif`: a word inside
        another word declares nothing. The mutation that substring-matches
        fails here."""
        assert fonts_meta.classify(sfnt(panose=SILENT, family=family)) is None

    def test_sans_serif_in_words_is_a_sans_serif(self):
        assert fonts_meta.classify(sfnt(panose=SILENT, family="Open Sans Serif")) == "sans-serif"

    def test_mono_beats_sans_in_the_name(self):
        """`DejaVu Sans Mono` is monospaced whatever its serifs do — the same
        precedence PANOSE proportion 9 gets."""
        assert fonts_meta.classify(sfnt(panose=SILENT, family="DejaVu Sans Mono")) == "monospace"

    def test_the_typographic_family_wins_over_the_style_split_name(self):
        """`Alegreya Sans Medium` is name 1 and `Alegreya Sans` is name 16;
        either says sans, but the typographic family is the one the designer
        set on purpose."""
        font = sfnt(panose=SILENT, family="Kroj Medium", typographic_family="Kroj Serif")
        assert fonts_meta.classify(font) == "serif"

    def test_a_macintosh_name_record_is_read_too(self):
        font = sfnt(panose=SILENT, family="Alegreya Sans", name_platform=1)
        assert fonts_meta.classify(font) == "sans-serif"

    def test_the_fixed_pitch_flag_is_a_declaration(self):
        assert fonts_meta.classify(sfnt(panose=SILENT, fixed_pitch=True)) == "monospace"
        assert fonts_meta.classify(sfnt(panose=SILENT, fixed_pitch=False)) is None

    def test_os2_speaks_first(self):
        """When PANOSE does say something, the name does not overrule it: the
        ten bytes are the field made for this question, the name is a word
        in passing."""
        font = sfnt(panose=text_panose(2), family="Kroj Sans")
        assert fonts_meta.classify(font) == "serif"

    def test_no_os2_table_at_all_still_lets_the_name_speak(self):
        assert fonts_meta.classify(sfnt(panose=None, family="Kroj Sans")) == "sans-serif"

    def test_a_name_that_says_nothing_is_still_nothing(self):
        """TeX Gyre Heros: embedded, readable, blank PANOSE, a name with no
        word in it. The answer stays None — common knowledge about that name
        is a question's business, not this module's."""
        assert fonts_meta.classify(sfnt(panose=SILENT, family="TeX Gyre Heros")) is None

    def test_a_truncated_name_table_does_not_raise(self):
        from tests.test_fonts_meta import _sfnt_of

        broken = _sfnt_of({b"name": b"\x00\x00\x00\x05\x00"})
        assert fonts_meta.classify(broken) is None


class TestCommonKnowledgeIgnoresSpacing:
    """`TexGyreHeros` in a stylesheet and `TeX Gyre Heros` in a font are one
    face; a converter writes the name either way."""

    @pytest.mark.parametrize(
        "spelled, expected",
        [
            ("TexGyreHeros", "sans-serif"),
            ("TeX Gyre Heros", "sans-serif"),
            ("TimesNewRoman", "serif"),
            ("Times New Roman", "serif"),
            ('"Times New Roman"', "serif"),
            ("garamond_be", "serif"),
            ("Garamond BE", "serif"),
            ("Ex Ponto Pro", "cursive"),
            ("Lucida Handwriting", "cursive"),
            ("Aharoni", "sans-serif"),
        ],
    )
    def test_spelling_variants_meet_in_the_table(self, spelled, expected):
        assert fonts_meta.well_known(spelled) == expected

    @pytest.mark.parametrize("unknown", ["Wingdings", "Krojwlasny", "Aleygreya", ""])
    def test_what_is_not_common_knowledge_stays_unknown(self, unknown):
        assert fonts_meta.well_known(unknown) is None


class TestItDeclinesToAnswerRatherThanGuess:
    def test_something_that_is_not_a_font(self):
        assert fonts_meta.classify(b"nie jest czcionka") is None

    def test_an_empty_file(self):
        assert fonts_meta.classify(b"") is None

    def test_a_font_with_no_os2_table(self):
        """The fixture font in this repository is a valid sfnt with no OS/2
        table at all. "I do not know" is the right answer and has to stay one:
        inventing a family for it is the guess this module exists to avoid."""
        from tests.factory import fake_ttf

        assert fonts_meta.classify(fake_ttf()) is None

    def test_a_truncated_table_directory_does_not_raise(self):
        assert fonts_meta.classify(b"\x00\x01\x00\x00\xff\xff") is None
