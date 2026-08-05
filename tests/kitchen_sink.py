"""A package document carrying one of everything EPUB 3.3 §5 allows.

Not a book anyone would ship. Its only purpose is to be fed to
`test_package_completeness.py`, which compares the constructs going in against
the constructs coming out and reports whatever fell off the way.

Every construct here is real and legal. Where the specification allows an
attribute in several places, it appears in each of them, because the defect this
exists to catch was exactly of that shape: `page-progression-direction` survived
nowhere while `rendition:layout` survived everywhere, and the difference was
that one is an attribute and the other is a `<meta>`.
"""

from __future__ import annotations

import zipfile

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

PACKAGE = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
         unique-identifier="pub-id" xml:lang="pl" dir="ltr"
         prefix="foaf: http://xmlns.com/foaf/spec/">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:5f0a1c22-7788-4b0e-9a11-2c3d4e5f6071</dc:identifier>
    <meta refines="#pub-id" property="identifier-type" scheme="onix:codelist5">06</meta>
    <dc:identifier id="isbn">urn:isbn:9788324594567</dc:identifier>

    <dc:title id="main-title" xml:lang="ja" dir="ltr">吾輩は猫である</dc:title>
    <meta refines="#main-title" property="title-type">main</meta>
    <meta refines="#main-title" property="file-as">Wagahai wa neko de aru</meta>
    <meta refines="#main-title" property="alternate-script" xml:lang="en">I Am a Cat</meta>
    <meta refines="#main-title" property="display-seq">1</meta>
    <dc:title id="sub-title">powieść</dc:title>
    <meta refines="#sub-title" property="title-type">subtitle</meta>
    <meta refines="#sub-title" property="display-seq">2</meta>

    <dc:creator id="author" xml:lang="ja">夏目漱石</dc:creator>
    <meta refines="#author" property="role" scheme="marc:relators">aut</meta>
    <meta refines="#author" property="file-as">Natsume, Soseki</meta>
    <meta refines="#author" property="alternate-script" xml:lang="en">Natsume Soseki</meta>
    <dc:contributor id="translator">Mikołaj Melanowicz</dc:contributor>
    <meta refines="#translator" property="role" scheme="marc:relators">trl</meta>

    <dc:language>pl</dc:language>
    <dc:language>ja</dc:language>
    <dc:publisher>Wydawnictwo Testowe</dc:publisher>
    <dc:date>2011-03-12</dc:date>
    <dc:description>Opis książki.</dc:description>
    <dc:subject>Literatura japońska</dc:subject>
    <dc:subject>Powieść</dc:subject>
    <dc:rights>Wszelkie prawa zastrzeżone.</dc:rights>
    <dc:source>urn:isbn:9784101010014</dc:source>
    <dc:type>monograph</dc:type>
    <dc:coverage>Japonia</dc:coverage>
    <dc:relation>urn:isbn:9788324500000</dc:relation>
    <dc:format>application/epub+zip</dc:format>

    <meta property="belongs-to-collection" id="box">Dzieła zebrane</meta>
    <meta refines="#box" property="collection-type">set</meta>
    <meta refines="#box" property="group-position">1</meta>
    <meta property="belongs-to-collection" id="series">Klasyka</meta>
    <meta refines="#series" property="collection-type">series</meta>
    <meta refines="#series" property="group-position">7</meta>

    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
    <meta property="rendition:layout">reflowable</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">auto</meta>
    <meta property="rendition:flow">paginated</meta>

    <meta property="schema:accessMode">textual</meta>
    <meta property="schema:accessibilityFeature">tableOfContents</meta>

    <meta name="cover" content="cover-image"/>
    <meta name="calibre:timestamp" content="2011-03-12T00:00:00+00:00"/>

    <!-- The total must be the sum of the per-overlay durations; EPUBCheck
         warns when it is not, and a fixture that is itself wrong teaches the
         wrong lesson. One overlay, so the two are equal. -->
    <meta property="media:duration">0:16:14</meta>
    <meta refines="#ch1-overlay" property="media:duration">0:16:14</meta>
    <meta property="media:active-class">-epub-media-overlay-active</meta>

    <link rel="record" href="https://example.invalid/onix.xml" media-type="application/xml"/>
  </metadata>

  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="cover-image" href="cover.png" media-type="image/png" properties="cover-image"/>
    <item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml" media-overlay="ch1-overlay"/>
    <item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml" properties="scripted"/>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="font" href="font.ttf" media-type="font/ttf"/>
    <item id="ch1-overlay" href="ch1.smil" media-type="application/smil+xml"/>
    <item id="narration" href="ch1.mp3" media-type="audio/mpeg"/>
    <item id="trailer" href="https://example.invalid/trailer.mp4" media-type="video/mp4"/>
    <item id="odd" href="odd.xyz" media-type="application/octet-stream" fallback="ch2"/>
  </manifest>

  <spine toc="ncx" page-progression-direction="rtl">
    <itemref idref="cover-page" linear="no" properties="page-spread-center"/>
    <itemref idref="ch1"/>
    <itemref idref="ch2" properties="rendition:layout-pre-paginated"/>
  </spine>

  <guide>
    <reference type="cover" title="Okładka" href="cover.xhtml"/>
    <reference type="text" title="Początek" href="ch1.xhtml"/>
  </guide>

  <!-- Roles from a private vocabulary, which EPUB 3 allows as an absolute URI.
       The registered ones each carry rules of their own — `manifest` has to be
       nested, `index` requires an <index> element in the document it names —
       and a fixture that breaks those teaches EPUBCheck's rules rather than
       this program's. Two of them, because losing one of two is the defect. -->
  <collection role="https://example.invalid/roles#notatki">
    <link href="ch1.xhtml"/>
    <link href="style.css"/>
  </collection>
  <!-- A collection holds links *or* collections, never both; nesting is the
       only way to have one of each, and nesting is worth a fixture. -->
  <collection role="https://example.invalid/roles#dodatki">
    <collection role="https://example.invalid/roles#zagniezdzona">
      <link href="ch2.xhtml"/>
      <link href="cover.xhtml"/>
    </collection>
  </collection>
