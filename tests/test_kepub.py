"""Kobo's own flavour of the file, written on request.

The reference is kepubify 4.0.4 (`kepub/transform.go`): the wrappers, the
sentence spans, the style block, and a sentence splitter carried over rule for
rule. The cases below that name the reference are its own test cases, kept to
those where an XML parse and an HTML5 parse agree on the tree — the reference
parses tag soup, this program parses XHTML, and a `<ul>` inside a `<p>` is two
different trees to the two of them.
"""

from __future__ import annotations

import re
import zipfile

import pytest

from epubforge import fidelity, kepub, plan
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.validate import find_epubcheck, validate
from epubforge.xhtml import parse_document, qname

from tests.test_shelf_refusals import make_book, rules_of

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><title>R</title></head>'
    "<body>{body}</body></html>"
)

CHAPTER = (
    "<h1>Rozdział pierwszy</h1>"
    "<p>Zdanie pierwsze. Zdanie <b>drugie</b>? „Trzecie…” Czwarte.</p>"
    "<p><img src=\"i.png\" alt=\"\"/> Podpis pod obrazem.</p>"
    "<pre>kod.  nie ruszany. </pre>"
    "<ul><li>Raz.</li><li>Dwa.</li></ul>"
)
LONG_CHAPTER = "<h1>Rozdział</h1>" + "".join(
    f"<p>Akapit numer {n} niesie kilka dłuższych wyrazów, żeby pierwsza strona była tekstem.</p>"
    for n in range(6)
)
ALREADY = (
    '<p><span class="koboSpan" id="kobo.7.1">Już oznaczone. </span>'
    '<span class="koboSpan" id="kobo.7.2">Zostaje.</span></p>'
)


# ------------------------------------------------------------- the splitter
#: The reference's own test strings, less the ones made of invalid bytes — a
#: Python string cannot hold those, and a document that reaches the splitter
#: has already been decoded.
REFERENCE_SENTENCES = [
    "Lorem ipsum dolor sit amet. Consectetur adipiscing elit ut labore et dolore magna aliqua. " * 40,
    "                                ",
    "...       !!!       ???       .'.'.'.'   ",
    "test .. .",
    "",
    "🌝. 🌝      🌝.    🌝",
    "!",
    "? ",
    "? ?",
    "?  ",
    "  ?  ",
    " ?'  .",
    " ?'  .   ",
    "Sentence 1. Sentence 2. Stray text\nAnother sentence.",
    "The Christmas Collection: All Of Your Favourite Stories",
    "Koniec.Bez odstępu. Ze spacją.",
    "„Trzecie…” Czwarte.",
]

#: The regular expression the reference's state machine replaced, and is tested
#: against: ``((?ms).*?[\.\!\?]['"”’“…]?\s+)``, with Go's ASCII-only ``\s``.
_REFERENCE_RE = re.compile(r"(.*?[.!?]['\"”’“…]?[\t\n\f\r ]+)", re.S)


def split_by_regexp(text: str) -> list[str]:
    matches = list(_REFERENCE_RE.finditer(text))
    if not matches:
        return [text]
    pieces = []
    position = 0
    for match in matches:
        pieces.append(text[position:match.end()])
        position = match.end()
    if len(text) > position:
        pieces.append(text[position:])
    return pieces


class TestTheSplitterIsTheReferences:
    @pytest.mark.parametrize("text", REFERENCE_SENTENCES)
    def test_it_agrees_with_the_regular_expression_it_replaced(self, text):
        assert kepub.split_sentences(text) == split_by_regexp(text)

    @pytest.mark.parametrize("text", REFERENCE_SENTENCES)
    def test_the_pieces_join_back_into_the_text(self, text):
        assert "".join(kepub.split_sentences(text)) == text

    def test_the_whitespace_belongs_to_the_sentence_it_ends(self):
        assert kepub.split_sentences("Sentence 1. Sentence 2. Sentence 3.") == [
            "Sentence 1. ", "Sentence 2. ", "Sentence 3.",
        ]

    def test_a_colon_and_a_no_break_space_do_not_end_a_sentence(self):
        assert kepub.split_sentences("Title: All Of It") == ["Title: All Of It"]
        assert kepub.split_sentences("Tak. Nie.") == ["Tak. Nie."]

    def test_one_closing_quote_may_follow_the_stop(self):
        assert kepub.split_sentences('He said "no." She left.') == ['He said "no." ', "She left."]
        assert kepub.split_sentences("Koniec…” Dalej.") == ["Koniec…” Dalej."]


# ------------------------------------------------------------- the markers
def body_of(fragment: str):
    root = parse_document(PAGE.format(body=fragment).encode("utf-8")).root
    return root, root.find(qname("body"))


