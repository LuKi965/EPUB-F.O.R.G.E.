"""Pillar 1 of the 0.3 plan: converter class names become the epubforge dictionary.

The shape is D-031, negotiated with the owner across six conversations and
frozen there: `ef-<category>-<number>`, category from what the class is
attached to in this book, number from the order of first use, a speaking name
where one to three atomic declarations carry the whole truth, the name's
language following the interface, values never touched, the full old→new map
in the report. The owner's acceptance line for the category logic —
`ef-akapit-20` must never turn out to be the book's title — is a test here,
not a sentence in a plan.
"""

from __future__ import annotations

import re
import zipfile

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    '<title>R</title><link rel="stylesheet" type="text/css" href="s.css"/></head>'
    "<body>{body}</body></html>"
)

BODY = (
    '<h2 class="calibre4">Nagłówek</h2>'
    '<p class="calibre9">Akapit pierwszy z treścią rozdziału.</p>'
    '<p class="calibre2">Akapit drugi, inaczej złożony.</p>'
    '<p><span class="sgc-1">kursywa w toku</span></p>'
)

#: `calibre9` appears in the text before `calibre2`, and the two must number
#: by that order, not alphabetically — the number means "which you meet
#: first" and nothing else.
SHEET = (
    "h2.calibre4 { font-size: 1.4em; font-weight: bold; margin: 1em 0 0.5em 0; } "
    "p.calibre9 { margin: 0 0 0.2em 0; text-indent: 1.2em; text-align: justify; line-height: 1.4; } "
    "p.calibre2 { margin: 0.5em 0; text-indent: 0; text-align: left; line-height: 1.2; } "
    "span.sgc-1 { font-style: italic; }"
)


def build(tmp_path, *, translate=True, language="pl", body=BODY, sheet=SHEET):
    source = make_book(
        tmp_path / "in.epub",
        {"c0.xhtml": PAGE.format(body=body)},
        extra_items='<item id="s" href="s.css" media-type="text/css"/>',
        extra_files={"OEBPS/s.css": sheet.encode()},
    )
    policy = Policy.preset("preserve", render_gate="off")
    policy.translate_class_names = translate
    policy.class_name_language = language
    return rebuild(source, str(tmp_path / "out.epub"), policy)


def sheet_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        for name in archive.namelist():
            if name.endswith(".css") and "margin" in archive.read(name).decode("utf-8"):
                return archive.read(name).decode("utf-8")
    raise AssertionError("no stylesheet in the rebuild")


def classes_of(result) -> "set[str]":
    with zipfile.ZipFile(result.output_path) as archive:
        found: set = set()
        for name in archive.namelist():
            if name.endswith(".xhtml") and "kapit" in archive.read(name).decode("utf-8"):
                for value in re.findall(r'class="([^"]+)"', archive.read(name).decode("utf-8")):
                    found.update(value.split())
        return found


class TestTheDictionarySpeaks:
    def test_on_by_default_and_untickable(self, tmp_path):
        """D-032: on in both modes, after the acceptance measurements — and
        untickable, which is what S-02 requires of every change."""
        for name in ("preserve", "strict"):
            assert Policy.preset(name).translate_class_names is True, name
        result = build(tmp_path, translate=False)
        assert "calibre9" in sheet_of(result)
        assert "css.classes-renamed" not in rules_of(result)

    def test_names_land_in_css_and_content_together(self, tmp_path):
        result = build(tmp_path)
        assert result.status.wrote_a_file, result.report.to_text()
        sheet = sheet_of(result)
        assert "calibre" not in sheet and "sgc-1" not in sheet
        assert "h2.ef-naglowek-1" in sheet
        assert classes_of(result) == {
            "ef-naglowek-1", "ef-akapit-1", "ef-akapit-2", "ef-kursywa"
        }
        assert "css.classes-renamed" in rules_of(result)

    def test_values_are_untouched(self, tmp_path):
        """Only the name changes — the composition survives to the character."""
        result = build(tmp_path)
        sheet = sheet_of(result)
        assert "margin: 0 0 0.2em 0; text-indent: 1.2em; text-align: justify; line-height: 1.4;" in sheet

    def test_the_number_is_the_order_of_first_use(self, tmp_path):
        """`calibre9` meets the reader before `calibre2`, so it is `-1` —
        alphabetical order would say the opposite, and the mutation that
        sorts the census fails here."""
        result = build(tmp_path)
        sheet = sheet_of(result)
        first = sheet.index("p.ef-akapit-1")
        assert "text-indent: 1.2em" in sheet[first:first + 120]

    def test_a_simple_rule_speaks(self, tmp_path):
        result = build(tmp_path)
        assert "span.ef-kursywa { font-style: italic; }" in sheet_of(result)

    def test_the_english_window_names_in_english(self, tmp_path):
        result = build(tmp_path, language="en")
        sheet = sheet_of(result)
        assert "h2.ef-heading-1" in sheet
        assert "p.ef-paragraph-1" in sheet
        assert "span.ef-italic" in sheet

    def test_identical_bodies_share_one_name(self, tmp_path):
        """D-031: duplicates merge — measured at 11 on the shelf."""
        body = (
            '<p class="calibre7">Raz.</p><p class="calibre8">Dwa.</p>'
        )
        sheet = (
            "p.calibre7 { margin: 1em 0; text-indent: 2em; line-height: 1.3; text-align: justify; } "
            "p.calibre8 { margin: 1em 0; text-indent: 2em; line-height: 1.3; text-align: justify; }"
        )
        result = build(tmp_path, body=body, sheet=sheet)
        assert classes_of(result) == {"ef-akapit-1"}


