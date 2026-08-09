"""Finding a rule in a stylesheet without rewriting the parts left alone.

The scanner exists because the obvious method does not work. Rebuilding a sheet
from a CSS parser's model reformats every line, drops every comment, and —
measured over the seventy-two stylesheets in thirty-two commercial books —
**silently loses `@media` blocks in twenty-one of them**. A removal whose method
deletes a media query while claiming to delete an unused rule is not a removal.

So the tests below are mostly about what the scanner refuses to touch.
"""

from __future__ import annotations

from epubforge.stylesheet import (
    names_nothing_here,
    top_level_rules,
    without,
)


class TestFindingRules:
    def test_it_reads_a_plain_sheet(self):
        text = "p { margin: 0; }\n.dropcap { float: left; }\n"
        spans = top_level_rules(text)
        assert [s.selector for s in spans] == ["p", ".dropcap"]
        assert text[spans[1].start : spans[1].end].strip() == ".dropcap { float: left; }"

    def test_a_minified_sheet_reads_the_same(self):
        """Three of the owner's books ship minified. A scanner that needs
        whitespace to find a boundary would report them as empty."""
        spans = top_level_rules("body.a,body.b{padding-top:6em}p{margin:0}")
        assert [s.selector for s in spans] == ["body.a,body.b", "p"]

    def test_a_brace_inside_a_string_is_not_structure(self):
        """`content: "}"` is legal CSS and has ended more than one hand-written
        parser."""
        text = '.q:before { content: "}"; }\n.after { color: red; }\n'
        assert [s.selector for s in top_level_rules(text)] == [".q:before", ".after"]

    def test_a_brace_inside_a_comment_is_not_structure_either(self):
        text = "/* was: .old { color: red } */\n.new { color: blue; }\n"
        assert [s.selector for s in top_level_rules(text)] == [".new"]

    def test_an_at_rule_is_returned_as_nothing_at_all(self):
        """Not the block, and not the rules inside it. `@media` says "under
        this condition", and a condition this cannot evaluate is a reason to
        leave the contents alone rather than a reason to guess."""
        text = "@media print { .x { color: red; } }\n.y { color: blue; }\n"
        assert [s.selector for s in top_level_rules(text)] == [".y"]

    def test_a_font_face_is_left_alone_too(self):
        text = '@font-face { font-family: "A"; src: url(a.ttf); }\np { margin: 0; }\n'
        assert [s.selector for s in top_level_rules(text)] == ["p"]

    def test_a_charset_line_is_not_mistaken_for_a_selector(self):
        text = '@charset "utf-8";\n.x { color: red; }\n'
        assert [s.selector for s in top_level_rules(text)] == [".x"]


class TestCutting:
    def test_everything_outside_the_cut_survives_exactly(self):
        text = "/* keep me */\np { margin: 0; }\n\n.dead { color: red; }\n\nh1 { font-size: 2em; }\n"
        spans = top_level_rules(text)
        dead = [s for s in spans if s.selector == ".dead"]
        result = without(text, dead)
        assert "/* keep me */" in result
        assert "p { margin: 0; }" in result
        assert "h1 { font-size: 2em; }" in result
        assert ".dead" not in result

    def test_a_media_block_survives_a_cut_around_it(self):
        """The failure mode that decided the method."""
        text = ".dead { color: red; }\n@media print { .x { color: blue; } }\n"
        spans = top_level_rules(text)
        assert without(text, spans).strip() == "@media print { .x { color: blue; } }"

    def test_removing_nothing_returns_the_text_unchanged(self):
        text = "p { margin: 0; }\n"
        assert without(text, []) == text


class TestWhatCountsAsUnreachable:
    """Every one of these is a case that would otherwise be got wrong, and the
    cost of getting it wrong is a page that loses its styling."""

    def test_a_class_no_document_carries(self):
        assert names_nothing_here("td.proc4", set(), set())

    def test_a_class_some_document_carries(self):
        assert not names_nothing_here("td.proc4", {"proc4"}, set())

    def test_a_selector_list_dies_only_when_every_branch_does(self):
        """`.dead, .alive { … }` is a rule about `.alive`, and deleting it
        deletes that."""
        assert not names_nothing_here(".dead, .alive", {"alive"}, set())
        assert names_nothing_here(".dead, .also-dead", {"alive"}, set())

    def test_a_descendant_selector_dies_if_any_part_of_it_is_absent(self):
        """`.chapter .dropcap` cannot match when nothing carries `dropcap`,
        however many chapters there are."""
        assert names_nothing_here(".chapter .dropcap", {"chapter"}, set())

    def test_a_bare_tag_is_never_unreachable(self):
        """Not because it could not be, but because deciding that from a parse
        would put a book's whole running-text styling one bug away from
        deletion."""
        assert not names_nothing_here("p", set(), set())
        assert not names_nothing_here("blockquote > p", set(), set())

    def test_an_attribute_selector_is_never_unreachable(self):
        """What it reaches cannot be settled by name."""
        assert not names_nothing_here('.x[data-role="note"]', set(), set())

    def test_a_pseudo_class_is_never_unreachable(self):
        """It may depend on document position or on reader state."""
        assert not names_nothing_here(".x:first-child", set(), set())
        assert not names_nothing_here(".x::first-letter", set(), set())

    def test_a_universal_is_never_unreachable(self):
        assert not names_nothing_here("*.x", set(), set())

    def test_an_id_counts_the_same_way_as_a_class(self):
        assert names_nothing_here("#nowhere", set(), set())
        assert not names_nothing_here("#somewhere", set(), {"somewhere"})


