"""The book's own cover, from the file to the row.

F02 of the handoff, and the reason it is a *missing feature* rather than a
styling defect: `reader._detect_cover` has worked out which resource is the
cover for a long time, and the window drew a 22 px generic book glyph for every
title anyway, because nothing carried the answer across.

C01…C06 of the acceptance matrix, and every one of them on a **real EPUB** the
production adapter reads — the handoff says in as many words not to take
`DemoBackend` for proof. The covers here are this file's own coloured
rectangles: the point is which resource is chosen and what is done with it, and
a repository that shipped somebody's cover art to make that point would be
making a different one (S-06).
"""

from __future__ import annotations

import io
import pathlib
import zipfile

import pytest

from epubforge.gui.shell import thumbnails
from epubforge.gui.shell.backend import EngineBackend
from epubforge.gui.shell.models import CoverState
from tests.factory import CONTAINER, MODERN_CHAPTER, MODERN_NAV, write_zip

PIL = pytest.importorskip("PIL.Image")


def picture(size=(120, 180), colour=(180, 40, 40), fmt="PNG") -> bytes:
    """A cover of this file's own making, in whatever shape a test needs."""
    out = io.BytesIO()
    PIL.new("RGB", size, colour).save(out, format=fmt)
    return out.getvalue()


#: An EPUB 3 package that says which image is the cover the modern way — the
#: `cover-image` manifest property — and carries a second image that is not it.
EPUB3_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="first" href="picture.png" media-type="image/png"/>
    <item id="cov" href="{cover}" media-type="{media}" properties="cover-image"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>
"""

#: And an EPUB 2 package that says it the old way: `<meta name="cover">`
#: pointing at a manifest id. The image it points at is deliberately **not**
#: the first in the archive, which is what C02 is about.
EPUB2_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:22222222-3333-4444-5555-666666666666</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>pl</dc:language>
    <meta name="cover" content="cov"/>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="first" href="picture.png" media-type="image/png"/>
    <item id="cov" href="okladka.png" media-type="image/png"/>
  </manifest>
  <spine toc="ncx"><itemref idref="ch1"/></spine>
</package>
"""

NCX = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:22222222-3333-4444-5555-666666666666"/></head>
  <docTitle><text>Ksiazka</text></docTitle>
  <navMap><navPoint id="n1" playOrder="1">
    <navLabel><text>Rozdzial</text></navLabel><content src="chapter.xhtml"/>
  </navPoint></navMap>
