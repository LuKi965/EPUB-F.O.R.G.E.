"""Names inside the container, and the three ways they used to go wrong quietly.

An archive entry name is attacker-controlled data. It used to be folded into
shape by one expression — `filename.replace("\\\\", "/").lstrip("/")` — and stored,
which had three consequences nobody could see from the outside:

* a name that had been changed looked exactly like one that had not;
* two entries that collided after folding left only whichever came last;
* a name that climbed out of the container was copied into the output, where
  unpacking it became somebody else's problem.

None of the three raised anything. The book opened, EPUBCheck passed it, and one
document was gone.
"""

from __future__ import annotations

import unicodedata
import warnings
import zipfile

import pytest

from epubforge.ocf import canonical, collisions
from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy
from epubforge.report import Level

from .factory import CONTAINER, MODERN_NAV

CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
<head><meta charset="utf-8"/><title>R</title></head>
<body><h1>R</h1><p>{marker}</p></body>
</html>"""

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Ścieżki</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""


def archive(path, extra: dict) -> str:
    """A minimal book plus whatever oddly-named entries the test needs.

    `zipfile` warns when asked to write a name twice, which is precisely what
    several of these tests need it to do; the warning is the library noticing
    the same thing the tests are about.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return _archive(path, extra)


def _archive(path, extra: dict) -> str:
    with zipfile.ZipFile(path, "w") as handle:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        handle.writestr(info, b"application/epub+zip")
        handle.writestr(
            "META-INF/container.xml",
            CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
        )
        handle.writestr("OEBPS/package.opf", OPF)
        handle.writestr("OEBPS/nav.xhtml", MODERN_NAV)
        handle.writestr("OEBPS/chapter.xhtml", CHAPTER.format(marker="Tekst"))
        for name, data in extra.items():
            # `ZipInfo.__init__` replaces os.sep with "/", so on Windows an
            # entry named with a backslash silently becomes a well-formed one
            # and the test has nothing left to test. Setting the name after
            # construction produces the same archive on both platforms — which
            # is the point, since the archives under test come from elsewhere.
            #
            # The same replacement happens again on the way back in, which is
            # why the reader canonicalises `orig_filename` rather than
            # `filename`; this fixture only guarantees the bytes on disk.
            info = zipfile.ZipInfo("placeholder")
            info.filename = name
            handle.writestr(info, data)
    return str(path)


class TestCanonicalNames:
    @pytest.mark.parametrize(
        "raw, expected, change",
        [
            ("OEBPS/a.xhtml", "OEBPS/a.xhtml", None),
            ("OEBPS\\a.xhtml", "OEBPS/a.xhtml", "backslash"),
            ("/OEBPS/a.xhtml", "OEBPS/a.xhtml", "leading slash"),
            ("C:/OEBPS/a.xhtml", "OEBPS/a.xhtml", "drive letter"),
            ("OEBPS/./a.xhtml", "OEBPS/a.xhtml", "current-directory"),
            ("OEBPS/sub/../a.xhtml", "OEBPS/a.xhtml", "parent-directory"),
            ("OEBPS/a%20b.xhtml", "OEBPS/a b.xhtml", "percent-encoding"),
            ("OEBPS/a.xhtml\0.exe", "OEBPS/a.xhtml", "null byte"),
        ],
    )
    def test_folding_is_recorded_not_just_done(self, raw, expected, change):
        name = canonical(raw)
        assert name.path == expected
        assert name.changed is (change is not None)
        if change:
            assert any(change in note for note in name.changes), name.changes

    @pytest.mark.parametrize("raw", ["../outside.bin", "..", "a/../../b", "", "./", "/"])
    def test_a_name_that_is_not_a_container_path_is_rejected(self, raw):
        """Rejected rather than repaired: repairing would invent an answer."""
        name = canonical(raw)
        assert name.rejected
        assert name.reason


class TestCollisionViews:
    def test_identical_names_block(self):
        found = collisions(["a.xhtml", "a.xhtml"])
        assert [c.kind for c in found] == ["identical"]
        assert found[0].blocking

    def test_case_and_normalisation_do_not_block(self):
        nfc = unicodedata.normalize("NFC", "zażółć.xhtml")
        nfd = unicodedata.normalize("NFD", "zażółć.xhtml")
        found = {c.kind: c for c in collisions(["B.xhtml", "b.xhtml", nfc, nfd])}
        assert set(found) == {"case", "normalisation"}
        assert not any(c.blocking for c in found.values())

    def test_a_pair_is_reported_once_under_its_narrowest_view(self):
        """Two identical names are not also a case collision. Saying it twice
        makes the report longer without making it truer."""
        assert len(collisions(["a.xhtml", "a.xhtml"])) == 1

    def test_ordinary_names_collide_with_nothing(self):
        assert collisions(["a.xhtml", "b.xhtml", "images/a.png"]) == []


