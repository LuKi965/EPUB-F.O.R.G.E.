"""A `<link>` in the head naming a file the book does not contain goes, in
preserve mode too.

Record 042: after 0.3.1, every one of the 313 dead references preserve mode
kept on the shelf was such a `<link>` — Word's `filelist.xml` and
`themedata.thmx`, a converter's pointer at a cover file it never packed, one
book's stylesheet that was never there. None loads anything, none is a link a
reader can see, and a validator counts each as an error. So they are swept
with the rest of the generator's leavings (D-029), behind the same tick. A
dead `<a>` or `<img>` is a different thing: a reader sees those, and preserve
keeps them as found.
"""

from __future__ import annotations

import re
import zipfile

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><title>R</title>{head}</head>'
    "<body>{body}</body></html>"
)

WORD_LEAVINGS = (
    '<link rel="File-List" href="Misery_files/filelist.xml"/>'
    '<link rel="themeData" href="Misery_files/themedata.thmx"/>'
)
LIVE_SHEET = '<link rel="stylesheet" type="text/css" href="s.css"/>'
BODY = '<h1>R</h1><p>Tekst rozdziału.</p>'
DEAD_ANCHOR = '<p>Zobacz <a href="brak.xhtml">tam</a>.</p>'
DEAD_IMAGE = '<p><img src="brak.png" alt="Rycina"/></p>'


def build(tmp_path, head, body, *, policy=None):
    source = make_book(
        tmp_path / "in.epub",
        {"c0.xhtml": PAGE.format(head=head, body=body)},
        extra_items='<item id="s" href="s.css" media-type="text/css"/>',
        extra_files={"OEBPS/s.css": b"p { margin: 0 }"},
    )
    return rebuild(
        source, str(tmp_path / "out.epub"),
        policy or Policy.preset("preserve", render_gate="off"),
    )


def document_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".xhtml") and not n.endswith("nav.xhtml"))
        return archive.read(name).decode("utf-8")


def kept_in_the_chapter(result) -> bool:
    """Whether the chapter — not the fixture's navigation document, whose own
    dead anchor is the factory's and stays — still reports a dead reference."""
    return any(
        f.rule == "xhtml.dead-reference-kept" and "nav" not in f.location
        for f in result.report.findings
    )


class TestADeadLinkInTheHead:
    def test_goes_in_preserve_mode_and_is_reported(self, tmp_path):
        result = build(tmp_path, WORD_LEAVINGS + LIVE_SHEET, BODY)
        text = document_of(result)
        assert "filelist.xml" not in text and "themedata.thmx" not in text
        assert len(re.findall(r"<link\b", text)) == 1  # the live stylesheet stays
        assert "xhtml.dead-link-removed" in rules_of(result)
        assert not kept_in_the_chapter(result)

    def test_the_text_and_the_live_stylesheet_are_untouched(self, tmp_path):
        result = build(tmp_path, WORD_LEAVINGS + LIVE_SHEET, BODY)
        text = document_of(result)
        assert "Tekst rozdziału." in text
        assert 'rel="stylesheet"' in text

    def test_stays_when_the_generator_sweep_is_unticked(self, tmp_path):
        """S-02: every removal has a tick, and this one shares the generator
        basket's (D-029). Unticked, the link is kept and counted as before."""
        policy = Policy.preset("preserve", render_gate="off")
        policy.sweep_style_blocks = False
        result = build(tmp_path, WORD_LEAVINGS, BODY, policy=policy)
        assert "filelist.xml" in document_of(result)
        assert "xhtml.dead-reference-kept" in rules_of(result)
        assert "xhtml.dead-link-removed" not in rules_of(result)

    def test_strict_mode_still_neutralises(self, tmp_path):
        result = build(tmp_path, WORD_LEAVINGS, BODY, policy=Policy.preset("strict", render_gate="off"))
        assert "filelist.xml" not in document_of(result)


class TestWhatAReaderSeesIsKept:
    def test_a_dead_anchor_and_a_dead_image_stay_in_preserve_mode(self, tmp_path):
        """The basket is the head's `<link>`, nothing else: a link a reader can
        tap and a picture that should have been there are kept as found and
        reported, as they always were. The mutation that widens the basket
        to every dead reference fails here."""
        result = build(tmp_path, "", BODY + DEAD_ANCHOR + DEAD_IMAGE)
        text = document_of(result)
        assert 'href="brak.xhtml"' in text
        assert 'src="brak.png"' in text
        assert "xhtml.dead-reference-kept" in rules_of(result)
        assert "xhtml.dead-link-removed" not in rules_of(result)

    def test_the_two_baskets_are_counted_apart(self, tmp_path):
        result = build(tmp_path, WORD_LEAVINGS, BODY + DEAD_ANCHOR)
        text = document_of(result)
        assert "filelist.xml" not in text
        assert 'href="brak.xhtml"' in text
        assert "xhtml.dead-link-removed" in rules_of(result)
        assert "xhtml.dead-reference-kept" in rules_of(result)
