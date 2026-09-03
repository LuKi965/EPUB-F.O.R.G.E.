"""Record 045: a Word export with 134 chapters, each carrying the same 86 KB
`<style>` block (nine distinct blocks in all), spent 173 of 248 seconds
parsing that block once per chapter, and the stylesheet walker another 38
walking it one character at a time. Two facts are held here: the selector
scan and the walk are memoised on the text, and the walk still says the same
thing about the shapes it was written for.
"""

from __future__ import annotations

from epubforge import stylesheet
from epubforge.stages.content import _selector_classes

SHEET = """<!--
/* Font Definitions */ @font-face { font-family: "Calibri"; }
/* Page Definitions */ @page WordSection1 { size: 8.5in 11.0in; margin: 1in; }
p.MsoNormal, li.MsoNormal { margin: 0; font-size: 12pt; font-family: "Calibri", sans-serif; }
.x { content: "}"; }
@media print { .only-print { display: block; } }
h1 { /* a comment with a { brace */ color: red; }
-->
"""


class TestTheSelectorScanIsMemoised:
    def test_the_same_text_is_parsed_once(self):
        _selector_classes.cache_clear()
        first = _selector_classes(SHEET)
        again = _selector_classes(str(SHEET))  # a different string object, the same text
        assert first is again
        assert _selector_classes.cache_info().hits >= 1

    def test_and_finds_the_classes_including_those_inside_media(self):
        assert {"MsoNormal", "x", "only-print"} <= set(_selector_classes(SHEET))


class TestTheWalkStillReadsTheShapesItWasWrittenFor:
    def test_rules_and_at_rules_are_told_apart(self):
        kinds = [(kind, span.selector) for kind, span in stylesheet._walk(SHEET)]
        assert ("@font-face", "@font-face") in kinds
        assert any(kind == "@page" for kind, _ in kinds)
        assert any(kind == "@media" for kind, _ in kinds)
        plain = [selector for kind, selector in kinds if kind is None]
        assert plain == ["p.MsoNormal, li.MsoNormal", ".x", "h1"]

    def test_a_brace_inside_a_string_or_a_comment_is_not_structure(self):
        spans = {span.selector: span for kind, span in stylesheet._walk(SHEET) if kind is None}
        assert SHEET[spans[".x"].start:spans[".x"].end] == '.x { content: "}"; }'
        assert SHEET[spans["h1"].start:spans["h1"].end] == "h1 { /* a comment with a { brace */ color: red; }"

    def test_callers_get_their_own_list(self):
        one = stylesheet.top_level_rules(SHEET)
        two = stylesheet.top_level_rules(SHEET)
        assert one == two and one is not two
        one.clear()
        assert stylesheet.top_level_rules(SHEET)

    def test_an_unclosed_block_runs_to_the_end(self):
        text = "p { color: red"
        (span,) = stylesheet.top_level_rules(text)
        assert (span.start, span.end) == (0, len(text))

    def test_a_statement_ends_the_prelude(self):
        text = '@import url("a.css"); p { color: red; }'
        assert [span.selector for span in stylesheet.top_level_rules(text)] == ["p"]
