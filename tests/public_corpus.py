"""A corpus everybody has, built rather than downloaded.

The private corpus is the strongest regression net this project has, and it runs
on exactly one machine in the world. Everywhere else `test_corpus.py` skips, so
a contributor changing the reader has nothing telling them what moved.

Real public-domain books would be the ideal second corpus and are not available
from this environment — the network policy does not reach Project Gutenberg.
What is available is the knowledge of *what real books do wrong*, which came out
of a 64-book survey and is written down here as eight generated books.

Three of them exist because the measured library contains **no** example of the
thing they carry: no right-to-left book, no Media Overlays, no fixed layout.
Those are precisely the areas where the model is thinnest, and until now nothing
in this repository exercised them at all.

Generation is byte-deterministic — fixed ZIP timestamps, no clock, no random —
so the signature of a generated book is the same on every machine. That is what
makes committing the signatures worth anything.
"""

from __future__ import annotations

import pathlib
import zipfile

#: Same epoch the writer uses. Without it the source hash changes every run and
#: the recorded signatures are worthless.
EPOCH = (1980, 1, 1, 0, 0, 0)

#: And the same host-system byte. `zipfile` stamps every entry with the platform
#: it ran on — 0 for Windows, 3 for everything else — so a corpus generated on
#: Windows hashed differently from the one generated here, every book came back
#: "new", and the regression proved nothing.
#:
#: This is exactly the defect fixed in `epubforge/writer.py` for the real output,
#: reproduced two days later in the fixture meant to guard against it. The public
#: corpus caught it on its first run in CI, which is what it was built for.
CREATE_SYSTEM = 3

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

#: 1×1 PNG. Small enough to be noise, real enough for Pillow to open.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


def _page(title: str, body: str, *, lang: str = "pl", head: str = "") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}">
<head><meta charset="utf-8"/><title>{title}</title>{head}</head>
<body>{body}</body>
</html>
"""


def _nav(entries: list[tuple[str, str]], *, lang: str = "pl") -> str:
    items = "".join(f'<li><a href="{href}">{label}</a></li>' for href, label in entries)
    return _page("Spis treści", f'<nav epub:type="toc"><ol>{items}</ol></nav>', lang=lang)


def _opf(*, metadata: str = "", manifest: str, spine: str, spine_attrs: str = "",
         version: str = "3.0", title: str = "Książka", lang: str = "pl",
         identifier: str = "urn:uuid:00000000-0000-4000-8000-000000000001") -> str:
    modified = (
        '    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>\n'
        if version == "3.0" else ""
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{version}" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="pub-id">{identifier}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>{lang}</dc:language>
    <dc:creator>Autor Testowy</dc:creator>
{modified}{metadata}  </metadata>
  <manifest>
{manifest}  </manifest>
  <spine{spine_attrs}>
{spine}  </spine>
</package>
"""


