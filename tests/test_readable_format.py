"""Pillar A of the 0.4 plan, seventh slice: one-line sheets made readable.

The shelf holds exactly five sheets packed onto a single line; nothing
else is touched, because everything else is somebody's formatting. The
transform is pure whitespace, and the guard is the strongest equality in
the family: both texts with every whitespace removed must match to the
character.
"""

from __future__ import annotations

from epubforge.stages import style

from tests.test_shelf_refusals import rules_of
from tests.test_duplicate_selectors import build, sheet_of

#: Ten ordinary rules on one line — the measured floor is ten, and the
#: smallest real one-liner on the shelf packs 27.
PACKED = (
    "p.jeden { margin: 0; text-indent: 1em; } p.dwa { color: navy; } "
    "p.trzy { line-height: 1.3; } p { widows: 2; } body { orphans: 2; } "
    ".jeden { padding: 0; } .dwa { letter-spacing: normal; } "
    ".trzy { word-spacing: normal; } span { font-style: normal; } "
    "h2 { page-break-after: avoid; } @media print { p.jeden { margin: 1em; } }"
)


class TestTheRewrite:
    def test_a_packed_sheet_comes_out_one_declaration_per_line(self, tmp_path):
        result = build(tmp_path, sheet=PACKED)
        out = sheet_of(result)
        assert "p.jeden {\n    margin: 0;\n    text-indent: 1em\n}" in out.replace(";\n}", "\n}")
        assert "css.reformatted" in rules_of(result)

    def test_every_character_outside_whitespace_survives(self, tmp_path):
        import re
        result = build(tmp_path, sheet=PACKED)
        out = sheet_of(result)
        assert re.sub(r"\s+", "", out) == re.sub(r"\s+", "", PACKED)

    def test_the_media_interior_is_indented_not_flattened(self, tmp_path):
        result = build(tmp_path, sheet=PACKED)
        out = sheet_of(result)
        assert "@media print {\n    p.jeden {\n        margin: 1em" in out

    def test_a_string_packing_structure_characters_survives(self, tmp_path):
        """`content: "a; b { }"` is somebody's text — the walker skips
        strings whole. The mutation that inserts newlines blindly fails
        here."""
        sheet = (
            'p.jeden::before { content: "a; b { }"; } p.dwa { margin: 0; } '
            "p.trzy { color: black; } p { widows: 2; } body { orphans: 2; } "
            ".jeden { padding: 0; } .dwa { letter-spacing: normal; } "
            ".trzy { word-spacing: normal; } span { font-style: normal; } "
            "h2 { page-break-after: avoid; }"
        )
        result = build(tmp_path, sheet=sheet)
        assert 'content: "a; b { }"' in sheet_of(result)
        assert "css.reformatted" in rules_of(result)


class TestTheBoundary:
    def test_a_readable_sheet_is_left_byte_alone(self, tmp_path):
        """Three rules across three lines is somebody's formatting; the
        mutation that reformats everything fails here."""
        sheet = (
            "p.jeden { margin: 0; }\n"
            "p.dwa { color: navy; }\n"
            "p.trzy { line-height: 1.3; }\n"
        )
        result = build(tmp_path, sheet=sheet)
        assert sheet == sheet_of(result)
        assert "css.reformatted" not in rules_of(result)

    def test_the_opt_out_counts_instead(self, tmp_path):
        result = build(tmp_path, sheet=PACKED, sweep=False)
        assert "\n    margin" not in sheet_of(result)
        assert "css.single-line-found" in rules_of(result)


class TestTheGuard:
    def test_a_rewrite_that_loses_a_character_is_refused(self, tmp_path, monkeypatch):
        """Structure can survive a lost character; the character-equality
        guard cannot. The mutation that drops it fails here."""
        from epubforge import stylesheet as st
        real = st.readable
        monkeypatch.setattr(st, "readable",
                            lambda text: real(text).replace("navy", "nav", 1))
        result = build(tmp_path, sheet=PACKED)
        assert "navy" in sheet_of(result)
        assert "css.reformat-unverified" in rules_of(result)

    def test_a_failed_verification_hands_the_sheet_back(self, tmp_path, monkeypatch):
        monkeypatch.setattr(style, "_structurally_sound", lambda text: False)
        result = build(tmp_path, sheet=PACKED)
        assert "\n    margin" not in sheet_of(result)
        assert "css.reformat-unverified" in rules_of(result)
