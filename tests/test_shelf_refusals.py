"""Five findings from one measurement: the strict run over 160 real books.

The run is `PRZEBIEG-POLKI-2026-08-18-001`. It rebuilt the owner's whole shelf in
strict mode on the pinned engine and refused nine books. Three of those refusals
were honest — the book links an anchor it never had, and `references.py` explains
why inventing one is a forgery rather than a repair. The other six came from this
program, and they are what this file is about:

* **EF-056** — content sitting in `<head>` was moved into the body and thereby
  *made visible*, in documents where no reader had ever drawn it.
* **EF-057** — the block of CSS added to an existing cover page pushed the cover
  down and off the bottom of the screen.
* **EF-058** — the NCX numbered its entries with a running counter, so a book
  whose table of contents names one anchor several times came out invalid.
* **EF-059** — a `<style>` element inside a document never went through the
  stylesheet repairs, so a dead url in one stayed dead.
* **EF-060** — an `<a name="…">` anchor was not counted as an anchor, so a live
  link was reported as pointing at nothing.

Each class below states the shape the shelf produced, not a tidied version of
it: the whole reason these were missed is that all five look correct in a
fixture written by the person who wrote the code.
"""

from __future__ import annotations

import re
import zipfile

from epubforge import covers
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import MODERN_NAV, png_bytes, write_zip

CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/package.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)

PACKAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:identifier id="i">urn:uuid:1</dc:identifier><dc:title>T</dc:title>'
    "<dc:language>pl</dc:language>"
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>{cover}</metadata>'
    "<manifest>{items}</manifest>"
    "<spine>{spine}</spine></package>"
)

BASE_ITEMS = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'


def make_book(path, documents: dict[str, str], *, extra_items="", extra_files=None, cover="") -> str:
    """A book of exactly the documents given, in the order given."""
    items = BASE_ITEMS + "".join(
        f'<item id="d{n}" href="{name}" media-type="application/xhtml+xml"/>'
        for n, name in enumerate(documents)
    ) + extra_items
    spine = "".join(f'<itemref idref="d{n}"/>' for n, _ in enumerate(documents))
    entries = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/package.opf": PACKAGE.format(items=items, spine=spine, cover=cover).encode(),
        "OEBPS/nav.xhtml": MODERN_NAV.encode(),
    }
    for name, markup in documents.items():
        entries[f"OEBPS/{name}"] = markup.encode()
    entries.update(extra_files or {})
    return write_zip(str(path), entries)


def documents_of(result) -> dict[str, str]:
    with zipfile.ZipFile(result.output_path) as archive:
        return {
            name: archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        }


def body_of(result, contains: str) -> str:
    for markup in documents_of(result).values():
        if contains in markup:
            return markup[markup.find("<body"):]
    raise AssertionError(f"no document carries {contains!r}")


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


#: A `<p>` where only a `<meta>` belongs. Written as `.xhtml` and well-formed,
#: which is the whole point: an XML parser leaves it in the head, and the head is
#: not drawn.
HEAD_FLOW = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title><p>Nigdy tego nie widziałeś.</p></head>"
    "<body><h1>Rozdział</h1><p>Tekst rozdziału.</p></body></html>"
)


