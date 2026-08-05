"""No positive accessibility claim without having looked.

Discovery metadata under EPUB Accessibility 1.1 is an assertion by the
publisher. A false one is worse than a missing one: a reader who depends on
`alternativeText` is told the book is usable, and finds out otherwise.

Two things were being asserted without evidence. A document whose only graphic
was an inline `<svg>` with no title, desc or ARIA label came out claiming
`alternativeText`, because the survey counted `<img>` elements and inline SVG
was not one. And `accessibilityHazard: none` was decided by looking at exactly
two sources of movement — video and script — so a CSS keyframe animation, an
animated GIF or an animating SVG all passed as motionless.

Both of those are the same mistake in two places: treating "I did not see a
problem" as "there is no problem".
"""

from __future__ import annotations

import re
import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .factory import CONTAINER, MODERN_NAV, png_bytes

SVG_WITHOUT_ALTERNATIVE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
    '<rect width="10" height="10" fill="red"/></svg>'
)
SVG_WITH_TITLE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
    "<title>Mapa wybrzeża</title><rect width=\"10\" height=\"10\" fill=\"red\"/></svg>"
)
SVG_DECORATIVE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" role="presentation">'
    '<rect width="10" height="10" fill="red"/></svg>'
)
SVG_ANIMATED = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><title>Kółko</title>'
    '<circle r="5"><animate attributeName="r" from="0" to="5" dur="1s"/></circle></svg>'
)

DOCUMENT = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
<head><meta charset="utf-8"/><title>R</title>{link}</head>
<body><h1>Rozdział</h1><p>Tekst.</p>{body}</body>
</html>"""


def build(tmp_path, *, body="", link="", stylesheet=None, extra=None, properties="") -> str:
    manifest = '    <item id="css" href="a.css" media-type="text/css"/>\n' if stylesheet else ""
    for name, media_type in (extra or {}).items():
        manifest += f'    <item id="{name.replace(".", "-")}" href="{name}" media-type="{media_type}"/>\n'
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Dostępność</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"{properties}/>
{manifest}  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""
    path = str(tmp_path / "a11y.epub")
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
        )
        archive.writestr("OEBPS/package.opf", opf)
        archive.writestr("OEBPS/nav.xhtml", MODERN_NAV)
        archive.writestr("OEBPS/chapter.xhtml", DOCUMENT.format(body=body, link=link))
        if stylesheet:
            archive.writestr("OEBPS/a.css", stylesheet)
        for name, _ in (extra or {}).items():
            archive.writestr(f"OEBPS/{name}", ANIMATED_GIF if name.endswith(".gif") else png_bytes())
    return path


#: Two frames, which is all the check looks for.
ANIMATED_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    b"\x21\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00"
    b"\x21\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00"
    b";"
)


def metadata_of(tmp_path, **kwargs) -> tuple[list[str], list[str]]:
    """(features, hazards) as written into the package document."""
    source = build(tmp_path, **kwargs)
    result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
    with zipfile.ZipFile(result.output_path) as archive:
        package = archive.read("EPUB/package.opf").decode()
    return (
        re.findall(r'property="schema:accessibilityFeature">([^<]*)<', package),
        re.findall(r'property="schema:accessibilityHazard">([^<]*)<', package),
    )


class TestAlternativeTextIsEarned:
    def test_an_undescribed_inline_svg_blocks_the_claim(self, tmp_path):
        features, _ = metadata_of(tmp_path, body=SVG_WITHOUT_ALTERNATIVE, properties=' properties="svg"')
        assert "alternativeText" not in features

    def test_a_titled_inline_svg_counts_as_described(self, tmp_path):
        features, _ = metadata_of(tmp_path, body=SVG_WITH_TITLE, properties=' properties="svg"')
        assert "alternativeText" in features

    def test_an_explicitly_decorative_svg_counts_as_described(self, tmp_path):
        """`role="presentation"` is a statement somebody made on purpose, which
        is exactly what distinguishes it from silence."""
        features, _ = metadata_of(tmp_path, body=SVG_DECORATIVE, properties=' properties="svg"')
        assert "alternativeText" in features

    def test_one_undescribed_graphic_among_several_is_enough_to_block_it(self, tmp_path):
        features, _ = metadata_of(
            tmp_path,
            body=SVG_WITH_TITLE + SVG_WITHOUT_ALTERNATIVE,
            properties=' properties="svg"',
        )
        assert "alternativeText" not in features

    def test_a_graphic_the_parser_never_saw_blocks_it_too(self, tmp_path):
        """The manifest says this document holds an SVG and the parser found
        none. That is a graphic in an unknown state, not an absent one."""
        features, _ = metadata_of(tmp_path, body="", properties=' properties="svg"')
        assert "alternativeText" not in features

    def test_a_book_with_no_graphics_at_all_is_unaffected(self, tmp_path):
        features, _ = metadata_of(tmp_path, body="<p>Sama proza.</p>")
        assert "alternativeText" not in features
        assert "readingOrder" in features


class TestHazardNoneRequiresLooking:
    @pytest.mark.parametrize(
        "kwargs, why",
        [
            ({"body": SVG_ANIMATED, "properties": ' properties="svg"'}, "SVG animation"),
            (
                {
                    "body": '<p class="x">rusza się</p>',
                    "link": '<link rel="stylesheet" href="a.css" type="text/css"/>',
                    "stylesheet": "@keyframes s { from {opacity:0} to {opacity:1} }\n.x { animation: s 2s infinite; }",
                },
                "CSS animation",
            ),
            (
                {
                    "body": '<p style="transition: opacity 2s">powoli</p>',
                },
                "inline transition",
            ),
            (
                {
                    "body": '<p><img src="moving.gif" alt="ruch"/></p>',
                    "extra": {"moving.gif": "image/gif"},
                },
                "animated GIF",
            ),
        ],
        ids=["svg-animate", "css-keyframes", "inline-transition", "animated-gif"],
    )
    def test_motion_makes_the_hazard_unknown(self, tmp_path, kwargs, why):
        _, hazards = metadata_of(tmp_path, **kwargs)
        assert hazards == ["unknown"], f"{why} was not noticed"

    def test_a_still_book_may_still_say_none(self, tmp_path):
        """The opposite failure would be just as bad: if everything is unknown,
        the metadata says nothing to anybody."""
        _, hazards = metadata_of(tmp_path, body="<p>Nic się nie rusza.</p>")
        assert hazards == ["none"]

    def test_a_still_svg_does_not_trip_it(self, tmp_path):
        _, hazards = metadata_of(tmp_path, body=SVG_WITH_TITLE, properties=' properties="svg"')
        assert hazards == ["none"]
