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

    def test_the_font_shorthand_is_beyond_the_argument(self, tmp_path):
        sheet = "p.jeden { font-weight: bold; font: 12pt serif; }"
        result = build(tmp_path, sheet=sheet)
        assert "font-weight: bold" in sheet_of(result)
        assert "css.shorthand-overrides-kept" in rules_of(result)

    def test_the_opt_out_counts_instead(self, tmp_path):
        sheet = "p.jeden { border-top-color: #343830; border: 1px solid; }"
        result = build(tmp_path, sheet=sheet, sweep=False)
        assert "border-top-color" in sheet_of(result)
        assert "css.shorthand-overrides-found" in rules_of(result)


class TestTheGuard:
    def test_a_failed_verification_hands_the_sheet_back(self, tmp_path, monkeypatch):
        monkeypatch.setattr(style, "_structurally_sound", lambda text: False)
        sheet = "p.jeden { border-top-color: #343830; border: 1px solid; }"
        result = build(tmp_path, sheet=sheet)
        assert "border-top-color" in sheet_of(result)
        assert "css.shorthand-overrides-unverified" in rules_of(result)
