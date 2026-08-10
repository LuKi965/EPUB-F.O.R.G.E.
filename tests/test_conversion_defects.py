"""Three defects the corpus found on the day it first held converted books.

`docs/ROADMAP.md` point [1] asks for a corpus sorted by provenance rather than
by title, on the argument that what a book was made by decides what is wrong
with it. These tests are that argument's receipt. Seven books arrived in three
families the corpus had never held — MOBI back-conversions, a Google Docs
export, a PDF reflow — and every one of them came out of the rebuild with an
EPUBCheck error the previous seventy books had never produced.

None of the three is our regression: each is present in the source and survives
because the rebuild had no rule for it. That is precisely the failure the
families exist to expose, so each gets a rule and a test here.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Level
from epubforge.stages.content import strip_remote_imports
from tests.factory import MODERN_NAV, MODERN_OPF, png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>Rozdzia&#x142;</title>{head}</head>
  <body>{body}</body>
</html>
"""


def book(path, *, body: str, head: str = "") -> str:
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": MODERN_OPF.format(title="Test", extra_metadata="").encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": PAGE.format(body=body, head=head).encode(),
            "OEBPS/picture.png": png_bytes(),
        },
    )


def built(source, tmp_path, mode: str = "preserve"):
    return rebuild(source, str(tmp_path / "out.epub"), Policy.preset(mode))


def chapter_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("chapter.xhtml"))
        return archive.read(name).decode("utf-8")


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


class TestAListItemIsOnlyNumberedInsideAnOrderedList:
    """Calibre's MOBI back-conversion puts `value` on every bullet it ever had.

    HTML 5 allows the attribute on `li` only when the parent is `ol`, where it
    sets the number. Inside `<ul>` it numbers nothing, draws nothing, and makes
    the document invalid — all five back-converted books failed on it.
    """

    def test_it_goes_when_the_list_is_unordered(self, tmp_path):
        source = book(tmp_path / "ul.epub", body='<ul><li value="1">Raz</li><li value="2">Dwa</li></ul>')
        chapter = chapter_of(built(source, tmp_path))
        assert "value=" not in chapter
        assert "Raz" in chapter and "Dwa" in chapter

    def test_it_stays_where_it_means_something(self, tmp_path):
        """In an ordered list the attribute is the numbering. Removing it there
        would renumber the list, which is a change to what the reader sees."""
        source = book(tmp_path / "ol.epub", body='<ol><li value="7">Siedem</li></ol>')
        assert 'value="7"' in chapter_of(built(source, tmp_path))

    def test_the_report_says_which_markup_moved(self, tmp_path):
        source = book(tmp_path / "ul2.epub", body='<ul><li value="1">Raz</li></ul>')
        result = built(source, tmp_path)
        details = [
            f.detail for f in result.report.findings
            if f.rule == "xhtml.presentational-markup-converted"
        ]
        assert any("li[value]" in (d or "") for d in details)


class TestALinkToAnAnchorNobodyDefines:
    """A PDF reflow writes a page-number strip and gives only some pages an id.

    The file each link names is there; the anchor inside it is not. EPUBCheck
    calls that an error, and it is one the reader cannot act on — so the
    fragment goes and the link lands at the top of the right document.
    """

    def test_the_fragment_is_dropped_and_the_link_survives(self, tmp_path):
        source = book(
            tmp_path / "frag.epub",
            body='<p><a href="nav.xhtml#nie-ma-takiej">strona 258</a></p>',
        )
        result = built(source, tmp_path)
        chapter = chapter_of(result)
        assert "#nie-ma-takiej" not in chapter
        # The rebuild moves the navigation, so the path is repointed as usual;
        # what matters is that a link still goes to it, without a fragment.
        assert 'href="../nav.xhtml"' in chapter
        assert "strona 258" in chapter
        assert "xhtml.dead-fragment-dropped" in rules_of(result)

    def test_an_anchor_that_exists_is_left_alone(self, tmp_path):
        source = book(
            tmp_path / "ok.epub",
            body='<p id="tu">Tu</p><p><a href="chapter.xhtml#tu">wróć</a></p>',
        )
        result = built(source, tmp_path)
        assert "#tu" in chapter_of(result)
        assert "xhtml.dead-fragment-dropped" not in rules_of(result)

    def test_a_same_document_link_is_judged_the_same_way(self, tmp_path):
        source = book(tmp_path / "same.epub", body='<p><a href="#brak">gdzieś</a></p>')
        result = built(source, tmp_path)
        chapter = chapter_of(result)
        assert "#brak" not in chapter
        # The text stays; only the reference that pointed nowhere is gone.
        assert "gdzieś" in chapter
        assert "xhtml.dead-fragment-dropped" in rules_of(result)

    def test_a_fragment_into_something_we_did_not_parse_is_not_guessed_at(self, tmp_path):
        """An SVG carries ids this stage never reads. Silence is not a "no"."""
        source = book(tmp_path / "svg.epub", body='<p><a href="picture.png#page=2">rys.</a></p>')
        result = built(source, tmp_path)
        assert "#page=2" in chapter_of(result)