def spans_of(element) -> list[tuple[str, str]]:
    """Every Kobo span in document order, as ``(id, text)``; an image span
    carries the image's file name instead of text."""
    found = []
    for node in element.iter():
        if not isinstance(node.tag, str) or "koboSpan" not in (node.get("class") or "").split():
            continue
        image = node.find(qname("img"))
        found.append((node.get("id"), image.get("src") if image is not None else node.text))
    return found


class TestTheSpansAreTheReferences:
    """Each case is one of kepubify's, trees agreeing."""

    def test_three_sentences_in_one_paragraph(self):
        root, body = body_of("<p>Sentence 1. Sentence 2. Sentence 3.</p>")
        kepub.mark(root)
        assert spans_of(body) == [
            ("kobo.1.1", "Sentence 1. "), ("kobo.1.2", "Sentence 2. "), ("kobo.1.3", "Sentence 3."),
        ]

    def test_paragraphs_lists_and_tables_count_as_paragraphs(self):
        root, body = body_of(
            "<p>Sentence 1. Sentence 2.</p><p>Sentence 3.</p>"
            "<ul><li>Sentence 4</li><li>Sentence 5</li></ul>"
            "<ol><li>Sentence 6</li><li>Sentence 7</li></ol>"
            "<table><tbody><tr><td>Test</td></tr><tr><td>Test</td></tr></tbody></table>"
        )
        kepub.mark(root)
        assert [i for i, _ in spans_of(body)] == [
            "kobo.1.1", "kobo.1.2", "kobo.2.1", "kobo.3.1", "kobo.3.2",
            "kobo.4.1", "kobo.4.2", "kobo.5.1", "kobo.5.2",
        ]

    def test_inline_markup_splits_a_sentence_into_pieces(self):
        root, body = body_of(
            '<p>Sentence<b> 1. </b>Sentence <span>2. Se</span>nten<a href="test.html">ce 3. Another word</a></p>'
        )
        kepub.mark(root)
        assert spans_of(body) == [
            ("kobo.1.1", "Sentence"), ("kobo.1.2", " 1. "), ("kobo.1.3", "Sentence "),
            ("kobo.1.4", "2. "), ("kobo.1.5", "Se"), ("kobo.1.6", "nten"),
            ("kobo.1.7", "ce 3. "), ("kobo.1.8", "Another word"),
        ]

    def test_nested_inline_markup_too(self):
        root, body = body_of(
            '<p>Sentence<b> 1. Sente<i>nce <span>2. Se</span>nt</i>en<a href="test.html">ce 3. Another word</a></b></p>'
        )
        kepub.mark(root)
        assert [t for _, t in spans_of(body)] == [
            "Sentence", " 1. ", "Sente", "nce ", "2. ", "Se", "nt", "en", "ce 3. ", "Another word",
        ]
        assert spans_of(body)[-1][0] == "kobo.1.10"

    def test_code_and_media_keep_their_text(self):
        root, body = body_of(
            "<p>Touch this.</p><script>not this</script><style>or this</style><pre>or this</pre>"
            "<audio>or this</audio><video>or this</video><p>Touch this.</p>"
        )
        kepub.mark(root)
        assert [i for i, _ in spans_of(body)] == ["kobo.1.1", "kobo.2.1"]
        assert body.find(f".//{qname('pre')}").text == "or this"

    def test_an_image_is_a_paragraph_of_its_own(self):
        root, body = body_of('<p>One.</p><img src="test"/><p>Three.</p>')
        kepub.mark(root)
        assert spans_of(body) == [("kobo.1.1", "One."), ("kobo.2.1", "test"), ("kobo.3.1", "Three.")]

    def test_an_empty_paragraph_uses_no_number_but_a_blank_one_does(self):
        root, body = body_of("<p>One.</p><p> </p><p><!-- comment --></p><p>Two.</p><p><b>Three.</b></p>")
        kepub.mark(root)
        assert spans_of(body) == [
            ("kobo.1.1", "One."), ("kobo.2.1", " "), ("kobo.3.1", "Two."), ("kobo.4.1", "Three."),
        ]

    def test_svg_and_mathml_are_left_alone(self):
        root, body = body_of(
            '<svg xmlns="http://www.w3.org/2000/svg"><g><text y="20" x="0">kepubify</text></g></svg>'
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi><mo>=</mo></math>'
        )
        kepub.mark(root)
        assert spans_of(body) == []

    def test_headings_count_and_a_colon_does_not_split(self):
        root, body = body_of(
            '<div class="img_container"><p class="ad_image"><img src="cover1.jpg" alt="image"/></p></div>\n'
            '    <h2 class="subheadline">The Christmas Collection: All Of Your Favourite Classic Stories</h2>\n'
            '    <p class="subheadline2"></p>\n'
            '    <p class="metadata">Carr, Annie Roe</p>'
        )
        kepub.mark(root)
        assert spans_of(body) == [
            ("kobo.1.1", "cover1.jpg"),
            ("kobo.2.1", "The Christmas Collection: All Of Your Favourite Classic Stories"),
            ("kobo.3.1", "Carr, Annie Roe"),
        ]

    def test_whitespace_between_blocks_stays_text(self):
        root, body = body_of("<p>One.</p>\n  <p>Two.</p>\n")
        kepub.mark(root)
        inner = body.find(f".//*[@id='{kepub.INNER_ID}']")
        paragraphs = list(inner)
        assert paragraphs[0].tail == "\n  " and paragraphs[1].tail == "\n"