class TestTheGuards:
    def test_a_scripted_book_is_left_alone(self, tmp_path):
        """A script may hold a class name in a string — `document.body
        .className = "calibre9"` — and a rename this rewrite cannot see into
        would break it. The mutation that drops the guard fails here."""
        body = BODY + '<script type="text/javascript">var x = "calibre9";</script>'
        result = build(tmp_path, body=body)
        assert "calibre9" in sheet_of(result)
        assert "css.class-translation-scripted" in rules_of(result)
        assert "css.classes-renamed" not in rules_of(result)

    def test_an_attribute_selector_stops_the_rename(self, tmp_path):
        """`[class~="calibre9"]` reaches the class by a route the rewrite
        does not travel; renaming the attribute under it would detach the
        rule. The whole book is left alone, and the report says so."""
        sheet = SHEET + ' [class~="calibre9"] { color: black; }'
        result = build(tmp_path, sheet=sheet)
        assert "calibre9" in sheet_of(result)
        assert "css.class-translation-attr-selector" in rules_of(result)

    def test_broken_markup_in_the_text_is_not_renamed(self, tmp_path):
        """Found by the first shelf run with the switch on, and refused by K1
        before it could ship: one book's visible text contains a literal,
        broken tag — `span class="sgc-5">` with its `<` lost in the source's
        own conversion. That is the book's TEXT, and renaming it changes the
        book. The rewrite touches class attributes inside tags only; the
        mutation that loosens it back to bare `class="…"` fails here."""
        body = (
            '<p class="calibre9">Highway span class="calibre9"&gt;i33 in.</p>'
        )
        sheet = "p.calibre9 { margin: 0; text-indent: 1em; line-height: 1.4; text-align: justify; }"
        result = build(tmp_path, body=body, sheet=sheet)
        assert result.status.wrote_a_file, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            document = next(
                archive.read(n).decode("utf-8")
                for n in archive.namelist()
                if n.endswith(".xhtml") and "Highway" in archive.read(n).decode("utf-8")
            )
        assert 'Highway span class="calibre9"' in document  # the text, untouched
        assert '<p class="ef-akapit-1">' in document        # the attribute, renamed

    def test_the_map_is_in_the_report(self, tmp_path):
        result = build(tmp_path)
        renamed = next(
            finding for finding in result.report.findings
            if finding.rule == "css.classes-renamed"
        )
        assert "calibre4 → ef-naglowek-1" in renamed.detail
        assert "sgc-1 → ef-kursywa" in renamed.detail


TOC_BODY = (
    '<div class="sgc-toc-title">Spis treści</div>'
    '<div class="sgc-toc-level-2"><a href="c0.xhtml">Rozdział</a></div>'
    '<p class="calibre9">Akapit z treścią rozdziału.</p>'
)

TOC_SHEET = (
    "div.sgc-toc-title { font-size: 1.5em; font-weight: bold; margin: 1em 0; } "
    "div.sgc-toc-level-2 { margin-left: 2em; text-indent: 0; } "
    "p.calibre9 { margin: 0 0 0.2em 0; text-indent: 1.2em; line-height: 1.4; }"
)


