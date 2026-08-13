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

import pathlib
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
        # The gate is off here on purpose, and the reason is worth stating: this
        # fixture arrives with an EPUBCheck error of its own — a document links
        # to a resource the spine does not hold — and strict now refuses to
        # publish an invalid file, so the whole class would be testing the gate
        # rather than the nav replacement it is named after. Measured: source
        # and rebuild carry that error in equal number, so nothing here
        # introduces it. That strict *does* refuse this book is asserted in
        # `tests/test_publication_gate.py`, where it is the subject.
        result = rebuild(
            source,
            str(tmp_path / f"{request.param}.epub"),
            Policy.preset(request.param, validate_before_publish="off"),
        )
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
        # The gate is off here on purpose, and the reason is worth stating: this
        # fixture arrives with an EPUBCheck error of its own — a document links
        # to a resource the spine does not hold — and strict now refuses to
        # publish an invalid file, so the whole class would be testing the gate
        # rather than the nav replacement it is named after. Measured: source
        # and rebuild carry that error in equal number, so nothing here
        # introduces it. That strict *does* refuse this book is asserted in
        # `tests/test_publication_gate.py`, where it is the subject.
        result = rebuild(
            source,
            str(tmp_path / f"{request.param}.epub"),
            Policy.preset(request.param, validate_before_publish="off"),
        )
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


class TestTheNavigationSpeaksTheBooksLanguage:
    """"Table of Contents" headed a Polish novel whose own `lang` says `pl`.

    These headings are the only words this program puts in front of a reader
    *inside their book*, and they were English in every book it ever produced.
    The bilingual report made that worse rather than better: the one piece of
    text nobody could change was the piece printed in the book itself.
    """

    @staticmethod
    def nav(source, tmp_path, name="out.epub"):
        import zipfile

        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        result = rebuild(source, str(tmp_path / name), Policy.preset("preserve"))
        with zipfile.ZipFile(result.output_path) as archive:
            return archive.read("EPUB/nav.xhtml").decode()

    def test_a_polish_book_gets_a_polish_heading(self, tmp_path):
        from tests.factory import make_legacy_epub

        markup = self.nav(make_legacy_epub(str(tmp_path / "src.epub")), tmp_path)
        assert "<h1>Spis treści</h1>" in markup
        assert "Table of Contents" not in markup

    def test_an_english_book_still_gets_english(self, tmp_path):
        """The fix must not swap one hard-coded language for another."""
        import pathlib

        from epubforge.stages.navigation import heading

        assert heading("en", "toc") == "Table of Contents"
        assert heading("pl", "toc") == "Spis treści"
        source = pathlib.Path("tests/corpus_gutenberg/oliver-twist-vol-2-of-3.epub")
        if source.is_file():
            markup = self.nav(str(source), tmp_path, "en.epub")
            assert "<h1>Table of Contents</h1>" in markup

    def test_a_regional_tag_resolves_to_its_language(self):
        from epubforge.stages.navigation import heading

        assert heading("pl-PL", "toc") == "Spis treści"
        assert heading("pl_PL", "toc") == "Spis treści"
        assert heading("PL", "toc") == "Spis treści"

    def test_a_language_nobody_wrote_falls_back_rather_than_failing(self):
        """A heading in the wrong language is a blemish; a book that fails to
        build is not."""
        from epubforge.stages.navigation import heading

        assert heading("de", "toc") == "Table of Contents"
        assert heading("", "toc") == "Table of Contents"

    def test_every_section_is_translated_in_every_language(self):
        """A half-translated navigation is the shape a stalled translation
        takes, and it is visible to the reader rather than to us."""
        from epubforge.stages.navigation import NAV_HEADINGS

        sections = set(NAV_HEADINGS["en"])
        for language, headings in NAV_HEADINGS.items():
            assert set(headings) == sections, language
            if language != "en":
                shared = [k for k in sections if headings[k] == NAV_HEADINGS["en"][k]]
                assert not shared, (language, shared)