class TestAStylesheetFetchedOverTheNetwork:
    """Google Docs exports `@import url(https://themes.googleusercontent.com/…)`.

    Reported under two ids, by where it was found: `xhtml.` when the import is
    inside a `<style>` element and `css.` when it is in a linked sheet. The
    prefix on a rule id names the stage that reports it, and the survey caught
    the one entry in the whole catalogue that broke that — `css.` coming out of
    the xhtml stage. Two ids are not duplication when they send you to two
    different places to look.

    EPUB 3 permits one remote resource — a font declared on its manifest item —
    and a stylesheet is not one. The rule is dropped; the font-family
    declarations are not, so the fallback is exactly what it was.
    """

    IMPORT = "@import url(https://themes.googleusercontent.com/fonts/css?kit=abc);"

    def test_a_remote_import_in_a_style_element_is_removed(self, tmp_path):
        source = book(
            tmp_path / "remote.epub",
            head=f"<style>{self.IMPORT} p {{ font-family: 'Roboto', serif; }}</style>",
            body="<p>Tekst.</p>",
        )
        result = built(source, tmp_path)
        chapter = chapter_of(result)
        assert "googleusercontent" not in chapter
        assert "font-family" in chapter
        assert "xhtml.remote-import-removed" in rules_of(result)

    def test_it_is_a_fix_not_a_thing_merely_reported(self, tmp_path):
        source = book(
            tmp_path / "remote2.epub",
            head=f"<style>{self.IMPORT}</style>",
            body="<p>Tekst.</p>",
        )
        result = built(source, tmp_path)
        levels = {
            f.level for f in result.report.findings if f.rule == "xhtml.remote-import-removed"
        }
        assert levels == {Level.FIX}

    @pytest.mark.parametrize(
        "rule",
        [
            '@import url(https://example.test/a.css);',
            '@import url("https://example.test/a.css");',
            "@import 'https://example.test/a.css';",
            '@import url(//example.test/a.css) screen;',
        ],
    )
    def test_every_spelling_of_a_remote_import_is_caught(self, rule):
        text, dropped = strip_remote_imports(rule + " p { color: red; }")
        assert dropped == 1
        assert "example.test" not in text
        assert "color: red" in text

    @pytest.mark.parametrize(
        "rule",
        ['@import url(local.css);', '@import "local.css";', "@import url('sub/local.css');"],
    )
    def test_a_local_import_is_none_of_its_business(self, rule):
        text, dropped = strip_remote_imports(rule)
        assert dropped == 0
        assert text == rule


class TestTheSameIdTwiceInOneDocument:
    """Word writes `bookmark63`, a converter writes `heading_id_3`, and either
    can land in a document twice. The mixed shelf produced eight of them across
    two books, in all three modes — invalid under XHTML 1.1 exactly as under
    HTML 5, so nothing about the upgrade caused it and nothing about the upgrade
    excuses carrying it.
    """

    BODY = (
        '<p id="bookmark63">pierwszy</p>'
        '<p id="bookmark63">drugi</p>'
        '<p id="bookmark63">trzeci</p>'
        '<p><a href="#bookmark63">odnośnik</a></p>'
    )

    def test_the_document_stops_having_the_same_id_twice(self, tmp_path):
        source = book(tmp_path / "in.epub", body=self.BODY)
        page = chapter_of(built(source, tmp_path))
        import re

        found = re.findall(r'id="([^"]+)"', page)
        assert len(found) == len(set(found)), found

    def test_the_first_one_keeps_its_name_so_links_do_not_move(self, tmp_path):
        """Every parser resolves `#bookmark63` to the first element carrying it.
        Renaming that one would move an existing link; renaming the copies
        cannot, because no link could ever have meant them."""
        source = book(tmp_path / "in.epub", body=self.BODY)
        page = chapter_of(built(source, tmp_path))

        assert '<a href="#bookmark63"' in page
        first = page.index('id="bookmark63"')
        assert page.index("pierwszy") - first < page.index("drugi") - first

    def test_the_rename_is_reported_with_the_name_that_repeated(self, tmp_path):
        source = book(tmp_path / "in.epub", body=self.BODY)
        result = built(source, tmp_path)
        finding = next(
            f for f in result.report.findings if f.rule == "xhtml.duplicate-ids-renamed"
        )
        assert finding.level is Level.FIX
        assert finding.values["count"] == 2
        assert "bookmark63" in finding.values["names"]

    def test_a_document_whose_ids_are_already_unique_is_left_alone(self, tmp_path):
        source = book(
            tmp_path / "in.epub", body='<p id="a">x</p><p id="b">y</p>'
        )
        result = built(source, tmp_path)
        assert "xhtml.duplicate-ids-renamed" not in rules_of(result)
        assert 'id="a"' in chapter_of(result) and 'id="b"' in chapter_of(result)

    def test_an_invalid_name_repeated_is_both_things_and_survives_both(self, tmp_path):
        """`a b` is not an XML name *and* appears twice. The first becomes `a-b`
        and references to it follow; the second gets a name of its own and no
        reference follows it anywhere."""
        source = book(
            tmp_path / "in.epub",
            body='<p id="a b">x</p><p id="a b">y</p><p><a href="#a b">z</a></p>',
        )
        page = chapter_of(built(source, tmp_path))
        import re

        found = re.findall(r'id="([^"]+)"', page)
        assert len(found) == len(set(found)), found
        assert all(" " not in name for name in found)
        assert 'href="#a-b"' in page


