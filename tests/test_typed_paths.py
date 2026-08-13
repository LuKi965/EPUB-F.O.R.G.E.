"""F-002 — a ZIP entry name is a name; an href is a URL.

The audit put it in one line: *the ZIP entry name, the OCF path, the URL, the
href and the fragment are all one `str` today*, and `ocf.canonical()`
percent-decodes the entry name, **which changes the identity of the file**.

Reproduced before the fix, and it was worse than the example given:

    entry a%23b.xhtml  ->  path a#b.xhtml     two different files, one path
    entry a%2Fb.xhtml  ->  path a/b.xhtml     a file moved into a directory

Both sides were decoding — `paths.resolve` decodes an href, correctly, because
an href *is* a URL — so the two wrongs cancelled for the ordinary book and
collided for the rest. The measurable consequence: a correctly encoded href to a
file genuinely named `a%23b.xhtml` is `a%2523b.xhtml`, which resolved to
`a%23b.xhtml`, which the reader had already folded to `a#b.xhtml`. A reference
this program broke by itself.

**What was done, and what was not.** The decoding is gone from the entry-name
side, and the matrix below is the completion criterion the plan names. What is
*not* done is the type-level separation — `NewType` for each kind of string,
carried through every call site — and that stays open under F-029, because it
is a refactor of the whole program rather than a defect. The behaviour is what a
book can be damaged by, and the behaviour is what is asserted here.

**The books this could have abandoned.** Archives whose entry names really are
percent-encoded exist — two well-known tools write them — and a Mac stores `ł`
decomposed while the document spells it composed. Neither is now resolved by
*decoding on principle*: the reference is looked up under the other spellings
and one is accepted only because the archive holds a file under it. The archive
settles which file was meant; this program does not decide that two names are
the same file.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import ocf, paths
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.reader import read_epub
from epubforge.report import Report
from tests.factory import MODERN_NAV, png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>R</title></head>
  <body><p>{body}</p></body>
</html>
"""

PACKAGE = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Test</dc:title><dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="{href}" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>
"""


def book(path, *, entry: str, href: str, body: str = "Tekst rozdziału.") -> str:
    """One chapter, stored under *entry*, referenced from the manifest as *href*."""
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": PACKAGE.format(href=href).encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            f"OEBPS/{entry}": PAGE.format(body=body).encode(),
            "OEBPS/picture.png": png_bytes(),
        },
    )


def read(path: str):
    return read_epub(path, Report(source=path))


def rules_of(report) -> set[str]:
    return {f.rule for f in report.findings if f.rule}


class TestF002TheEntryNameIsNotAUrl:
    """The matrix the plan names: `%23`, `%2F`, `#`, `?`, NFC/NFD."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("OEBPS/a%23b.xhtml", "OEBPS/a%23b.xhtml"),
            ("OEBPS/a#b.xhtml", "OEBPS/a#b.xhtml"),
            ("OEBPS/a%2Fb.xhtml", "OEBPS/a%2Fb.xhtml"),
            ("OEBPS/a%20b.xhtml", "OEBPS/a%20b.xhtml"),
            ("OEBPS/a?b.xhtml", "OEBPS/a?b.xhtml"),
            ("OEBPS/ok%C5%82adka.png", "OEBPS/ok%C5%82adka.png"),
            ("OEBPS/okładka.png", "OEBPS/okładka.png"),
        ],
        ids=["hash-encoded", "hash-literal", "slash-encoded", "space", "query", "utf8-encoded", "utf8"],
    )
    def test_a_container_path_is_the_entry_name(self, raw, expected):
        assert ocf.canonical(raw).path == expected

    def test_an_encoded_slash_does_not_become_a_directory(self):
        """The worst of them: percent-decoding moved a file into a folder that
        does not exist, which is an identity change with a structural
        consequence — the manifest then names a path in a directory nothing
        else knows about."""
        assert "/" not in ocf.canonical("a%2Fb.xhtml").path

    def test_two_files_that_differ_only_by_encoding_stay_two_files(self):
        assert ocf.canonical("a%23b.xhtml").path != ocf.canonical("a#b.xhtml").path

    def test_the_folding_that_is_still_done_is_still_done(self):
        """The name is not a URL and it is also not sacred: separators, drive
        letters and `..` are folded, because those are how a name stops being a
        path inside this container."""
        assert ocf.canonical("OEBPS\\a.xhtml").path == "OEBPS/a.xhtml"
        assert ocf.canonical("/OEBPS/a.xhtml").path == "OEBPS/a.xhtml"
        assert ocf.canonical("OEBPS/sub/../a.xhtml").path == "OEBPS/a.xhtml"
        assert ocf.canonical("../outside.xhtml").rejected


