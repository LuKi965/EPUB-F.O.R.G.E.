"""Which image is the cover, and what a cover page needs in order to fit.

WP-8, and three findings that turn out to be one mistake made in two places:
the cover was recognised by a path that had already changed, and it was
repaired with a rule that could not work.

**EF-024.** `_cover_fits_the_page` resolved each `<img src>` against the
document's *original* path, at a point in the pipeline where `src` had already
been rewritten to its new one. The result named nothing; `path_map` answered
`None` for it and `None` for the cover; `None != None` is false; and the guard
meant to keep the cover's rule on the cover let every unsized image in the book
through. On the suite's own fixture that is two decorative images in one
document, and on a real book it is the title artwork.

**EF-026.** What it added was `max-width: 100%; max-height: 100%` inline. The
second of those is a percentage, and a percentage height resolves against the
containing block — with no height on `html` and `body` there is nothing to
resolve against, so the rule that keeps a tall cover on one page was inert
exactly where it was needed. A cover page this program *generates* has had that
height since the day it was written. Two paths to one effect, one of them dead.

**EF-034.** One report line covered two different facts: a page whose indent
came from a stylesheet, and a page that links no stylesheet at all and so had
no indent to remove. Both got the sentence about removing the indent.
"""

from __future__ import annotations

import zipfile


from epubforge import covers
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import make_legacy_epub


def rebuilt(tmp_path, name: str = "out.epub"):
    source = make_legacy_epub(str(tmp_path / "in.epub"))
    result = rebuild(
        source, str(tmp_path / name),
        Policy.preset("preserve", validate_before_publish="off"),
    )
    assert result.status.wrote_a_file, result.report.to_text()
    return result


#: Ta sama okładka co w atrapie legacy, ale na stronie, która jest **wyłącznie**
#: okładką: obrazek i nic poza nim. To jest kształt, dla którego szablon strony
#: okładkowej powstał, i jedyny, w którym wolno go użyć (EF-041).
COVER_ONLY_PAGE = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
    '<meta charset="utf-8"/><title>Okładka</title></head>'
    '<body><div><img src="cover.png" alt=""/></div></body></html>'
)


def cover_page_book(tmp_path, name: str = "cover-page.epub"):
    """Książka, której okładka jest osobną stroną bez tekstu."""
    from tests.factory import MODERN_NAV, write_zip
    from tests.test_dead_css_urls import CONTAINER, PNG

    package = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="i"><metadata '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="i">urn:uuid:9</dc:identifier><dc:title>T</dc:title>'
        "<dc:language>pl</dc:language>"
        '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>'
        "<manifest>"
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="c" href="cover.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="img" href="cover.png" media-type="image/png" properties="cover-image"/>'
        "</manifest>"
        '<spine><itemref idref="c"/></spine></package>'
    )
    source = write_zip(str(tmp_path / name), {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/package.opf": package.encode(),
        "OEBPS/nav.xhtml": MODERN_NAV.encode(),
        "OEBPS/cover.xhtml": COVER_ONLY_PAGE.encode(),
        "OEBPS/cover.png": PNG,
    })
    result = rebuild(
        source, str(tmp_path / f"out-{name}"),
        Policy.preset("preserve", validate_before_publish="off"),
    )
    assert result.status.wrote_a_file, result.report.to_text()
    return result


def documents(result) -> "dict[str, str]":
    with zipfile.ZipFile(result.output_path) as archive:
        return {
            name: archive.read(name).decode()
            for name in archive.namelist()
            if name.endswith(".xhtml")
        }


def rules_of(result) -> set:
    return {finding.rule for finding in result.report.findings if finding.rule}


