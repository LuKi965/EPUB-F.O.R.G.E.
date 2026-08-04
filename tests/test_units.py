"""Unit coverage for the pieces the pipeline leans on hardest."""

from __future__ import annotations

import pathlib

import pytest

from epubforge import paths, xhtml
from epubforge.stages.fonts import (
    ADOBE_PREFIX_LENGTH,
    IDPF_PREFIX_LENGTH,
    adobe_key,
    deobfuscate,
    idpf_key,
    sniff_font_type,
)
from epubforge.stages.metadata import normalize_date

from .factory import fake_ttf


class TestPaths:
    @pytest.mark.parametrize(
        "base,href,expected",
        [
            ("OEBPS/Text/ch1.xhtml", "../Images/a.png", "OEBPS/Images/a.png"),
            ("OEBPS/Text/ch1.xhtml", "ch2.xhtml#frag", "OEBPS/Text/ch2.xhtml"),
            ("OEBPS/content.opf", "Text/ch1.xhtml", "OEBPS/Text/ch1.xhtml"),
            ("OEBPS/Text/ch1.xhtml", "../Images/ok%C5%82adka.png", "OEBPS/Images/okładka.png"),
        ],
    )
    def test_resolve(self, base, href, expected):
        assert paths.resolve(base, href) == expected

    @pytest.mark.parametrize("href", ["http://x.test/a.png", "mailto:a@b.test", "#frag", ""])
    def test_resolve_skips_non_local(self, href):
        assert paths.resolve("OEBPS/a.xhtml", href) is None

    def test_relative_round_trips(self):
        href = paths.relative("EPUB/text/ch1.xhtml", "EPUB/images/a.png")
        assert href == "../images/a.png"
        assert paths.resolve("EPUB/text/ch1.xhtml", href) == "EPUB/images/a.png"

    def test_relative_percent_encodes_spaces(self):
        assert paths.relative("EPUB/text/a.xhtml", "EPUB/text/b c.xhtml") == "b%20c.xhtml"

    @pytest.mark.parametrize(
        "name,expected",
        [
            # NFKD strips the accent but keeps the base letter...
            ("Ćwiczenia.XHTML", "Cwiczenia.xhtml"),
            ("chapter 1.html", "chapter-1.html"),
            # ...while ł has no decomposition, so it is simply dropped.
            # `ł` has no canonical decomposition, so NFKD alone dropped it.
            ("okładka.png", "okladka.png"),
            ("Żółć.xhtml", "Zolc.xhtml"),
            ("Straße.txt", "Strasse.txt"),
            ("søster.png", "soster.png"),
            # A name that transliterates to nothing still needs to be addressable.
            ("日本語.png", "images.png"),
        ],
    )
    def test_ascii_slug(self, name, expected):
        assert paths.ascii_slug(name, fallback="images") == expected

    def test_unique_disambiguates(self):
        taken = {"a.png", "a-2.png"}
        assert paths.unique("a.png", taken) == "a-3.png"

    def test_resolve_cannot_escape_the_container(self):
        assert not paths.resolve("a.xhtml", "../../../etc/passwd").startswith("..")


class TestFontObfuscation:
    IDENTIFIER = "urn:uuid:8f2c1b44-9c1e-4f0a-9c2b-3f6b1a7d5e21"

    def test_idpf_round_trip(self):
        original = fake_ttf()
        key = idpf_key(self.IDENTIFIER)
        obfuscated = deobfuscate(original, key, IDPF_PREFIX_LENGTH)
        assert obfuscated != original
        assert deobfuscate(obfuscated, key, IDPF_PREFIX_LENGTH) == original

    def test_adobe_round_trip(self):
        original = fake_ttf()
        key = adobe_key(self.IDENTIFIER)
        assert key is not None and len(key) == 16
        obfuscated = deobfuscate(original, key, ADOBE_PREFIX_LENGTH)
        assert deobfuscate(obfuscated, key, ADOBE_PREFIX_LENGTH) == original

    def test_idpf_key_ignores_whitespace(self):
        assert idpf_key(" urn:uuid:x\n") == idpf_key("urn:uuid:x")

    def test_adobe_key_needs_a_uuid(self):
        assert adobe_key("978-83-1234-567-8") is None

    def test_only_the_prefix_is_touched(self):
        data = fake_ttf(4096)
        scrambled = deobfuscate(data, idpf_key(self.IDENTIFIER), IDPF_PREFIX_LENGTH)
        assert scrambled[IDPF_PREFIX_LENGTH:] == data[IDPF_PREFIX_LENGTH:]

    @pytest.mark.parametrize(
        "signature,expected",
        [(b"\x00\x01\x00\x00", "font/ttf"), (b"OTTO", "font/otf"), (b"wOFF", "font/woff")],
    )
    def test_signature_sniffing(self, signature, expected):
        assert sniff_font_type(signature + b"rest") == expected


class TestDateNormalisation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("12/03/2011", "2011-03-12"),
            ("2011-03-12", "2011-03-12"),
            ("2011-03-12T10:00:00Z", "2011-03-12"),
            ("1998", "1998"),
            ("opublikowano w 1998 roku", "1998"),
            ("nonsense", None),
        ],
    )
    def test_normalize(self, raw, expected):
        assert normalize_date(raw) == expected


