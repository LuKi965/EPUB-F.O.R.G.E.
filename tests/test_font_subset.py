"""Filar E: fonts cut to the characters the book uses, and every refusal.

The measurement that opened this: 62 books of the owner's 160 carry 491 font
files weighing 116 MB, the heaviest spending 11.05 MB on about a hundred
distinct characters. Measured again through this stage on the shelf's
heaviest book — 7.36 MB of subsettable fonts came to 415 KB, the appearance
gate compared 24 pages and found nothing lost, and the two fonts whose own
files forbid it were left whole.

What is tested here is mostly what the stage *refuses* to do, because that
is where a book gets damaged: a glyph that is not in the subset is a square
on the page, and S-03 says losing an ornament is damage too.
"""

from __future__ import annotations

import struct
import zipfile

import pytest

from epubforge import fonts_meta
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_class_translation import PAGE
from tests.test_shelf_refusals import make_book, rules_of

fontTools = pytest.importorskip("fontTools")

from fontTools.fontBuilder import FontBuilder  # noqa: E402
from fontTools.pens.ttGlyphPen import TTGlyphPen  # noqa: E402


def a_font(characters: str = "abcdefghijklmnopqrstuvwxyząćęłńóśżź", fs_type: int = 0) -> bytes:
    """A real TrueType file carrying a glyph per character.

    Built rather than checked in: a fixture font in the repository would be
    somebody's licensed file, which is the very thing this stage is careful
    about.
    """
    import io

    order = [".notdef"] + [f"g{ord(c):x}" for c in characters]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({ord(c): f"g{ord(c):x}" for c in characters})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((0, 700))
    pen.lineTo((500, 700))
    pen.lineTo((500, 0))
    pen.closePath()
    glyph = pen.glyph()
    builder.setupGlyf({name: glyph for name in order})
    builder.setupHorizontalMetrics({name: (600, 50) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Proba", "styleName": "Regular"})
    builder.setupOS2(fsType=fs_type)
    builder.setupPost()
    out = io.BytesIO()
    builder.save(out)
    return out.getvalue()


def build(tmp_path, *, subset=True, font=None, body="Ala ma kota."):
    source = make_book(
        tmp_path / "in.epub",
        {"c0.xhtml": PAGE.format(body=f"<p>{body}</p>")},
        extra_items=(
            '<item id="s" href="s.css" media-type="text/css"/>'
            '<item id="f" href="p.ttf" media-type="font/ttf"/>'
        ),
        extra_files={
            "OEBPS/s.css": b"@font-face { font-family: Proba; src: url(p.ttf); }",
            "OEBPS/p.ttf": a_font() if font is None else font,
        },
    )
    policy = Policy.preset("preserve", render_gate="off", validate_before_publish="off")
    policy.subset_fonts = subset
    return rebuild(source, str(tmp_path / "out.epub"), policy)


def font_bytes(result) -> bytes:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".ttf"))
        return archive.read(name)


def glyph_count(data: bytes) -> int:
    import io

    from fontTools.ttLib import TTFont

    return len(TTFont(io.BytesIO(data)).getGlyphOrder())


class TestTheSwitchIsTheWholeAgreement:
    def test_nothing_happens_unless_it_is_turned_on(self, tmp_path):
        """Off in every mode, and that is the decision rather than a default:
        `fsType` speaks about embedding, and the right to *modify* a font
        lives in a text licence no bit in the file carries."""
        original = a_font()
        result = build(tmp_path, subset=False, font=original)
        assert font_bytes(result) == original
        assert "font.subset" not in rules_of(result)

    def test_the_default_policy_has_it_off(self):
        assert Policy.preset("preserve").subset_fonts is False
        assert Policy.preset("strict").subset_fonts is False


