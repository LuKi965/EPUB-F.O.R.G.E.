"""Pillar A of the 0.4 plan, sixth slice: longhands a shorthand resets.

A shorthand resets every longhand it covers, the omitted ones included —
`border: 1px solid` sets the colour back to its initial value in every
parser since CSS1, which is why the template's `border-top-color` above it
(43 of the shelf's 45 measured pairs) was already being discarded
everywhere. The cut is allowed only when no validator can reject the
*shorthand's* value; a rejectable shorthand is the one case where the
earlier longhand still matters.
"""

from __future__ import annotations

from epubforge.stages import style

from tests.test_shelf_refusals import rules_of
from tests.test_duplicate_selectors import build, sheet_of


class TestTheProvableCuts:
    def test_the_templates_stamped_colour_is_dead(self, tmp_path):
        sheet = "p.jeden { border-top-color: #343830; border: 1px solid; }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "border-top-color" not in out
        assert "border: 1px solid" in out
        assert "css.shorthand-overrides-removed" in rules_of(result)

    def test_the_margin_family_uses_the_same_proof(self, tmp_path):
        sheet = "p.jeden { margin-top: 1em; margin: 0 auto; }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "margin-top" not in out
        assert "margin: 0 auto" in out
        assert "css.shorthand-overrides-removed" in rules_of(result)

    def test_a_longhand_after_the_shorthand_is_untouched(self, tmp_path):
        """Only what stands *before* the shorthand is dead; the colour
        written after it is the block's live word on the subject. The
        mutation that cuts on both sides fails here."""
        sheet = (
            "p.jeden { border-top-color: #343830; border: 1px solid; "
            "border-top-color: #444444; }"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert out.count("border-top-color") == 1
        assert "#444444" in out
        assert "css.shorthand-overrides-removed" in rules_of(result)


class TestTheKeptPairs:
    def test_a_rejectable_shorthand_value_keeps_the_longhand(self, tmp_path):
        """`var(--c)` is a value an old validator rejects, and a rejected
        shorthand leaves the earlier longhand in charge. The mutation
        that cuts without the CSS1 proof fails here."""
        sheet = "p.jeden { border-top-color: #343830; border: 1px solid var(--c); }"
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "border-top-color" in out
        assert "css.shorthand-overrides-kept" in rules_of(result)
        assert "css.shorthand-overrides-removed" not in rules_of(result)

    def test_two_words_of_one_category_are_not_css1(self, tmp_path):
        """`solid double` is two styles in one `border` — CSS1 words,
        invalid grammar, rejectable. The mutation that checks vocabulary
        without grammar fails here."""
        sheet = "p.jeden { border-top-color: #343830; border: solid double; }"
        result = build(tmp_path, sheet=sheet)
        assert "border-top-color" in sheet_of(result)
        assert "css.shorthand-overrides-removed" not in rules_of(result)

    def test_an_important_longhand_beats_a_plain_shorthand(self, tmp_path):
        sheet = (
            "p.jeden { border-top-color: #343830 !important; "
            "border: 1px solid; }"
        )
        result = build(tmp_path, sheet=sheet)
        assert "border-top-color" in sheet_of(result)
        assert "css.shorthand-overrides-kept" in rules_of(result)

    def test_a_system_font_is_beyond_the_argument(self, tmp_path):
        """`font: menu` is CSS2's, not CSS1's, so a validator may reject it —
        and then the longhand it overrode is somebody's fallback after all.

        This test used to say `font: 12pt serif` and to claim the whole `font`
        family was beyond proving. That was never true of the value; it was
        true of the code, which had no grammar for `font` and fell through to
        `False`. Two findings sat on the gate's exception list on the strength
        of it. The grammar is written now, so the case that still cannot be
        proved has to be a value that genuinely cannot.
        """
        sheet = "p.jeden { font-weight: bold; font: menu; }"
        result = build(tmp_path, sheet=sheet)
        assert "font-weight: bold" in sheet_of(result)
        assert "css.shorthand-overrides-kept" in rules_of(result)

    def test_the_opt_out_counts_instead(self, tmp_path):
        sheet = "p.jeden { border-top-color: #343830; border: 1px solid; }"
        result = build(tmp_path, sheet=sheet, sweep=False)
        assert "border-top-color" in sheet_of(result)
        assert "css.shorthand-overrides-found" in rules_of(result)


class TestTheFontGrammar:
    """The last two entries on the gate's exception list, and the owner's
    question that got them looked at again: *is this some early compatibility
    thing?* It was not — the proof had simply never been written, and
    "unprovable" was being reported where "unexamined" was the truth.

    The grammar is CSS1's, and it is strict about order because that is where
    a shorthand gets rejected:

        font: [ <style> || <variant> || <weight> ]? <size> [ / <height> ]? <family>
    """

    def test_the_shape_the_shelf_actually_carries(self, tmp_path):
        """Size and a quoted family — the two findings, in their own form."""
        sheet = 'p.jeden { font-family: "Stara"; font-style: normal; font: 90% "Nowa"; }'
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "Stara" not in out and "font-style" not in out
        assert 'font: 90% "Nowa"' in out
        assert "css.shorthand-overrides-removed" in rules_of(result)

    def test_the_whole_grammar_is_accepted(self, tmp_path):
        sheet = "p.jeden { font-weight: bold; font: italic bold 12pt/1.5 Georgia, serif; }"
        result = build(tmp_path, sheet=sheet)
        assert "font-weight: bold" not in sheet_of(result)

    def test_an_unquoted_family_of_several_words_is_still_a_family(self, tmp_path):
        sheet = "p.jeden { font-weight: bold; font: 12pt New Century Schoolbook; }"
        result = build(tmp_path, sheet=sheet)
        assert "font-weight: bold" not in sheet_of(result)

    def test_a_size_with_no_family_proves_nothing(self, tmp_path):
        """The grammar requires a family. Without one the value is not a
        `font` shorthand at all, and a validator may say so. The mutation
        that stops requiring it fails here."""
        sheet = "p.jeden { font-weight: bold; font: 12pt; }"
        result = build(tmp_path, sheet=sheet)
        assert "font-weight: bold" in sheet_of(result)

    def test_a_unit_css1_never_had_proves_nothing(self, tmp_path):
        sheet = "p.jeden { font-weight: bold; font: 2rem Arial; }"
        result = build(tmp_path, sheet=sheet)
        assert "font-weight: bold" in sheet_of(result)

    def test_one_keyword_twice_proves_nothing(self, tmp_path):
        """`bold bold` is two words of one slot, the same shape the border
        proof refuses. The mutation that lets a slot be filled twice fails
        here."""
        sheet = "p.jeden { font-weight: bold; font: bold bold 12pt Arial; }"
        result = build(tmp_path, sheet=sheet)
        assert "font-weight: bold" in sheet_of(result)

    def test_a_slash_promising_a_height_that_is_absent_proves_nothing(self, tmp_path):
        sheet = "p.jeden { font-weight: bold; font: 12pt/ Arial; }"
        result = build(tmp_path, sheet=sheet)
        assert "font-weight: bold" in sheet_of(result)


class TestTheGuard:
    def test_a_failed_verification_hands_the_sheet_back(self, tmp_path, monkeypatch):
        monkeypatch.setattr(style, "_structurally_sound", lambda text: False)
        sheet = "p.jeden { border-top-color: #343830; border: 1px solid; }"
        result = build(tmp_path, sheet=sheet)
        assert "border-top-color" in sheet_of(result)
        assert "css.shorthand-overrides-unverified" in rules_of(result)