def _write(path: pathlib.Path, entries: dict[str, bytes | str]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        first = zipfile.ZipInfo("mimetype", date_time=EPOCH)
        first.compress_type = zipfile.ZIP_STORED
        first.create_system = CREATE_SYSTEM
        archive.writestr(first, b"application/epub+zip")
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, date_time=EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = CREATE_SYSTEM
            archive.writestr(info, data.encode("utf-8") if isinstance(data, str) else data)
    return path


# --------------------------------------------------------------- the books

def epub2_ncx_only(path: pathlib.Path) -> pathlib.Path:
    """The commonest thing on a Polish shelf: EPUB 2, NCX, `<guide>`, no nav.

    29 of the 64 surveyed books are this.
    """
    ncx = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:00000000-0000-4000-8000-000000000002"/></head>
  <docTitle><text>Stara książka</text></docTitle>
  <navMap>
    <navPoint id="n1" playOrder="1"><navLabel><text>Rozdział I</text></navLabel>
      <content src="text/r1.xhtml"/></navPoint>
    <navPoint id="n2" playOrder="2"><navLabel><text>Rozdział II</text></navLabel>
      <content src="text/r2.xhtml"/></navPoint>
  </navMap>
</ncx>
"""
    return _write(path, {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": _opf(
            version="2.0", title="Stara książka",
            identifier="urn:uuid:00000000-0000-4000-8000-000000000002",
            manifest=(
                '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
                '    <item id="r1" href="text/r1.xhtml" media-type="application/xhtml+xml"/>\n'
                '    <item id="r2" href="text/r2.xhtml" media-type="application/xhtml+xml"/>\n'
            ),
            spine='    <itemref idref="r1"/>\n    <itemref idref="r2"/>\n',
            spine_attrs=' toc="ncx"',
        ).replace("</package>", '  <guide>\n'
                  '    <reference type="text" title="Początek" href="text/r1.xhtml"/>\n'
                  '  </guide>\n</package>'),
        "OEBPS/toc.ncx": ncx,
        "OEBPS/text/r1.xhtml": _page("Rozdział I", "<h1>Rozdział I</h1><p>Pierwszy akapit.</p>"),
        "OEBPS/text/r2.xhtml": _page("Rozdział II", "<h1>Rozdział II</h1><p>Drugi akapit.</p>"),
    })


def nav_in_spine(path: pathlib.Path) -> pathlib.Path:
    """A visible table of contents — the page a reader turns to.

    Regenerating the nav used to delete it from the reading order.
    """
    return _write(path, {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": _opf(
            title="Ze spisem w treści",
            identifier="urn:uuid:00000000-0000-4000-8000-000000000003",
            manifest=(
                '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
                '    <item id="r1" href="text/r1.xhtml" media-type="application/xhtml+xml"/>\n'
            ),
            spine='    <itemref idref="nav" linear="yes"/>\n    <itemref idref="r1"/>\n',
        ),
        "OEBPS/nav.xhtml": _nav([("text/r1.xhtml", "Rozdział I")]),
        "OEBPS/text/r1.xhtml": _page("Rozdział I", "<h1>Rozdział I</h1><p>Tekst.</p>"),
    })


def right_to_left(path: pathlib.Path) -> pathlib.Path:
    """Manga: read from the right, fixed layout, spread properties.

    **Not one book in the measured 64 has any of this.** Reading direction was
    silently lost once already, in every mode including the one that promises to
    touch nothing, and nothing in this repository would have caught it again.
    """
    return _write(path, {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": _opf(
            title="漫画", lang="ja",
            identifier="urn:uuid:00000000-0000-4000-8000-000000000004",
            metadata=(
                '    <meta property="rendition:layout">pre-paginated</meta>\n'
                '    <meta property="rendition:orientation">portrait</meta>\n'
                '    <meta property="rendition:spread">landscape</meta>\n'
            ),
            manifest=(
                '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
                '    <item id="p1" href="text/p1.xhtml" media-type="application/xhtml+xml"/>\n'
                '    <item id="p2" href="text/p2.xhtml" media-type="application/xhtml+xml"/>\n'
                '    <item id="img" href="images/page.png" media-type="image/png"/>\n'
            ),
            spine=(
                '    <itemref idref="p1" properties="page-spread-right"/>\n'
                '    <itemref idref="p2" properties="page-spread-left"/>\n'
            ),
            spine_attrs=' page-progression-direction="rtl"',
        ),
        "OEBPS/nav.xhtml": _nav([("text/p1.xhtml", "第一頁")], lang="ja"),
        "OEBPS/text/p1.xhtml": _page("一", '<div><img src="../images/page.png" alt="頁"/></div>', lang="ja"),
        "OEBPS/text/p2.xhtml": _page("二", '<div><img src="../images/page.png" alt="頁"/></div>', lang="ja"),
        "OEBPS/images/page.png": PNG,
    })


def media_overlays(path: pathlib.Path) -> pathlib.Path:
    """A read-aloud book: SMIL, `media-overlay`, `media:duration`.

    **Also absent from the measured 64.** The audit found all three of these
    dropped without an error — a book that loses its narration synchronisation
    and still passes EPUBCheck.
    """
    smil = """<?xml version="1.0" encoding="utf-8"?>
<smil xmlns="http://www.w3.org/ns/SMIL" xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">
  <body>
    <seq id="s1" epub:textref="../text/r1.xhtml" epub:type="chapter">
      <par id="p1">
        <text src="../text/r1.xhtml#akapit"/>
        <audio src="../audio/r1.mp3" clipBegin="0s" clipEnd="3.5s"/>
      </par>
    </seq>
  </body>
</smil>
"""
    return _write(path, {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": _opf(
            title="Czytana na głos",
            identifier="urn:uuid:00000000-0000-4000-8000-000000000005",
            metadata=(
                '    <meta property="media:duration">0:00:03.500</meta>\n'
                '    <meta property="media:duration" refines="#smil">0:00:03.500</meta>\n'
                '    <meta property="media:active-class">-epub-media-overlay-active</meta>\n'
            ),
            manifest=(
                '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
                '    <item id="r1" href="text/r1.xhtml" media-type="application/xhtml+xml" media-overlay="smil"/>\n'
                '    <item id="smil" href="audio/r1.smil" media-type="application/smil+xml"/>\n'
                '    <item id="mp3" href="audio/r1.mp3" media-type="audio/mpeg"/>\n'
            ),
            spine='    <itemref idref="r1"/>\n',
        ),
        "OEBPS/nav.xhtml": _nav([("text/r1.xhtml", "Rozdział I")]),
        "OEBPS/text/r1.xhtml": _page("Rozdział I", '<h1>Rozdział I</h1><p id="akapit">Czytane.</p>'),
        "OEBPS/audio/r1.smil": smil,
        # Not real audio; nothing in the pipeline decodes it, and a real MP3
        # would be a megabyte of nothing.
        "OEBPS/audio/r1.mp3": b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 64,
    })


def srcset_gallery(path: pathlib.Path) -> pathlib.Path:
    """Every reference edge the orphan sweep could not see.

    `img@srcset`, `<picture><source>`, and an image reachable only from inside
    an SVG. All three were deleted while the markup pointing at them stayed.
    """
    svg = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'width="10" height="10"><title>Rycina</title>'
           '<image xlink:href="tekstura.png" width="10" height="10"/></svg>\n')
    body = (
        '<p><img src="images/a.png" srcset="images/a2x.png 2x" alt="Ilustracja"/></p>'
        '<picture><source srcset="images/c.png" type="image/png"/>'
        '<img src="images/a.png" alt="Druga"/></picture>'
        '<p><img src="images/rycina.svg" alt="Rycina"/></p>'
    )
    manifest = (
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
        '    <item id="r1" href="text/r1.xhtml" media-type="application/xhtml+xml"/>\n'
        '    <item id="svg" href="images/rycina.svg" media-type="image/svg+xml"/>\n'
        '    <item id="tex" href="images/tekstura.png" media-type="image/png"/>\n'
    ) + "".join(
        f'    <item id="i{n}" href="images/{n}.png" media-type="image/png"/>\n'
        for n in ("a", "a2x", "c")
    )
    entries = {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": _opf(
            title="Galeria",
            identifier="urn:uuid:00000000-0000-4000-8000-000000000006",
            manifest=manifest, spine='    <itemref idref="r1"/>\n',
        ),
        "OEBPS/nav.xhtml": _nav([("text/r1.xhtml", "Ilustracje")]),
        "OEBPS/text/r1.xhtml": _page("Ilustracje", f"<h1>Ilustracje</h1>{body}"),
        "OEBPS/images/rycina.svg": svg,
    }
    for name in ("a", "a2x", "c", "tekstura"):
        entries[f"OEBPS/images/{name}.png"] = PNG
    return _write(path, entries)


def legacy_markup(path: pathlib.Path) -> pathlib.Path:
    """Presentational markup from a 2004 HTML converter, plus a running-text
    rule that pushes a cover image sideways."""
    css = (
        "body { text-align: justify; }\n"
        "p { text-indent: 2%; text-align: justify; }\n"
        "p.ilustracja { text-align: right; }\n"
        "body.okladka { text-align: center; }\n"
    )
    body = (
        "<h1>Rozdział</h1>"
        '<center><p>Wyśrodkowane po staremu.</p></center>'
        '<p><font color="#884400" size="2" face="Times">Kolorowy tekst.</font></p>'
        '<table border="1" cellspacing="2" bgcolor="#eeeeee"><tr><td>Komórka</td></tr></table>'
        '<p><img src="../images/rysunek.png" alt="Rysunek"/></p>'
        '<p class="ilustracja"><img src="../images/rysunek.png" alt="Wybór wydawcy"/></p>'
    )
    link = '<link rel="stylesheet" href="../styles/main.css" type="text/css"/>'
    return _write(path, {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": _opf(
            title="Stary skład",
            identifier="urn:uuid:00000000-0000-4000-8000-000000000007",
            manifest=(
                '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
                '    <item id="ok" href="text/okladka.xhtml" media-type="application/xhtml+xml"/>\n'
                '    <item id="r1" href="text/r1.xhtml" media-type="application/xhtml+xml"/>\n'
                '    <item id="css" href="styles/main.css" media-type="text/css"/>\n'
                '    <item id="cov" href="images/okladka.png" media-type="image/png" properties="cover-image"/>\n'
                '    <item id="rys" href="images/rysunek.png" media-type="image/png"/>\n'
            ),
            spine='    <itemref idref="ok"/>\n    <itemref idref="r1"/>\n',
        ),
        "OEBPS/nav.xhtml": _nav([("text/r1.xhtml", "Rozdział")]),
        "OEBPS/styles/main.css": css,
        "OEBPS/text/okladka.xhtml": _page(
            "Okładka", '<div><img src="../images/okladka.png" alt=""/></div>', head=link
        ).replace("<body>", '<body class="okladka">'),
        "OEBPS/text/r1.xhtml": _page("Rozdział", body, head=link),
        "OEBPS/images/okladka.png": PNG,
        "OEBPS/images/rysunek.png": PNG,
    })


def watermarked(path: pathlib.Path) -> pathlib.Path:
    """Retailer social DRM as it actually ships: one token, every document, in a
    one-pixel div with `!important`. Present in 40 of the 64 surveyed books.

    The token is never removed. The point of the fixture is that it stays."""
    marker = '<div class="wm" style="font-size:1px !important;color:#FFF">NzgxMjI0NjMzOTUzMDk</div>'
    notice = (
        '<div style="margin:0 1cm;font-style:italic">Ten egzemplarz jest chroniony '
        "znakiem wodnym. Zamówienie ##46932.</div>"
    )
    pages = {f"OEBPS/text/r{n}.xhtml": _page(
        f"Rozdział {n}", f"<h1>Rozdział {n}</h1><p>Treść {n}.</p>{marker}"
    ) for n in (1, 2, 3)}
    return _write(path, {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": _opf(
            title="Ze znakiem wodnym",
            identifier="urn:uuid:00000000-0000-4000-8000-000000000008",
            manifest=(
                '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
                + "".join(
                    f'    <item id="r{n}" href="text/r{n}.xhtml" media-type="application/xhtml+xml"/>\n'
                    for n in (1, 2, 3)
                )
                + '    <item id="pr" href="text/prawne.xhtml" media-type="application/xhtml+xml"/>\n'
            ),
            spine="".join(f'    <itemref idref="r{n}"/>\n' for n in (1, 2, 3))
            + '    <itemref idref="pr"/>\n',
        ),
        "OEBPS/nav.xhtml": _nav([(f"text/r{n}.xhtml", f"Rozdział {n}") for n in (1, 2, 3)]),
        "OEBPS/text/prawne.xhtml": _page("Nota prawna", f"<h1>Nota prawna</h1>{notice}{marker}"),
        **pages,
    })


def declared_entities(path: pathlib.Path) -> pathlib.Path:
    """A document that declares its own entities in the DOCTYPE's internal
    subset — a DocBook and TeX habit, and three books in the survey.

    EPUB 3 replaces that DOCTYPE, so the declarations go; the references have to
    be resolved before they do, or the reader sees `&mypauza;` on the page.
    """
    document = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html [
  <!ENTITY mypauza "&#8212;">
  <!ENTITY wydawca "Wydawnictwo Przykładowe">
]>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
<head><meta charset="utf-8"/><title>Encje</title></head>
<body><h1>Encje</h1><p>Tekst &mypauza; z pauzą.</p><p>&wydawca;, Kraków.</p></body>
</html>
"""
    return _write(path, {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": _opf(
            title="Z własnymi encjami",
            identifier="urn:uuid:00000000-0000-4000-8000-000000000009",
            manifest=(
                '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
                '    <item id="r1" href="text/r1.xhtml" media-type="application/xhtml+xml"/>\n'
            ),
            spine='    <itemref idref="r1"/>\n',
        ),
        "OEBPS/nav.xhtml": _nav([("text/r1.xhtml", "Encje")]),
        "OEBPS/text/r1.xhtml": document,
    })