</ncx>
"""


def epub3(path, *, cover: bytes, name: str = "okladka.png",
          media: str = "image/png", first: bytes | None = None) -> str:
    """An EPUB 3 whose cover is declared with the manifest property."""
    return write_zip(str(path), {
        "META-INF/container.xml":
            CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf").encode(),
        "OEBPS/package.opf":
            EPUB3_OPF.format(title="Ksiazka trzecia", cover=name, media=media).encode(),
        "OEBPS/nav.xhtml": MODERN_NAV.encode(),
        "OEBPS/chapter.xhtml": MODERN_CHAPTER.format(image="").encode(),
        # First in the archive on purpose, and not the cover.
        "OEBPS/picture.png": first if first is not None else picture(colour=(20, 90, 20)),
        f"OEBPS/{name}": cover,
    })


def epub2(path, *, cover: bytes) -> str:
    """An EPUB 2 whose cover is declared with `<meta name="cover">`."""
    return write_zip(str(path), {
        "META-INF/container.xml":
            CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf").encode(),
        "OEBPS/package.opf": EPUB2_OPF.format(title="Ksiazka druga").encode(),
        "OEBPS/toc.ncx": NCX.encode(),
        "OEBPS/chapter.xhtml": MODERN_CHAPTER.format(image="").encode(),
        "OEBPS/picture.png": picture(colour=(20, 90, 20)),
        "OEBPS/okladka.png": cover,
    })


def analysed(source) -> "object":
    """One book through the production adapter, as the window gets it."""
    backend = EngineBackend("pl")
    (item,) = backend.analyse([pathlib.Path(source)],
                              progress=lambda _p: None, cancelled=lambda: False)
    return item


def colour_of(item) -> tuple:
    """What the thumbnail actually looks like, so a test can tell two covers
    apart rather than only counting that there is one."""
    with PIL.open(io.BytesIO(item.cover)) as opened:
        return opened.convert("RGB").resize((1, 1)).getpixel((0, 0))


def near(one: tuple, two: tuple, slack: int = 24) -> bool:
    return all(abs(a - b) <= slack for a, b in zip(one, two))


class TestC01AndC02WhichImageIsTheCover:
    """Two ways a book says which picture is its cover, and the rule that the
    first image in the archive is not one of them."""

    def test_c01_an_epub_3_cover_image_property_is_the_cover(self, tmp_path):
        red = (200, 30, 30)
        item = analysed(epub3(tmp_path / "three.epub", cover=picture(colour=red)))
        assert item.cover_state is CoverState.READY, item.error
        assert item.has_a_cover
        assert near(colour_of(item), red), "wzięta została inna ilustracja"

    def test_c02_an_epub_2_meta_cover_names_the_image_and_not_the_first_one(self, tmp_path):
        blue = (30, 60, 210)
        source = epub2(tmp_path / "two.epub", cover=picture(colour=blue))
        with zipfile.ZipFile(source) as archive:
            images = [n for n in archive.namelist() if n.endswith(".png")]
        assert images[0].endswith("picture.png"), "test nie sprawdza tego, co miał"

        item = analysed(source)
        assert item.cover_state is CoverState.READY, item.error
        assert near(colour_of(item), blue), "wzięty został pierwszy obraz w ZIP-ie"

    def test_a_book_that_names_no_cover_says_so_and_is_still_a_book(self, tmp_path):
        from tests.factory import make_modern_epub

        item = analysed(make_modern_epub(str(tmp_path / "plain.epub")))
        assert item.cover_state is CoverState.MISSING
        assert not item.has_a_cover and item.cover == b""
        # And the book is perfectly usable: no cover is not a defect.
        assert item.status.name in ("READY", "ATTENTION")


class TestC03WhatHappensToACoverThatCannotBeDrawn:
    """*„brak/uszkodzona/za duża okładka | stabilny placeholder; książka nadal
    obsługiwana"* — three different nothings, one placeholder, and never a
    failed book."""

    def test_a_damaged_cover_leaves_the_book_alone(self, tmp_path):
        item = analysed(epub3(tmp_path / "broken.epub", cover=b"NOT A PNG AT ALL"))
        assert item.cover_state is CoverState.FAILED
        assert not item.has_a_cover
        assert item.status.name in ("READY", "ATTENTION"), "książka padła przez obrazek"
        assert item.title, "metadane przepadły razem z okładką"

    def test_a_cover_the_program_will_not_decode_is_refused_by_size(self):
        assert thumbnails.shrink(b"x" * (thumbnails.MOST_BYTES + 1)) is None
        assert thumbnails.shrink(b"") is None
        assert thumbnails.shrink(b"nie obraz") is None

    def test_and_a_picture_with_too_many_pixels_is_refused_before_decoding(self,
                                                                          monkeypatch):
        """The number that costs memory is pixels, not bytes: a small file can
        decode to hundreds of megabytes."""
        monkeypatch.setattr(thumbnails, "MOST_PIXELS", 100)
        assert thumbnails.shrink(picture(size=(200, 300))) is None
        monkeypatch.setattr(thumbnails, "MOST_PIXELS", 40_000_000)
        assert thumbnails.shrink(picture(size=(200, 300))) is not None

    def test_a_format_pillow_can_read_is_read_whatever_the_book_calls_it(self, tmp_path):
        """A JPEG cover is as much a cover as a PNG one; the media type in the
        manifest is the book's claim and the bytes are the fact."""
        item = analysed(epub3(tmp_path / "jpeg.epub", cover=picture(fmt="JPEG"),
                              name="okladka.jpg", media="image/jpeg"))
        assert item.cover_state is CoverState.READY, item.error


class TestTheThumbnailItself:
    """What crosses the thread boundary, and what it is allowed to be."""

    def test_it_fits_the_box_and_keeps_its_proportions(self):
        tall = thumbnails.shrink(picture(size=(600, 1200)))
        assert tall is not None
        assert tall.width <= thumbnails.BIGGEST[0] and tall.height <= thumbnails.BIGGEST[1]
        # `contain`: 1:2 in, 1:2 out, nothing cropped to fill the box.
        assert abs(tall.width * 2 - tall.height) <= 2, (tall.width, tall.height)

    def test_a_wide_cover_is_not_stretched_into_the_box_either(self):
        wide = thumbnails.shrink(picture(size=(1200, 300)))
        assert wide is not None
        assert abs(wide.width - wide.height * 4) <= 4, (wide.width, wide.height)

    def test_what_crosses_the_line_is_bytes_and_not_a_widget(self, tmp_path):
        item = analysed(epub3(tmp_path / "bytes.epub", cover=picture()))
        assert isinstance(item.cover, bytes)
        assert item.cover.startswith(b"\x89PNG"), "miniatura nie jest PNG"
        assert item.cover_size[0] > 0 and item.cover_size[1] > 0
        import copy

        # It has to survive being copied between threads, which a QPixmap
        # would not (02-UI-DESIGN, „Kontrakt miniatur").
        assert copy.deepcopy(item).cover == item.cover

    def test_a_thumbnail_is_small_enough_to_carry(self, tmp_path):
        item = analysed(epub3(tmp_path / "small.epub", cover=picture(size=(2000, 3000))))
        assert item.has_a_cover
        assert len(item.cover) < 80_000, f"{len(item.cover)} bajtów na jedną miniaturę"


