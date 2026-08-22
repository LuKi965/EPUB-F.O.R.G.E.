"""Reader-compatibility profiles.

Two properties matter more than any individual measure and are asserted first:
selecting no profile must change nothing at all, and selecting every profile
must not break the book on a reader that follows the specification.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import compat
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.stages.compat import CompatibilityStage

ALL_PROFILES = tuple(sorted(compat.PROFILES))


@pytest.fixture
def rebuilt_compat(legacy_epub, tmp_path):
    result = rebuild(
        legacy_epub,
        str(tmp_path / "compat.epub"),
        Policy.preset("preserve", compat_profiles=ALL_PROFILES),
    )
    assert result.output_path, result.report.to_text()
    return result


@pytest.fixture
def compat_archive(rebuilt_compat):
    with zipfile.ZipFile(rebuilt_compat.output_path) as handle:
        yield handle


def test_no_profile_changes_nothing(legacy_epub, tmp_path):
    """The default path must be byte-identical to one with the stage present.

    `dcterms:modified` is stamped from the clock and is the one field meant to
    differ between two runs, so it is pinned here. Without the pin this passed
    except when the two rebuilds happened to straddle a second — a test that is
    right about the wrong thing 99 times out of 100.
    """
    pinned = {"modified_override": "2026-01-01T00:00:00Z"}
    plain = rebuild(legacy_epub, str(tmp_path / "a.epub"), Policy.preset("preserve", **pinned))
    explicit = rebuild(
        legacy_epub,
        str(tmp_path / "b.epub"),
        Policy.preset("preserve", compat_profiles=(), **pinned),
    )
    with zipfile.ZipFile(plain.output_path) as one, zipfile.ZipFile(explicit.output_path) as two:
        assert one.namelist() == two.namelist()
        for name in one.namelist():
            assert one.read(name) == two.read(name), name


def test_unknown_profile_is_reported_not_ignored(legacy_epub, tmp_path):
    result = rebuild(
        legacy_epub,
        str(tmp_path / "out.epub"),
        Policy.preset("preserve", compat_profiles=("kindel",)),
    )
    assert any("kindel" in f.message for f in result.report.findings)


# --------------------------------------------------------------------- guide
def test_guide_is_absent_by_default(archive):
    assert "<guide>" not in archive.read("EPUB/package.opf").decode()


def test_guide_points_where_the_landmarks_do(compat_archive):
    opf = compat_archive.read("EPUB/package.opf").decode()
    assert "<guide>" in opf
    # The cover and the start of the text are the two references the legacy
    # readers actually consult.
    assert 'type="cover"' in opf
    assert 'type="text"' in opf


def test_guide_references_resolve_to_real_files(compat_archive):
    import re

    opf = compat_archive.read("EPUB/package.opf").decode()
    names = set(compat_archive.namelist())
    for href in re.findall(r'<reference [^>]*href="([^"#]+)', opf):
        assert f"EPUB/{href}" in names, href


# ------------------------------------------------------------- html5 blocks
def test_html5_block_stylesheet_is_added_and_linked(compat_archive):
    sheet = f"EPUB/styles/{compat.COMPAT_STYLESHEET_NAME}"
    assert sheet in compat_archive.namelist()
    assert "display: block" in compat_archive.read(sheet).decode()
    for name in compat_archive.namelist():
        if name.endswith(".xhtml"):
            assert compat.COMPAT_STYLESHEET_NAME in compat_archive.read(name).decode(), name


def test_compat_stylesheet_is_linked_before_the_books_own(compat_archive):
    """Same specificity means source order decides; the publisher must win."""
    import re

    document = compat_archive.read("EPUB/text/0000-cover.xhtml").decode()
    links = re.findall(r'<link[^>]*href="([^"]+)"', document)
    ours = [i for i, href in enumerate(links) if compat.COMPAT_STYLESHEET_NAME in href]
    theirs = [i for i, href in enumerate(links) if compat.COMPAT_STYLESHEET_NAME not in href]
    assert ours and theirs
    assert max(ours) < min(theirs)


def test_compat_stylesheet_is_in_the_manifest(compat_archive):
    opf = compat_archive.read("EPUB/package.opf").decode()
    assert compat.COMPAT_STYLESHEET_NAME in opf


# --------------------------------------------------------------- page breaks
@pytest.mark.parametrize(
    "css, expected",
    [
        ("h1 { break-before: page }", "page-break-before: always"),
        ("p { break-inside: avoid }", "page-break-inside: avoid"),
        ("div { break-after: avoid; }", "page-break-after: avoid"),
        ("@media screen { h2 { break-before: page } }", "page-break-before: always"),
    ],
)
def test_break_declarations_are_mirrored(css, expected):
    rewritten, count = CompatibilityStage()._mirror_breaks(css)
    assert count == 1
    assert expected in rewritten


@pytest.mark.parametrize(
    "css",
    [
        # No page-break equivalent exists for these.
        "p { break-inside: column }",
        "p { break-before: region }",
        # Already present: mirroring would fight the author.
        "h1 { break-before: page; page-break-before: avoid }",
        "p { color: red }",
    ],
)
def test_unmappable_or_present_declarations_are_left_alone(css):
    rewritten, count = CompatibilityStage()._mirror_breaks(css)
    assert count == 0
    assert rewritten == css


def test_legacy_spelling_precedes_the_modern_one():
    """A current renderer treats them as aliases, so the publisher's must be last."""
    rewritten, _ = CompatibilityStage()._mirror_breaks("h1 { break-before: page }")
    assert rewritten.index("page-break-before") < rewritten.index("break-before: page")