class TestThroughTheRebuild:
    """The rule as the reader of a report meets it: reported in `preserve`,
    removed in `strict`, and never on a book that carries a script.

    The split is the roadmap's, written before any of this existed and against
    a source document that wanted the removal in `preserve` too. The reasoning
    has not aged: a selector matching nothing *in the documents we parsed* is
    not the same claim as a selector matching nothing.
    """

    SHEET = """@charset "utf-8";
/* Section heading the publisher wrote */
p { margin: 0; }
td.proc4 { text-align: center; width: 3%; }
hr.dotted_line { border-top: 2px dotted gray; }
.used { font-style: italic; }
@media print { .proc9 { color: red; } }
"""

    def book(self, tmp_path, *, body: str) -> str:
        from .factory import write_zip

        package = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Powiesc bez tabel</dc:title>
    <dc:identifier id="id">urn:uuid:4b7d2c88-1e35-4a90-9f77-3c02e6a5d118</dc:identifier>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""
        nav = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl"><head><title>Spis</title>'
            '</head><body><nav epub:type="toc"><ol><li>'
            '<a href="chapter.xhtml">Rozdzial</a></li></ol></nav></body></html>\n'
        )
        chapter = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">'
            '<head><title>Rozdzial</title><link rel="stylesheet" href="style.css"/></head>\n'
            f"<body>{body}</body></html>\n"
        )
        container = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
        )
        return write_zip(
            str(tmp_path / "in.epub"),
            {
                "META-INF/container.xml": container.encode(),
                "OEBPS/package.opf": package.encode(),
                "OEBPS/nav.xhtml": nav.encode(),
                "OEBPS/chapter.xhtml": chapter.encode(),
                "OEBPS/style.css": self.SHEET.encode(),
            },
        )

    PROSE = '<p class="used">Tekst rozdzialu, bez jednej tabeli.</p>'

    def forge(self, tmp_path, mode, body=None):
        import zipfile

        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        source = self.book(tmp_path, body=body or self.PROSE)
        result = rebuild(source, str(tmp_path / f"out-{mode}.epub"), Policy.preset(mode))
        assert result.output_path, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if n.endswith(".css"))
            return result, archive.read(name).decode()

    def rules(self, result) -> set:
        return {f.rule for f in result.report.findings if f.rule}

    def test_preserve_reports_and_keeps_every_byte(self, tmp_path):
        result, sheet = self.forge(tmp_path, "preserve")
        assert "css.unreachable-rules-found" in self.rules(result)
        assert "td.proc4" in sheet and "hr.dotted_line" in sheet

    def test_strict_removes_them(self, tmp_path):
        result, sheet = self.forge(tmp_path, "strict")
        assert "css.unreachable-rules-removed" in self.rules(result)
        assert "td.proc4" not in sheet and "hr.dotted_line" not in sheet

    def test_what_the_book_uses_stays(self, tmp_path):
        _, sheet = self.forge(tmp_path, "strict")
        assert ".used" in sheet and "font-style: italic" in sheet

    def test_a_bare_tag_rule_stays(self, tmp_path):
        """Running-text styling is not decided from a parse."""
        _, sheet = self.forge(tmp_path, "strict")
        assert "p { margin: 0; }" in sheet

    def test_the_media_block_stays_whole(self, tmp_path):
        """`.proc9` matches nothing either. It is inside a condition this cannot
        evaluate, and rebuilding sheets through a CSS serialiser instead of
        cutting the text dropped `@media` outright in 21 of 72 real
        stylesheets."""
        _, sheet = self.forge(tmp_path, "strict")
        assert "@media print" in sheet and ".proc9" in sheet

    def test_the_publishers_comment_stays_where_he_put_it(self, tmp_path):
        """A comment in front of a rule may be a section heading, not a note
        about that rule."""
        _, sheet = self.forge(tmp_path, "strict")
        assert "Section heading the publisher wrote" in sheet

    def test_a_scripted_book_is_left_alone_entirely(self, tmp_path):
        """A script can add a class while the book is being read, and then
        "matches nothing" is a statement about the file rather than about the
        reading."""
        body = self.PROSE + '<script>document.body.className = "proc4";</script>'
        result, sheet = self.forge(tmp_path, "strict", body=body)
        assert "css.unreachable-rules-scripted" in self.rules(result)
        assert "td.proc4" in sheet

    def test_a_class_used_only_inside_svg_counts_as_used(self, tmp_path):
        """A rule for a drawn element is not dead because the element is drawn
        rather than written."""
        self.SHEET = self.SHEET.replace(
            ".used { font-style: italic; }", ".drawn { fill: red; }\n.used { font-style: italic; }"
        )
        body = (
            self.PROSE
            + '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4">'
            '<rect class="drawn" width="4" height="4"/></svg>'
        )
        try:
            _, sheet = self.forge(tmp_path, "strict", body=body)
        finally:
            del self.SHEET
        assert ".drawn" in sheet