class TestC04TheCacheKnowsWhenTheFileChanged:
    """*„zmiana źródła pod tą samą ścieżką | unieważniona stara miniatura"*."""

    def test_the_identifier_is_the_file_and_not_the_path(self, tmp_path):
        source = tmp_path / "same-name.epub"
        epub3(source, cover=picture(colour=(200, 30, 30)))
        first = analysed(source)

        # The person replaces the book with another edition, same name.
        epub3(source, cover=picture(colour=(30, 60, 210)))
        second = analysed(source)

        assert first.book_id != second.book_id, "odcisk nie zauważył podmiany"
        assert not near(colour_of(first), colour_of(second)), "stara miniatura została"

    def test_and_the_same_file_twice_is_read_once(self, tmp_path):
        source = epub3(tmp_path / "twice.epub", cover=picture())
        backend = EngineBackend("pl")
        made = []
        real = thumbnails.shrink

        def counted(data, **kwargs):
            made.append(1)
            return real(data, **kwargs)

        thumbnails.shrink, saved = counted, thumbnails.shrink
        try:
            for _ in range(3):
                backend.analyse([pathlib.Path(source)],
                                progress=lambda _p: None, cancelled=lambda: False)
        finally:
            thumbnails.shrink = saved
        assert made == [1], f"okładka dekodowana {len(made)} razy zamiast raz"

    def test_a_cover_that_could_not_be_read_is_not_retried_forever(self, tmp_path):
        """`None` is an answer, not a cache miss: a damaged cover decoded on
        every look would cost the same as one that works."""
        store = thumbnails.Covers()
        assert not store.knows("x")
        store.put("x", None)
        assert store.knows("x") and store.get("x") is None

    def test_the_store_stays_bounded_and_drops_the_oldest_first(self):
        store = thumbnails.Covers(keep=3)
        for name in "abc":
            store.put(name, thumbnails.Thumbnail(b"", 1, 1, name))
        store.get("a")  # looked at, so no longer the oldest
        store.put("d", thumbnails.Thumbnail(b"", 1, 1, "d"))
        assert len(store) == 3
        assert not store.knows("b"), "wypadła nie ta, na którą nikt nie patrzył"
        assert store.knows("a") and store.knows("c") and store.knows("d")


class TestC05ACoverThatArrivesAfterTheBookIsGone:
    """*„okładka kończy odczyt po usunięciu książki | brak obcego wiersza i
    brak błędu"*."""

    def test_the_cover_belongs_to_the_item_and_not_to_a_shared_slot(self, tmp_path):
        one = analysed(epub3(tmp_path / "one.epub", cover=picture(colour=(200, 30, 30))))
        two = analysed(epub3(tmp_path / "two.epub", cover=picture(colour=(30, 60, 210))))
        assert one.book_id != two.book_id
        assert not near(colour_of(one), colour_of(two))
        # Removing one from a list cannot affect the other's picture, because
        # the picture is on the item rather than in a slot the row looks up.
        books = [one, two]
        books.remove(one)
        assert books[0].cover == two.cover


# --------------------------------------------------------------------------
# And the same thing in the window, which is where F02 was visible.
# --------------------------------------------------------------------------

qt = pytest.importorskip("PySide6.QtWidgets")

import os  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from epubforge.gui.shell import tokens as tokens_module  # noqa: E402
from epubforge.gui.shell.models import BookItem  # noqa: E402
from epubforge.gui.shell.responsive import LayoutMode  # noqa: E402
from epubforge.gui.shell.widgets import BookRow, Cover  # noqa: E402
from epubforge.gui.strings import tr  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = qt.QApplication.instance() or qt.QApplication([])
    yield app


def item_with(cover: bytes, **over) -> BookItem:
    made = thumbnails.shrink(cover) if cover else None
    return BookItem(
        source=pathlib.Path(over.pop("name", "a.epub")),
        title=over.pop("title", "Ksiazka"),
        book_id="odcisk",
        cover=made.data if made else b"",
        cover_size=(made.width, made.height) if made else (0, 0),
        cover_state=CoverState.READY if made else CoverState.MISSING,
        **over,
    )


