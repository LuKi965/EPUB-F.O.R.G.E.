"""Library inventory: what the books are made of.

The class of test that matters most here is the third one. The measurements are
easy to compute from raw markup and wrong in ways nobody notices, because a
number that is too high still looks like a number. Each case below is a defect
a bytes-level scanner inherits by construction, and the reason this module reads
through `read_epub` instead.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from epubforge.inventory import measure, summarise, to_json

from .factory import make_legacy_epub, make_modern_epub


@pytest.fixture
def legacy(tmp_path, legacy_epub):
    return measure(pathlib.Path(legacy_epub))


class TestStructure:
    def test_the_version_is_recorded(self, legacy):
        assert legacy.fields["version"].startswith("2")

    def test_counts_match_the_book(self, legacy):
        assert legacy.fields["documents"] == 2
        assert legacy.fields["images"] >= 2
        assert legacy.fields["stylesheets"] == 1

    def test_obfuscated_fonts_are_distinguished_from_drm(self, legacy):
        assert legacy.fields["obfuscated_fonts"] is True
        assert legacy.fields["drm"] is False

    def test_an_unreadable_file_records_the_reason_and_nothing_else(self, tmp_path):
        broken = tmp_path / "broken.epub"
        broken.write_bytes(b"not a zip")
        book = measure(broken)
        assert "error" in book.fields
        assert "version" not in book.fields


class TestPrivacy:
    """Counts and frequencies. Never a word of anybody's book."""

    def test_no_title_or_author_reaches_the_output(self, legacy):
        payload = to_json([legacy])
        assert "Kowalski" not in payload
        assert "Ksi" not in payload

    def test_no_body_text_reaches_the_output(self, tmp_path):
        source = make_modern_epub(
            str(tmp_path / "in.epub"), title="Bardzo Rozpoznawalny Tytul"
        )
        payload = to_json([measure(pathlib.Path(source))])
        assert "Rozpoznawalny" not in payload
        assert "Tekst rozdzia" not in payload

    def test_the_identifier_is_a_hash_of_the_file(self, tmp_path):
        import hashlib

        source = pathlib.Path(make_modern_epub(str(tmp_path / "in.epub")))
        expected = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        assert measure(source).identifier == expected

    def test_the_json_parses_and_carries_only_measurements(self, legacy):
        entry = json.loads(to_json([legacy]))[0]
        assert set(entry) >= {"id", "size_mb", "version", "blocks"}
        assert all(not isinstance(v, str) or len(v) < 200 for v in entry.values())


class TestMeasurementsAreNotFooledByMarkup:
    """Counts a raw-bytes scanner gets wrong, and gets wrong silently."""

    def build(self, tmp_path, body: str) -> pathlib.Path:
        import zipfile

        from .factory import CONTAINER, MODERN_NAV, MODERN_OPF, png_bytes

        document = (
            '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">'
            "<head><meta charset=\"utf-8\"/><title>T</title></head>"
            f"<body>{body}</body></html>"
        )
        path = tmp_path / "shaped.epub"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            archive.writestr(
                "META-INF/container.xml",
                CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
            )
            archive.writestr(
                "OEBPS/package.opf", MODERN_OPF.format(title="T", extra_metadata="")
            )
            archive.writestr("OEBPS/nav.xhtml", MODERN_NAV)
            archive.writestr("OEBPS/chapter.xhtml", document)
            archive.writestr("OEBPS/picture.png", png_bytes())
        return path

    def test_an_entity_counts_as_the_character_it_denotes(self, tmp_path):
        """`&nbsp;` is one non-breaking space, not six ordinary characters."""
        book = measure(self.build(tmp_path, "<p>w&#160;lesie i&#160;w&#160;polu</p>"))
        assert book.fields["non_breaking_spaces"] == 3

    def test_ordinary_source_wrapping_is_not_mistaken_for_damage(self, tmp_path):
        """Pretty-printers wrap at spaces, so they cannot manufacture the signal
        that would license de-hyphenation — the riskiest rule we have planned."""
        body = "<p>To jest tekst\n    zawijany w źródle\n    przez formatowanie</p>"
        assert measure(self.build(tmp_path, body)).fields["broken_hyphens"] == 0

    def test_a_hyphen_left_hanging_at_a_line_break_is_counted(self, tmp_path):
        """And it should be: whitespace collapses, so the reader sees the space.

        Whether it came from a PDF converter or from somebody's line wrapping,
        `biało- czerwony` is what ends up on the page, and it is wrong.
        """
        body = "<p>flaga biało-\n    czerwona wisiała</p>"
        assert measure(self.build(tmp_path, body)).fields["broken_hyphens"] == 1

    def test_a_hyphen_with_no_space_after_it_is_left_alone(self, tmp_path):
        """`biało-czerwony` is a compound, not damage. Counting it would put
        every Polish book on the list."""
        body = "<p>flaga biało-czerwona wisiała</p>"
        assert measure(self.build(tmp_path, body)).fields["broken_hyphens"] == 0


class TestTypographyCensus:
    def build(self, tmp_path, text: str):
        source = make_modern_epub(str(tmp_path / "t.epub"))
        return measure(pathlib.Path(source))

    def test_quote_forms_are_tallied(self, tmp_path, legacy):
        assert isinstance(legacy.fields["quotes"], dict)

    def test_dash_forms_are_always_present_even_at_zero(self, legacy):
        """A zero is an answer; a missing key is not, and breaks the summary."""
        assert set(legacy.fields["dashes"]) == {"hyphen", "en-dash", "em-dash"}


class TestProvenance:
    def test_a_calibre_trace_is_recognised(self, legacy):
        assert "calibre" in legacy.fields["generators"]

    def test_an_unmarked_book_claims_nothing(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "plain.epub"))
        assert measure(pathlib.Path(source)).fields["generators"] == []


class TestSummary:
    def test_it_survives_a_library_where_everything_failed(self, tmp_path):
        broken = tmp_path / "b.epub"
        broken.write_bytes(b"nope")
        assert "nothing could be read" in summarise([measure(broken)])

    def test_it_reports_shares_over_readable_books_only(self, tmp_path, legacy_epub):
        broken = tmp_path / "b.epub"
        broken.write_bytes(b"nope")
        text = summarise([measure(pathlib.Path(legacy_epub)), measure(broken)])
        assert "2 book(s), 1 readable" in text


def test_nothing_is_written_next_to_the_books(tmp_path):
    folder = tmp_path / "lib"
    folder.mkdir()
    make_legacy_epub(str(folder / "a.epub"))
    before = set(folder.iterdir())
    measure(folder / "a.epub")
    assert set(folder.iterdir()) == before