class TestF002TheHrefStillIsAUrl:
    @pytest.mark.parametrize(
        "href, expected",
        [
            # `%25` is an escaped percent sign, so this names a file whose own
            # name contains `%23`.
            ("a%2523b.xhtml", "OEBPS/a%23b.xhtml"),
            # `%23` is an escaped hash, which is how a URL names a file with a
            # `#` in it *without* starting a fragment.
            ("a%23b.xhtml", "OEBPS/a#b.xhtml"),
            # A literal hash does start one.
            ("a.xhtml#gdzies", "OEBPS/a.xhtml"),
            ("ok%C5%82adka.png", "OEBPS/okładka.png"),
            ("a%20b.xhtml", "OEBPS/a b.xhtml"),
        ],
        ids=["encoded-percent", "encoded-hash", "fragment", "utf8", "space"],
    )
    def test_it_is_decoded_exactly_once(self, href, expected):
        assert paths.resolve("OEBPS/ch.xhtml", href) == expected

    def test_the_fragment_is_split_before_the_decoding_and_not_after(self):
        """The order is the whole of the last two cases above. Decoding first
        would turn `a%23b.xhtml` into `a#b.xhtml` and then split *that* on the
        hash, leaving `a` — a third file, named by nobody."""
        assert paths.resolve("OEBPS/ch.xhtml", "a%23b.xhtml") == "OEBPS/a#b.xhtml"

    def test_a_reference_to_a_file_with_a_percent_in_its_name_now_finds_it(self, tmp_path):
        """The defect stated as a book. Before the fix this resolved to
        `a#b.xhtml`, which the archive does not contain."""
        source = book(tmp_path / "pct.epub", entry="a%23b.xhtml", href="a%2523b.xhtml")
        parsed = read(source)
        assert "OEBPS/a%23b.xhtml" in parsed.resources
        assert any(item.path == "OEBPS/a%23b.xhtml" for item in parsed.spine)

    def test_and_the_rebuilt_book_still_holds_its_text(self, tmp_path):
        source = book(tmp_path / "pct2.epub", entry="a%23b.xhtml", href="a%2523b.xhtml")
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status.wrote_a_file
        with zipfile.ZipFile(result.output_path) as archive:
            everything = b"".join(archive.read(name) for name in archive.namelist())
        assert "Tekst rozdziału".encode() in everything


class TestF002TheBooksThisCouldHaveAbandoned:
    """Not decoding is right and would strand two real families of book.

    Both are resolved by looking the reference up under other spellings and
    accepting one **only because the archive holds a file under it** — evidence,
    not convention.
    """

    def test_an_archive_whose_entry_names_are_percent_encoded(self, tmp_path):
        """Two well-known tools write them that way. The href says `okładka`,
        the entry says `ok%C5%82adka`, and exactly one file answers."""
        source = book(tmp_path / "enc.epub", entry="ok%C5%82adka.xhtml", href="okładka.xhtml")
        report = Report(source=source)
        parsed = read_epub(source, report)
        assert "OEBPS/ok%C5%82adka.xhtml" in parsed.resources
        assert "reader.manifest-spelling-matched" in rules_of(report)

    def test_a_book_written_where_the_filesystem_decomposes_its_letters(self, tmp_path):
        """macOS stores `ł`… the interesting one is `ó`, which decomposes into
        `o` plus a combining acute. The document spells it composed."""
        import unicodedata

        decomposed = unicodedata.normalize("NFD", "wróbel.xhtml")
        assert decomposed != "wróbel.xhtml"
        source = book(tmp_path / "nfd.epub", entry=decomposed, href="wróbel.xhtml")
        report = Report(source=source)
        parsed = read_epub(source, report)
        assert any("wr" in path for path in parsed.resources)
        assert "reader.manifest-spelling-matched" in rules_of(report)

    def test_the_report_says_which_file_it_used_and_why(self, tmp_path):
        source = book(tmp_path / "enc2.epub", entry="ok%C5%82adka.xhtml", href="okładka.xhtml")
        report = Report(source=source)
        read_epub(source, report)
        finding = next(
            f for f in report.findings if f.rule == "reader.manifest-spelling-matched"
        )
        assert finding.values["how"] == "percent-encoding"
        assert "ok%C5%82adka" in finding.values["found"]

    def test_a_reference_to_nothing_is_still_a_reference_to_nothing(self, tmp_path):
        """The guard: a lookup that tries harder must not start inventing. No
        file, no match, and the report says the manifest names a missing file."""
        source = book(tmp_path / "gone.epub", entry="jest.xhtml", href="niema.xhtml")
        report = Report(source=source)
        read_epub(source, report)
        assert "reader.manifest-file-missing" in rules_of(report)

    def test_an_exact_match_is_never_reported_as_a_repair(self, tmp_path):
        source = book(tmp_path / "plain.epub", entry="ch.xhtml", href="ch.xhtml")
        report = Report(source=source)
        read_epub(source, report)
        assert "reader.manifest-spelling-matched" not in rules_of(report)


class TestF002TheAlternativesAreOfferedRatherThanApplied:
    def test_spellings_never_includes_the_path_itself(self):
        assert "a%23b.xhtml" not in ocf.spellings("a%23b.xhtml")

    def test_it_offers_both_directions(self):
        offered = ocf.spellings("okładka.png")
        assert any("%C5%82" in candidate for candidate in offered)
        assert ocf.spellings("ok%C5%82adka.png")[0] == "okładka.png"

    def test_nothing_in_it_escapes_the_container(self):
        """A candidate is a lookup key, and a lookup key that climbs out of the
        archive would be this program asking for a file outside the book."""
        for candidate in ocf.spellings("a%2E%2E%2Fb.xhtml"):
            assert not candidate.startswith("../")
            assert ".." not in candidate.split("/")