class TestTextDirectionInAStyleSheet:
    """`CSS-001: The "direction" property must not be included in an EPUB Style
    Sheet` — EPUB 3 bars `direction` and `unicode-bidi` from style sheets
    outright, because a reading system has to know which way text runs before it
    resolves any CSS. One book on the mixed shelf carries it, in all three modes.

    The rule is easy to satisfy and easy to satisfy wrongly: `direction: ltr` is
    boilerplate and means nothing, `direction: rtl` is holding an Arabic book the
    right way round. Same validator message either way.
    """

    def sheet_of(self, result) -> str:
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if n.endswith(".css"))
            return archive.read(name).decode("utf-8")

    def styled(self, tmp_path, css: str):
        source = write_zip(
            str(tmp_path / "in.epub"),
            {
                "META-INF/container.xml": CONTAINER.encode(),
                "OEBPS/package.opf": MODERN_OPF.format(title="Test", extra_metadata="")
                .replace(
                    "</manifest>",
                    '<item id="css" href="style.css" media-type="text/css"/></manifest>',
                )
                .encode(),
                "OEBPS/nav.xhtml": MODERN_NAV.encode(),
                "OEBPS/style.css": css.encode(),
                "OEBPS/chapter.xhtml": PAGE.format(
                    body="<p>tekst</p>", head='<link rel="stylesheet" href="style.css"/>'
                ).encode(),
                "OEBPS/picture.png": png_bytes(),
            },
        )
        return built(source, tmp_path)

    def test_the_default_says_nothing_and_goes(self, tmp_path):
        result = self.styled(tmp_path, "body { direction: ltr; color: red; }")
        sheet = self.sheet_of(result)
        assert "direction" not in sheet
        assert "color: red" in sheet
        assert "css.direction-default-removed" in rules_of(result)

    def test_a_direction_the_page_depends_on_stays(self, tmp_path):
        """Conformance does not outrank the page. A book that validates and
        reads backwards is not the better outcome."""
        result = self.styled(tmp_path, "body { direction: rtl; }")
        assert "direction: rtl" in self.sheet_of(result)
        finding = next(f for f in result.report.findings if f.rule == "css.direction-kept")
        assert finding.level is Level.PRESERVED
        assert "rtl" in finding.values["declarations"]

    def test_both_barred_properties_are_seen_even_back_to_back(self, tmp_path):
        """Consuming the separator would hide the second behind the first."""
        result = self.styled(
            tmp_path, "body { direction:ltr;unicode-bidi:normal;font-size:1em }"
        )
        sheet = self.sheet_of(result)
        assert "direction" not in sheet and "unicode-bidi" not in sheet
        assert "font-size:1em" in sheet
        finding = next(
            f for f in result.report.findings if f.rule == "css.direction-default-removed"
        )
        assert finding.values["count"] == 2

    @pytest.mark.parametrize(
        ("css", "survives"),
        [
            (".x { flex-direction: column; }", "flex-direction"),
            ("a.direction:hover { color: red; }", "a.direction:hover"),
        ],
    )
    def test_a_name_that_merely_contains_the_word_is_not_it(self, tmp_path, css, survives):
        """`flex-direction` is a different property and `a.direction:hover` is a
        selector. Both look like the barred declaration to a careless pattern."""
        result = self.styled(tmp_path, css)
        assert survives in self.sheet_of(result)
        assert "css.direction-default-removed" not in rules_of(result)
        assert "css.direction-kept" not in rules_of(result)