class TestTheContentsPageSurvivesACollidingPath:
    """Found on a real book: 24 MB, 9 809 spine items, and 32 characters gone.

    The protection for a navigation document that is also a contents page was
    guarded by `book.nav_path != nav_path`. In container-only mode nothing is
    renamed, so the generated nav lands on the same path the source's nav
    already holds — the two are equal, the guard is skipped, and the
    publisher's page is overwritten in place.

    That is the one mode whose promise is that content files come out byte for
    byte, and the report said `xhtml.untouched` while it happened: true of the
    stage that says it, false of the book.
    """

    def book(self, tmp_path):
        from tests.factory import write_zip

        nav = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><head>'
            "<title>Inhoudsopgave</title></head><body>"
            '<nav epub:type="toc"><h1>Inhoudsopgave</h1><ol><li>'
            '<a href="d0.xhtml">Begin</a></li></ol></nav></body></html>\n'
        )
        document = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>R</title>'
            "</head><body><p>Rozdzial z tekstem.</p></body></html>\n"
        )
        package = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>P</dc:title>
<dc:language>nl</dc:language><dc:identifier id="i">urn:uuid:9</dc:identifier>
<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata>
<manifest>
  <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  <item id="d0" href="d0.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine><itemref idref="nav"/><itemref idref="d0"/></spine></package>
"""
        container = (
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="c.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>"
        )
        return write_zip(
            str(tmp_path / "in.epub"),
            {
                "META-INF/container.xml": container.encode(),
                "c.opf": package.encode(),
                "nav.xhtml": nav.encode(),
                "d0.xhtml": document.encode(),
            },
        )

    @pytest.mark.parametrize("mode", ["minimal", "preserve", "strict"])
    def test_the_publishers_own_word_for_contents_survives(self, tmp_path, mode):
        import pathlib as _pathlib

        from epubforge.inventory import spine_text
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        source = self.book(tmp_path)
        result = rebuild(
            source,
            str(tmp_path / f"{mode}.epub"),
            Policy.preset(mode, modified_override="2026-01-01T00:00:00Z"),
        )
        assert result.output_path, result.report.to_text()
        before = " ".join(spine_text(_pathlib.Path(source)).split())
        after = " ".join(spine_text(_pathlib.Path(result.output_path)).split())
        assert "Inhoudsopgave" in before
        assert before == after, mode

    @pytest.mark.parametrize("mode", ["minimal", "preserve", "strict"])
    def test_the_page_is_reported_as_kept_in_every_mode(self, tmp_path, mode):
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        result = rebuild(
            self.book(tmp_path),
            str(tmp_path / f"{mode}-r.epub"),
            Policy.preset(mode, modified_override="2026-01-01T00:00:00Z"),
        )
        assert "nav.contents-page-kept" in {f.rule for f in result.report.findings}

    def test_the_generated_nav_moves_aside_rather_than_over(self, tmp_path):
        """One nav document, as EPUB 3 requires, and the publisher's page still
        in the reading order beside it."""
        import zipfile

        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        result = rebuild(
            self.book(tmp_path),
            str(tmp_path / "aside.epub"),
            Policy.preset("minimal", modified_override="2026-01-01T00:00:00Z"),
        )
        with zipfile.ZipFile(result.output_path) as archive:
            names = archive.namelist()
            package = next(archive.read(n).decode() for n in names if n.endswith(".opf"))
        assert package.count('properties="nav"') == 1
        assert any(n.endswith("nav.xhtml") for n in names)
        assert any("nav-epub3" in n for n in names), names


UNSPINED_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Książka z kolofonem</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="toc" href="spis.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="r1" href="r1.xhtml" media-type="application/xhtml+xml"/>
    <item id="kol" href="kolofon.xhtml" media-type="application/xhtml+xml"/>
    <item id="r2" href="r2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="r1"/>
    <itemref idref="r2"/>
  </spine>
</package>
"""

UNSPINED_CONTENTS = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
<head><meta charset="utf-8"/><title>Spis treści</title></head>
<body><nav epub:type="toc"><ol>
  <li><a href="r1.xhtml">Rozdział pierwszy</a></li>
  <li><a href="kolofon.xhtml">Kolofon</a></li>
  <li><a href="r2.xhtml">Rozdział drugi</a></li>
