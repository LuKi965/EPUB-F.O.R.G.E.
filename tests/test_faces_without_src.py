"""`@font-face` rules that declare no `src` — the shelf's largest dead weight.

Found by asking what the biggest remaining block of lint warnings actually
was. The answer: **48 963 warnings, more than every other rule on the shelf put
together, and all of them one obsolete descriptor** — `panose-1` — inside
`@font-face` rules written by a word processor into every document of ten
books.

Reading those rules settled what to do with them. `src` is required; a face
without one names a family and gives no way to fetch it, so every parser drops
the rule. **49 177 such rules, 3.93 MB of CSS, and not one with a `src`** — in
one book 68% of the file, in another 82%, and in a third the uncompressed rules
outweigh the whole compressed book.

Removing them cannot change a pixel, which is this basket's test (D-029/D-030)
and the same argument D-039 used for a declaration written as an HTML
attribute. The program already says the sentence one method away, where
neutralising a dead url can empty a face: *a face that can load nothing is not
a face.*
"""

from __future__ import annotations

import re
import zipfile

from epubforge import stylesheet
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title><style>{css}</style></head>"
    '<body><p class="rozdzial">Tekst rozdziału.</p></body></html>'
)

#: The shape the shelf actually carries: a word processor's font table, a
#: comment heading it, and one real face with a source among them.
CSS = (
    "/* Font Definitions */ "
    "@font-face {font-family:Helvetica; panose-1:2 11 6 4 2 2 2 2 2 4;} "
    "@font-face {font-family:\"Cambria Math\"; panose-1:2 4 5 3 5 4 6 3 2 4;} "
    "@font-face { font-family: Wlasny; src: url(w.ttf); } "
    "p.rozdzial { margin-top: 1em; }"
)


def a_book(tmp_path, css: str = CSS) -> str:
    return make_book(tmp_path / "in.epub", {"c0.xhtml": PAGE.format(css=css)})


def forge(tmp_path, *, sweep: bool = True, css: str = CSS, mode="preserve"):
    policy = Policy.preset(mode, render_gate="off", validate_before_publish="off")
    policy.sweep_style_blocks = sweep
    return rebuild(a_book(tmp_path, css), str(tmp_path / "out.epub"), policy)


def style_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        for name in archive.namelist():
            if not name.endswith(".xhtml"):
                continue
            markup = archive.read(name).decode("utf-8")
            found = re.search(r"<style[^>]*>(.*?)</style>", markup, re.S)
            if found and "rozdzial" in found.group(1):
                return found.group(1)
    raise AssertionError("no swept <style> block in the rebuild")


class TestAFaceThatLoadsNothingGoes:
    def test_the_sourceless_faces_are_removed(self, tmp_path):
        result = forge(tmp_path)
        css = style_of(result)
        assert "Helvetica" not in css
        assert "Cambria Math" not in css
        assert "panose-1" not in css
        assert "css.faces-without-src-removed" in rules_of(result)

    def test_a_face_with_a_source_stays(self, tmp_path):
        """The line between the two buckets. A face with a `src` is a font
        somebody meant to load, however strange it looks."""
        css = style_of(forge(tmp_path))
        assert "Wlasny" in css and "w.ttf" in css

    def test_the_ordinary_rules_are_untouched(self, tmp_path):
        css = style_of(forge(tmp_path))
        assert "p.rozdzial" in css and "margin-top" in css

    def test_the_comment_above_them_stays(self, tmp_path):
        """`/* Font Definitions */` is a note somebody wrote, and removing the
        rules under it is not a reason to remove it. The same courtesy the
        unreachable-rule sweep already pays a section heading."""
        assert "Font Definitions" in style_of(forge(tmp_path))

    def test_it_says_how_many(self, tmp_path):
        result = forge(tmp_path)
        found = [
            f for f in result.report.findings
            if f.rule == "css.faces-without-src-removed"
        ]
        assert found and found[0].values["count"] == 2


class TestTheOptOut:
    def test_unticking_keeps_them_and_still_reports(self, tmp_path):
        """The opt-out S-02 requires of every removal: nothing goes, and the
        report is the only trace."""
        result = forge(tmp_path, sweep=False)
        css = style_of(result)
        assert "Helvetica" in css and "panose-1" in css
        assert "css.faces-without-src-removed" not in rules_of(result)
        assert "css.faces-without-src-found" in rules_of(result)

    def test_a_book_without_any_says_nothing(self, tmp_path):
        """A rule with no work does not put a line in the report. A report that
        says something about every book says nothing."""
        result = forge(tmp_path, css="p.rozdzial { margin-top: 1em; }")
        assert "css.faces-without-src-found" not in rules_of(result)
        assert "css.faces-without-src-removed" not in rules_of(result)


class TestWhatCountsAsDeclaringASource:
    """`src` has to be a descriptor, not the letters `src` somewhere in the
    rule — and each of these was written because the naive test gets it
    wrong."""

    def test_a_family_named_src_is_not_a_source(self, tmp_path):
        css = '@font-face { font-family: "src"; } p.rozdzial { margin-top: 1em; }'
        assert "font-family" not in style_of(forge(tmp_path, css=css))

    def test_a_source_after_another_declaration_still_counts(self, tmp_path):
        css = (
            "@font-face { font-family: X; font-weight: bold; src: url(x.ttf); } "
            "p.rozdzial { margin-top: 1em; }"
        )
        assert "x.ttf" in style_of(forge(tmp_path, css=css))

    def test_the_first_declaration_counts_too(self, tmp_path):
        css = "@font-face {src: url(x.ttf); font-family: X;} p.rozdzial { margin-top: 1em; }"
        assert "x.ttf" in style_of(forge(tmp_path, css=css))


class TestTheParserUnderneath:
    """`stylesheet.at_rules` is new, and it is the one place that decides what
    an `@font-face` even is. Word writes them behind a comment, which has
    already been misread once."""

    SHEET = (
        "/* Font Definitions */ @font-face {font-family:A; panose-1:1 2 3}"
        " p { color: red } @media print { p { color: blue } }"
        " @font-face { font-family: B; src: url(b.ttf) }"
    )

    def test_it_finds_both_faces_and_not_the_media(self):
        faces = stylesheet.at_rules(self.SHEET, "font-face")
        assert len(faces) == 2
        assert [f.selector for f in stylesheet.at_rules(self.SHEET, "media")] == [
            "@media print"
        ]

    def test_the_body_is_what_is_between_the_braces(self):
        first = stylesheet.at_rules(self.SHEET, "font-face")[0]
        assert stylesheet.body_of(self.SHEET, first) == "font-family:A; panose-1:1 2 3"

    def test_ordinary_rules_are_still_only_ordinary_rules(self):
        """The other half of the split: `top_level_rules` must not start
        returning at-rules now that one walk serves both."""
        assert [r.selector for r in stylesheet.top_level_rules(self.SHEET)] == ["p"]

    def test_removing_one_leaves_the_rest_intact(self):
        faces = stylesheet.at_rules(self.SHEET, "font-face")
        left = stylesheet.without(self.SHEET, [faces[0]])
        assert "panose-1" not in left
        assert "b.ttf" in left
        assert "@media print" in left
        assert "Font Definitions" in left

    def test_a_name_with_or_without_the_at_sign_asks_the_same_thing(self):
        assert len(stylesheet.at_rules(self.SHEET, "@font-face")) == 2