class TestTheWrappersAndTheStyle:
    def test_the_body_is_wrapped_twice_and_the_head_gets_the_style(self):
        root, body = body_of("<p>Tekst.</p>")
        marking = kepub.mark(root)
        assert marking.wrapped and marking.styled
        (columns,) = list(body)
        assert columns.get("id") == kepub.COLUMNS_ID
        (inner,) = list(columns)
        assert inner.get("id") == kepub.INNER_ID and inner[0].tag == qname("p")
        style = root.find(qname("head")).find(qname("style"))
        assert style.get("class") == kepub.STYLE_CLASS and style.text == kepub.STYLE_TEXT

    def test_text_directly_in_the_body_moves_inside(self):
        root, body = body_of("Luźny tekst.<p>Akapit.</p>")
        kepub.mark(root)
        inner = body.find(f".//*[@id='{kepub.INNER_ID}']")
        assert spans_of(inner)[0] == ("kobo.0.1", "Luźny tekst.")

    def test_marking_twice_adds_nothing(self):
        root, body = body_of(CHAPTER)
        first = kepub.mark(root)
        again = kepub.mark(root)
        assert first.changed and not again.changed and again.already
        assert len(spans_of(body)) == first.spans + first.images

    def test_a_document_with_spans_keeps_them_and_still_gets_the_wrappers(self):
        root, body = body_of(ALREADY)
        marking = kepub.mark(root)
        assert marking.already and marking.wrapped and marking.spans == 0
        assert spans_of(body) == [("kobo.7.1", "Już oznaczone. "), ("kobo.7.2", "Zostaje.")]


# ------------------------------------------------------------- the pipeline
def build(tmp_path, documents, *, kepub_on=True, name="out.kepub.epub", cover=""):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = make_book(
        tmp_path / "in.epub",
        {n: PAGE.format(body=b) for n, b in documents.items()},
        extra_items='<item id="i" href="i.png" media-type="image/png"/>',
        extra_files={"OEBPS/i.png": PNG},
        cover=cover,
    )
    policy = Policy.preset("preserve", render_gate="off")
    policy.kepub = kepub_on
    return rebuild(source, str(tmp_path / name), policy)


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
    "9c6360f8cfc000000301010018dd8db00000000049454e44ae426082"
)


def chapters_of(result) -> dict[str, bytes]:
    with zipfile.ZipFile(result.output_path) as archive:
        return {
            n: archive.read(n) for n in archive.namelist()
            if n.endswith(".xhtml") and not n.endswith("nav.xhtml")
        }


