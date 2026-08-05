"""Replacing the navigation document, and the two ways it went wrong.

Found by running thirty-two real books — commercial Polish editions, not
fixtures — through the rebuild and looking at what EPUBCheck and K1 said. Four
of the thirty-two failed, all four in the same way, and neither defect had a
test because neither could happen to a book written to be a test.

**A page the reader loses.** A nav document is allowed to be in the reading
order, and when it is, it is two things at once: the machine-readable
navigation, and a contents page the publisher wrote. Regenerating it served the
first and destroyed the second — "Spis treści", "Punkty orientacyjne" and the
publisher's own chapter labels were replaced by ours. Text the source had and
the output did not: K1, on four books out of thirty-two.

**A book that no longer opens cleanly.** When the old document is replaced, the
references to it are not references to the new one. The regenerated nav listed
the page it had just deleted, and in one book twenty-seven chapters carried a
"back to contents" link to it. EPUBCheck: *Referenced resource ... could not be
found*. The output was invalid, and the report said nothing.
"""

from __future__ import annotations

import re
import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Level

from .factory import CONTAINER

CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
<head><meta charset="utf-8"/><title>{title}</title></head>
<body><h1>{title}</h1><p>{body}</p>
<p><a href="{contents}">Powrót do spisu treści</a></p></body>
</html>"""

#: The publisher's own contents page: a nav document *and* a page in the spine.
#: Its wording is the thing at stake — nothing regenerated would produce
#: "Spis treści niniejszego wydania".
CONTENTS_PAGE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
<head><meta charset="utf-8"/><title>Spis treści</title></head>
<body>
  <h1>Spis treści niniejszego wydania</h1>
  <nav epub:type="toc"><ol>
    <li><a href="r1.xhtml">Rozdział pierwszy</a></li>
    <li><a href="r2.xhtml">Rozdział drugi</a></li>
  </ol></nav>
</body>
</html>"""

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Książka ze spisem</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="toc" href="spis.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="r1" href="r1.xhtml" media-type="application/xhtml+xml"/>
    <item id="r2" href="r2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
{spine}  </spine>
</package>
"""


def build(path, *, contents_in_spine: bool) -> str:
    spine = '    <itemref idref="toc"/>\n' if contents_in_spine else ""
    spine += '    <itemref idref="r1"/>\n    <itemref idref="r2"/>\n'
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
        )
        archive.writestr("OEBPS/package.opf", OPF.format(spine=spine))
        archive.writestr("OEBPS/spis.xhtml", CONTENTS_PAGE)
        archive.writestr(
            "OEBPS/r1.xhtml",
            CHAPTER.format(title="Rozdział pierwszy", body="Tekst.", contents="spis.xhtml"),
        )
        archive.writestr(
            "OEBPS/r2.xhtml",
            CHAPTER.format(title="Rozdział drugi", body="Więcej.", contents="spis.xhtml"),
        )
    return str(path)


def files_of(path: str) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def read(path: str, ending: str) -> str:
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(ending))
        return archive.read(name).decode()


class TestAContentsPageInTheSpineIsKept:
    @pytest.fixture(params=["preserve", "strict", "minimal"])
    def rebuilt(self, request, tmp_path):
        source = build(tmp_path / "src.epub", contents_in_spine=True)
        result = rebuild(source, str(tmp_path / f"{request.param}.epub"), Policy.preset(request.param))
        assert result.output_path, result.report.to_text()
        return result

    def test_the_publishers_wording_survives(self, rebuilt):
        """The whole point. Nothing generated would ever write this sentence."""
        documents = "".join(
            read(rebuilt.output_path, name)
            for name in files_of(rebuilt.output_path)
            if name.endswith(".xhtml")
        )
        assert "Spis treści niniejszego wydania" in documents

    def test_there_is_still_exactly_one_navigation_document(self, rebuilt):
        package = read(rebuilt.output_path, ".opf")
        assert len(re.findall(r'properties="[^"]*\bnav\b[^"]*"', package)) == 1

    def test_the_generated_nav_is_not_the_publishers_page(self, rebuilt):
        """Keeping the page must not mean skipping the regeneration: the source's
        markup is not guaranteed to be a conforming nav document."""
        package = read(rebuilt.output_path, ".opf")
        nav_href = re.search(r'<item[^>]*properties="[^"]*\bnav\b[^"]*"[^>]*href="([^"]+)"', package)
        if nav_href is None:  # attribute order differs; find it the other way
            nav_href = re.search(r'<item[^>]*href="([^"]+)"[^>]*properties="[^"]*\bnav\b', package)
        assert nav_href
        assert "spis" not in nav_href.group(1)

    def test_it_is_reported_as_preserved(self, rebuilt):
        kept = [f for f in rebuilt.report.findings if f.level is Level.PRESERVED]
        assert any("contents page" in f.message for f in kept), [f.message for f in kept]


class TestAReplacedNavTakesItsReferencesWithIt:
    @pytest.fixture(params=["preserve", "strict", "minimal"])
    def rebuilt(self, request, tmp_path):
        source = build(tmp_path / "src.epub", contents_in_spine=False)
        result = rebuild(source, str(tmp_path / f"{request.param}.epub"), Policy.preset(request.param))
        assert result.output_path, result.report.to_text()
        return result

    def test_no_link_points_at_a_file_that_is_gone(self, rebuilt):
        """EPUBCheck's complaint, asserted without needing EPUBCheck."""
        import posixpath

        names = set(files_of(rebuilt.output_path))
        for name in [n for n in names if n.endswith((".xhtml", ".opf"))]:
            markup = read(rebuilt.output_path, name)
            for href in re.findall(r'(?:href|src)="([^"#]+)', markup):
                if href.startswith(("http:", "https:", "mailto:", "data:")):
                    continue
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), href))
                assert resolved in names, f"{name} → {href!r} resolves to {resolved!r}, absent"

    def test_the_chapters_link_to_the_new_navigation(self, rebuilt):
        chapter = next(
            read(rebuilt.output_path, name)
            for name in files_of(rebuilt.output_path)
            if "r1" in name and name.endswith(".xhtml")
        )
        assert "Powrót do spisu treści" in chapter
        assert "nav.xhtml" in chapter

    def test_the_repointing_is_reported(self, rebuilt):
        assert any(
            "repointed" in f.message and "navigation" in f.message
            for f in rebuilt.report.findings
        ), [f.message for f in rebuilt.report.findings]
