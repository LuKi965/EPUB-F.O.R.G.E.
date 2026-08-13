"""The audit findings my own plan left out.

The plan written after the audit covered seventeen of its thirty findings. The
owner noticed: *the audit is 41 pages — if you have not read all of it, read it,
and police yourself.* I had read all of it. What I had not done was **write all
of it down**, and a plan that silently covers half the ground is worse than no
plan, because it answers "what is left?" with a number that is wrong.

So the plan now holds all thirty, and these are the ones that turned out to be
real once somebody looked. Four of five reproduced. The fifth — F-022, output
not being reproducible — did not reproduce on the fixture I built, and the
reason is recorded rather than the failure being claimed as a pass: my fixture
had both an identifier and a pinned `dcterms:modified`, which is precisely the
case the finding is *not* about.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import zipfile

import pytest

from epubforge.model import guess_media_type
from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy
from epubforge.xhtml import mend_encoding

CONTAINER = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    b'<rootfiles><rootfile full-path="OEBPS/package.opf" '
    b'media-type="application/oebps-package+xml"/></rootfiles></container>'
)


def opf(manifest: str, spine: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="pid">urn:uuid:00000000-0000-4000-8000-000000000000</dc:identifier>
<dc:title>T</dc:title><dc:language>pl</dc:language>
<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>
<manifest>{manifest}</manifest><spine>{spine}</spine></package>""".encode()


def page(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">'
        "<head><meta charset=\"utf-8\"/><title>t</title></head>"
        f"<body>{body}</body></html>"
    ).encode()


NAV = page('<nav epub:type="toc"><ol><li><a href="chapter.xhtml">c</a></li></ol></nav>')
NAV_ITEM = '<item id="n" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
CHAPTER_ITEM = '<item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/>'


def build(path, entries: dict) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/epub+zip")
        for name, data in entries.items():
            archive.writestr(name, data)
    return str(path)


def read(path: str, ending: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(ending))
        return archive.read(name)


class TestF021AStrayByteIsNotACharacterLost:
    """**Measured on 0.2.21:** a chapter declaring `encoding="utf-8"` and
    carrying one `0x92` — an apostrophe in the Windows-1250 an older Polish shop
    wrote — came out with `U+FFFD` in the text and **no finding of any kind**.
    The output was valid UTF-8 for ever after.

    K1 says no character of the book's text is lost. This was the one path that
    lost one and called it a repair.
    """

    def test_the_character_survives(self):
        raw = (
            b'<?xml version="1.0" encoding="utf-8"?><html><body><p>g'
            + b"\x92"
            + " jaźń</p></body></html>".encode()
        )
        mended, how = mend_encoding(raw)
        assert "�" not in mended.decode("utf-8")
        assert "’" in mended.decode("utf-8")
        assert "cp1250" in how

    def test_the_polish_letters_beside_it_are_not_reinterpreted(self):
        """The first version of the fix asked only whether *some* legacy
        encoding decodes the whole file and round-trips. For a UTF-8 document
        with one stray byte, cp1250 answers yes — and `jaźń` came back as
        `jaĹşĹ„`. One replacement character had become a document of mojibake,
        a worse outcome from a better intention."""
        raw = (
            b'<?xml version="1.0" encoding="utf-8"?><html><body><p>'
            + "zażółć gęślą".encode()
            + b"\x92"
            + b"</p></body></html>"
        )
        assert "zażółć gęślą" in mend_encoding(raw)[0].decode("utf-8")

    def test_a_document_that_really_is_legacy_is_believed_whole(self):
        raw = (
            '<?xml version="1.0" encoding="windows-1250"?>'
            "<html><body><p>zażółć gęślą jaźń</p></body></html>"
        ).encode("cp1250")
        mended, how = mend_encoding(raw)
        assert how == "windows-1250"
        assert "zażółć gęślą jaźń" in mended.decode("utf-8")
        assert b'encoding="utf-8"' in mended, "the declaration has to follow the bytes"

    def test_an_honest_document_is_not_touched(self):
        raw = '<?xml version="1.0" encoding="utf-8"?><html><body><p>zażółć</p></body></html>'.encode()
        assert mend_encoding(raw) == (raw, "")

    def test_the_rebuild_says_it_happened(self, tmp_path):
        """A silent repair is only a little better than a silent loss: both
        leave a person unable to tell what the file they have is."""
        damaged = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><title>t</title></head>'
            b"<body><p>g" + b"\x92" + b"</p></body></html>"
        )
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(CHAPTER_ITEM + NAV_ITEM, '<itemref idref="c"/>'),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/chapter.xhtml": damaged,
        })
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "�" not in read(result.output_path, "chapter.xhtml").decode("utf-8")
        assert "xhtml.encoding-mended" in {f.rule for f in result.report.findings if f.rule}