class TestTheArchiveIsReadThroughThatModel:
    def test_a_traversal_entry_never_reaches_the_output(self, tmp_path):
        """It used to be copied through in minimal mode. This tool never unpacks
        an archive, so it was never at risk itself — whoever unpacked the output
        was."""
        source = archive(tmp_path / "trav.epub", {"../outside.bin": b"outside"})
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("minimal"))

        with zipfile.ZipFile(result.output_path) as handle:
            assert not [n for n in handle.namelist() if ".." in n.split("/")]
        assert any(
            f.rule == "reader.name-dropped"
            for f in result.report.findings
            if f.level is Level.WARN
        )

    def test_two_entries_with_one_name_and_two_bodies_stop_the_read(self, tmp_path):
        """One of the two documents cannot be represented whatever we do. Picking
        the later one is a decision made by iteration order, and it was silent."""
        path = tmp_path / "dup.epub"
        archive(path, {})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "a") as handle:
                handle.writestr("OEBPS/chapter.xhtml", CHAPTER.format(marker="DRUGI"))

        result = rebuild(str(path), str(tmp_path / "out.epub"), Policy.preset("preserve"))

        assert result.status is Status.FAILED
        assert result.output_path is None
        assert any(
            "more than one entry named" in f.message
            for f in result.report.findings
            if f.level is Level.ERROR
        )

    def test_an_identical_duplicate_is_noted_and_survived(self, tmp_path):
        """Nothing is lost when both copies say the same thing, so nothing needs
        to stop. The opposite rule would refuse books that are merely untidy."""
        path = tmp_path / "same.epub"
        archive(path, {})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "a") as handle:
                handle.writestr("OEBPS/chapter.xhtml", CHAPTER.format(marker="Tekst"))

        result = rebuild(str(path), str(tmp_path / "out.epub"), Policy.preset("preserve"))

        assert result.status.wrote_a_file
        assert any(f.rule == "reader.duplicate-entry" for f in result.report.findings)

    def test_names_differing_only_by_case_are_kept_and_reported(self, tmp_path):
        """Legal and distinct inside the archive; one file on Windows. Refusing
        the book would refuse one that reads perfectly well on Linux."""
        source = archive(
            tmp_path / "case.epub",
            {"OEBPS/Chapter.xhtml": CHAPTER.format(marker="WIELKA")},
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))

        assert result.status.wrote_a_file
        warnings = [f.message for f in result.report.findings if f.level is Level.WARN]
        assert any("differ only by case" in message for message in warnings), warnings

    def test_names_differing_only_by_unicode_normalisation_are_reported(self, tmp_path):
        source = archive(
            tmp_path / "uni.epub",
            {
                "OEBPS/" + unicodedata.normalize("NFC", "zażółć.xhtml"): CHAPTER.format(marker="C"),
                "OEBPS/" + unicodedata.normalize("NFD", "zażółć.xhtml"): CHAPTER.format(marker="D"),
            },
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))

        warnings = [f.message for f in result.report.findings if f.level is Level.WARN]
        assert any("differ only by normalisation" in message for message in warnings), warnings

    def test_a_rewritten_name_is_reported(self, tmp_path):
        source = archive(tmp_path / "back.epub", {"OEBPS\\odd.bin": b"x"})
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("minimal"))

        rewrites = [
            f for f in result.report.findings
            if "not a container path" in f.message and f.level is Level.FIX
        ]
        assert rewrites, [f.message for f in result.report.findings]
        # The name as it was written down, not as the standard library handed
        # it over. On Windows those are two different strings, and reporting
        # the second one would mean reporting that nothing had happened.
        assert "\\" in rewrites[0].location, rewrites[0].location

    def test_the_same_book_is_read_the_same_way_on_every_platform(self, tmp_path):
        """`zipfile` folds os.sep out of entry names on the way in *and* on the
        way back out, so on Windows this book used to arrive already repaired
        and the repair went unmentioned. The reader reads `orig_filename` for
        exactly this reason; this asserts the raw name survives to it."""
        source = archive(tmp_path / "back.epub", {"OEBPS\\odd.bin": b"x"})
        with zipfile.ZipFile(source) as handle:
            raw = [info.orig_filename for info in handle.infolist()]
        assert "OEBPS\\odd.bin" in raw

    def test_an_ordinary_book_says_nothing_about_paths(self, tmp_path):
        """The whole point is that this is quiet when there is nothing to say."""
        source = archive(tmp_path / "plain.epub", {})
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))

        assert not [
            f for f in result.report.findings
            if "container path" in f.message or "differ only" in f.message
        ]
