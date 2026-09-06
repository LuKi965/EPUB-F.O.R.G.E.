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
    def test_every_aria_attribute_is_counted_not_three_picked_by_hand(self):
        """EF-075 (independent audit 2026-09-04): `aria-labelledby` stood on
        two shelf books and the hand-picked list did not see it."""
        page = PAGE.format(body=(
            '<p aria-labelledby="h1" aria-describedby="n1" aria-hidden="true" aria-live="polite">x</p>'
        )).encode("utf-8")
        counts = balance.semantic_attributes_in(page)
        assert counts["aria-labelledby"] == 1
        assert counts["aria-live"] == 1
        assert counts["aria-describedby"] == 1 and counts["aria-hidden"] == 1

    def test_a_raw_greater_than_inside_a_value_does_not_end_the_tag(self):
        """The byte-level counter read tags with `<[^>]*>`, so a `>` in an
        attribute value cut the tag short and hid every attribute after it.
        The program exists for books with markup like that."""
        page = PAGE.format(body='<p title="a > b" lang="en" role="note">x</p>').encode("utf-8")
        counts = balance.semantic_attributes_in(page)
        assert counts == {"title": 1, "lang": 2, "role": 1}

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


class LabelledByStripper(Stage):
    """The EF-075 shape: an attribute the old hand-picked list did not know."""

    name = "xhtml"

    def run(self, ctx):
        for resource in ctx.book.content_docs():
            root = ctx.take(resource).root
            for element in root.iter():
                if isinstance(element.tag, str):
                    element.attrib.pop("aria-labelledby", None)
            from epubforge import xhtml
            resource.data = xhtml.serialize(root)


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

    def test_a_stage_that_strips_aria_labelledby_is_seen(self, tmp_path):
        body = BODY + '<p id="n1">n</p><p aria-labelledby="n1">z</p>'
        source = make_book(tmp_path / "in.epub", {"c0.xhtml": PAGE.format(body=body)},
                           extra_items='<item id="i" href="i.png" media-type="image/png"/>',
                           extra_files={"OEBPS/i.png": PNG})
        result = rebuild(source, str(tmp_path / "out.epub"),
                         Policy.preset("preserve", render_gate="off"),
                         stages=(*DEFAULT_STAGES, LabelledByStripper))
        assert result.output_path
        assert "package.attributes-fell" in rules_of(result)
        assert ("aria-labelledby", 1, 0) in result.report.balance.attributes_fell

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


ORPHAN = PAGE.format(body='<p lang="de" title="Waise">Sierota</p>')


def side_with(documents: dict) -> "balance.Side":
    side = balance.Side()
    side.semantic_attributes_by_document = {
        path: balance.semantic_attributes_in(markup.encode("utf-8"))
        for path, markup in documents.items()
    }
    side.semantic_attributes = balance._summed(side.semantic_attributes_by_document.values())
    return side


class TestADocumentTheLedgerRemovedIsTakenOutOfTheComparison:
    """The warning's own text says nothing in the rebuild claims to have
    removed them. So a whole document removed with an entry — an orphan swept
    on request — must not count as a fall, and one that left without an entry
    must, because that is what EF-071 looked like."""

    def test_removed_with_an_entry_naming_the_path(self):
        from epubforge.report import Action, Change

        before = side_with({"OEBPS/c0.xhtml": PAGE.format(body=BODY), "OEBPS/orphan.xhtml": ORPHAN})
        after = side_with({"OEBPS/c0.xhtml": PAGE.format(body=BODY)})
        swept = Change("structure", Action.REMOVED, "documents",
                       before="OEBPS/orphan.xhtml (241 B)", rule="structure.orphan-removed")
        assert balance.reconcile(before, after, [swept]).attributes_fell == []

    def test_removed_without_an_entry_still_counts(self):
        before = side_with({"OEBPS/c0.xhtml": PAGE.format(body=BODY), "OEBPS/orphan.xhtml": ORPHAN})
        after = side_with({"OEBPS/c0.xhtml": PAGE.format(body=BODY)})
        fell = balance.reconcile(before, after, []).attributes_fell
        # `lang` twice on each page (the root and a paragraph), `title` once.
        assert ("lang", 4, 2) in fell and ("title", 2, 1) in fell

    def test_an_entry_about_another_path_is_not_a_match(self):
        from epubforge.report import Action, Change

        before = side_with({"OEBPS/c0.xhtml": PAGE.format(body=BODY), "OEBPS/orphan.xhtml": ORPHAN})
        after = side_with({"OEBPS/c0.xhtml": PAGE.format(body=BODY)})
        other = Change("structure", Action.REMOVED, "documents",
                       before="OEBPS/orphan.xhtml.bak (12 B)", rule="structure.junk-removed")
        assert balance.reconcile(before, after, [other]).attributes_fell

    def test_on_the_real_orphan_path(self, tmp_path):
        """`drop_orphans` is the one production path that removes a whole
        document on request; its entry has to be the one this reads."""
        source = make_book(tmp_path / "in.epub", {"c0.xhtml": PAGE.format(body=BODY)},
                           extra_items='<item id="i" href="i.png" media-type="image/png"/>'
                                       '<item id="o" href="orphan.xhtml" media-type="application/xhtml+xml"/>',
                           extra_files={"OEBPS/i.png": PNG, "OEBPS/orphan.xhtml": ORPHAN.encode("utf-8")})
        result = rebuild(source, str(tmp_path / "out.epub"),
                         Policy.preset("preserve", render_gate="off", drop_orphans=True))
        assert result.output_path, result.report.to_text()
        assert any(c.rule == "structure.orphan-removed" for c in result.report.changes)
        with zipfile.ZipFile(result.output_path) as archive:
            assert "OEBPS/orphan.xhtml" not in archive.namelist()
        assert "package.attributes-fell" not in rules_of(result)
        assert result.report.balance.attributes_fell == []


