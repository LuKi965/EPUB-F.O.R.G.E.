"""Real books and real documents for the pictures, written here on the spot.

The acceptance list asks for screenshots of the actual application and says in
as many words that a `DemoBackend` run is not evidence about the real adapter.
So `ui_screenshots.py` runs the production backends, and this module gives them
files that exist: EPUBs with covers, an EPUB without one, a book with enough
wrong with it to come out of a rebuild carrying remarks, a PDF with a text
layer and a PDF without one.

None of it is anybody's book. The covers are coloured rectangles this module
paints and the titles are generic (S-06); what a picture has to show is that
three *different* covers arrive, that a book with no cover still reads as a
book, and that a scan is refused rather than half-converted.

Two shelves, because "several locations" in the results card is one of the
things being photographed, and a batch written beside its sources lands in as
many folders as it came from.
"""

from __future__ import annotations

import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tests.factory import (CONTAINER, MODERN_CHAPTER,  # noqa: E402
                           MODERN_NAV, write_zip)
from tests.test_pdf import make_pdf  # noqa: E402

#: Long enough to need eliding, and Polish, because a title that fits in the
#: mock-up and not in the window is exactly what these pictures are for.
LONG_TITLE = (
    "Zazolc gesla jazn — wydanie drugie, poprawione i uzupelnione, "
    "z posłowiem oraz indeksem nazwisk"
)

EPUB3_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:{uuid}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="chapter.xhtml" media-type="application/xhtml+xml"/>
{cover_item}  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>
"""

COVER_ITEM = (
    '    <item id="cov" href="okladka.png" media-type="image/png" '
    'properties="cover-image"/>\n'
)


def picture(size=(300, 450), colour=(36, 74, 140)) -> bytes:
    """A cover of this module's own making, in whatever shape a shot needs."""
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, format="PNG")
    return out.getvalue()


def epub(path: pathlib.Path, *, title: str, uuid: str, cover: "bytes | None") -> str:
    """One valid EPUB 3, with a cover or deliberately without one."""
    entries = {
        "META-INF/container.xml":
            CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf").encode(),
        "OEBPS/package.opf": EPUB3_OPF.format(
            title=title, uuid=uuid, cover_item=COVER_ITEM if cover else ""
        ).encode(),
        "OEBPS/nav.xhtml": MODERN_NAV.encode(),
        "OEBPS/chapter.xhtml": MODERN_CHAPTER.format(image="").encode(),
    }
    if cover is not None:
        entries["OEBPS/okladka.png"] = cover
    return write_zip(str(path), entries)


def shelf(root: pathlib.Path, *, batch: int = 48) -> dict:
    """Write everything the eight pictures need and say where it all is.

    Three books with three covers that are visibly *different* — a portrait, a
    squarer one and a tall one, in three colours — because "three covers" and
    "the same cover three times" look identical when the cover is a glyph, and
    that was the defect. A fourth with no cover and a title that does not fit.

    All four are on two shelves, because "several locations" in the results
    card is one of the things being photographed and a batch written beside its
    sources lands in as many folders as it came from. None of them declares an
    author, so each comes out of a rebuild with one honest remark against it —
    which is what makes the results card say *Zapisano · 1 uwaga* rather than
    an unqualified "done", and that distinction is the point of the picture.

    Nothing here carries an unresolvable reference on purpose. A book that has
    one makes the window stop and ask, correctly — and a run with nobody at the
    keyboard would wait for that answer forever.
    """
    first, second = root / "polka-a", root / "polka-b"
    first.mkdir(parents=True, exist_ok=True)
    second.mkdir(parents=True, exist_ok=True)

    covered = [
        epub(first / "Powiesc przykladowa.epub", title="Powiesc przykladowa",
             uuid="11111111-1111-4111-8111-111111111111",
             cover=picture((300, 450), (36, 74, 140))),
        epub(first / "Zbior opowiadan.epub", title="Zbior opowiadan",
             uuid="22222222-2222-4222-8222-222222222222",
             cover=picture((360, 400), (140, 52, 40))),
        epub(second / "Poradnik techniczny.epub", title="Poradnik techniczny",
             uuid="33333333-3333-4333-8333-333333333333",
             cover=picture((260, 500), (32, 108, 74))),
    ]
    plain = [
        epub(second / "Ksiazka bez okladki.epub", title=LONG_TITLE,
             uuid="44444444-4444-4444-8444-444444444444", cover=None),
    ]

    #: The long batch of picture 8. Real files, so the row a person sees is
    #: the row the adapter made; small ones, so taking a screenshot of fifty
    #: books does not take a minute.
    many = root / "polka-c"
    many.mkdir(parents=True, exist_ok=True)
    crowd = [
        epub(many / f"Ksiazka {number:02d}.epub",
             title=LONG_TITLE if number % 7 == 3 else f"Ksiazka {number:02d}",
             uuid=f"55555555-5555-4555-8555-{number:012d}",
             cover=picture((300, 450), (36 + number % 90, 74, 140)) if number % 3 else None)
        for number in range(batch)
    ]

    return {
        "covered": covered,
        "plain": plain,
        "books": covered + plain,
        "crowd": crowd,
        "documents": documents(root),
    }


def documents(root: pathlib.Path) -> list:
    """One PDF the converter handles and one it must refuse.

    The second has no text layer at all — a page with a picture on it and
    nothing else — which is the shape the module is required to name as
    unsupported rather than convert into an empty book.
    """
    folder = root / "dokumenty"
    folder.mkdir(parents=True, exist_ok=True)

    text = make_pdf(
        folder / "Instrukcja urzadzenia.pdf",
        [
            [(72, 700, 18, "Instrukcja urzadzenia"),
             (72, 660, 11, "Rozdzial 1. Przygotowanie"),
             (72, 640, 11, "Ustaw urzadzenie na plaskiej powierzchni i podlacz"),
             (72, 624, 11, "przewod zasilajacy do gniazda."),
             (72, 590, 11, "Rozdzial 2. Pierwsze uruchomienie"),
             (72, 570, 11, "Wcisnij przycisk zasilania i odczekaj chwile.")],
            [(72, 700, 11, "Rozdzial 3. Czyszczenie"),
             (72, 680, 11, "Wylacz urzadzenie i odczekaj, az ostygnie.")],
        ],
        title="Instrukcja urzadzenia", language="pl",
        outline=[("Przygotowanie", 0), ("Czyszczenie", 1)],
    )
    scan = make_pdf(
        folder / "Skan bez tekstu.pdf",
        [[]],
        title="Skan bez tekstu",
        images={0: [(72, 400, 460, 320, 8, 6, bytes(range(8 * 6 * 3)))]},
    )
    return [str(text), str(scan)]
