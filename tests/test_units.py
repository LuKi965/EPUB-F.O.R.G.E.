"""Unit coverage for the pieces the pipeline leans on hardest."""

from __future__ import annotations

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
            ("okładka.png", "okadka.png"),
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
