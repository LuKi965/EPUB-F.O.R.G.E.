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