def collections_and_refinements(path: pathlib.Path) -> pathlib.Path:
    """Two collections, refinements, several creators with roles, alternate
    scripts. Everything the package document can carry and the model must not
    quietly narrow."""
    metadata = (
        '    <dc:identifier id="isbn">urn:isbn:9788324594567</dc:identifier>\n'
        '    <dc:publisher>Wydawnictwo Przykładowe</dc:publisher>\n'
        '    <dc:date>2019-03-01</dc:date>\n'
        '    <dc:contributor id="tlum">Marcin Tłumacz</dc:contributor>\n'
        '    <meta refines="#tlum" property="role" scheme="marc:relators">trl</meta>\n'
        '    <meta property="belongs-to-collection" id="ser">Kroniki</meta>\n'
        '    <meta refines="#ser" property="collection-type">series</meta>\n'
        '    <meta refines="#ser" property="group-position">7</meta>\n'
        '    <meta property="belongs-to-collection" id="box">Dzieła zebrane</meta>\n'
        '    <meta refines="#box" property="collection-type">set</meta>\n'
        '    <meta refines="#box" property="group-position">1</meta>\n'
    )
    return _write(path, {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": _opf(
            title="Siódma kronika",
            identifier="urn:uuid:00000000-0000-4000-8000-00000000000a",
            metadata=metadata,
            manifest=(
                '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
                '    <item id="r1" href="text/r1.xhtml" media-type="application/xhtml+xml"/>\n'
            ),
            spine='    <itemref idref="r1"/>\n',
        ),
        "OEBPS/nav.xhtml": _nav([("text/r1.xhtml", "Rozdział")]),
        "OEBPS/text/r1.xhtml": _page("Rozdział", "<h1>Rozdział</h1><p>Treść.</p>"),
    })


