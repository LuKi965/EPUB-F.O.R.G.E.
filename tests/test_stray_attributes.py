"""Attributes an element is not allowed to carry, and what happens to them.

Seven shapes of `RSC-005` survived a `preserve` rebuild on the owner's second
shelf — errors *this program produced*, in books that arrived without them. Two
of the seven were attributes nobody ever defined: `font17` and `p`, written by
an exporter recording its own state in the markup. The rest were real legacy
attributes sitting on elements that never took them: `clear` on a `<p>`, `size`
on a `<span>`, `link` on a `<div>`.

Every one of them had a route no list of known names would have covered, which
is why the rule here runs the other way round. **An attribute this element is
not allowed to carry is one no engine reads** — that is what makes removing it
safe, and it is also exactly why leaving it is an error rather than a quirk.

Two things keep that from becoming a licence to strip:

* where the attribute still means something to a page, the meaning is
  translated into CSS first, so the appearance survives the removal;
* anything under a vocabulary of its own — `data-`, `aria-`, `epub:`, RDFa, and
  every element outside the XHTML namespace — is not this sweep's business.

The last of those is not theoretical. The first version of this had no
namespace exemption and stripped `viewBox` off an `<svg>`, which is a drawing
losing its coordinate system. The suite caught it in one run; the exemption is
by namespace rather than by a list of element names, because an SVG document
can contain elements this program has never heard of.
"""

from __future__ import annotations

import zipfile


from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.stages.content import ContentStage
from tests.factory import make_legacy_epub


def rebuilt_document(tmp_path, body: str, *, head: str = "", mode: str = "preserve") -> str:
    """A legacy book carrying *body*, rebuilt, with its first chapter read back."""
    source = make_legacy_epub(str(tmp_path / "in.epub"))
    entries = {}
    with zipfile.ZipFile(source) as archive:
        for name in archive.namelist():
            entries[name] = archive.read(name)
    document = next(
        name for name in entries
        if name.endswith(".xhtml") and "nav" not in name and "cover" not in name
    )
    page = entries[document].decode()
    # A sentinel, because the rebuild renumbers documents: the chapter edited
    # here comes out under a different name, and picking "the first chapter" on
    # both sides read back a document this function had never touched.
    page = page.replace("</body>", body + '<i id="znacznik-testu"></i></body>')
    if head:
        page = page.replace("</head>", head + "</head>")
    entries[document] = page.encode()
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)

    result = rebuild(
        source,
        str(tmp_path / "out.epub"),
        Policy.preset(mode, validate_before_publish="off"),
    )
    assert result.status.wrote_a_file, result.report.to_text()
    with zipfile.ZipFile(result.output_path) as archive:
        for entry in archive.namelist():
            if not entry.endswith(".xhtml"):
                continue
            written = archive.read(entry).decode()
            if "znacznik-testu" in written:
                return written
    raise AssertionError("the edited document is not in the output")


class TestWhatAnExporterInvented:
    """`font17` and `p` as attribute names. Neither is a misspelling of
    anything; both are an exporter writing its own bookkeeping into the file."""

    def test_an_invented_attribute_goes(self, tmp_path):
        written = rebuilt_document(tmp_path, '<p font17="1">Tekst akapitu.</p>')
        assert "font17" not in written
        assert "Tekst akapitu." in written, "and the text it was on stays"

    def test_an_attribute_named_after_an_element_goes(self, tmp_path):
        written = rebuilt_document(tmp_path, '<p p="x">Drugi akapit.</p>')
        assert ' p="x"' not in written
        assert "Drugi akapit." in written


class TestWhatStillMeantSomething:
    """The half that separates this from stripping markup.

    `clear` and `size` were honoured by the engines of their day. Removing them
    without translating would take a piece of the page with them, which is the
    owner's rule twice over: *losing an ornament is damage to the book too.*
    """

    def test_clear_on_a_paragraph_becomes_css(self, tmp_path):
        written = rebuilt_document(tmp_path, '<p clear="all">Po ilustracji.</p>')
        assert 'clear="all"' not in written
        assert "clear: both" in written

    def test_size_on_a_rule_becomes_a_height(self, tmp_path):
        written = rebuilt_document(tmp_path, '<hr size="3"/>')
        assert 'size="3"' not in written
        assert "height: 3px" in written

    def test_size_where_it_never_drew_anything_is_simply_dropped(self, tmp_path):
        """`size` on a `<span>` was never rendered by anything. There is nothing
        to translate, so translating would be inventing."""
        written = rebuilt_document(tmp_path, '<span size="2">Tekst prób.</span>')
        assert 'size="2"' not in written
        # Asserted on this span rather than on the document: the fixture carries
        # a `font-size: larger` of its own elsewhere, and a document-wide search
        # would have passed for the wrong reason.
        assert "<span>Tekst prób.</span>" in written