</ol></nav></body>
</html>"""


def build_unspined(path) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
        )
        archive.writestr("OEBPS/package.opf", UNSPINED_OPF)
        archive.writestr("OEBPS/spis.xhtml", UNSPINED_CONTENTS)
        for name, title in (("r1", "Rozdział pierwszy"), ("r2", "Rozdział drugi")):
            archive.writestr(
                f"OEBPS/{name}.xhtml",
                CHAPTER.format(title=title, body="Tekst.", contents="spis.xhtml"),
            )
        archive.writestr(
            "OEBPS/kolofon.xhtml",
            CHAPTER.format(title="Kolofon", body="Wydano w 1998.", contents="spis.xhtml"),
        )
    return str(path)


class TestTheContentsMayNotLeadOutOfTheReadingOrder:
    """`RSC-011: Found a reference to a resource that is not a spine item`, on
    four books of the mixed shelf and on none of their sources' own verdicts:
    EPUB 2 navigated by NCX and had no such rule, EPUB 3 does. The publisher
    meant the page reachable — it is in the manifest and in the contents — and
    meant page-turning not to arrive at it, which is `linear="no"` exactly.
    """

    @pytest.fixture(params=["preserve", "strict", "minimal"])
    def rebuilt(self, request, tmp_path):
        source = build_unspined(tmp_path / "in.epub")
        # Gate off, same reason as the class above and worth being exact about:
        # this fixture's source carries one `RSC-011` and its rebuild carries
        # one `RSC-011`, so the repair below is not what leaves it there and
        # nothing here introduces it. Strict refuses the book over it, which is
        # strict working; asserting that belongs in the gate's own tests, not in
        # four tests about where a colophon sits in the reading order.
        return rebuild(
            source,
            str(tmp_path / f"out-{request.param}.epub"),
            Policy.preset(request.param, validate_before_publish="off"),
        )

    def test_the_page_joins_the_reading_order(self, rebuilt):
        opf = read(rebuilt.output_path, ".opf")
        assert "kolofon.xhtml" in opf
        idref = re.search(r'<item id="([^"]+)" href="[^"]*kolofon\.xhtml"', opf)
        assert idref, opf
        assert re.search(rf'<itemref idref="{idref.group(1)}"[^>]*linear="no"', opf), opf

    def test_it_joins_out_of_the_flow_and_not_into_it(self, rebuilt):
        """Turning pages must not start landing on the colophon. The other two
        stay linear, so the book still reads chapter one, chapter two."""
        opf = read(rebuilt.output_path, ".opf")
        itemrefs = re.findall(r"<itemref [^>]*/>", opf)
        assert sum(1 for ref in itemrefs if 'linear="no"' in ref) == 1

    def test_the_contents_entry_is_kept_rather_than_dropped(self, rebuilt):
        nav = read(rebuilt.output_path, "nav.xhtml")
        assert "Kolofon" in nav
        assert "kolofon.xhtml" in nav

    def test_it_sits_where_the_contents_put_it(self, rebuilt):
        """Listed between the two chapters, so it goes between them — appending
        would put a front-matter page after the last chapter."""
        opf = read(rebuilt.output_path, ".opf")
        order = [
            re.search(rf'<item id="{ref}" href="([^"]+)"', opf).group(1)
            for ref in re.findall(r'<itemref idref="([^"]+)"', opf)
        ]
        # The paths are relaid out in two of the three modes, so match on the
        # stem the source gave each document rather than on the whole path.
        stems = [
            next(stem for stem in ("r1", "kolofon", "r2") if name.endswith(f"{stem}.xhtml"))
            for name in order
            if name.endswith(("r1.xhtml", "kolofon.xhtml", "r2.xhtml"))
        ]
        assert stems == ["r1", "kolofon", "r2"]

    def test_it_is_reported(self, rebuilt):
        finding = next(
            f for f in rebuilt.report.findings if f.rule == "nav.unspined-target-added"
        )
        assert finding.level is Level.FIX
        assert finding.values["count"] == 1
        assert "kolofon" in finding.values["names"]

    def test_a_book_whose_contents_stay_inside_the_spine_gains_nothing(self, tmp_path):
        source = build(tmp_path / "in.epub", contents_in_spine=True)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert 'linear="no"' not in read(result.output_path, ".opf")
        assert "nav.unspined-target-added" not in {
            f.rule for f in result.report.findings if f.rule
        }

    def test_the_page_is_not_counted_as_text_appearing_from_nowhere(self, tmp_path):
        """K1 asks whether a reader loses text, and `linear="no"` is the spine's
        own word for "not in the reading order". Counting it would have reported
        four books gaining text for a repair that moves no word anybody reads."""
        from epubforge.inventory import measure, spine_text

        source = build_unspined(tmp_path / "in.epub")
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("minimal"))
        before, after = spine_text(pathlib.Path(source)), spine_text(
            pathlib.Path(result.output_path)
        )
        assert len(after) == len(before)
        assert "Wydano w 1998" not in after, "the colophon is reachable, not read"
        assert (
            measure(pathlib.Path(result.output_path)).fields["spine_text_characters"]
            == len(after)
        ), "the count and the text it counts have to agree"