#: Name → builder. The name becomes the filename, so it is part of the corpus's
#: identity and should not be changed casually.
# ------------------------------------------------------- the edges

# The roadmap's tenth family: "brak okładki, jeden plik 8 MB, 400 pozycji
# spine". Unlike every other family these are not files anyone owns — a
# publisher does not ship a book with four hundred chapters and no cover — so
# they are built rather than collected. Each stresses exactly one thing and is
# otherwise ordinary, because a file broken in six ways tells you nothing when
# it fails.
#
# `tools/make_edge_cases.py` writes them into a real corpus folder; the three
# cheap ones are also registered below so they are exercised on every run.

def _item(identifier: str, href: str, media_type: str, properties: str = "") -> str:
    extra = f' properties="{properties}"' if properties else ""
    return f'    <item id="{identifier}" href="{href}" media-type="{media_type}"{extra}/>\n'


def no_cover(path: pathlib.Path) -> pathlib.Path:
    """A book with no cover image and nothing claiming to be one.

    Every reader shows *something* in a library list, so the question is what
    this program does when there is nothing to show it — and whether it invents
    a cover, which would be adding to somebody's book.
    """
    pages = {f"text/ch{i}.xhtml": _page(f"Rozdział {i}", f"<h1>Rozdział {i}</h1><p>Treść.</p>")
             for i in range(1, 4)}
    manifest = "".join(_item(f"ch{i}", f"text/ch{i}.xhtml", "application/xhtml+xml")
                       for i in range(1, 4))
    manifest += _item("nav", "nav.xhtml", "application/xhtml+xml", "nav")
    spine = "".join(f'    <itemref idref="ch{i}"/>\n' for i in range(1, 4))
    return _write(path, {
        "META-INF/container.xml": _CONTAINER,
        "EPUB/package.opf": _opf(manifest=manifest, spine=spine, title="Bez okładki"),
        "EPUB/nav.xhtml": _nav([(f"text/ch{i}.xhtml", f"Rozdział {i}") for i in range(1, 4)]),
        **{f"EPUB/{name}": body for name, body in pages.items()},
    })


