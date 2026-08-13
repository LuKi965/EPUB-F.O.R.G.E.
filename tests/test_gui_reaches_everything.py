"""Every choice this program offers has to be offerable in the window.

The owner's standing rule, restated by him on 2026-08-13 and older than that in
substance: *whatever the application ever removes must be either optional to
untick or asked about first.* A switch that exists only as a command-line flag
does not satisfy it. He runs the Windows build; a flag he cannot reach is a
choice he was not offered.

It found three the day it was written. `allow_incomplete` had shipped in 0.2.20
as the only way past a gate that now **refuses to write a book** — so a book
that tripped it was simply unrebuildable from the window, with no visible way
through. `deobfuscate_fonts` and `transcode_images` had been on and unreachable
since before that.

The exemptions below are the interesting part of this file. Each names a field
and why it is *not* a decision a person makes in the window; a field with no
entry and no control fails, which forces the argument to be had rather than
skipped.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Fields that are deliberately not switches in the window, and why.
#:
#: "Nobody would ever want it" is not a reason and does not appear here — the
#: reasons are all of the form *this is reachable another way* or *this is not a
#: choice about a book*.
NOT_IN_THE_WINDOW = {
    "strict": "not a field a person sets — it is what the mode combo means",
    "rewrite_content": "the same: 'rebuild the container only' is a mode, not a tick",
    "content_dir": (
        "where the package document sits inside the archive. Not a decision about "
        "a book; a diagnostic for reproducing a particular reader's layout, and "
        "one whose wrong values are refused outright"
    ),
    "package_name": "the same, and for the same reason",
    "default_language": "set by the language field beside title and author",
    "metadata_overrides": "the title, author and language fields are this",
    "compat_profiles": "one checkbox per device profile, built from the compat module",
    "modified_override": (
        "the timestamp written into the package. Reachable, but as part of a "
        "reproducible-build mode rather than as a bare date field — open, and "
        "named in docs/PLAN-PO-AUDYCIE.md under F-022"
    ),
    "accessibility_metadata": (
        "generated accessibility metadata describes what the rebuild did and is "
        "true by construction. Turning it off makes the output less useful to a "
        "blind reader and better for nobody"
    ),
    "claim_conformance": (
        "an accessibility conformance claim is a legal assertion about a book, "
        "not a preference. This program does not make one on anybody's behalf and "
        "there is nothing to tick"
    ),
}


def policy_fields() -> list[str]:
    text = (ROOT / "epubforge" / "policy.py").read_text(encoding="utf-8")
    body = text.split("class Policy:", 1)[1]
    return re.findall(r"^    ([a-z_][a-z_0-9]*): ", body, re.M)


def window_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "epubforge" / "gui").glob("*.py")
    )


class TestEveryChoiceIsReachable:
    @pytest.mark.parametrize("field", policy_fields())
    def test_a_policy_field_is_either_a_control_or_argued_away(self, field):
        if field in NOT_IN_THE_WINDOW:
            assert NOT_IN_THE_WINDOW[field].strip(), f"{field} is exempt with no reason given"
            return
        assert f"policy.{field}" in window_source() or field in window_source(), (
            f"Policy.{field} can be set from the command line and not from the "
            f"window. Either give it a control or add it to NOT_IN_THE_WINDOW "
            f"with the argument for why it is not a choice a person makes."
        )

    @pytest.mark.parametrize("field", sorted(NOT_IN_THE_WINDOW))
    def test_no_exemption_outlives_its_field(self, field):
        """A ratchet in the other direction: an exemption for a field that no
        longer exists is folklore, and folklore is what this file replaces."""
        assert field in policy_fields(), f"{field} is exempt from a rule it is no longer subject to"


class TestTheControlsThatWereMissing:
    """Named individually, because these are the three the rule caught and a
    parametrised test that goes green says nothing about which."""

    @pytest.mark.parametrize(
        "key", ["policy.incomplete", "policy.fonts", "policy.images"]
    )
    def test_it_has_a_control_and_a_label_and_a_tooltip(self, key):
        from epubforge.gui.strings import EN, PL

        assert key in PL and key in EN, f"{key} has no label"
        assert f"{key}.tip" in PL and f"{key}.tip" in EN, f"{key} has no tooltip"

    def test_the_tooltip_says_what_happens_and_not_what_the_box_is_called(self):
        """The house rule for this file: a person deciding whether to tick a box
        needs to know what it will do to their book."""
        from epubforge.gui.strings import PL

        assert len(PL["policy.incomplete.tip"]) > 200
        assert "zatrzymuje" in PL["policy.incomplete.tip"]

    def test_the_escape_hatch_reaches_the_policy(self):
        """A checkbox wired to nothing is worse than no checkbox."""
        source = (ROOT / "epubforge" / "gui" / "app.py").read_text(encoding="utf-8")
        assert "policy.allow_incomplete = self.incomplete_check.isChecked()" in source
        assert "policy.deobfuscate_fonts = self.fonts_check.isChecked()" in source
        assert "policy.transcode_images = self.images_check.isChecked()" in source
