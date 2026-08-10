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
        data = system_font(*names)
        if data is None:
            pytest.skip(f"none of {names} installed here")
        assert fonts_meta.classify(data) == expected

    def test_a_rounded_sans_is_not_a_serif(self):
        """The first thing this got wrong, on the first real font it met. PANOSE
        serif styles 14 (Flared) and 15 (Rounded) describe how a stem *ends*,
        not whether the letter has a serif, and sans-serif families use them —
        Lato is 15 and is as sans-serif as a font gets. They fall through to
        `sFamilyClass`, which says 8, and is right.
        """
        data = system_font("Lato-Regular.ttf", "Lato-Light.ttf")
        if data is None:
            pytest.skip("Lato not installed here")
        assert fonts_meta.classify(data) == "sans-serif"


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
