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


def sfnt(*, panose: "tuple[int, ...]", family_class: int = 0) -> bytes:
    """A minimal sfnt carrying one OS/2 table and the two fields read from it.

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

    table = bytearray(96)
    struct.pack_into(">h", table, 30, family_class << 8)
    table[32:32 + len(panose)] = bytes(panose)
    offset = 12 + 16
    header = struct.pack(">4sHHHH", b"\x00\x01\x00\x00", 1, 16, 0, 0)
    # tag, checksum, offset, length — the sixteen bytes of a table record.
    record = struct.pack(">4sIII", b"OS/2", 0, offset, len(table))
    return header + record + bytes(table)


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