class TestTheExportThroughThePipeline:
    def test_off_by_default_and_a_plain_epub_carries_nothing_of_kobos(self, tmp_path):
        assert Policy().kepub is False
        result = build(tmp_path, {"c0.xhtml": CHAPTER}, kepub_on=False, name="out.epub")
        with zipfile.ZipFile(result.output_path) as archive:
            for name in archive.namelist():
                if name.endswith(".xhtml"):
                    assert b"koboSpan" not in archive.read(name)
                    assert b"book-inner" not in archive.read(name)
        assert not any(rule.startswith("kepub.") for rule in rules_of(result))

    def test_every_document_gets_the_markers_and_the_report_says_so(self, tmp_path):
        result = build(tmp_path, {"c0.xhtml": CHAPTER, "c1.xhtml": "<p>Drugi.</p>"})
        assert result.output_path and result.output_path.endswith(".kepub.epub")
        for data in chapters_of(result).values():
            assert b'id="book-columns"' in data and b'id="book-inner"' in data
            assert b'class="koboSpan" id="kobo.1.1"' in data
            assert b'class="kobostylehacks"' in data
        assert "kepub.marked" in rules_of(result)
        (entry,) = [c for c in result.report.changes if c.rule == "kepub.marked"]
        assert entry.action.value == "added" and "image span" in entry.after

    def test_the_text_is_the_same_to_the_character(self, tmp_path):
        plain = build(tmp_path / "plain", {"c0.xhtml": CHAPTER}, kepub_on=False, name="out.epub")
        kobo = build(tmp_path / "kobo", {"c0.xhtml": CHAPTER})
        (before,) = chapters_of(plain).values()
        (after,) = chapters_of(kobo).values()
        assert fidelity.document_text(after) == fidelity.document_text(before)
        assert b"<pre>kod.  nie ruszany. </pre>" in after

    def test_the_image_is_wrapped_and_the_caption_follows_it(self, tmp_path):
        result = build(tmp_path, {"c0.xhtml": CHAPTER})
        (data,) = chapters_of(result).values()
        root = parse_document(data).root
        found = spans_of(root.find(qname("body")))
        assert ("kobo.3.2", " Podpis pod obrazem.") in found
        assert any(i == "kobo.3.1" and t.endswith("i.png") for i, t in found)

    def test_a_book_that_is_already_a_kepub_keeps_its_ids(self, tmp_path):
        result = build(tmp_path, {"c0.xhtml": ALREADY})
        (data,) = chapters_of(result).values()
        assert b'id="kobo.7.2"' in data and b'id="kobo.1.1"' not in data
        assert b'id="book-inner"' in data
        assert "kepub.already-marked" in rules_of(result)

    def test_a_name_a_kobo_will_not_recognise_is_reported(self, tmp_path):
        result = build(tmp_path, {"c0.xhtml": CHAPTER}, name="out.epub")
        assert "kepub.name" in rules_of(result)
        assert "kepub.name" not in rules_of(build(tmp_path / "k", {"c0.xhtml": CHAPTER}))

    def test_a_first_page_that_is_a_chapter_is_reported_not_padded(self, tmp_path):
        result = build(tmp_path, {"c0.xhtml": LONG_CHAPTER})
        assert "kepub.first-page-not-a-cover" in rules_of(result)
        with zipfile.ZipFile(result.output_path) as archive:
            assert not any("blank" in n or "dummy" in n for n in archive.namelist())
        short = build(tmp_path / "s", {"c0.xhtml": CHAPTER})
        assert "kepub.first-page-not-a-cover" not in rules_of(short)

    def test_a_first_page_named_as_a_cover_is_not_judged(self, tmp_path):
        result = build(tmp_path, {"cover.xhtml": LONG_CHAPTER, "c1.xhtml": "<p>Dalej.</p>"})
        assert "kepub.first-page-not-a-cover" not in rules_of(result)


@pytest.mark.skipif(find_epubcheck() is None, reason="EPUBCheck not installed")
def test_the_kepub_is_still_a_valid_epub(tmp_path):
    """The markers are ordinary XHTML: a Kobo file must pass the validator
    exactly as the plain file does, or the export has broken the book."""
    result = build(tmp_path, {"c0.xhtml": CHAPTER, "c1.xhtml": LONG_CHAPTER})
    verdict = validate(result.output_path)
    assert verdict.available
    assert verdict.errors == 0 and verdict.fatal == 0, "\n".join(verdict.messages)


# ------------------------------------------------------------- the file name
class TestTheFileIsNamedForTheDevice:
    def test_beside_the_source(self, tmp_path):
        source = str(tmp_path / "ksiazka.epub")
        assert plan.destination_for(source, None, kepub=True) == str(tmp_path / "ksiazka.forged.kepub.epub")
        assert plan.destination_for(source, None) == str(tmp_path / "ksiazka.forged.epub")

    def test_into_a_directory(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        assert plan.destination_for("/a/ksiazka.epub", str(out), kepub=True) == str(out / "ksiazka.kepub.epub")
        assert plan.destination_for("/a/ksiazka.epub", str(out)) == str(out / "ksiazka.epub")

    def test_a_kobo_source_does_not_double_up(self, tmp_path):
        assert plan.stem_of("/a/ksiazka.kepub.epub") == "ksiazka"
        assert plan.destination_for("/a/ksiazka.kepub.epub", None, kepub=True) == "/a/ksiazka.forged.kepub.epub"

    def test_a_name_given_verbatim_is_the_persons(self, tmp_path):
        assert plan.destination_for("/a/b.epub", "/x/mine.epub", kepub=True) == "/x/mine.epub"

    def test_the_command_line_offers_it_and_it_reaches_the_policy(self):
        from epubforge.cli import build_parser, build_policy

        parsed = build_parser().parse_args(["build", "x.epub", "--kepub"])
        assert parsed.kepub and build_policy(parsed).kepub
        assert not build_policy(build_parser().parse_args(["build", "x.epub"])).kepub