class TestOnlyTheCoverGetsTheCoverRule:
    """EF-024, and it is asserted on the fixture the whole suite already uses,
    because that is where it was reproduced: `deco.webp` is decoration, it is
    not the cover, and before this it came out with the cover's limits on it —
    twice in one document."""

    def test_a_decorative_image_is_left_alone(self, tmp_path):
        written = documents(rebuilt(tmp_path))
        for name, page in written.items():
            if "cover" in name:
                continue
            for line in page.splitlines():
                if "deco.webp" in line:
                    assert "max-height" not in line, f"{name}: {line.strip()}"

    def test_the_cover_still_gets_it(self, tmp_path):
        """The other half, and the one that stops this being a rule against
        doing anything: the fixture's cover has no sizing rule anywhere, so it
        is exactly the case the repair exists for."""
        result = rebuilt(tmp_path, "cover.epub")
        assert "xhtml.cover-fitted" in rules_of(result)

    def test_the_question_is_asked_of_the_manifest(self):
        """Asserted on `covers`, because that is where the change of authority
        lives. A path can be rewritten by the relayout; a manifest entry cannot.
        """
        class Book:
            cover_path = "OEBPS/images/okladka.png"

            def get(self, _path):
                return None

        assert covers.is_the_cover(Book(), "OEBPS/images/okladka.png")
        assert not covers.is_the_cover(Book(), "OEBPS/images/deco.webp")

    def test_two_unknown_paths_are_not_the_same_path(self):
        """The exact shape of the defect, kept as a test because it is the kind
        of comparison that reads as correct: both sides answered `None`, and
        `None != None` is false, so the guard passed everything."""
        class Bookless:
            cover_path = ""

            def get(self, _path):
                return None

        assert not covers.is_the_cover(Bookless(), "cokolwiek.png")
        assert covers.cover_identities(Bookless()) == set()


class TestOneTemplateForBothCoverPages:
    """EF-026. A generated cover page and a repaired one are now fitted by the
    same three rules, from one place."""

    def test_the_generated_page_and_the_repair_share_their_rules(self):
        import inspect

        from epubforge.stages import navigation

        assert "cover_style" in navigation.COVER_PAGE_TEMPLATE
        assert "covers.COVER_STYLE" in inspect.getsource(navigation)

    def test_the_repair_gives_the_percentage_something_to_resolve_against(self):
        """The load-bearing line. `max-height: 100%` without a height on `html`
        and `body` is a declaration that does nothing, which is why a tall cover
        kept coming out across two screens."""
        assert "height: 100%" in covers.COVER_STYLE
        assert "height: 100%" in covers.COVER_STYLE_ADDED
        for style in (covers.COVER_STYLE, covers.COVER_STYLE_ADDED):
            assert "max-height: 100%" in style
            assert "object-fit: contain" in style

    def test_the_repair_lands_in_the_document_head(self, tmp_path):
        """Two of the three rules are about `html` and `body`, and an inline
        style cannot say anything about an ancestor. So it has to be a block.

        Measured on a page that is *only* the cover, which is what this template
        is for. The earlier version of this test used the legacy fixture, whose
        cover reference points at chapter one — see `TestTheTemplateNeedsAPage`
        below for why that was asserting a defect.
        """
        written = documents(cover_page_book(tmp_path))
        fitted = [
            page for page in written.values()
            if "EPUB-Forge: nothing in this book sized the cover" in page
        ]
        assert fitted, "the cover is unsized, so the page must carry the template"
        assert "<head" in fitted[0].split("html, body")[0]


class TestTheTemplateNeedsAPageWithNothingToLayOut:
    """EF-041, and the finding that held a release back.

    `COVER_STYLE_ADDED` lays out the **whole document**: `height: 100%` on html
    and body, and a centring flex box. That is right for a cover page — one
    image, nothing else — and it destroys any document with text in it, because
    the running text is centred and clipped to the height of the screen and
    whatever does not fit is simply not drawn.

    A legacy `<guide>` may point `type="cover"` at a document that is also
    chapter one, and books do — the suite's own legacy fixture is one. That
    chapter was getting the page template, and the rebuilt page came out with
    **3.3% → 2.9%** of it inked at 600×800. The render gate refused to publish,
    which is the gate doing exactly what it exists for.

    The previous version of the test above asserted that behaviour, because the
    test was written from the same misunderstanding as the code.
    """

    def test_a_chapter_that_happens_to_be_named_as_the_cover_keeps_its_layout(
        self, tmp_path
    ):
        written = documents(rebuilt(tmp_path, "guide.epub"))
        chapter = next(
            page for name, page in written.items() if name.endswith("chapter-1.xhtml")
        )
        assert "Rozdział pierwszy" in chapter, "wrong page — the fixture moved"
        assert "display: flex" not in chapter
        assert "html, body { height: 100%" not in chapter

    def test_but_the_image_is_still_kept_from_overflowing(self, tmp_path):
        """The repair is not withdrawn, only scoped. `max-width`/`max-height` on
        the image itself can only ever make it smaller, so it is safe on any
        document — and it is what this code did before WP-8."""
        written = documents(rebuilt(tmp_path, "scoped.epub"))
        chapter = next(
            page for name, page in written.items() if name.endswith("chapter-1.xhtml")
        )
        assert "max-width: 100%" in chapter

    def test_a_real_cover_page_still_gets_the_template(self, tmp_path):
        """The other side, so that the condition cannot be tightened into
        uselessness: a page carrying the cover and no text gets the block."""
        written = documents(cover_page_book(tmp_path))
        assert any("display: flex" in page for page in written.values())


