"""Constitutional tests — whole-output properties, not individual behaviours.

Kept in their own file because they are a different category from the rest of
the suite. A behaviour test says "this defect is repaired"; these say "whatever
you add next, the output still has this property". They are the tests that are
allowed to veto a feature.

The properties are stated in `CONTRIBUTING.md`; the identifiers below (K1…) are
the ones used there.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import zipfile

import lxml.html

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

MODIFIED_RE = re.compile(rb"<meta property=\"dcterms:modified\">[^<]*</meta>")


# --------------------------------------------------------------------- helpers
def body_text(path: str) -> str:
    """Every readable character in the book, in spine order, whitespace-folded.

    Deliberately scoped to `<body>`. An earlier version of this compared whole
    documents and reported false differences, because `text_content()` pulls in
    `<title>` from the head — and the rebuild writes the chapter title there.
    The navigation document is excluded for the same reason: it is generated,
    so it is output rather than content.
    """
    parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = sorted(n for n in archive.namelist() if n.endswith((".xhtml", ".html", ".htm")))
        for name in names:
            if "nav" in name.rsplit("/", 1)[-1].lower():
                continue
            document = lxml.html.fromstring(archive.read(name))
            body = document.xpath('//*[local-name()="body"]')
            parts.append((body[0] if body else document).text_content())
    folded = re.sub(r"\s+", " ", " ".join(parts))
    return unicodedata.normalize("NFC", folded).strip()


def entries(path: str) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def without_modified(opf: bytes) -> bytes:
    """The package document with the one field that is *meant* to change removed."""
    return MODIFIED_RE.sub(b"", opf)


def digest(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ------------------------------------------------------------------------ K1
def test_rebuild_preserves_every_readable_character(legacy_epub, tmp_path):
    """K1. No stage may lose, gain or reorder a character of the book's text."""
    result = rebuild(legacy_epub, str(tmp_path / "out.epub"), Policy.preset("preserve"))
    assert result.output_path, result.report.to_text()
    assert body_text(result.output_path) == body_text(legacy_epub)


def test_strict_mode_also_preserves_every_readable_character(legacy_epub, tmp_path):
    """K1 is not relaxed by --strict. Conformance may move markup, never text."""
    result = rebuild(legacy_epub, str(tmp_path / "strict.epub"), Policy.preset("strict"))
    assert result.output_path, result.report.to_text()
    assert body_text(result.output_path) == body_text(legacy_epub)


# ------------------------------------------------------------------------ K2
def test_output_is_byte_reproducible(legacy_epub, tmp_path):
    """K2. Two runs on the same input differ only in `dcterms:modified`."""
    one = rebuild(legacy_epub, str(tmp_path / "one.epub"), Policy.preset("preserve"))
    two = rebuild(legacy_epub, str(tmp_path / "two.epub"), Policy.preset("preserve"))

    first, second = entries(one.output_path), entries(two.output_path)
    assert set(first) == set(second)
    differing = {name for name in first if first[name] != second[name]}
    assert differing <= {"EPUB/package.opf"}, differing
    assert without_modified(first["EPUB/package.opf"]) == without_modified(
        second["EPUB/package.opf"]
    )


def test_zip_entries_carry_no_wall_clock_timestamp(legacy_epub, tmp_path):
    """A timestamp from the clock is the usual reason K2 quietly stops holding."""
    result = rebuild(legacy_epub, str(tmp_path / "out.epub"), Policy.preset("preserve"))
    with zipfile.ZipFile(result.output_path) as archive:
        stamps = {info.filename: info.date_time for info in archive.infolist()}
    assert set(stamps.values()) == {(1980, 1, 1, 0, 0, 0)}, stamps


def test_frozen_modified_makes_the_whole_file_reproducible(legacy_epub, tmp_path):
    """With the one moving part pinned, the output hashes identically."""
    policy = Policy.preset("preserve", modified_override="2020-01-01T00:00:00Z")
    one = rebuild(legacy_epub, str(tmp_path / "one.epub"), policy)
    two = rebuild(legacy_epub, str(tmp_path / "two.epub"), policy)
    assert digest(one.output_path) == digest(two.output_path)


# ------------------------------------------------------------------------ K3
def test_second_pass_changes_nothing_but_the_timestamp(legacy_epub, tmp_path):
    """K3. Idempotence at the level of file *contents*, not of file names.

    The weaker version of this test — comparing the set of names — passed while
    two separate defects silently changed the data: the series number was lost
    on the second pass, and an auto-supplied empty alt was promoted into an
    `alternativeText` claim.
    """
    first = rebuild(legacy_epub, str(tmp_path / "first.epub"), Policy.preset("preserve"))
    second = rebuild(first.output_path, str(tmp_path / "second.epub"), Policy.preset("preserve"))
    assert second.output_path, second.report.to_text()

    one, two = entries(first.output_path), entries(second.output_path)
    assert set(one) == set(two)
    differing = {name for name in one if one[name] != two[name]}
    assert differing <= {"EPUB/package.opf"}, differing
    assert without_modified(one["EPUB/package.opf"]) == without_modified(
        two["EPUB/package.opf"]
    )


def test_second_pass_reports_no_errors(legacy_epub, tmp_path):
    from epubforge.report import Level

    first = rebuild(legacy_epub, str(tmp_path / "first.epub"), Policy.preset("preserve"))
    second = rebuild(first.output_path, str(tmp_path / "second.epub"), Policy.preset("preserve"))
    assert second.report.count(Level.ERROR) == 0, second.report.to_text()