def one_huge_image(path: pathlib.Path, megabytes: int = 9) -> pathlib.Path:
    """A single image larger than most whole books.

    The model holds every resource as bytes, so this is the shape that turns a
    comfortable rebuild into an uncomfortable one. Nine megabytes is over the
    eight the roadmap names and small enough to keep in a repository nobody
    wants to clone twice.
    """
    # Incompressible: a PNG of noise, so the archive is as large as the file.
    import os

    from .factory import png_bytes

    payload = png_bytes() + os.urandom(megabytes * 1024 * 1024)
    manifest = (
        _item("plate", "images/plate.png", "image/png", "cover-image")
        + _item("ch1", "text/ch1.xhtml", "application/xhtml+xml")
        + _item("nav", "nav.xhtml", "application/xhtml+xml", "nav")
    )
    return _write(path, {
        "META-INF/container.xml": _CONTAINER,
        "EPUB/package.opf": _opf(
            manifest=manifest,
            spine='    <itemref idref="ch1"/>\n',
            title="Jedna wielka plansza",
        ),
        "EPUB/nav.xhtml": _nav([("text/ch1.xhtml", "Plansza")]),
        "EPUB/text/ch1.xhtml": _page(
            "Plansza", '<p><img src="../images/plate.png" alt="Plansza"/></p>'
        ),
        "EPUB/images/plate.png": payload,
    })


