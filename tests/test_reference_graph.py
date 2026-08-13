"""F-003 — moving a file must take its references with it, or not move it.

The audit's reproduction, and the half of it that matters more. A standalone
`diagram.svg` referring to `../assets/pic.png` was moved to `images/` along with
the picture and came out still saying `../assets/pic.png`, which now resolves to
nothing: an `<image>` that does not load, inside a file EPUBCheck has no reason
to open. Confirmed on 0.2.19, and confirmed again here before the fix.

Adding SVG to the rewriter closes the type somebody thought of. The rule
underneath closes the ones nobody has: **a relayout may proceed only where every
reference in a moved file can be followed**, and a file whose references cannot
be followed is not moved. That costs a tidy directory listing and keeps a book
that works.
"""

from __future__ import annotations

import posixpath
import re
import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .factory import png_bytes, write_zip

CONTAINER = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    b'<rootfiles><rootfile full-path="OEBPS/package.opf" '
    b'media-type="application/oebps-package+xml"/></rootfiles></container>'
)


def opf(manifest: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="pid">urn:uuid:00000000-0000-4000-8000-000000000000</dc:identifier>
<dc:title>T</dc:title><dc:language>pl</dc:language>
<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
</metadata>
<manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/>
<item id="n" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{manifest}</manifest>
<spine><itemref idref="c"/></spine></package>""".encode()


def page(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">'
        "<head><meta charset=\"utf-8\"/><title>t</title></head>"
        f"<body>{body}</body></html>"
    ).encode()


NAV = page('<nav epub:type="toc"><ol><li><a href="chapter.xhtml">c</a></li></ol></nav>')


def book(path, extra_manifest: str, entries: dict, body: str) -> str:
    return write_zip(str(path), {
        "META-INF/container.xml": CONTAINER,
        "OEBPS/package.opf": opf(extra_manifest),
        "OEBPS/nav.xhtml": NAV,
        "OEBPS/chapter.xhtml": page(body),
        **entries,
    })


def entries_of(path: str) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def read(path: str, ending: str) -> str:
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(ending))
        return archive.read(name).decode("utf-8", "replace")


def dangling(path: str) -> list[str]:
    """Every relative reference in the output that resolves to nothing.

    The assertion the whole file is about, computed rather than guessed: for each
    file that can be read as text, resolve what it points at against its own
    location and check the archive actually holds it.
    """
    names = set(entries_of(path))
    broken: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in names:
            if not name.endswith((".svg", ".xhtml", ".css", ".smil", ".opf", ".ncx")):
                continue
            text = archive.read(name).decode("utf-8", "replace")
            found = re.findall(r'(?:href|src|xlink:href)="([^"#]+)', text)
            found += re.findall(r"url\(['\"]?([^'\")]+)", text)
            for href in found:
                if href.startswith(("http:", "https:", "data:", "mailto:", "#")):
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), href))
                if target not in names:
                    broken.append(f"{name} → {href}")
    return broken


class TestAStandaloneSvgFollowsThePictureItPointsAt:
    """The audit's own reproduction, to the character."""

    @pytest.fixture(params=["preserve", "strict"])
    def rebuilt(self, request, tmp_path):
        svg = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10">'
            '<image xlink:href="../assets/pic.png" href="../assets/pic.png" '
            'width="10" height="10"/></svg>'
        ).encode()
        source = book(
            tmp_path / "in.epub",
            '<item id="s" href="figures/diagram.svg" media-type="image/svg+xml"/>'
            '<item id="p" href="assets/pic.png" media-type="image/png"/>',
            {"OEBPS/figures/diagram.svg": svg, "OEBPS/assets/pic.png": png_bytes()},
            '<p><img src="figures/diagram.svg" alt="d"/></p>',
        )
        return rebuild(source, str(tmp_path / f"out-{request.param}.epub"),
                       Policy.preset(request.param))

    def test_nothing_in_the_output_points_at_a_file_that_is_not_there(self, rebuilt):
        assert dangling(rebuilt.output_path) == []

    def test_the_svg_says_where_the_picture_actually_is(self, rebuilt):
        svg = read(rebuilt.output_path, "diagram.svg")
        assert "../assets/pic.png" not in svg
        assert "pic.png" in svg

    def test_both_spellings_of_the_attribute_are_followed(self, rebuilt):
        """A file old enough to be in an EPUB 2 book uses `xlink:href`, a new one
        uses `href`, and a converter writes both on the same element."""
        svg = read(rebuilt.output_path, "diagram.svg")
        assert svg.count("pic.png") == 2

    def test_a_url_inside_the_svgs_own_stylesheet_is_followed(self, tmp_path):
        svg = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            "<style>rect { fill: url('../assets/pic.png'); }</style>"
            '<rect width="10" height="10"/></svg>'
        ).encode()
        source = book(
            tmp_path / "in.epub",
            '<item id="s" href="figures/diagram.svg" media-type="image/svg+xml"/>'
            '<item id="p" href="assets/pic.png" media-type="image/png"/>',
            {"OEBPS/figures/diagram.svg": svg, "OEBPS/assets/pic.png": png_bytes()},
            '<p><img src="figures/diagram.svg" alt="d"/></p>',
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert dangling(result.output_path) == []


class TestAFileThisCannotRepointIsNotMoved:
    """The rule under the rewriter, and the reason it is the important half.

    Adding a media type to the rewriter fixes the type somebody thought of. This
    fixes the ones nobody has — a script naming a JSON beside it, a WebVTT naming
    an image, a vendor XML naming anything. All were moved to a typed folder and
    all kept saying where they used to be.
    """

    @pytest.fixture
    def rebuilt(self, tmp_path):
        script = b'fetch("../data/quiz.json").then(r => r.json());'
        source = book(
            tmp_path / "in.epub",
            '<item id="j" href="scripts/quiz.js" media-type="text/javascript"/>'
            '<item id="d" href="data/quiz.json" media-type="application/json"/>',
            {"OEBPS/scripts/quiz.js": script, "OEBPS/data/quiz.json": b'{"a": 1}'},
            "<p>x</p>",
        )
        return rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))

    def test_the_file_stays_where_the_publisher_put_it(self, rebuilt):
        assert any(n.endswith("scripts/quiz.js") for n in entries_of(rebuilt.output_path))

    def test_what_it_points_at_is_still_reachable_from_where_it_sits(self, rebuilt):
        script = read(rebuilt.output_path, "quiz.js")
        name = next(n for n in entries_of(rebuilt.output_path) if n.endswith("quiz.js"))
        href = re.search(r'fetch\("([^"]+)"', script).group(1)
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), href))
        assert target in entries_of(rebuilt.output_path)

    def test_the_report_says_so_rather_than_staying_quiet(self, rebuilt):
        finding = next(
            f for f in rebuilt.report.findings
            if f.rule == "structure.reference-bearing-kept"
        )
        assert "quiz.json" in finding.values["names"]

    def test_a_file_that_links_to_nothing_is_relaid_out_as_before(self, tmp_path):
        """The rule must cost nothing where it buys nothing: an ordinary picture
        holds no link and moves exactly as it did."""
        source = book(
            tmp_path / "in.epub",
            '<item id="p" href="assets/pic.png" media-type="image/png"/>',
            {"OEBPS/assets/pic.png": png_bytes()},
            '<p><img src="assets/pic.png" alt="p"/></p>',
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert any(n.endswith("images/pic.png") for n in entries_of(result.output_path))


class TestMediaOverlaysStillWork:
    """The case this mechanism was built for, kept honest while it was widened."""

    def test_a_smil_file_still_follows_what_it_narrates(self, tmp_path):
        smil = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0">'
            "<body><par><text src=\"../chapter.xhtml#p1\"/>"
            '<audio src="../Audio/one.mp3"/></par></body></smil>'
        ).encode()
        source = book(
            tmp_path / "in.epub",
            '<item id="m" href="Misc/one.smil" media-type="application/smil+xml"/>'
            '<item id="a" href="Audio/one.mp3" media-type="audio/mpeg"/>',
            {"OEBPS/Misc/one.smil": smil, "OEBPS/Audio/one.mp3": b"ID3fake"},
            '<p id="p1">x</p>',
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert dangling(result.output_path) == []
