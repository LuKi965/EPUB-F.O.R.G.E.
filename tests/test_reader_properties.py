"""D-036: `adobe-*` is dropped by default in both modes; the `legacy`
compat profile — the program's word for "this book is meant for RMSDK
readers" — is what keeps it. The owner's call, conditional on the compat
module existing, and it does: protection belongs to the profile, not to
a mode.
"""

from __future__ import annotations

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of
from tests.test_class_translation import PAGE

BODY = '<p class="jeden">Akapit z treścią rozdziału.</p>'
SHEET = "p.jeden { adobe-hyphenate: none; -epub-hyphens: auto; margin: 0; }"


def build(tmp_path, *, preset="preserve", compat=()):
    source = make_book(
        tmp_path / "in.epub",
        {"c0.xhtml": PAGE.format(body=BODY)},
        extra_items='<item id="s" href="s.css" media-type="text/css"/>',
        extra_files={"OEBPS/s.css": SHEET.encode()},
    )
    policy = Policy.preset(preset, render_gate="off")
    policy.compat_profiles = tuple(compat)
    return rebuild(source, str(tmp_path / "out.epub"), policy)


def sheet_of(result):
    """Every stylesheet concatenated — the legacy profile injects its own
    sheet beside the book's, and the first-match habit reads the wrong one."""
    import zipfile
    texts = []
    with zipfile.ZipFile(result.output_path) as archive:
        for name in archive.namelist():
            if name.endswith(".css"):
                texts.append(archive.read(name).decode("utf-8"))
    if not texts:
        raise AssertionError("no stylesheet in the rebuild")
    return "\n".join(texts)


class TestTheDefaultIsCleanliness:
    def test_preserve_drops_adobe_properties_now(self, tmp_path):
        """The old mode split protected them here; D-036 moved the
        protection to the profile."""
        result = build(tmp_path, preset="preserve")
        out = sheet_of(result)
        assert "adobe-hyphenate" not in out
        assert "css.reader-property-removed" in rules_of(result)

    def test_strict_drops_them_as_before(self, tmp_path):
        result = build(tmp_path, preset="strict")
        assert "adobe-hyphenate" not in sheet_of(result)

    def test_a_real_vendor_prefix_is_never_touched(self, tmp_path):
        """`-epub-hyphens` is honoured by shipping readers; only Adobe's
        bare inventions are the profile's business."""
        result = build(tmp_path)
        assert "-epub-hyphens: auto" in sheet_of(result)


class TestTheProfileProtects:
    def test_legacy_keeps_them_and_says_for_whom(self, tmp_path):
        """The mutation that ignores the profile fails here."""
        result = build(tmp_path, compat=("legacy",))
        out = sheet_of(result)
        assert "adobe-hyphenate" in out
        assert "css.reader-property-kept" in rules_of(result)
        assert "css.reader-property-removed" not in rules_of(result)

    def test_an_unrelated_profile_does_not_protect(self, tmp_path):
        result = build(tmp_path, compat=("kindle",))
        assert "adobe-hyphenate" not in sheet_of(result)