class AriaLabelMover(Stage):
    """Moves the `aria-label` from the note's span onto the paragraph that
    holds it. Every name's count stays exactly where it was."""

    name = "xhtml"

    def run(self, ctx):
        from epubforge import xhtml

        for resource in ctx.book.content_docs():
            root = ctx.take(resource).root
            for span in root.iter(qname("span")):
                label = span.attrib.pop("aria-label", None)
                if label is not None:
                    span.getparent().set("aria-label", label)
            resource.data = xhtml.serialize(root)


class AltReworder(Stage):
    """Keeps every `alt` and changes what one says."""

    name = "xhtml"

    def run(self, ctx):
        from epubforge import xhtml

        for resource in ctx.book.content_docs():
            root = ctx.take(resource).root
            for image in root.iter(qname("img")):
                if image.get("alt") == "Rycina":
                    image.set("alt", "Obraz")
            resource.data = xhtml.serialize(root)


class TestTheAttributeIsCountedWhereItStandsAndWhatItSays:
    """EF-089, second half (DROGA-DO-1.0, 6.3): a count by name holds while
    the attribute moved to another element or says something else. The same
    count is taken once more as (tag, name, value)."""

    def test_triples_carry_the_tag_and_the_value_in_either_quote_style(self):
        page = PAGE.format(body="<p aria-label='Uwaga  ważna'>x</p><img src=\"i.png\" alt=\"Rycina\"/>").encode("utf-8")
        triples = balance.semantic_attribute_triples_in(page)
        assert triples[("p", "aria-label", "Uwaga ważna")] == 1
        assert triples[("img", "alt", "Rycina")] == 1
        assert triples[("html", "lang", "pl")] == 1

    def test_an_attribute_moved_to_another_element_is_seen(self, tmp_path):
        result = build(tmp_path, stages=(*DEFAULT_STAGES, AriaLabelMover))
        assert result.output_path, "a warning, not a refusal"
        assert "package.attributes-fell" in rules_of(result)
        fell = {name for name, _, _ in result.report.balance.attributes_fell}
        assert any(name.startswith('aria-label="uwaga" na <span>') for name in fell), fell
        assert "aria-label" not in fell, "the count by name did not fall — that is the point"

    def test_an_attribute_that_says_something_else_is_seen(self, tmp_path):
        result = build(tmp_path, stages=(*DEFAULT_STAGES, AltReworder))
        assert result.output_path
        fell = {name for name, _, _ in result.report.balance.attributes_fell}
        assert any(name.startswith('alt="Rycina" na <img>') for name in fell), fell

    def test_a_name_that_fell_is_said_once(self, tmp_path):
        """The `alt` stripped from the only image: the name fell to zero and
        that line says it; its triple is not repeated underneath."""
        result = build(tmp_path, stages=(*DEFAULT_STAGES, AltStripper))
        names = [name for name, _, _ in result.report.balance.attributes_fell]
        assert names.count("alt") == 1
        assert not any(name.startswith('alt="') for name in names)


class TestTheNavigationBodyKeepsItsType:
    """Found by the (tag, name, value) count on its first shelf run: the
    regenerated navigation document was written with a bare `<body>`, and
    the publisher's `epub:type="frontmatter"` on the old one left with it —
    six shelf books and every Gutenberg book of the corpus, without a line."""

    def _nav_with_typed_body(self, tmp_path):
        from tests.test_shelf_refusals import MODERN_NAV, make_book

        typed = MODERN_NAV.replace("<body>", '<body epub:type="frontmatter">')
        assert typed != MODERN_NAV
        return make_book(
            tmp_path / "in.epub", {"c0.xhtml": PAGE.format(body="<p>Tekst.</p>")},
            extra_files={"OEBPS/nav.xhtml": typed.encode("utf-8")},
        )

    def test_the_type_is_carried_and_said(self, tmp_path):
        source = self._nav_with_typed_body(tmp_path)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve", render_gate="off"))
        assert result.output_path, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            nav = next(n for n in archive.namelist() if n.endswith("nav.xhtml"))
            assert b'<body epub:type="frontmatter">' in archive.read(nav)
        assert "nav.body-type-carried" in rules_of(result)
        assert not any(name.startswith("epub:type=") for name, _, _ in result.report.balance.attributes_fell)


class TestTheValueIsReadAsAReaderMeetsIt:
    def test_an_entity_and_the_character_are_the_same_value(self):
        """`i&#160;Ian` in the source, the character in the rebuild: the
        first shelf run called that a lost `alt` on a real book."""
        source = PAGE.format(body='<img src="i.png" alt="Logo 007 i&#160;Ian"/>').encode("utf-8")
        output = PAGE.format(body='<img src="i.png" alt="Logo 007 i Ian"/>').encode("utf-8")
        assert balance.semantic_attribute_triples_in(source) == balance.semantic_attribute_triples_in(output)