class TestTheRoleWords:
    """D-033, the owner's own example seconded by the seventh audit:
    `sgc-toc-title` is Sigil's record that it generated a table of contents —
    the tool's note of purpose, the same class of fact as the cover repair's
    marker — and `ef-akapit-1` in its place loses information the old name
    carried. A role word found in the generator's name is translated; a toc
    level's digit is the source's own level and travels with it."""

    def test_a_toc_title_speaks_its_role(self, tmp_path):
        result = build(tmp_path, body=TOC_BODY, sheet=TOC_SHEET)
        assert result.status.wrote_a_file, result.report.to_text()
        sheet = sheet_of(result)
        assert "div.ef-spis-tresci {" in sheet
        # The digit is the source name's own level, carried over — not this
        # program's first-use counter. The mutation that stops carrying it
        # fails here.
        assert "div.ef-spis-tresci-2 {" in sheet
        renamed = next(
            finding for finding in result.report.findings
            if finding.rule == "css.classes-renamed"
        )
        assert "sgc-toc-title → ef-spis-tresci" in renamed.detail

    def test_the_english_window_says_contents(self, tmp_path):
        result = build(tmp_path, body=TOC_BODY, sheet=TOC_SHEET, language="en")
        sheet = sheet_of(result)
        assert "div.ef-contents {" in sheet
        assert "div.ef-contents-2 {" in sheet

    def test_a_heading_styled_block_is_not_a_paragraph(self, tmp_path):
        """The seventh audit's judgment case: converters compose titles out
        of `<div>`, so a block class dressed like a heading — bold, uppercase
        or a font a third larger — must land in `inne`, which claims nothing,
        not in `akapit`, which would lie. Fourteen such classes on the shelf.
        The mutation that drops the heading guard from `categorize` fails
        here."""
        body = (
            '<div class="calibre55">Wielki tytuł rozdziału</div>'
            '<p class="calibre9">Akapit z treścią.</p>'
        )
        sheet = (
            "div.calibre55 { font-size: 1.5em; font-weight: bold; margin: 1em 0; } "
            "p.calibre9 { margin: 0; text-indent: 1.2em; line-height: 1.4; }"
        )
        result = build(tmp_path, body=body, sheet=sheet)
        sheet_text = sheet_of(result)
        assert "div.ef-inne-1 {" in sheet_text
        assert "div.ef-akapit" not in sheet_text

    def test_a_role_name_is_never_shared_by_a_body_double(self, tmp_path):
        """The identical-bodies merge (D-031) must not hand a role name to a
        class that merely shares a rule body: `ef-spis-tresci` on a class
        that is not the contents title would be the lie the whole dictionary
        exists to avoid."""
        body = (
            '<div class="sgc-toc-title">Spis treści</div>'
            '<div class="calibre77">Zupełnie inna rzecz</div>'
            '<p class="calibre9">Akapit z treścią.</p>'
        )
        sheet = (
            "div.sgc-toc-title { font-size: 1.5em; font-weight: bold; margin: 1em 0; } "
            "div.calibre77 { font-size: 1.5em; font-weight: bold; margin: 1em 0; } "
            "p.calibre9 { margin: 0; text-indent: 1.2em; line-height: 1.4; }"
        )
        result = build(tmp_path, body=body, sheet=sheet)
        sheet_text = sheet_of(result)
        assert "div.ef-spis-tresci {" in sheet_text
        assert sheet_text.count("ef-spis-tresci") == 1
        assert "div.ef-inne-1 {" in sheet_text  # heading-styled, no role word

    def test_a_name_cannot_outvote_an_image(self):
        """The one cheap, certain contradiction: a class carried only by
        images is not a table of contents whatever its name says. The role
        falls away and the evidence answers. The mutation that drops the
        guard from `role_name` fails here."""
        from epubforge import naming

        assert naming.role_name("sgc-toc-1", {"img"}, "pl") is None
        assert naming.role_name("sgc-toc-1", {"div"}, "pl") == "ef-spis-tresci-1"
        assert naming.role_name("MsoHyperlink", {"a"}, "pl") == "ef-odnosnik"
        assert naming.role_name("MsoNormal", {"p"}, "pl") is None
