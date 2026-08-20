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
    def test_off_by_default(self, tmp_path):
        policy = Policy.preset("preserve")
        assert policy.translate_class_names is False
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

    def test_the_map_is_in_the_report(self, tmp_path):
        result = build(tmp_path)
        renamed = next(
            finding for finding in result.report.findings
            if finding.rule == "css.classes-renamed"
        )
        assert "calibre4 → ef-naglowek-1" in renamed.detail
        assert "sgc-1 → ef-kursywa" in renamed.detail