class TestF015AMissingSpineIsNotAnAlphabet:
    """**Measured on 0.2.21:** a manifest listing `rozdzial-2`, `rozdzial-10`,
    `przedmowa` and no spine came back as `przedmowa`, `rozdzial-10`,
    `rozdzial-2` — a book that reads chapter ten before chapter two."""

    @pytest.fixture
    def rebuilt(self, tmp_path):
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(
                '<item id="b" href="rozdzial-2.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="a" href="rozdzial-10.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="p" href="przedmowa.xhtml" media-type="application/xhtml+xml"/>'
                + NAV_ITEM, ""),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/rozdzial-2.xhtml": page("<p>DRUGI</p>"),
            "OEBPS/rozdzial-10.xhtml": page("<p>DZIESIATY</p>"),
            "OEBPS/przedmowa.xhtml": page("<p>PRZEDMOWA</p>"),
        })
        return rebuild(source, str(tmp_path / "out.epub"), Policy.preset("minimal"))

    def test_the_manifest_order_is_followed(self, rebuilt):
        """Not normative and not random: every tool that writes a manifest
        writes it in the order it thinks about the book."""
        order = [item.path.rsplit("/", 1)[-1] for item in rebuilt.book.spine]
        assert order[:3] == ["rozdzial-2.xhtml", "rozdzial-10.xhtml", "przedmowa.xhtml"]

    def test_it_is_reported_rather_than_done_quietly(self, rebuilt):
        assert "reader.spine-rebuilt" in {f.rule for f in rebuilt.report.findings if f.rule}

    def test_the_contents_page_outranks_the_manifest(self, tmp_path):
        """A table of contents is the publisher stating the order in their own
        words. Nothing this program works out beats it."""
        contents = page(
            '<nav epub:type="toc"><ol>'
            '<li><a href="przedmowa.xhtml">Przedmowa</a></li>'
            '<li><a href="rozdzial-2.xhtml">II</a></li>'
            "</ol></nav>"
        )
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(
                '<item id="b" href="rozdzial-2.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="p" href="przedmowa.xhtml" media-type="application/xhtml+xml"/>'
                + NAV_ITEM, ""),
            "OEBPS/nav.xhtml": contents,
            "OEBPS/rozdzial-2.xhtml": page("<p>DRUGI</p>"),
            "OEBPS/przedmowa.xhtml": page("<p>PRZEDMOWA</p>"),
        })
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("minimal"))
        order = [item.path.rsplit("/", 1)[-1] for item in result.book.spine]
        assert order.index("przedmowa.xhtml") < order.index("rozdzial-2.xhtml")

    def test_ten_follows_two_when_only_names_are_left(self):
        from epubforge.reader import _natural

        assert sorted(["r-10.xhtml", "r-2.xhtml", "r-1.xhtml"], key=_natural) == [
            "r-1.xhtml", "r-2.xhtml", "r-10.xhtml",
        ]


class TestF024AFilenameIsNotEvidence:
    """**Measured on 0.2.21:** a stylesheet correctly declared `text/css` and
    named `styl.xhtml` came out as `application/xhtml+xml` — a file the pipeline
    then tries to parse as a document, on the strength of the part of its name
    somebody typed by mistake."""

    def test_a_plausible_declaration_beats_the_extension(self):
        assert guess_media_type("styl.xhtml", "text/css") == "text/css"

    @pytest.mark.parametrize("declared", ["text/html", "application/octet-stream", ""])
    def test_the_declarations_generators_write_without_looking_do_not(self, declared):
        """`text/html` for XHTML is what Calibre and Sigil write; octet-stream
        is what a tool writes when it has not looked."""
        assert guess_media_type("chapter.xhtml", declared) == "application/xhtml+xml"

    def test_with_no_declaration_the_extension_is_all_there_is(self):
        assert guess_media_type("cover.jpg") == "image/jpeg"

    def test_an_unknown_extension_keeps_what_the_book_said(self):
        assert guess_media_type("dane.qqq", "application/x-vendor") == "application/x-vendor"

    def test_end_to_end(self, tmp_path):
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(
                CHAPTER_ITEM + NAV_ITEM
                + '<item id="s" href="styl.xhtml" media-type="text/css"/>',
                '<itemref idref="c"/>'),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/chapter.xhtml": page("<p>x</p>"),
            "OEBPS/styl.xhtml": b"p { color: red; }",
        })
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        package = read(result.output_path, ".opf").decode()
        assert 'media-type="text/css"' in package


