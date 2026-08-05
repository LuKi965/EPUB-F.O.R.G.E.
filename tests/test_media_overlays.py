"""A book with narration comes out as a book with narration.

Media Overlays are how an audiobook stays in step with its text: a SMIL file
per document, an attribute on the manifest item pointing at it, and a duration
for each overlay and for the publication. Losing any one of the three is not a
smaller book — EPUBCheck rejects the rest, so the book that comes out is
broken rather than poorer.

That is exactly what happened. The SMIL file was carried through as opaque
bytes and moved to `misc/`, which left its own `src` attributes pointing at
files that were no longer there; the `media-overlay` attribute was never read;
and `media:duration` was skipped by the reader because it is a refinement, and
refinements were assumed to belong to collections. Three separate omissions
producing one invalid book, with nothing said in the report.
"""

from __future__ import annotations

import re
import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .kitchen_sink import make_kitchen_sink


@pytest.fixture(scope="module")
def sink(tmp_path_factory):
    return make_kitchen_sink(str(tmp_path_factory.mktemp("overlay") / "sink.epub"))


@pytest.fixture(params=["preserve", "strict", "minimal"], scope="module")
def rebuilt(request, sink, tmp_path_factory):
    folder = tmp_path_factory.mktemp(f"out-{request.param}")
    result = rebuild(sink, str(folder / "out.epub"), Policy.preset(request.param))
    assert result.output_path, result.report.to_text()
    return result.output_path


def package_of(path: str) -> str:
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".opf"))
        return archive.read(name).decode()


def read(path: str, name_ending: str) -> str:
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(name_ending))
        return archive.read(name).decode()


class TestTheDeclarationSurvives:
    def test_the_document_still_points_at_its_overlay(self, rebuilt):
        package = package_of(rebuilt)
        overlay = re.search(r'<item[^>]*media-overlay="([^"]+)"', package)
        assert overlay, "no manifest item declares a media overlay"
        # The attribute names an id, and the rebuild regenerates ids — so what
        # matters is that the id it names is the SMIL file's, not that it is
        # the id the source used.
        smil = re.search(r'<item id="([^"]+)"[^>]*media-type="application/smil\+xml"', package)
        assert smil and overlay.group(1) == smil.group(1)

    def test_the_durations_survive(self, rebuilt):
        package = package_of(rebuilt)
        assert '<meta property="media:duration">0:16:14</meta>' in package
        refined = re.search(
            r'<meta refines="#([^"]+)" property="media:duration">([^<]+)</meta>', package
        )
        assert refined, "the per-overlay duration is gone"
        assert refined.group(2) == "0:16:14"

    def test_the_active_class_survives(self, rebuilt):
        assert "media:active-class" in package_of(rebuilt)

    def test_the_smil_file_is_still_there(self, rebuilt):
        with zipfile.ZipFile(rebuilt) as archive:
            assert [n for n in archive.namelist() if n.endswith(".smil")]


class TestTheOverlayStillWorks:
    """Carrying the file without carrying its references is worse than dropping
    it: the book becomes invalid rather than merely poorer."""

    def test_the_references_inside_the_smil_point_at_files_that_exist(self, rebuilt):
        import posixpath

        with zipfile.ZipFile(rebuilt) as archive:
            smil_name = next(n for n in archive.namelist() if n.endswith(".smil"))
            smil = archive.read(smil_name).decode()
            present = set(archive.namelist())

        targets = re.findall(r'src="([^"#]+)', smil)
        assert targets, "the fixture's overlay references nothing"
        for target in targets:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(smil_name), target))
            assert resolved in present, f"{target!r} resolves to {resolved!r}, which is not there"

    def test_the_repointing_is_reported_rather_than_done_quietly(self, sink, tmp_path):
        """`preserve` moves the file, so it must say that it touched it."""
        result = rebuild(sink, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert any("carried as-is" in f.message for f in result.report.findings), [
            f.message for f in result.report.findings
        ]


class TestTheChainThatWasNeverWritten:
    def test_a_fallback_survives(self, rebuilt):
        """`item/@fallback` had a field on the model and no line in the writer,
        so it was read and then dropped — the most invisible kind of loss."""
        package = package_of(rebuilt)
        fallback = re.search(r'<item[^>]*fallback="([^"]+)"', package)
        assert fallback, "the fallback chain is gone"
        assert re.search(rf'<item id="{re.escape(fallback.group(1))}"', package)

    def test_a_fallback_pointing_nowhere_is_reported_not_invented(self, tmp_path):
        from .factory import CONTAINER, MODERN_NAV

        opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Ślepy odnośnik</dc:title><dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch" href="ch.xhtml" media-type="application/xhtml+xml"/>
    <item id="odd" href="odd.xyz" media-type="application/octet-stream" fallback="nie-ma-takiego"/>
  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""
        path = str(tmp_path / "dangling.epub")
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            archive.writestr(
                "META-INF/container.xml",
                CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
            )
            archive.writestr("OEBPS/package.opf", opf)
            archive.writestr("OEBPS/nav.xhtml", MODERN_NAV)
            archive.writestr(
                "OEBPS/ch.xhtml",
                '<?xml version="1.0" encoding="utf-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
                "<meta charset=\"utf-8\"/><title>R</title></head><body><h1>R</h1>"
                "<p>Tekst.</p></body></html>",
            )
            archive.writestr("OEBPS/odd.xyz", b"cos")

        result = rebuild(path, str(tmp_path / "out.epub"), Policy.preset("preserve"))

        assert any(
            "points at an id the manifest does not define" in f.message
            for f in result.report.findings
        ), [f.message for f in result.report.findings]
        assert "fallback=" not in package_of(result.output_path)
