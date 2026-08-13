"""F-004 — the two things a parse quietly did to a document on the way in.

Every content document goes through `xhtml.parse_document`, which tries strict
XML and falls back to an HTML parser that recovers from anything. Both of the
losses below happened *before* any stage had an opinion about the book, which is
why neither showed up in a report: the damage was in the tree the stages were
handed, so as far as they could tell it was what the publisher wrote.

**One.** `<?xml-stylesheet href="main.css"?>` — how an XHTML document written
before EPUB 3 links a stylesheet — was deleted by a `sub()` at the top of the
parse. EPUB 3 does not allow the instruction, so removing it is right; removing
it and putting nothing in its place means the book comes out unstyled, and the
report says nothing at all. This project's own rule is that a construct
carrying visual meaning is *translated*, not deleted.

**Two.** HTML is case-insensitive and SVG is not. A document that has to be
recovered by the HTML parser comes back with `linearGradient` spelled
`lineargradient`, which is not that element — it is nothing — and `viewBox` as
`viewbox`, without which the drawing has no coordinate system to scale into. A
gradient that renders as flat colour, in a file that validates.

**And the mode itself.** A tag-soup recovery is a reconstruction, not a repair
with a known result. It was reported at FIX, alongside things this program can
show it got right. The audit asked for such a document to be marked and not
published as an ordinary result; it is WARN now, and the rebuild's status says
there is something to read.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import xhtml
from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy
from tests.factory import MODERN_NAV, MODERN_OPF, png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

GRADIENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50" width="100" height="50">'
    '<defs><linearGradient id="g" gradientUnits="objectBoundingBox">'
    '<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#000"/>'
    "</linearGradient></defs>"
    '<rect width="100" height="50" fill="url(#g)"/></svg>'
)


def document(*, head: str = "", body: str, well_formed: bool = True) -> bytes:
    text = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f"{head}"
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">'
        "<head><meta charset=\"utf-8\"/><title>Rozdział</title></head>"
        f"<body>{body}</body></html>"
    )
    if not well_formed:
        # An unclosed <b>, which is what a converter leaves behind and what
        # sends the document down the recovery path.
        text = text.replace("<body>", "<body><b>")
    return text.encode("utf-8")


def book(path, *, chapter: bytes, extra: dict[str, bytes] | None = None) -> str:
    entries = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/package.opf": MODERN_OPF.format(title="Test", extra_metadata="").encode(),
        "OEBPS/nav.xhtml": MODERN_NAV.encode(),
        "OEBPS/chapter.xhtml": chapter,
        "OEBPS/picture.png": png_bytes(),
    }
    entries.update(extra or {})
    return write_zip(str(path), entries)


def built(source, tmp_path, mode: str = "preserve"):
    return rebuild(source, str(tmp_path / "out.epub"), Policy.preset(mode))


def chapter_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("chapter.xhtml"))
        return archive.read(name).decode("utf-8")


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


class TestF004AStylesheetLinkedTheOldWay:
    @staticmethod
    def styled(path) -> str:
        return book(
            path,
            chapter=document(
                head='<?xml-stylesheet type="text/css" href="styl.css"?>\n',
                body="<p>Tekst</p>",
            ),
            extra={"OEBPS/styl.css": b"p { color: #123456 }"},
        )

    def test_the_instruction_is_translated_rather_than_dropped(self, tmp_path):
        chapter = chapter_of(built(self.styled(tmp_path / "pi.epub"), tmp_path))
        assert "xml-stylesheet" not in chapter, "EPUB 3 does not allow the instruction"
        assert 'rel="stylesheet"' in chapter, "and the styling has to survive it"

    def test_the_link_points_at_the_stylesheet_where_it_now_lives(self, tmp_path):
        """The href is rewritten with every other reference in the document, so
        a `<link>` added here follows the file into its new folder."""
        result = built(self.styled(tmp_path / "pi2.epub"), tmp_path)
        chapter = chapter_of(result)
        href = chapter.split('rel="stylesheet"', 1)[1].split('href="', 1)[1].split('"', 1)[0]
        with zipfile.ZipFile(result.output_path) as archive:
            names = archive.namelist()
        assert any(name.endswith(href.rsplit("/", 1)[-1]) for name in names)

    def test_the_report_names_the_stylesheet(self, tmp_path):
        result = built(self.styled(tmp_path / "pi3.epub"), tmp_path)
        assert "xhtml.stylesheet-pi-converted" in rules_of(result)
        finding = next(
            f for f in result.report.findings if f.rule == "xhtml.stylesheet-pi-converted"
        )
        assert "styl.css" in finding.values["names"]

    def test_a_document_that_already_links_it_gains_nothing(self, tmp_path):
        """Both forms in one document is a real shape — a converter adds the
        `<link>` and leaves the instruction — and two links to one sheet is a
        second, redundant fetch."""
        source = book(
            tmp_path / "both.epub",
            chapter=document(
                head='<?xml-stylesheet type="text/css" href="styl.css"?>\n',
                body="<p>Tekst</p>",
            ).replace(
                b"</title>", b'</title><link rel="stylesheet" type="text/css" href="styl.css"/>'
            ),
            extra={"OEBPS/styl.css": b"p { color: #123456 }"},
        )
        assert chapter_of(built(source, tmp_path)).count('rel="stylesheet"') == 1


class TestF004SvgSurvivesARecovery:
    @staticmethod
    def drawing(path) -> str:
        return book(path, chapter=document(body=f"<p>{GRADIENT}</p>", well_formed=False))

    def test_the_document_really_did_take_the_recovery_path(self, tmp_path):
        """A guard on the fixture: if it parsed as XML, the test below proves
        nothing about recovery."""
        result = built(self.drawing(tmp_path / "svg.epub"), tmp_path)
        assert "xhtml.recovered-with-html-parser" in rules_of(result)

    def test_the_gradient_is_still_a_gradient(self, tmp_path):
        chapter = chapter_of(built(self.drawing(tmp_path / "svg2.epub"), tmp_path))
        assert "linearGradient" in chapter
        assert "lineargradient" not in chapter

    def test_and_the_drawing_still_has_a_coordinate_system(self, tmp_path):
        chapter = chapter_of(built(self.drawing(tmp_path / "svg3.epub"), tmp_path))
        assert "viewBox" in chapter

    def test_the_report_says_it_had_to_do_that(self, tmp_path):
        result = built(self.drawing(tmp_path / "svg4.epub"), tmp_path)
        assert "xhtml.svg-case-restored" in rules_of(result)

    def test_nothing_outside_svg_is_recapitalised(self, tmp_path):
        """HTML attributes are lowercase and correct that way. A table keyed on
        SVG names must not reach into the rest of the document."""
        source = book(
            tmp_path / "html.epub",
            chapter=document(body='<p><img src="picture.png" alt="x"/></p>', well_formed=False),
        )
        chapter = chapter_of(built(source, tmp_path))
        assert "<img" in chapter and "Src=" not in chapter

    def test_a_well_formed_document_is_not_touched_at_all(self):
        """The restorer runs only on the recovery path. A document the XML
        parser accepted never lost its capitals, and a table applied to it could
        only ever invent something."""
        parsed = xhtml.parse_document(document(body=f"<p>{GRADIENT}</p>"))
        assert parsed.mode == "xml"
        assert parsed.svg_case_restored == 0


class TestF004ARecoveredDocumentIsNotAnOrdinaryResult:
    def test_the_finding_is_a_warning_rather_than_a_fix(self, tmp_path):
        """FIX means this program changed something and can say what the result
        is. A tag-soup recovery is a reconstruction: it cannot."""
        source = book(tmp_path / "warn.epub", chapter=document(body="<p>x</p>", well_formed=False))
        result = built(source, tmp_path)
        finding = next(
            f for f in result.report.findings if f.rule == "xhtml.recovered-with-html-parser"
        )
        assert finding.level.value == "warn"

    def test_the_book_is_written_and_does_not_claim_to_be_clean(self, tmp_path):
        source = book(tmp_path / "status.epub", chapter=document(body="<p>x</p>", well_formed=False))
        result = built(source, tmp_path)
        assert result.output_path is not None, "the book is still rebuilt"
        assert result.status is Status.SUCCEEDED_WITH_PROBLEMS

    def test_a_book_of_well_formed_documents_still_says_succeeded(self, tmp_path):
        """The guard on the guard: a status that is never clean says nothing."""
        source = book(tmp_path / "clean.epub", chapter=document(body="<p>x</p>"))
        assert built(source, tmp_path).status is Status.SUCCEEDED

    @pytest.mark.parametrize("mode", ["preserve", "strict", "minimal"])
    def test_the_document_is_reported_in_every_mode_that_reads_it(self, tmp_path, mode):
        source = book(tmp_path / f"{mode}.epub", chapter=document(body="<p>x</p>", well_formed=False))
        result = built(source, tmp_path, mode)
        if mode == "minimal":
            # Container-only mode does not parse content documents at all, so
            # there is nothing for it to have recovered — and nothing lost.
            pytest.skip("content is not parsed in container-only mode")
        assert "xhtml.recovered-with-html-parser" in rules_of(result)
