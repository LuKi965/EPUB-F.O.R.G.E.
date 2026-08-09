"""The cover has to fit the screen, and the rule that makes it fit is CSS.

Written after I got this wrong in conversation. Asked how to detect a stylesheet
that is correct but reaches no document — Calibre's characteristic damage — I
proposed exempting the cover page, on the reasoning that a page holding one
image does not need a stylesheet. The owner corrected it:

    Nie jest prawdą, że okładka nie potrzebuje CSS. Jak inaczej okładka miałaby
    się skalować do czytników? Wymiary pliku są zawsze takie same ale ekrany są
    różne. […] Dlatego to takie ważne aby nie zepsuć tego mechanizmu.

He is right, and the correction is not a detail. A cover is a fixed number of
pixels; screens are not. Without a rule sizing it, a reader falls back to the
image's natural dimensions, and the same file is a stamp on one device and
cropped on the next. The cover is not the page that can spare its stylesheet —
it is the page where losing it is most visible, on the first screen of the book.

So the cover page is the *worst* candidate for an exemption, and these tests pin
the three halves of the mechanism:

* an author's sizing is preserved exactly, wherever it lives;
* a cover nothing sizes gets limits added, because that is a defect;
* a cover page we generate ourselves is born with them.
"""

from __future__ import annotations

import zipfile

import pytest

from .factory import png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

PACKAGE = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Ksi&#x105;&#x17c;ka z ok&#x142;adk&#x105;</dc:title>
    <dc:identifier id="id">urn:uuid:2f1c9d3a-51b6-4c02-9d77-1a5f2e8b4c30</dc:identifier>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="cover-img" href="cover.png" media-type="image/png" properties="cover-image"/>
    <item id="style" href="style.css" media-type="text/css"/>
  </manifest>
  <spine>
    <itemref idref="cover-page"/>
    <itemref idref="chapter"/>
  </spine>
</package>
"""

NAV = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><title>Spis</title></head>
  <body>
    <nav epub:type="toc"><ol><li><a href="chapter.xhtml">Rozdzia&#x142;</a></li></ol></nav>
    <nav epub:type="landmarks">
      <ol><li><a epub:type="cover" href="cover.xhtml">Ok&#x142;adka</a></li></ol>
    </nav>
  </body>
</html>
"""

CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><title>Rozdzia&#x142;</title><link rel="stylesheet" href="style.css"/></head>
  <body><p>Tekst rozdzia&#x142;u, d&#x142;ugi na tyle, by ksi&#x105;&#x17c;ka co&#x15b; znaczy&#x142;a.</p></body>
</html>
"""

#: The shape the owner's own repair of *Book 7* took: a class on the cover
#: page, a rule in the sheet, and a link joining the two.
COVER_WITH_SHEET = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><title>Ok&#x142;adka</title><link rel="stylesheet" href="style.css"/></head>
  <body epub:type="cover"><div class="okladka"><img src="cover.png" alt="Ok&#x142;adka"/></div></body>
</html>
"""

COVER_WITH_INLINE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><title>Ok&#x142;adka</title></head>
  <body epub:type="cover"><img src="cover.png" alt="Ok&#x142;adka" style="max-width: 80%; max-height: 90%;"/></body>
</html>
"""

COVER_WITH_NOTHING = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><title>Ok&#x142;adka</title></head>
  <body epub:type="cover"><img src="cover.png" alt="Ok&#x142;adka"/></body>
</html>
"""

STYLE = """@charset "utf-8";
body { margin: 0; }
.okladka img { max-width: 100%; max-height: 100%; }
p { text-indent: 1.2em; }
"""


def make_book(path, cover_markup: str) -> str:
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": PACKAGE.encode(),
            "OEBPS/nav.xhtml": NAV.encode(),
            "OEBPS/cover.xhtml": cover_markup.encode(),
            "OEBPS/chapter.xhtml": CHAPTER.encode(),
            "OEBPS/style.css": STYLE.encode(),
            "OEBPS/cover.png": png_bytes(size=(1600, 2400)),
        },
    )


def forge(source: str, destination, mode: str = "preserve"):
    from epubforge.pipeline import rebuild
    from epubforge.policy import Policy

    result = rebuild(source, str(destination), Policy.preset(mode))
    assert result.output_path, result.report.to_text()
    return result


def contents(epub_path: str) -> dict[str, str]:
    with zipfile.ZipFile(epub_path) as archive:
        return {
            name: archive.read(name).decode("utf-8", "replace")
            for name in archive.namelist()
            if name.endswith((".xhtml", ".css", ".opf"))
        }