def four_hundred_documents(path: pathlib.Path, count: int = 400) -> pathlib.Path:
    """Four hundred spine items, which is where per-document work stops being free.

    Anything the rebuild does once per document — parsing, cascade resolution,
    rewriting every href — is multiplied here, and a cost that hides at thirty
    documents does not hide at four hundred.
    """
    entries: dict[str, bytes | str] = {}
    manifest = ""
    spine = ""
    toc: list[tuple[str, str]] = []
    for index in range(1, count + 1):
        name = f"text/s{index:04d}.xhtml"
        entries[f"EPUB/{name}"] = _page(
            f"Sekcja {index}",
            f"<h1>Sekcja {index}</h1><p>Krótki akapit numer {index}.</p>",
        )
        manifest += _item(f"s{index:04d}", name, "application/xhtml+xml")
        spine += f'    <itemref idref="s{index:04d}"/>\n'
        if index <= 40:  # A table of contents nobody would write in full.
            toc.append((name, f"Sekcja {index}"))
    manifest += _item("nav", "nav.xhtml", "application/xhtml+xml", "nav")
    entries["META-INF/container.xml"] = _CONTAINER
    entries["EPUB/package.opf"] = _opf(
        manifest=manifest, spine=spine, title="Czterysta sekcji"
    )
    entries["EPUB/nav.xhtml"] = _nav(toc)
    return _write(path, entries)


def single_document(path: pathlib.Path, paragraphs: int = 4000) -> pathlib.Path:
    """The opposite edge: one document holding the whole book.

    A back-conversion or a scan-to-EPUB often produces this, and it is the case
    where nothing can be split, skipped or streamed — the whole text is one
    parse.
    """
    body = "<h1>Całość</h1>" + "".join(
        f"<p>Akapit numer {i}, wypełniający tekst o umiarkowanej długości.</p>"
        for i in range(1, paragraphs + 1)
    )
    manifest = (
        _item("all", "text/all.xhtml", "application/xhtml+xml")
        + _item("nav", "nav.xhtml", "application/xhtml+xml", "nav")
    )
    return _write(path, {
        "META-INF/container.xml": _CONTAINER,
        "EPUB/package.opf": _opf(
            manifest=manifest, spine='    <itemref idref="all"/>\n', title="Jeden plik"
        ),
        "EPUB/nav.xhtml": _nav([("text/all.xhtml", "Całość")]),
        "EPUB/text/all.xhtml": _page("Całość", body),
    })


_CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


BOOKS = {
    "epub2-ncx-only": epub2_ncx_only,
    "nav-in-spine": nav_in_spine,
    "right-to-left": right_to_left,
    "media-overlays": media_overlays,
    "srcset-gallery": srcset_gallery,
    "legacy-markup": legacy_markup,
    "watermarked": watermarked,
    "declared-entities": declared_entities,
    "collections-and-refinements": collections_and_refinements,
    # The huge-image book is deliberately absent: it is about memory, not
    # correctness, and nine megabytes of noise per test run is a poor trade.
    "edge-no-cover": no_cover,
    "edge-400-sections": four_hundred_documents,
    "edge-single-document": single_document,
}


def build_all(folder: pathlib.Path) -> list[pathlib.Path]:
    """Write every book into *folder* and return the paths, sorted."""
    folder.mkdir(parents=True, exist_ok=True)
    return sorted(build(folder / f"{name}.epub") for name, build in BOOKS.items())


if __name__ == "__main__":  # pragma: no cover - a convenience for looking at them
    import sys

    target = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "public-corpus")
    for book in build_all(target):
        print(book)