class TestContentInTheHeadKeepsBeingInvisible:
    """EF-056. Three empty paragraphs in `<head>` pushed eighteen pages down by
    about 105 px on one book and the render gate refused it — correctly. The
    paragraphs cannot stay in `<head>`, because XHTML5 does not allow them
    there; what they must not do is start being drawn."""

    def test_the_paragraph_leaves_the_head(self, tmp_path):
        result = rebuild(
            make_book(tmp_path / "in.epub", {"chapter.xhtml": HEAD_FLOW}),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        markup = next(iter(documents_of(result).values()))
        head = markup[markup.find("<head"):markup.find("</head>")]
        assert "Nigdy tego nie widziałeś" not in head

    def test_and_arrives_in_the_body_without_being_drawn(self, tmp_path):
        """The text is still in the file and still in reading order — K1 — and
        the page looks exactly as it did."""
        result = rebuild(
            make_book(tmp_path / "in.epub", {"chapter.xhtml": HEAD_FLOW}),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        body = body_of(result, "Nigdy tego nie widziałeś")
        moved = re.search(r"<p[^>]*>Nigdy tego nie widziałeś\.</p>", body)
        assert moved, body
        assert "display: none" in moved.group()

    def test_the_report_says_it_out_loud(self, tmp_path):
        result = rebuild(
            make_book(tmp_path / "in.epub", {"chapter.xhtml": HEAD_FLOW}),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "xhtml.head-flow-hidden" in rules_of(result)

    def test_but_an_html_document_moves_it_visibly(self, tmp_path):
        """The other half, and the half that was already right. A browser
        reading HTML starts the body at the first thing that does not belong in
        the head, so there the paragraph *was* the first thing on the page and
        hiding it would be the change of appearance."""
        html = HEAD_FLOW.replace('<?xml version="1.0" encoding="utf-8"?>', "")
        result = rebuild(
            make_book(
                tmp_path / "in.epub",
                {"chapter.html": html},
                extra_items="",
            ),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        body = body_of(result, "Nigdy tego nie widziałeś")
        moved = re.search(r"<p[^>]*>Nigdy tego nie widziałeś\.</p>", body)
        assert moved, body
        assert "display: none" not in moved.group()
        assert "xhtml.head-flow-hidden" not in rules_of(result)


class TestTheCoverRulesDoNotMoveTheCover:
    """EF-057. `height: 100%` on a body that still carries the browser's default
    margin makes the page taller than the window; the flex centring then centres
    against that taller box and the bottom of the cover falls off. Measured on
    two books: `91.2% → 82.0%` and `56.2% → 44.5%` of the page's ink."""

    @staticmethod
    def declarations(block: str) -> str:
        """The block with its CSS comments taken out.

        Not fussiness. The first version of this test searched the whole string
        and **passed against the mutation that removed the rule**, because the
        comment explaining `margin: 0` still said `margin: 0`. A test that reads
        the prose instead of the code is a test that watches itself."""
        return re.sub(r"/\*.*?\*/", "", block, flags=re.S)

    def test_both_blocks_zero_the_margin(self):
        """One rule, two code paths, and the whole of EF-026 was that they had
        drifted apart. They may not drift apart again on the line that decides
        whether the page is taller than the window."""
        for block in (covers.COVER_STYLE, covers.COVER_STYLE_ADDED):
            assert re.search(r"margin:\s*0", self.declarations(block)), block

    def test_the_margin_is_zeroed_where_the_height_is_set(self):
        """`height: 100%` is what makes the missing margin matter, so the two
        belong to the same rule. Zeroing the margin somewhere else in the block
        would satisfy the test above and still leave the page too tall."""
        for block in (covers.COVER_STYLE, covers.COVER_STYLE_ADDED):
            rule = re.search(r"body\s*\{([^}]*height:\s*100%[^}]*)\}", self.declarations(block))
            assert rule, block
            assert re.search(r"margin:\s*0", rule.group(1)), rule.group(1)

    def test_the_added_block_still_limits_the_image(self):
        """The margin is not a substitute for the limits — a test that only
        watched the margin would pass on a block that had stopped fitting the
        cover at all."""
        assert "max-height: 100%" in covers.COVER_STYLE_ADDED
        assert "object-fit: contain" in covers.COVER_STYLE_ADDED


NCX_PAGE = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title></head><body>"
    '<h1 id="ten-sam">Jeden</h1><p>a</p>'
    '<h1 id="ten-sam">Dwa</h1><p>b</p>'
    '<h1 id="inny">Trzy</h1><p>c</p>'
    "</body></html>"
)

#: The table of contents the shelf produced: three entries, two of which name
#: the same anchor because the source put the same `id` on two headings.
NAV_WITH_A_REPEATED_TARGET = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><meta charset="utf-8"/><title>Spis</title></head>
  <body><nav epub:type="toc"><ol>
    <li><a href="chapter.xhtml#ten-sam">Jeden</a></li>
    <li><a href="chapter.xhtml#ten-sam">Dwa</a></li>
    <li><a href="chapter.xhtml#inny">Trzy</a></li>
  </ol></nav></body>
</html>
"""


def ncx_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".ncx"))
        return archive.read(name).decode("utf-8")


class TestTwoEntriesForOnePlaceCarryOneNumber:
    """EF-058. `playOrder` is a property of the place, not of the entry, and
    written as a running counter it says otherwise. A book arriving with the
    same `id` on several headings — a converter's doing, older than us — then
    came out with `different playOrder values … refer to same target`, and
    strict refused to publish it."""

    def build(self, tmp_path):
        return rebuild(
            make_book(
                tmp_path / "in.epub",
                {"chapter.xhtml": NCX_PAGE},
                extra_files={"OEBPS/nav.xhtml": NAV_WITH_A_REPEATED_TARGET.encode()},
            ),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )

    def pairs(self, ncx: str) -> list[tuple[str, str]]:
        return [
            (order, src)
            for order, src in re.findall(
                r'playOrder="(\d+)".*?<content src="([^"]+)"', ncx, re.S
            )
        ]

    def test_the_same_target_gets_the_same_number(self, tmp_path):
        result = self.build(tmp_path)
        assert result.status.wrote_a_file, result.report.to_text()
        by_target: dict[str, set[str]] = {}
        for order, src in self.pairs(ncx_of(result)):
            by_target.setdefault(src, set()).add(order)
        clashing = {src: orders for src, orders in by_target.items() if len(orders) > 1}
        assert not clashing, clashing

    def test_and_a_different_target_gets_a_different_one(self, tmp_path):
        """Half of this rule is trivially satisfiable by giving every entry the
        number 1, which is why the other half is a test."""
        pairs = self.pairs(ncx_of(self.build(tmp_path)))
        distinct_targets = {src for _, src in pairs}
        distinct_orders = {order for order, _ in pairs}
        assert len(distinct_orders) == len(distinct_targets) >= 2, pairs

    def test_the_numbering_starts_at_one_and_has_no_holes(self, tmp_path):
        orders = sorted({int(o) for o, _ in self.pairs(ncx_of(self.build(tmp_path)))})
        assert orders == list(range(1, len(orders) + 1)), orders


INLINE_DEAD_URL = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title>"
    "<style>body { background-image: url(nie-ma-takiego.png); color: black; }</style>"
    "</head><body><p>Tekst rozdziału.</p></body></html>"
)

INLINE_MALFORMED = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title>"
    '<style>p.sgc-1 {text-align="center"} p.sgc-1 { color: black; }</style>'
    "</head><body><p class=\"sgc-1\">Tekst rozdziału.</p></body></html>"
)


def style_of(result) -> str:
    for markup in documents_of(result).values():
        found = re.search(r"<style[^>]*>(.*?)</style>", markup, re.S)
        if found:
            return found.group(1)
    raise AssertionError("no <style> element in the rebuild")


class TestCssInsideADocumentIsRepairedToo:
    """EF-059. The stylesheet stage walked `by_type("style")` — separate `.css`
    files — so a `<style>` element got url repointing and nothing else. Two of
    the nine refusals came out of that gap, one of them the very defect F-017
    exists to prevent."""

    def test_a_dead_url_in_a_style_element_is_neutralised(self, tmp_path):
        result = rebuild(
            make_book(tmp_path / "in.epub", {"chapter.xhtml": INLINE_DEAD_URL}),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        css = style_of(result)
        assert "nie-ma-takiego.png" not in css
        assert "none" in css

    def test_and_the_rest_of_the_block_survives(self, tmp_path):
        result = rebuild(
            make_book(tmp_path / "in.epub", {"chapter.xhtml": INLINE_DEAD_URL}),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert "color" in style_of(result)

    def test_a_declaration_written_with_an_equals_sign_is_dropped(self, tmp_path):
        """`p.sgc-1 {text-align="center"}`, from the shelf. EPUBCheck: `Token
        "=" not allowed here, expecting :`."""
        result = rebuild(
            make_book(tmp_path / "in.epub", {"chapter.xhtml": INLINE_MALFORMED}),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        assert 'text-align="center"' not in style_of(result)
        assert "css.malformed-declaration-dropped" in rules_of(result)

    def test_and_dropping_it_does_not_start_centring_the_text(self, tmp_path):
        """The other repair — turning `=` into `:` — would also satisfy
        EPUBCheck, and would centre text that has never been centred. Which one
        the publisher meant is a question about intent, and the answer that
        happens without anybody to ask is the one that changes nothing."""
        result = rebuild(
            make_book(tmp_path / "in.epub", {"chapter.xhtml": INLINE_MALFORMED}),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert "text-align" not in style_of(result)

    def test_preserve_keeps_it_and_says_nothing_was_removed(self, tmp_path):
        """Removal is gated the same way every other removal in this stage is:
        `preserve` publishes the book as the publisher wrote it."""
        result = rebuild(
            make_book(tmp_path / "in.epub", {"chapter.xhtml": INLINE_MALFORMED}),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert 'text-align="center"' in style_of(result)
        assert "css.malformed-declaration-dropped" not in rules_of(result)

    def test_an_attribute_selector_is_not_a_malformed_declaration(self, tmp_path):
        """`a[href="x"]` carries the same three characters in the same order.
        A rule that cannot tell them apart eats selectors."""
        markup = INLINE_MALFORMED.replace(
            'p.sgc-1 {text-align="center"}', 'a[href="x"] { color: red; }'
        )
        result = rebuild(
            make_book(tmp_path / "in.epub", {"chapter.xhtml": markup}),
            str(tmp_path / "out.epub"),
            Policy.preset("strict"),
        )
        assert 'a[href="x"]' in style_of(result)


NAMED_ANCHOR_TARGET = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>Przypisy</title></head><body>"
    '<p><a name="fn1">Przypis pierwszy.</a></p>'
    "</body></html>"
)

NAMED_ANCHOR_SOURCE = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title></head><body>"
    '<p>Zdanie<a href="notes.xhtml#fn1">1</a>.</p>'
    "</body></html>"
)


class TestAnOldStyleAnchorCountsAsAnAnchor:
    """EF-060. The map of "which anchors each document has" was built from `id`
    alone, and `_modernise` turns `<a name="x">` into `<a id="x">` afterwards —
    so at the moment references were resolved the anchor did not exist yet. A
    live link was reported as pointing at nothing, and in strict that list is
    what decides whether the book may be published at all."""

    def build(self, tmp_path, policy: str):
        return rebuild(
            make_book(
                tmp_path / "in.epub",
                {"chapter.xhtml": NAMED_ANCHOR_SOURCE, "notes.xhtml": NAMED_ANCHOR_TARGET},
            ),
            str(tmp_path / "out.epub"),
            Policy.preset(policy),
        )

    def test_the_link_is_not_reported_as_unresolved(self, tmp_path):
        result = self.build(tmp_path, "preserve")
        assert "xhtml.fragment-unresolved" not in rules_of(result)

    def test_and_strict_publishes_the_book(self, tmp_path):
        result = self.build(tmp_path, "strict")
        assert result.status.wrote_a_file, result.report.to_text()

    def test_the_anchor_really_is_there_afterwards(self, tmp_path):
        """The map may not promise an anchor the rebuild does not deliver — that
        would trade a false alarm for a silent broken link."""
        result = self.build(tmp_path, "strict")
        notes = next(m for n, m in documents_of(result).items() if "Przypis" in m)
        assert 'id="fn1"' in notes

    def test_but_a_name_that_cannot_become_an_id_is_not_promised(self, tmp_path):
        """`_modernise` refuses to write an `id` that is not an XML name, so
        this anchor will not exist and the link into it really is dead."""
        target = NAMED_ANCHOR_TARGET.replace('name="fn1"', 'name="1 fn"')
        source = NAMED_ANCHOR_SOURCE.replace("#fn1", "#1 fn")
        result = rebuild(
            make_book(
                tmp_path / "in.epub",
                {"chapter.xhtml": source, "notes.xhtml": target},
            ),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "xhtml.fragment-unresolved" in rules_of(result)


def test_the_cover_page_is_still_recognised_by_the_manifest(tmp_path):
    """A guard for the fixture above rather than for the code: EF-024 was a
    cover rule that fired on every unsized image, and a test that stopped
    telling the two apart would hide its return."""
    result = rebuild(
        make_book(
            tmp_path / "in.epub",
            {
                "cover.xhtml": (
                    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
                    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
                    '<meta charset="utf-8"/><title>Okładka</title></head>'
                    '<body><div><img src="cover.png" alt="Okładka"/></div></body></html>'
                ),
                "chapter.xhtml": (
                    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
                    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
                    '<meta charset="utf-8"/><title>R</title></head>'
                    '<body><p>Tekst</p><img src="inne.png" alt=""/></body></html>'
                ),
            },
            extra_items=(
                '<item id="cov" href="cover.png" media-type="image/png" properties="cover-image"/>'
                '<item id="inne" href="inne.png" media-type="image/png"/>'
            ),
            extra_files={
                "OEBPS/cover.png": png_bytes(),
                "OEBPS/inne.png": png_bytes(size=(20, 20)),
            },
        ),
        str(tmp_path / "out.epub"),
        Policy.preset("preserve"),
    )
    assert result.status.wrote_a_file, result.report.to_text()
    documents = documents_of(result)
    cover = next(m for n, m in documents.items() if "Okładka" in m)
    other = next(m for n, m in documents.items() if "Tekst" in m)
    assert "object-fit: contain" in cover
    assert "object-fit: contain" not in other


class TestASignatureDoesNotCarryASomebodysTitle:
    """Not from the shelf run — from the gate that guards it.

    `sprawdz-nazwy.py` lives in the private notes repository and scans this one
    for book titles. Teaching it the seven books behind the findings above made
    it fail immediately, on a file that had been here for releases: a recorded
    corpus signature holding an EPUBCheck sentence with a package identifier of
    the form `Author_Title_9789024531790` still in it.

    The masking rule had been "keep a quoted string that looks like a markup
    name", and its pattern allowed underscores and forty characters — under
    which a publisher's identifier is a markup name. It is not, and the
    difference is exactly what S-06 is about: this repository is public.
    """

    def test_an_identifier_is_masked(self):
        from epubforge.validate import message_shape

        shape = message_shape(
            'NCX identifier ("Author_Title_9789024531790") does not match '
            'OPF identifier ("urn:uuid:0c1b55e8").'
        )
        assert "Author" not in shape and "Title" not in shape
        assert '"…"' in shape

    def test_but_an_element_name_survives(self):
        """The mask has to leave HTML's own words alone, or every schema error
        in every signature collapses to the same sentence and the signatures
        stop distinguishing anything."""
        from epubforge.validate import message_shape

        assert '"img"' in message_shape('element "img" not allowed here')
        assert '"xml:lang"' in message_shape('attribute "xml:lang" not allowed here')
        assert '"ns1:file-as"' in message_shape('expected attribute "ns1:file-as"')
        assert '"viewBox"' in message_shape('attribute "viewBox" not allowed here')

    def test_no_recorded_signature_carries_an_underscored_identifier(self):
        """The signatures already on disk, checked the way the scanner checks
        them — because fixing the function does nothing for a file recorded
        before it was fixed, and one such file was here."""
        import json
        import pathlib
        import re

        suspicious = re.compile(r'"([A-Za-z0-9]+_[A-Za-z0-9_]{6,})"')
        found: list[str] = []
        for path in pathlib.Path(__file__).parent.rglob("*.json"):
            recorded = json.loads(path.read_text(encoding="utf-8"))
            for shape in self._shapes(recorded):
                found += [f"{path.name}: {hit}" for hit in suspicious.findall(shape)]
        assert not found, found

    @classmethod
    def _shapes(cls, node) -> list[str]:
        if isinstance(node, dict):
            out: list[str] = []
            for key, value in node.items():
                if key == "shapes" and isinstance(value, dict):
                    out += list(value)
                else:
                    out += cls._shapes(value)
            return out
        if isinstance(node, list):
            return [s for item in node for s in cls._shapes(item)]
        return []