def cover_document(files: dict[str, str]) -> str:
    covers = [text for name, text in files.items() if "cover" in name and name.endswith(".xhtml")]
    assert covers, sorted(files)
    return covers[0]


class TestAnAuthorsCoverSizingSurvives:
    """The mechanism the owner asked not to be broken.

    Calibre "bezmyślnie po prostu wszystko czyści" — it clears everything
    without looking, and the cover's scaling goes with it. Doing that is not a
    conformance improvement; it is a rendering regression on the first page of
    the book, and it is the reason this project exists.
    """

    @pytest.mark.parametrize("mode", ["minimal", "preserve", "strict"])
    def test_the_link_from_the_cover_page_to_the_sheet_stays(self, tmp_path, mode):
        book = make_book(tmp_path / "in.epub", COVER_WITH_SHEET)
        result = forge(book, tmp_path / f"out-{mode}.epub", mode)
        files = contents(result.output_path)
        assert 'rel="stylesheet"' in cover_document(files)

    @pytest.mark.parametrize("mode", ["preserve", "strict"])
    def test_the_rule_that_sizes_the_cover_is_not_pruned(self, tmp_path, mode):
        """No rule is removed for being used by only one document. A cover rule
        is used by exactly one document by definition, so a pruner that counts
        uses is a pruner that deletes this."""
        book = make_book(tmp_path / "in.epub", COVER_WITH_SHEET)
        result = forge(book, tmp_path / f"out-{mode}.epub", mode)
        sheets = [t for name, t in contents(result.output_path).items() if name.endswith(".css")]
        assert any(".okladka img" in text and "max-width" in text for text in sheets)

    def test_no_second_opinion_is_written_over_it(self, tmp_path):
        """The safety net only catches a cover that is falling. An author who
        sized the image already gets no second opinion — ours would win the
        cascade, being inline, and quietly replace a considered choice.

        Narrowed to sizing on purpose. This page does gain an inline
        `text-align: center`, from the rule that centres an image nothing
        aligned, and that is a separate decision made on separate evidence. The
        invariant here is about width and height: the properties that decide
        whether a 1600-pixel cover fits a six-inch screen.
        """
        book = make_book(tmp_path / "in.epub", COVER_WITH_SHEET)
        result = forge(book, tmp_path / "out.epub")
        assert "xhtml.cover-fitted" not in {f.rule for f in result.report.findings}
        cover = cover_document(contents(result.output_path))
        assert "width" not in cover and "height" not in cover

    def test_an_inline_size_is_left_exactly_as_written(self, tmp_path):
        """80% and 90% are somebody's decision, not an approximation of 100%."""
        book = make_book(tmp_path / "in.epub", COVER_WITH_INLINE)
        result = forge(book, tmp_path / "out.epub")
        cover = cover_document(contents(result.output_path))
        assert "max-width: 80%" in cover and "max-height: 90%" in cover
        assert "xhtml.cover-fitted" not in {f.rule for f in result.report.findings}


class TestACoverNothingSizesIsRepaired:
    """The other half. A cover with no rule reaching it is the defect, and the
    one place where adding CSS is the correction rather than the damage."""

    def test_limits_are_added_and_reported(self, tmp_path):
        book = make_book(tmp_path / "in.epub", COVER_WITH_NOTHING)
        result = forge(book, tmp_path / "out.epub")
        assert "xhtml.cover-fitted" in {f.rule for f in result.report.findings}
        cover = cover_document(contents(result.output_path))
        assert "max-width: 100%" in cover and "max-height: 100%" in cover

    def test_the_limits_can_only_shrink_the_image_never_stretch_it(self):
        """Why this is safe to apply unasked. `max-width` and `max-height` have
        no effect on an image smaller than the box, so the worst outcome of
        guessing wrong is that nothing happens."""
        import inspect

        from epubforge.stages.content import ContentStage

        added = inspect.getsource(ContentStage._cover_fits_the_page)
        assert "max-width: 100%; max-height: 100%;" in added
        assert "width:" not in added.replace("max-width:", "").replace("min-width:", "")

    def test_a_generated_cover_page_is_born_with_them(self, tmp_path):
        """When the source has no cover page at all we write one, and a page we
        wrote ourselves has no excuse for arriving unscalable."""
        from epubforge.stages.navigation import COVER_PAGE_TEMPLATE

        assert "max-width: 100%" in COVER_PAGE_TEMPLATE
        assert "max-height: 100%" in COVER_PAGE_TEMPLATE
        assert "object-fit: contain" in COVER_PAGE_TEMPLATE