class TestAPixelSizedCoverIsReportedNotOverwritten:
    """`<img width="1472" height="2341">` fixes the cover at one size whatever
    the screen is. It is the publisher's instruction, so it is named in the
    report and left alone — changing it is a decision about how the book looks,
    and this program does not make those on its own (S-02, S-03)."""

    def test_the_attributes_survive_and_the_report_says_so(self, tmp_path):
        source = make_legacy_epub(str(tmp_path / "px.epub"))
        entries = {}
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                entries[name] = archive.read(name)
        # The fixture writes the cover's name percent-encoded, which is itself
        # the shape of book this exists for, so the marker is the encoded form.
        cover = next(
            name for name in entries
            if name.endswith(".xhtml") and b"ok%C5%82adka.png" in entries[name]
        )
        entries[cover] = entries[cover].replace(
            b'src="../Images/ok%C5%82adka.png"',
            b'src="../Images/ok%C5%82adka.png" width="1472" height="2341"',
        )
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

        result = rebuild(
            source, str(tmp_path / "px-out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert "xhtml.cover-sized-in-pixels" in rules_of(result)
        written = documents(result)
        assert any('width="1472"' in page for page in written.values()), (
            "the publisher's instruction is reported, not removed"
        )


class TestTwoFactsGetTwoSentences:
    """EF-034. The code told the two cases apart all along; the catalogue had
    one entry for both, so a page with no stylesheet was told its indent had
    been removed."""

    def test_both_messages_exist_in_both_languages(self):
        from epubforge import rules

        for language in ("en", "pl"):
            plain = rules.describe("xhtml.image-paragraph-centred", language, {"count": 2})
            unstyled = rules.describe(
                "xhtml.image-paragraph-centred-unstyled", language, {"count": 2}
            )
            assert plain and unstyled and plain != unstyled

    def test_the_message_for_a_page_with_no_stylesheet_does_not_mention_an_indent(self):
        from epubforge import rules

        said = rules.describe(
            "xhtml.image-paragraph-centred-unstyled", "en", {"count": 1}
        )
        assert "indent" not in said.lower()
        polish = rules.describe(
            "xhtml.image-paragraph-centred-unstyled", "pl", {"count": 1}
        )
        assert "wcięci" not in polish.lower()

    def test_a_page_with_no_stylesheet_gets_the_second_message(self, tmp_path):
        source = make_legacy_epub(str(tmp_path / "bez.epub"))
        entries = {}
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                entries[name] = archive.read(name)
        page = "OEBPS/Text/tytul.xhtml"
        entries[page] = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Tytuł</title></head>'
            '<body><p><img src="../Images/deco.webp" alt="ozdoba"/></p></body></html>'
        ).encode()
        opf = next(name for name in entries if name.endswith(".opf"))
        package = entries[opf].decode()
        package = package.replace(
            "</manifest>",
            '<item id="tytul" href="Text/tytul.xhtml" media-type="application/xhtml+xml"/></manifest>',
        ).replace("</spine>", '<itemref idref="tytul"/></spine>')
        entries[opf] = package.encode()
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

        result = rebuild(
            source, str(tmp_path / "bez-out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert "xhtml.image-paragraph-centred-unstyled" in rules_of(result)
