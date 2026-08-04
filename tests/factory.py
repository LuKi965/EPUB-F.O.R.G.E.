"""Builders for deliberately broken EPUB files, modelled on real-world damage."""

from __future__ import annotations

import io
import zipfile

from PIL import Image


def png_bytes(size=(60, 90), color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def webp_bytes(size=(40, 40), color=(10, 120, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="WEBP")
    return buffer.getvalue()


def write_zip(path: str, entries: dict[str, bytes], *, mimetype: bool = True) -> str:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        if mimetype:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


LEGACY_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>Zim&#x0142;a Ksi&#x0105;&#x017c;ka</dc:title>
    <dc:creator opf:role="aut" opf:file-as="Kowalski, Jan">Jan Kowalski</dc:creator>
    <dc:identifier id="BookId">urn:uuid:8f2c1b44-9c1e-4f0a-9c2b-3f6b1a7d5e21</dc:identifier>
    <dc:language>PL_pl</dc:language>
    <dc:date opf:event="publication">12/03/2011</dc:date>
    <meta name="cover" content="cover-img"/>
    <meta name="calibre:series" content="Kroniki"/>
    <meta name="calibre:series_index" content="2"/>
  </metadata>
  <manifest>
    <item id="cover-img" href="Images/ok%C5%82adka.png" media-type="image/png"/>
    <item id="deco" href="Images/deco.webp" media-type="image/webp"/>
    <item id="ch1" href="Text/chapter 1.html" media-type="application/xhtml+xml"/>
    <item id="ch2" href="Text/chapter2.xhtml" media-type="text/html"/>
    <item id="style" href="Styles/main.css" media-type="text/css"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
    <itemref idref="missing-id"/>
  </spine>
  <guide>
    <reference type="cover" title="Ok&#x0142;adka" href="Text/chapter 1.html"/>
  </guide>
</package>
"""

# Unclosed <p>, undefined &nbsp;, <font>, <center>, table attributes, id starting
# with a digit, and an <a name> anchor — all common converter output.
CHAPTER_ONE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<link rel="stylesheet" type="text/css" href="../Styles/main.css"/>
</head>
<body>
<center><h1 id="1st-heading">Rozdzia&#322; pierwszy</h1></center>
<p>Tekst z&nbsp;niez&#322;aman&#261; spacj&#261; i <font color="#884400" size="5">kolorem</font>.
<p align="justify">Drugi akapit bez zamkni&#281;cia.
<a name="kotwica">kotwica</a>
<img src="../Images/ok%C5%82adka.png"/>
<img src="../Images/deco.webp" align="left"/>
<table border="1" cellspacing="3" width="100%" bgcolor="#eeeeee">
<tr><td valign="top" nowrap="nowrap">kom&#243;rka</td></tr>
</table>
<a href="chapter2.xhtml#1st-heading">dalej</a>
<a href="brakujacy.xhtml">martwy link</a>
</body>
</html>
"""

CHAPTER_TWO = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title></title><link rel="stylesheet" type="text/css" href="../Styles/main.css"/></head>
<body>
<h1 id="1st-heading">Rozdzia&#322; drugi</h1>
<p>Koniec &mdash; naprawd&#281;.</p>
<tt>monospace</tt><big>wi&#281;kszy</big>
<p><img src="../Images/ok%C5%82adka.png" alt="tytu&#322;"/></p>
<p style="text-align: left"><img src="../Images/deco.webp" alt="ozdoba"/></p>
<p class="ilustracja"><img src="../Images/deco.webp" alt="wybor wydawcy"/></p>
<p><img src="../Images/deco.webp" alt="procent" width="10%"/></p>
<h1 id="naglowek"><a href="chapter2.xhtml"><span class="numer">III</span><br/>Tytu&#322;</a></h1>
<p><a href="https://example.test/strona">link zewn&#281;trzny</a></p>
<p style="font-size:0.9em">Drobny druk wydawcy, kt&#243;ry ma pozosta&#263; widoczny.</p>
<div style="font-size:1px !important;color:#FFF">NzgxMjI0NjMzOTUzNjQ</div>
<div style="margin:0 1cm;font-style:italic">This document is protected using an electronic watermark. Order ##46932 (jan@example.test)</div>
</body>
</html>
"""

STYLESHEET = """@charset "utf-8";
body { font-family: "Moja Czcionka", serif; margin: 1em; }
h1 {
  color: #884400;
  font-family: "Judson";
  adobe-hyphenate: none;
  -epub-hyphenate: auto;
}
.deco { background-image: url('../Images/deco.webp'); }
/* Publisher mistakes seen in shipped books: out-of-flow content in a
   reflowable title page, and a font-style value that does not exist. */
div.dol { position: absolute; bottom: 0; width: 100%; }
p.dedykacja { text-align: center; font-style: regular; }
/* Running-text defaults, as almost every publisher writes them. These reach an
   image-only paragraph by accident. */
p { text-align: justify; text-indent: 2%; }
/* A rule aimed at illustrations: a decision about those paragraphs, which the
   rebuild must not override even though it is not centred. */
p.ilustracja { text-align: right; }
/* A block box declared on a span that sits inside an inline <a>. */
.numer { display: block; font-size: 0.6em; }
@media amzn-kf8 { body { font-size: 1.1em; } }
@font-face { font-family: "Moja Czcionka"; src: url("../Fonts/moja.ttf"); }
"""

NCX = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:8f2c1b44-9c1e-4f0a-9c2b-3f6b1a7d5e21"/></head>
  <docTitle><text>Zim&#x0142;a Ksi&#x0105;&#x017c;ka</text></docTitle>
  <navMap>
    <navPoint id="np1" playOrder="1">
      <navLabel><text>Rozdzia&#x0142; pierwszy</text></navLabel>
      <content src="Text/chapter%201.html"/>
    </navPoint>
    <navPoint id="np2" playOrder="2">
      <navLabel><text>Rozdzia&#x0142; drugi</text></navLabel>
      <content src="Text/chapter2.xhtml"/>
      <navPoint id="np3" playOrder="3">
        <navLabel><text>Zako&#x0144;czenie</text></navLabel>
        <content src="Text/chapter2.xhtml#1st-heading"/>
      </navPoint>
    </navPoint>
    <navPoint id="np4" playOrder="4">
      <navLabel><text>Usuni&#x0119;ty</text></navLabel>
      <content src="Text/nieistnieje.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
"""

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""


def make_legacy_epub(path: str, *, font: bytes | None = None, encryption: str | None = None) -> str:
    """A representative EPUB 2 with the damage this tool exists to repair."""
    entries = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/content.opf": LEGACY_OPF.encode(),
        "OEBPS/Text/chapter 1.html": CHAPTER_ONE.encode(),
        "OEBPS/Text/chapter2.xhtml": CHAPTER_TWO.encode(),
        "OEBPS/Styles/main.css": STYLESHEET.encode(),
        "OEBPS/Images/okładka.png": png_bytes(),
        "OEBPS/Images/deco.webp": webp_bytes(),
        "OEBPS/toc.ncx": NCX.encode(),
        # Neither is referenced by anything.
        "OEBPS/Images/nieuzywany.png": png_bytes(color=(0, 255, 0)),
        "OEBPS/.DS_Store": b"\x00junk",
    }
    if font is not None:
        entries["OEBPS/Fonts/moja.ttf"] = font
    if encryption is not None:
        entries["META-INF/encryption.xml"] = encryption.encode()
    return write_zip(path, entries)


ENCRYPTION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
            xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="{algorithm}"/>
    <enc:CipherData><enc:CipherReference URI="OEBPS/Fonts/moja.ttf"/></enc:CipherData>
  </enc:EncryptedData>
</encryption>
"""


def fake_ttf(size: int = 2048) -> bytes:
    """Enough of a TrueType header for signature sniffing to accept it."""
    return b"\x00\x01\x00\x00" + bytes(range(256)) * ((size - 4) // 256 + 1)


MODERN_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
{extra_metadata}
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="picture.png" media-type="image/png"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>
"""

MODERN_NAV = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><meta charset="utf-8"/><title>Spis</title></head>
  <body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">Rozdzia&#x142;</a></li></ol></nav></body>
</html>
"""

MODERN_CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>Rozdzia&#x142;</title></head>
  <body>
    <h1>Rozdzia&#x142;</h1>
    <p>Tekst rozdzia&#x142;u.</p>
    <p>{image}</p>
  </body>
</html>
"""


def make_modern_epub(path: str, *, image: str = '<img src="picture.png" alt=""/>',
                     extra_metadata: str = "", title: str = "Nowa Ksi&#x105;&#x17c;ka") -> str:
    """A small, already-valid EPUB 3, for testing one thing at a time.

    ``make_legacy_epub`` carries every defect at once, which is what makes it
    useful for end-to-end checks and useless for isolating a single behaviour.
    """
    return write_zip(
        path,
        {
            "META-INF/container.xml": CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf").encode(),
            "OEBPS/package.opf": MODERN_OPF.format(
                title=title, extra_metadata=extra_metadata
            ).encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": MODERN_CHAPTER.format(image=image).encode(),
            "OEBPS/picture.png": png_bytes(),
        },
    )
