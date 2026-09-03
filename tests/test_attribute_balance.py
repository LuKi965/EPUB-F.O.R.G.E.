"""A-03 from the audit of 2026-09-03: what a screen reader depends on is
counted before and after, and a fall is said.

K1 guards the prose and the resource balance guards the files; an `alt`
or a `role` that leaves a document is visible to neither. The first time
these were counted on the shelf they found EF-071 within sixty books — a
publisher's `aria-label` leaving with a regenerated navigation document.
The count lives in the balance now, over the bytes, and a fall is a WARN
with the numbers rather than a refusal: a count of names inside tags is
evidence to look at, not a proof of loss.
"""

from __future__ import annotations

import zipfile

from epubforge import balance
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.stages import DEFAULT_STAGES
from epubforge.stages.base import Stage
from epubforge.xhtml import qname

from tests.test_shelf_refusals import make_book, rules_of

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">'
    "<head><title>R</title></head><body>{body}</body></html>"
)
BODY = (
    '<h1 title="Rozdział pierwszy">R</h1>'
    '<p lang="en" dir="ltr">Zdanie <span role="note" aria-label="uwaga">z uwagą</span>.</p>'
    '<p><img src="i.png" alt="Rycina"/></p>'
    '<section epub:type="chapter" hidden="hidden"><p>Tekst o alt= i role= w prozie.</p></section>'
)


class TestCountingByName:
    def test_names_inside_tags_are_counted_and_prose_is_not(self):
        counts = balance.semantic_attributes_in(PAGE.format(body=BODY).encode("utf-8"))
        assert counts == {
            "title": 1, "lang": 2, "dir": 1, "role": 1, "aria-label": 1, "alt": 1,
            "epub:type": 1, "hidden": 1,
        }

    def test_a_side_of_the_balance_carries_the_totals(self, tmp_path):
        from epubforge.budget import Budget
        from epubforge.reader import read_epub
        from epubforge.report import Report

        source = make_book(tmp_path / "in.epub", {"c0.xhtml": PAGE.format(body=BODY)},
                           extra_items='<item id="i" href="i.png" media-type="image/png"/>',
                           extra_files={"OEBPS/i.png": PNG})
        book = read_epub(source, Report(source=source), Budget())
        side = balance.Side.of(book)
        assert side.semantic_attributes["alt"] == 1
        assert "semantic_attributes" in side.as_dict()


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
    "9c6360f8cfc000000301010018dd8db00000000049454e44ae426082"
)


class AltStripper(Stage):
    """A stage that quietly takes the `alt` off every image — the shape of
    loss this count exists to see."""

    name = "xhtml"

    def run(self, ctx):
        for resource in ctx.book.content_docs():
            root = ctx.take(resource).root
            for image in root.iter(qname("img")):
                image.attrib.pop("alt", None)
            from epubforge import xhtml
            resource.data = xhtml.serialize(root)


def build(tmp_path, *, stages=None):
    source = make_book(tmp_path / "in.epub", {"c0.xhtml": PAGE.format(body=BODY)},
                       extra_items='<item id="i" href="i.png" media-type="image/png"/>',
                       extra_files={"OEBPS/i.png": PNG})
    return rebuild(
        source, str(tmp_path / "out.epub"),
        Policy.preset("preserve", render_gate="off"),
        stages=stages,
    )


class TestAFallIsSaidAndNotRefused:
    def test_an_ordinary_rebuild_loses_none_of_them(self, tmp_path):
        result = build(tmp_path)
        assert result.output_path
        assert "package.attributes-fell" not in rules_of(result)
        assert result.report.balance.attributes_fell == []

    def test_a_stage_that_strips_alt_is_named_with_the_numbers(self, tmp_path):
        result = build(tmp_path, stages=(*DEFAULT_STAGES, AltStripper))
        assert result.output_path, "a fall is a warning, not a refusal"
        assert "package.attributes-fell" in rules_of(result)
        (finding,) = [f for f in result.report.findings if f.rule == "package.attributes-fell"]
        assert "alt: 1 → 0" in finding.values["detail"]
        assert ("alt", 1, 0) in result.report.balance.attributes_fell
        assert result.report.balance.closes, "the resource balance is a different question"

    def test_the_fall_is_in_the_balance_json(self, tmp_path):
        result = build(tmp_path, stages=(*DEFAULT_STAGES, AltStripper))
        recorded = result.report.balance.as_dict()
        assert recorded["attributes_fell"] == [{"attribute": "alt", "before": 1, "after": 0}]
        with zipfile.ZipFile(result.output_path) as archive:
            assert any(n.endswith(".xhtml") for n in archive.namelist())