class TestVocabulariesThisDoesNotOwn:
    def test_data_and_aria_and_the_epub_namespace_survive(self, tmp_path):
        written = rebuilt_document(
            tmp_path,
            '<p data-rola="cos" aria-label="etykieta" class="Body" id="a1">Tekst.</p>',
        )
        for kept in ('data-rola="cos"', 'aria-label="etykieta"', 'class="Body"'):
            assert kept in written, kept

    def test_an_svg_keeps_its_coordinate_system(self, tmp_path):
        """The defect this test exists for. Stripped of `viewBox`, a drawing
        has no coordinate system and renders at whatever size the box happens
        to be — a picture silently changed, which is the one outcome this
        program is built to prevent."""
        written = rebuilt_document(
            tmp_path,
            '<p><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">'
            '<rect width="100" height="50"/></svg></p>',
        )
        assert "viewBox" in written

    def test_rdfa_is_not_stripped(self, tmp_path):
        """EPUB 3 allows RDFa in content documents, and a book uses it to say
        what its parts are. Held as exact names rather than a prefix, so that
        `relative` and `contents` are not kept by accident."""
        written = rebuilt_document(
            tmp_path, '<p property="dcterms:title" typeof="Work">Tytuł.</p>'
        )
        assert 'property="dcterms:title"' in written

    def test_an_element_this_table_has_never_heard_of_keeps_the_globals(self):
        """The conservative direction, asserted directly. An unknown element is
        judged on the global attributes alone rather than stripped on a guess.
        """
        from epubforge.stages import content

        assert "class" in content._GLOBAL_ATTRIBUTES
        assert content._ELEMENT_ATTRIBUTES.get("nieznany") is None


class TestContentInThePlaceAParserWouldMoveIt:
    """Two shapes from the same shelf, and the same principle behind both fixes:
    put the content where the reader was **already seeing it**.

    A browser has moved both of these for twenty years — content inside a table
    but not inside a cell is foster-parented out in front of the table, and flow
    content in `<head>` starts the body. Writing that down changes the markup
    and not the page.
    """

    def test_a_link_loose_inside_a_table_is_lifted_out_in_front_of_it(self, tmp_path):
        written = rebuilt_document(
            tmp_path,
            '<table><a href="#gdzies">Odnośnik</a><tr><td>komórka</td></tr></table>',
        )
        assert "Odnośnik" in written
        assert written.index("Odnośnik") < written.index("<table"), (
            "foster parenting puts it before the table, which is where it drew"
        )

    def test_a_paragraph_that_landed_in_the_head_moves_to_the_top_of_the_body(
        self, tmp_path
    ):
        written = rebuilt_document(tmp_path, "", head="<p>Zabłąkany akapit.</p>")
        assert "Zabłąkany akapit." in written
        assert written.index("Zabłąkany akapit.") > written.index("<body")

    def test_what_a_table_and_a_head_are_allowed_to_hold_is_named(self):
        """Both lists say what stays rather than what goes, so an element
        nobody thought of is moved rather than silently kept in an invalid
        place — and `<script>` and `<template>`, which are legal in both, are
        in both."""
        for allowed in (ContentStage._TABLE_CONTENT, ContentStage._HEAD_CONTENT):
            assert "script" in allowed and "template" in allowed
        assert "tr" in ContentStage._TABLE_CONTENT
        assert "title" in ContentStage._HEAD_CONTENT


class TestTheReportSaysWhatItDid:
    def test_every_removal_is_named_in_the_finding(self, tmp_path):
        source = make_legacy_epub(str(tmp_path / "named.epub"))
        entries = {}
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                entries[name] = archive.read(name)
        document = next(
            name for name in entries
            if name.endswith(".xhtml") and "nav" not in name and "cover" not in name
        )
        entries[document] = entries[document].decode().replace(
            "</body>", '<p font17="1" clear="all">Tekst.</p></body>'
        ).encode()
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

        result = rebuild(
            source,
            str(tmp_path / "named-out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        said = [
            finding for finding in result.report.findings
            if finding.rule == "xhtml.presentational-markup-converted"
        ]
        assert said, [f.rule for f in result.report.findings]
        detail = " ".join(finding.detail or "" for finding in said)
        assert "p[font17]" in detail and "p[clear]" in detail

    def test_the_text_is_untouched_by_any_of_it(self, tmp_path):
        """K1 says so for the whole book; this says so where the sweep ran."""
        written = rebuilt_document(
            tmp_path,
            '<p font17="1" clear="all" size="2">Zdanie, które musi przetrwać.</p>',
        )
        assert "Zdanie, które musi przetrwać." in written