class TestWhatItCutsAndWhatItKeeps:
    def test_a_font_is_cut_to_the_characters_in_the_book(self, tmp_path):
        result = build(tmp_path, body="Ala ma kota.")
        assert "font.subset" in rules_of(result)
        assert glyph_count(font_bytes(result)) < glyph_count(a_font())

    def test_every_character_the_book_shows_survives(self, tmp_path):
        """The failure this stage can cause, asserted directly: a glyph that
        went missing is a square on somebody's page."""
        import io

        from fontTools.ttLib import TTFont

        text = "zażółć gęślą jaźń"
        result = build(tmp_path, body=text)
        cmap = TTFont(io.BytesIO(font_bytes(result))).getBestCmap()
        # Every character of the text the font had a glyph for. The first
        # version of this asserted a lowercased copy of a capitalised
        # sentence and failed on a `z` the book did not contain — the stage
        # was right and the test was wrong, which is worth leaving a note
        # about: an over-broad assertion here would have been "fixed" by
        # making the subset keep glyphs nothing asks for.
        for character in text.replace(" ", ""):
            assert ord(character) in cmap, character

    def test_a_character_only_a_stylesheet_names_survives(self, tmp_path):
        """`content: "ą"` puts a glyph on the page without the text ever
        containing it. The mutation that reads documents and skips
        stylesheets fails here."""
        import io

        from fontTools.ttLib import TTFont

        source = make_book(
            tmp_path / "in.epub",
            {"c0.xhtml": PAGE.format(body="<p>abc</p>")},
            extra_items=(
                '<item id="s" href="s.css" media-type="text/css"/>'
                '<item id="f" href="p.ttf" media-type="font/ttf"/>'
            ),
            extra_files={
                "OEBPS/s.css": 'p::after { content: "ę"; }'.encode(),
                "OEBPS/p.ttf": a_font(),
            },
        )
        policy = Policy.preset("preserve", render_gate="off", validate_before_publish="off")
        policy.subset_fonts = True
        result = rebuild(source, str(tmp_path / "out.epub"), policy)
        cmap = TTFont(io.BytesIO(font_bytes(result))).getBestCmap()
        assert ord("ę") in cmap

    def test_the_report_carries_both_weights(self, tmp_path):
        result = build(tmp_path)
        finding = next(f for f in result.report.findings if f.rule == "font.subset")
        assert finding.values["before"] and finding.values["after"]
        entry = next(c for c in result.report.changes if c.rule == "font.subset")
        assert entry.before != entry.after, "the ledger read the new bytes as the old"


class TestTheLicenceIsReadFromTheFontItself:
    @pytest.mark.parametrize(
        "flag, rule",
        [
            (fonts_meta.FSTYPE_RESTRICTED, "font.subset-refused-restricted"),
            (fonts_meta.FSTYPE_PREVIEW_PRINT, "font.subset-refused-preview-print"),
            (fonts_meta.FSTYPE_NO_SUBSETTING, "font.subset-refused-no-subsetting"),
        ],
    )
    def test_a_font_that_forbids_it_is_left_whole(self, tmp_path, flag, rule):
        """Each of the three bits that touches this operation. `0x0100` is the
        one that names it exactly, and it was absent from the shelf
        measurement — a fact about 491 files, not a licence to skip the
        check. The mutation that drops any one of these fails here."""
        original = a_font(fs_type=flag)
        result = build(tmp_path, font=original)
        assert font_bytes(result) == original
        assert rule in rules_of(result)

    def test_a_file_that_will_not_say_is_not_touched(self, tmp_path):
        """A file whose terms cannot be read is a file whose terms this
        program does not assume are permissive."""
        assert fonts_meta.may_be_subset(b"to nie jest font") == (False, "unreadable")

    def test_an_editable_font_is_allowed(self):
        """The other side, so the licence check cannot be tightened into
        refusing everything: `0x0008` says editable embedding and 220 of the
        shelf's 491 files declare exactly that."""
        assert fonts_meta.may_be_subset(a_font(fs_type=0x0008)) == (True, "")


class TestObfuscatedBooksAreNotTouchedAtAll:
    def test_the_stage_stands_down_when_the_book_arrived_obfuscated(self, tmp_path):
        """Zero such books on the shelf, so this path is untested against a
        real one — which is the reason to refuse rather than the reason to
        try. The mutation that subsets them anyway fails here."""
        from epubforge.stages.font_subset import FontSubsetStage

        class Book:
            encrypted = True
            resources: dict = {}

        class Ctx:
            book = Book()
            policy = Policy.preset("preserve")

        Ctx.policy.subset_fonts = True
        stage = FontSubsetStage()
        noted: list = []
        stage.note = lambda ctx, level, rule, **kw: noted.append(rule)  # type: ignore[assignment]
        stage.run(Ctx())
        assert noted == ["font.subset-skipped-obfuscated"]


class TestWhatItGivesUpIsSaidOutLoud:
    def test_dropped_tables_are_named_when_there_are_any(self, tmp_path):
        """Measured on the shelf's heaviest book: `FFTM` (a font editor's
        bookkeeping) and Apple's `feat`, `morx`, `Silt`. Which of the owner's
        readers use the latter is unmeasured, and an unmeasured consequence
        belongs in the report rather than in a docstring."""
        from epubforge.stages.font_subset import _subset

        trimmed, dropped = _subset(a_font(), set("abc"))
        assert trimmed
        # The built fixture has no exotic tables, so nothing is dropped and
        # nothing is claimed — the finding must not appear out of politeness.
        assert dropped == set()
        result = build(tmp_path)
        assert "font.subset-tables-dropped" not in rules_of(result)
