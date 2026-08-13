"""F-018 — what a regenerated navigation document was quietly losing.

This program does not edit a navigation document; it writes a new one from the
model and throws the old one away. That is the right shape — the source's nav
can be an EPUB 2 relic, a Calibre export or nothing at all — and it has a cost
that nobody had priced: **whatever the model does not hold, the new document
does not have.**

The reader knew three kinds of `nav`: the contents, the landmarks and the page
list. EPUB 3 puts no limit on the kinds. `lot` is a list of tables, `loi` a list
of illustrations, `lov` a list of video, and a publisher may write their own
`epub:type` for anything else. Every one of those was parsed into nothing and
regenerated into nothing: the entries did not appear in the output, no finding
mentioned them, and the labels — text a person wrote, in the book's own
language — were gone.

K1 says no character of the book's text is lost. "We had no rule for that
section" is not an exemption from it.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import MODERN_OPF, png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>Rozdzia&#x142;</title></head>
  <body>
    <h1 id="start">Rozdzia&#x142;</h1>
    <p>Tekst.</p>
    <figure id="ilustracja-1"><img src="picture.png" alt="Rysunek"/></figure>
    <table id="tabela-1"><caption>Tabela pierwsza</caption><tr><td>1</td></tr></table>
  </body>
</html>
"""

#: A navigation document of the kind a real publisher ships: the contents, and
#: beside it two lists this program has no rule for.
RICH_NAV = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><meta charset="utf-8"/><title>Spis</title></head>
  <body>
    <nav epub:type="toc" id="spis">
      <h1>Spis treści</h1>
      <ol><li><a href="chapter.xhtml#start">Rozdział</a></li></ol>
    </nav>
    <nav epub:type="loi">
      <h1>Spis ilustracji</h1>
      <ol><li><a href="chapter.xhtml#ilustracja-1">Rysunek 1. Widok ogólny</a></li></ol>
    </nav>
    <nav epub:type="lot" hidden="hidden">
      <h1>Spis tabel</h1>
      <ol><li><a href="chapter.xhtml#tabela-1">Tabela 1. Wyniki</a></li></ol>
    </nav>
    <nav epub:type="page-list">
      <ol><li><a href="chapter.xhtml#start">7</a></li></ol>
    </nav>
  </body>