class TestTheRowDrawsTheBooksOwnCover:
    def test_a_book_with_a_cover_gets_its_picture_and_not_a_glyph(self, qt_app):
        with_one = Cover(item_with(picture(colour=(200, 30, 30))), tokens_module.DARK)
        without = Cover(item_with(b""), tokens_module.DARK)
        assert not with_one.pixmap().isNull() and not without.pixmap().isNull()
        # Different pictures, which is the whole of F02: every book used to
        # get the same 22 px glyph.
        assert with_one.pixmap().toImage() != without.pixmap().toImage()
        assert with_one.accessibleName() == tr("shell.cover.of", title="Ksiazka")
        assert without.accessibleName() == tr("shell.cover.none")

    def test_c06_the_placeholder_has_the_same_geometry_as_a_cover(self, qt_app):
        """*„stabilny placeholder o tej samej geometrii"*: a list of books with
        covers and a list without them are the same shape, so nothing jumps
        when one arrives."""
        for mode in LayoutMode:
            with_one = Cover(item_with(picture()), tokens_module.DARK, mode)
            without = Cover(item_with(b""), tokens_module.DARK, mode)
            assert with_one.size() == without.size(), mode
            assert with_one.size().width() > 0 and with_one.size().height() > 0

    def test_c06_a_cover_of_any_proportion_is_contained_and_not_deformed(self, qt_app):
        """Two very different shapes, both inside the box, neither stretched."""
        box = Cover.SIZES[LayoutMode.MEDIUM]
        for size in ((600, 1200), (1200, 300), (500, 500)):
            widget = Cover(item_with(picture(size=size)), tokens_module.DARK)
            drawn = widget.pixmap().size()
            assert drawn.width() <= box[0] and drawn.height() <= box[1], size
            wanted = size[0] / size[1]
            got = drawn.width() / drawn.height()
            assert abs(wanted - got) < 0.06, (size, drawn.width(), drawn.height())

    def test_the_cover_is_the_stated_size_at_each_width(self, qt_app):
        """02-UI-DESIGN: 48×72 in the list, up to 56×84 in a large view, 40×60
        compact — and never zero, which is what "still visible" means."""
        assert Cover.SIZES[LayoutMode.MEDIUM] == (48, 72)
        assert Cover.SIZES[LayoutMode.WIDE] == (56, 84)
        assert Cover.SIZES[LayoutMode.COMPACT] == (40, 60)

    def test_a_compact_row_keeps_the_cover_instead_of_hiding_it(self, qt_app):
        """The generic icon used to be hidden when the row narrowed, which took
        the only picture of the book with it."""
        row = BookRow(item_with(picture()), tokens_module.DARK)
        # Shown, because Qt delivers a resize event to a widget nobody has
        # shown only when it finally is — and this row's whole answer is in
        # that event.
        row.show()
        row.resize(360, 90)
        qt_app.processEvents()
        assert not row.mark.isHidden()
        assert row.mark.size().width() == Cover.SIZES[LayoutMode.COMPACT][0]

        # And the other two sizes, from the same two thresholds.
        row.resize(700, 90)
        qt_app.processEvents()
        assert row.mark.size().width() == Cover.SIZES[LayoutMode.MEDIUM][0]
        row.resize(1100, 90)
        qt_app.processEvents()
        assert row.mark.size().width() == Cover.SIZES[LayoutMode.WIDE][0]
        row.close()

    def test_the_row_shows_the_same_picture_in_the_plan_and_in_the_results(self, qt_app):
        book = item_with(picture(colour=(30, 60, 210)))
        planned = BookRow(book, tokens_module.DARK)
        finished = BookRow(book, tokens_module.DARK, results=True)
        assert planned.mark.pixmap().toImage() == finished.mark.pixmap().toImage()

    def test_c05_a_row_never_asks_a_shared_place_for_its_picture(self, qt_app):
        """*„okładka kończy odczyt po usunięciu książki"*: a row draws from the
        item it was given, so an answer about a book that is no longer in the
        list has nowhere to land and nothing to overwrite."""
        one = item_with(picture(colour=(200, 30, 30)), title="Pierwsza")
        two = item_with(picture(colour=(30, 60, 210)), title="Druga")
        rows = [BookRow(one, tokens_module.DARK), BookRow(two, tokens_module.DARK)]
        drawn = rows[1].mark.pixmap().toImage()

        # The first book is dropped from the batch while its cover was in hand.
        rows[0].setParent(None)
        rows[0].deleteLater()
        qt_app.processEvents()

        assert rows[1].mark.pixmap().toImage() == drawn
        assert rows[1].book is two