def test_original_declaration_survives_untouched():
    rewritten, _ = CompatibilityStage()._mirror_breaks("h1 { break-before: page; margin: 0 }")
    assert "break-before: page" in rewritten
    assert "margin: 0" in rewritten


# -------------------------------------------------------------- apple fonts
def test_apple_display_options_written_when_fonts_are_embedded(compat_archive):
    data = compat_archive.read(compat.APPLE_DISPLAY_OPTIONS_PATH).decode()
    assert "specified-fonts" in data
    assert "true" in data


def test_apple_display_options_absent_by_default(archive):
    assert compat.APPLE_DISPLAY_OPTIONS_PATH not in archive.namelist()


def test_apple_display_options_not_claimed_without_fonts(tmp_path):
    """A declaration the book cannot support is not written, and the skip is said."""
    from .factory import make_legacy_epub

    source = make_legacy_epub(str(tmp_path / "nofont.epub"))
    result = rebuild(
        source,
        str(tmp_path / "out.epub"),
        Policy.preset("preserve", compat_profiles=("apple",)),
    )
    with zipfile.ZipFile(result.output_path) as archive:
        assert compat.APPLE_DISPLAY_OPTIONS_PATH not in archive.namelist()
    assert any("embeds no fonts" in f.message for f in result.report.findings)


# --------------------------------------------------------------------- ncx
def test_profile_needing_the_ncx_objects_when_it_is_off(legacy_epub, tmp_path):
    result = rebuild(
        legacy_epub,
        str(tmp_path / "out.epub"),
        Policy.preset("preserve", compat_profiles=("kobo",), write_ncx=False),
    )
    assert any("NCX" in f.message for f in result.report.findings)


# ------------------------------------------------------------------ metadata
def test_every_profile_names_only_known_measures():
    for profile in compat.PROFILES.values():
        for key in profile.measures:
            assert key in compat.MEASURES, f"{profile.key} wants unknown measure {key}"


def test_every_measure_is_reachable_from_some_profile():
    used = {key for profile in compat.PROFILES.values() for key in profile.measures}
    assert used == set(compat.MEASURES)


class TestLegacyFontTypes:
    """The owner's call, on a Calibre report: if EPUB 3 does not need the older
    media type, it belongs in a backwards-compatibility profile.

    `font/ttf` is what this tool writes everywhere else and what EPUB 3.3
    registers. Adobe RMSDK shipped before RFC 8081 and looks the type up in a
    fixed list; a font declared by a name it does not know is a font it does
    not load.
    """

    def types(self, result):
        import zipfile

        from lxml import etree

        with zipfile.ZipFile(result.output_path) as archive:
            package = etree.fromstring(archive.read("EPUB/package.opf"))
        return {
            item.get("href"): item.get("media-type")
            for item in package.iter("{http://www.idpf.org/2007/opf}item")
            if (item.get("media-type") or "").split("/")[0] in ("font", "application")
        }

    def test_the_default_is_the_type_epub3_registers(self, rebuilt):
        found = [t for t in self.types(rebuilt).values() if "font" in (t or "")]
        assert any(t == "font/ttf" for t in found), found

    def test_the_legacy_profile_declares_what_rmsdk_knows(self, legacy_epub, tmp_path):
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        policy = Policy.preset("preserve", compat_profiles=("legacy",))
        result = rebuild(legacy_epub, str(tmp_path / "rmsdk.epub"), policy)
        assert result.output_path, result.report.to_text()
        found = list(self.types(result).values())
        assert "application/x-font-truetype" in found, found
        assert "font/ttf" not in found

    def test_it_says_so_in_the_report(self, legacy_epub, tmp_path):
        """Every measure in a compatibility profile is a step away from the
        standard, taken for a named device, and the report says which."""
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy
        from epubforge.report import Level

        policy = Policy.preset("preserve", compat_profiles=("legacy",))
        result = rebuild(legacy_epub, str(tmp_path / "rmsdk2.epub"), policy)
        found = [f for f in result.report.findings if f.rule == "compat.legacy-font-types"]
        assert found and found[0].level is Level.PRESERVED