</html>
"""


def source(path, nav: str = RICH_NAV) -> str:
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": MODERN_OPF.format(title="Test", extra_metadata="").encode(),
            "OEBPS/nav.xhtml": nav.encode(),
            "OEBPS/chapter.xhtml": CHAPTER.encode(),
            "OEBPS/picture.png": png_bytes(),
        },
    )


def built(path, tmp_path, mode: str = "preserve"):
    return rebuild(str(path), str(tmp_path / "out.epub"), Policy.preset(mode))


def navigation(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(
            n for n in archive.namelist()
            if n.endswith("nav.xhtml") or n.endswith("nav-epub3.xhtml")
        )
        return archive.read(name).decode("utf-8")


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


class TestASectionThisProgramHasNoRuleFor:
    def test_its_entries_are_in_the_rebuilt_book(self, tmp_path):
        """The labels are text the publisher wrote. K1 does not have a clause
        about which element they were in."""
        document = navigation(built(source(tmp_path / "rich.epub"), tmp_path))
        assert "Rysunek 1. Widok ogólny" in document
        assert "Tabela 1. Wyniki" in document

    def test_and_they_still_say_what_kind_of_list_they_are(self, tmp_path):
        """`epub:type` carried verbatim. It is the publisher's word for what the
        section is, and there is nothing here to translate it into."""
        document = navigation(built(source(tmp_path / "types.epub"), tmp_path))
        assert 'epub:type="loi"' in document
        assert 'epub:type="lot"' in document

    def test_a_section_the_source_hid_stays_hidden(self, tmp_path):
        """`hidden` is a decision about the rendered page, and the publisher made
        it. Dropping it puts a list of tables in front of a reader who was not
        shown one."""
        document = navigation(built(source(tmp_path / "hidden.epub"), tmp_path))
        table_section = document.split('epub:type="lot"', 1)[1].split(">", 1)[0]
        assert "hidden" in table_section

    def test_the_publishers_own_heading_is_kept(self, tmp_path):
        """This program writes headings for the three sections it generates, in
        the book's language. For a section it did not generate it has no name to
        offer and no business inventing one."""
        assert "Spis ilustracji" in navigation(built(source(tmp_path / "head.epub"), tmp_path))

    def test_the_report_says_it_carried_them_rather_than_understood_them(self, tmp_path):
        result = built(source(tmp_path / "report.epub"), tmp_path)
        assert "nav.sections-carried" in rules_of(result)
        finding = next(f for f in result.report.findings if f.rule == "nav.sections-carried")
        assert finding.level.value == "preserved"
        assert "loi" in finding.values["names"]

    def test_an_entry_whose_target_is_gone_does_not_survive_it(self, tmp_path):
        """Carried is not exempt from the rules the contents obey: an entry
        leading to a document that is not in the book is dropped there, and it
        is dropped here."""
        nav = RICH_NAV.replace("chapter.xhtml#ilustracja-1", "usuniety.xhtml#x")
        result = built(source(tmp_path / "gone.epub", nav), tmp_path)
        assert "usuniety.xhtml" not in navigation(result)

    @pytest.mark.parametrize("mode", ["preserve", "strict"])
    def test_in_every_mode_that_regenerates_the_document(self, tmp_path, mode):
        document = navigation(built(source(tmp_path / f"{mode}.epub"), tmp_path, mode))
        assert "Rysunek 1. Widok ogólny" in document


class TestWhatTheGeneratedDocumentDeclaresAboutItself:
    def test_the_page_list_says_it_is_one(self, tmp_path):
        """`doc-pagelist` is what tells assistive technology that these numbers
        are the print edition's pages rather than a list of links. The contents
        has carried `doc-toc` since it was written; this one had nothing."""
        document = navigation(built(source(tmp_path / "aria.epub"), tmp_path))
        assert 'role="doc-pagelist"' in document

    def test_the_contents_still_does_too(self, tmp_path):
        assert 'role="doc-toc"' in navigation(built(source(tmp_path / "toc.epub"), tmp_path))

    def test_a_section_with_no_standard_role_is_given_none(self, tmp_path):
        """There is no ARIA role for "list of tables". Inventing one states
        something about the section that the publisher did not."""
        document = navigation(built(source(tmp_path / "norole.epub"), tmp_path))
        opening = document.split('epub:type="lot"', 1)[1].split(">", 1)[0]
        assert "role=" not in opening


class TestTheDocumentIsStillValid:
    def test_epubcheck_accepts_the_carried_sections(self, tmp_path):
        """A carried section is markup this program did not write and is now
        responsible for. EPUB 3 constrains what a `nav` may contain — heading
        then `ol`, nothing else — so "we passed it through" has to mean "we
        passed it through into something that conforms"."""
        from epubforge.validate import find_epubcheck, validate

        if find_epubcheck() is None:
            pytest.skip("EPUBCheck is not installed here")
        result = built(source(tmp_path / "check.epub"), tmp_path)
        validate(result.output_path, result.report)
        errors = [
            f for f in result.report.findings
            if f.stage == "epubcheck" and f.level.value == "error"
        ]
        assert not errors, [f.detail for f in errors]


class TestTheMoveThatForgetsSomething:
    """`Book.rename` has now been the site of this bug three times.

    Media durations, then the encryption register, now the carried sections:
    each is a collection of paths, each was added to the model without being
    added to the move, and each failure looked like something else — entries
    quietly vanishing, a stale key nobody read. It is worth one direct test that
    does not go through a rebuild, because through a rebuild it reads as "the
    navigation lost a section" and the cause is four files away.
    """

    def test_a_carried_section_follows_the_file_it_points_at(self):
        from epubforge.model import Book, NavPoint, NavSection, Resource

        book = Book()
        book.add(Resource(path="OEBPS/chapter.xhtml", media_type="application/xhtml+xml", data=b""))
        book.extra_navs = [
            NavSection("loi", "Ilustracje", [NavPoint("Rysunek 1", "OEBPS/chapter.xhtml#il-1")])
        ]
        book.rename("OEBPS/chapter.xhtml", "EPUB/text/0000-chapter.xhtml")
        assert book.extra_navs[0].entries[0].target == "EPUB/text/0000-chapter.xhtml#il-1"