class TestF026OneBadDestinationIsNotTheEndOfABatch:
    """**Measured on 0.2.21:** a destination whose parent is a file raised
    `NotADirectoryError` straight out of `rebuild`. In a batch that is not one
    failed book — it is the ninth of a thousand taking the other 991 with it,
    and none of them appear in the report either."""

    @pytest.fixture
    def blocked(self, tmp_path):
        (tmp_path / "plik").write_bytes(b"x")
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(CHAPTER_ITEM + NAV_ITEM, '<itemref idref="c"/>'),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/chapter.xhtml": page("<p>x</p>"),
        })
        return rebuild(source, str(tmp_path / "plik" / "pod" / "out.epub"),
                       Policy.preset("preserve"))

    def test_it_is_a_result_and_not_an_exception(self, blocked):
        assert blocked.status is Status.FAILED
        assert blocked.output_path is None

    def test_the_report_says_what_the_filesystem_said(self, blocked):
        finding = next(f for f in blocked.report.findings if f.rule == "package.not-written")
        assert "NotADirectoryError" in finding.values["error"]

    def test_the_next_book_still_runs(self, tmp_path):
        """The whole point. One bad destination, then an ordinary one."""
        (tmp_path / "plik").write_bytes(b"x")
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(CHAPTER_ITEM + NAV_ITEM, '<itemref idref="c"/>'),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/chapter.xhtml": page("<p>x</p>"),
        })
        rebuild(source, str(tmp_path / "plik" / "pod" / "a.epub"), Policy.preset("preserve"))
        second = rebuild(source, str(tmp_path / "b.epub"), Policy.preset("preserve"))
        assert second.status is Status.SUCCEEDED


class TestF022WhatDidNotReproduce:
    """Recorded because a finding that did not reproduce is a result too, and
    because the reason matters more than the outcome.

    The audit says the output is not reproducible: a missing identifier gets a
    random UUID and `dcterms:modified` gets the wall clock. My reproduction
    built a fixture with **both** an identifier and a pinned `modified` — which
    is exactly the case the finding is not about — and of course came back
    identical. The mechanism is real and is in the code; what is missing is a
    reproducible *mode* rather than a mechanism, and it stays open in the plan
    under F-022 rather than being claimed here.
    """

    def test_a_book_that_says_who_it_is_rebuilds_identically(self, tmp_path):
        source = build(tmp_path / "in.epub", {
            "META-INF/container.xml": CONTAINER,
            "OEBPS/package.opf": opf(CHAPTER_ITEM + NAV_ITEM, '<itemref idref="c"/>'),
            "OEBPS/nav.xhtml": NAV,
            "OEBPS/chapter.xhtml": page("<p>x</p>"),
        })
        digests = []
        for run in range(2):
            result = rebuild(source, str(tmp_path / f"out-{run}.epub"), Policy.preset("preserve"))
            digests.append(hashlib.sha256(pathlib.Path(result.output_path).read_bytes()).hexdigest())
        assert digests[0] == digests[1]

    def test_the_mechanism_the_finding_names_is_still_there(self):
        """`modified_override` exists; a mode that sets it for a whole batch
        does not. Pinned so the open half is not mistaken for the closed one."""
        source = pathlib.Path("epubforge/stages/metadata.py").read_text(encoding="utf-8")
        assert re.search(r"uuid4|urn:uuid:", source), "the random identifier path"
        assert "modified_override" in pathlib.Path("epubforge/policy.py").read_text(encoding="utf-8")