</package>
"""

#: A Media Overlay: the thing that makes a book with narration a book with
#: narration. The rebuild currently drops the attribute, the file and the
#: duration together, and says nothing (EF-004).
SMIL = """<?xml version="1.0" encoding="utf-8"?>
<smil xmlns="http://www.w3.org/ns/SMIL" xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">
  <body>
    <seq id="s1" epub:textref="ch1.xhtml" epub:type="chapter">
      <par id="p1">
        <text src="ch1.xhtml#p1"/>
        <audio src="ch1.mp3" clipBegin="0s" clipEnd="12.5s"/>
      </par>
    </seq>
  </body>
</smil>
"""

NAV = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><meta charset="utf-8"/><title>Spis</title></head>
  <body>
    <nav epub:type="toc"><ol>
      <li><a href="ch1.xhtml">Rozdział I</a></li>
      <li><a href="ch2.xhtml">Rozdział II</a></li>
    </ol></nav>
    <nav epub:type="landmarks" hidden="hidden"><ol>
      <li><a epub:type="cover" href="cover.xhtml">Okładka</a></li>
      <li><a epub:type="bodymatter" href="ch1.xhtml">Początek</a></li>
    </ol></nav>
    <nav epub:type="page-list" hidden="hidden"><ol>
      <li><a href="ch1.xhtml#p1">1</a></li>
    </ol></nav>
  </body>
</html>
"""

NCX = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:5f0a1c22-7788-4b0e-9a11-2c3d4e5f6071"/></head>
  <docTitle><text>吾輩は猫である</text></docTitle>
  <navMap>
    <navPoint id="n1" playOrder="1">
      <navLabel><text>Rozdział I</text></navLabel><content src="ch1.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
"""

DOCUMENT = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>{title}</title>
    <meta name="viewport" content="width=1200, height=1600"/>
    <link rel="stylesheet" type="text/css" href="style.css"/></head>
  <body><h1 id="p1">{title}</h1><p>{body}</p></body>
</html>
"""

COVER_PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>Okładka</title></head>
  <body><p><img src="cover.png" alt="Okładka książki"/></p></body>
</html>
"""


def make_kitchen_sink(path: str) -> str:
    """Write the fixture and return its path."""
    from .factory import png_bytes

    entries = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/package.opf": PACKAGE.encode(),
        "OEBPS/nav.xhtml": NAV.encode(),
        "OEBPS/toc.ncx": NCX.encode(),
        "OEBPS/cover.xhtml": COVER_PAGE.encode(),
        "OEBPS/ch1.xhtml": DOCUMENT.format(title="Rozdział I", body="Tekst pierwszy.").encode(),
        "OEBPS/ch2.xhtml": DOCUMENT.format(title="Rozdział II", body="Tekst drugi.").encode(),
        "OEBPS/style.css": b"p { text-indent: 1.2em; }\n",
        "OEBPS/cover.png": png_bytes(),
        "OEBPS/font.ttf": b"\x00\x01\x00\x00" + b"\x00" * 2048,
        "OEBPS/ch1.smil": SMIL.encode(),
        # Not real audio. Nothing here decodes it; what matters is that the
        # manifest declares it and that it is still declared afterwards.
        "OEBPS/ch1.mp3": b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 512,
        "OEBPS/odd.xyz": b"a resource of a type this tool has never heard of",
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/epub+zip")
        for name, data in entries.items():
            archive.writestr(name, data)
    return path