class TestXhtmlRecovery:
    def test_unclosed_tags_recover(self):
        root, mode = xhtml.parse(b"<html><body><p>a<p>b</body></html>")
        assert mode == "html"
        assert len(root.find(xhtml.qname("body"))) == 2

    def test_undefined_entities_recover_without_html_fallback(self):
        root, mode = xhtml.parse(
            b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>a&nbsp;b&mdash;c</p></body></html>'
        )
        assert mode == "xml-entities"
        assert " " in "".join(root.itertext())

    def test_serialisation_is_reparsable_xhtml(self):
        root, _ = xhtml.parse(b"<html><body><p>x<br></body></html>")
        output = xhtml.serialize(root)
        from lxml import etree

        reparsed = etree.fromstring(output)
        assert reparsed.tag == f"{{{xhtml.XHTML_NS}}}html"
        assert b"<html:" not in output

    def test_empty_block_elements_do_not_self_close(self):
        root, _ = xhtml.parse(b"<html><body><div></div></body></html>")
        assert b"<div></div>" in xhtml.serialize(root)

    def test_internal_dtd_entities_do_not_break_parsing(self):
        source = (
            b'<?xml version="1.0"?>\n'
            b'<!DOCTYPE html [<!ENTITY custom "value">]>\n'
            b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>a&nbsp;b</p></body></html>'
        )
        root, _ = xhtml.parse(source)
        assert root.tag == f"{{{xhtml.XHTML_NS}}}html"


class TestArchiveLimits:
    """A book is held entirely in memory, so the reader must bound what it reads."""

    def _archive(self, path, entries):
        import zipfile

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as handle:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            handle.writestr(info, b"application/epub+zip")
            for name, data in entries.items():
                handle.writestr(name, data)
        return str(path)

    def test_a_highly_compressible_bomb_is_refused(self, tmp_path):
        from epubforge.reader import _read_archive
        from epubforge.report import Report

        source = self._archive(
            tmp_path / "bomb.epub",
            {"META-INF/container.xml": b"<x/>", "OEBPS/bomb.bin": b"\0" * (4 * 1024 * 1024)},
        )
        report = Report(source=source)
        raw = _read_archive(source, report)
        assert "OEBPS/bomb.bin" not in raw.entries
        assert any("implausibly large" in f.message for f in report.findings)

    def test_ordinary_content_is_not_refused(self, tmp_path):
        """The limits must be invisible to every real book."""
        import os

        from epubforge.reader import _read_archive
        from epubforge.report import Report

        # Incompressible, so the ratio guard cannot fire.
        source = self._archive(
            tmp_path / "normal.epub",
            {"META-INF/container.xml": b"<x/>", "OEBPS/photo.jpg": os.urandom(2 * 1024 * 1024)},
        )
        report = Report(source=source)
        raw = _read_archive(source, report)
        assert "OEBPS/photo.jpg" in raw.entries
        assert not [f for f in report.findings if "implausibly large" in f.message]

    def test_small_files_are_never_judged_by_ratio(self, tmp_path):
        """A page of repeated whitespace compresses enormously and harmlessly."""
        from epubforge.reader import _read_archive
        from epubforge.report import Report

        source = self._archive(
            tmp_path / "spaces.epub",
            {"META-INF/container.xml": b"<x/>", "OEBPS/ch.xhtml": b" " * 20000},
        )
        report = Report(source=source)
        assert "OEBPS/ch.xhtml" in _read_archive(source, report).entries

    def _lying_archive(self, tmp_path, payload: bytes):
        """An archive whose header understates how much an entry expands to.

        The size fields are what the author of the file chose to write there,
        so a limit that reads them is a limit an attacker sets.
        """
        import struct
        import zipfile

        path = str(tmp_path / "lying.epub")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as handle:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            handle.writestr(info, b"application/epub+zip")
            handle.writestr("META-INF/container.xml", b"<x/>")
            handle.writestr("OEBPS/bomb.bin", payload)

        raw = bytearray(pathlib.Path(path).read_bytes())
        # Both the local and the central header carry the size; patch each.
        truth = struct.pack("<I", len(payload))
        lie = struct.pack("<I", 1000)
        at = 0
        while (at := raw.find(truth, at)) >= 0:
            raw[at : at + 4] = lie
            at += 4
        pathlib.Path(path).write_bytes(bytes(raw))
        return path

    def test_a_lying_header_does_not_get_the_entry_through(self, tmp_path):
        from epubforge.reader import _read_archive
        from epubforge.report import Report

        source = self._lying_archive(tmp_path, b"\0" * (4 * 1024 * 1024))
        report = Report(source=source)
        raw = _read_archive(source, report)
        assert "OEBPS/bomb.bin" not in raw.entries

    def test_the_limit_is_measured_while_reading_not_asked_of_the_header(self, tmp_path):
        """The header check is a cheap first pass; the stream is the real one."""
        import zipfile

        from epubforge.reader import MAX_ENTRY_BYTES, _read_bounded

        path = str(tmp_path / "big.epub")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as handle:
            handle.writestr("big.bin", b"\0" * (2 * 1024 * 1024))
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("big.bin")
            assert _read_bounded(archive, info, MAX_ENTRY_BYTES) is not None
            # Same entry, same honest header, budget below its real size.
            assert _read_bounded(archive, info, 1024) is None
