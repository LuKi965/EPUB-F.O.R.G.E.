"""F-025 — a container that offers two books, and a rebuild that produced one.

EPUB 3 lets a container list several `rootfile` elements. Each is a complete
publication of the same work: a fixed-layout edition beside a reflowable one,
two languages, with and without narration. A reading system chooses between
them; that is what the `rendition:` attributes on each `rootfile` are for.

This program read the first one and said nothing about the rest. The other
rendition's files were still in the archive, so they came through as
unmanifested strays — the output was one publication *plus somebody else's
chapters*, declared as a single book. Nothing said so.

**The owner's decision, 2026-08-13: rebuild each version separately.** Refusing
the book was the other option and he did not take it. Merging was never one:
two renditions are two books, and flattening them decides on the reader's
behalf which edition they get.

So `rebuild_all` writes one file per rendition, named after what the container
calls them, and each file holds its own publication. The plain `rebuild` is
unchanged — it still produces one file from the first rendition and now says in
the report that there were others, because there is no sibling file for those
chapters to go to and dropping them would be a loss with nowhere to land.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import Status, rebuild, rebuild_all
from epubforge.policy import Policy
from epubforge.reader import read_epub, rootfiles
from epubforge.report import Report
from tests.factory import MODERN_NAV, png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
           xmlns:rendition="http://www.idpf.org/2013/rendition">
  <rootfiles>
{rootfiles}
  </rootfiles>
</container>
"""

ROOTFILE = (
    '    <rootfile full-path="{path}" media-type="application/oebps-package+xml"{extra}/>'
)

PACKAGE = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:{uuid}</dc:identifier>
    <dc:title>{title}</dc:title><dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="../wspolny.png" media-type="image/png"/>
  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""

PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>R</title></head>
  <body><p>{body}</p><p><img src="../wspolny.png" alt="x"/></p></body>
</html>
"""


def two_renditions(path, *, labels: tuple[str, str] = ("Tekst", "Album")) -> str:
    """One work, two publications, and one picture they share."""
    listed = "\n".join(
        ROOTFILE.format(path=f"{folder}/package.opf", extra=extra)
        for folder, extra in (
            ("reflow", f' rendition:layout="reflowable" rendition:label="{labels[0]}"'),
            ("fixed", f' rendition:layout="pre-paginated" rendition:label="{labels[1]}"'),
        )
    )
    entries = {
        "META-INF/container.xml": CONTAINER.format(rootfiles=listed).encode(),
        "wspolny.png": png_bytes(),
    }
    for folder, title, body, uuid in (
        ("reflow", "Wersja tekstowa", "Tekst wersji pierwszej.", "1111-1"),
        ("fixed", "Wersja albumowa", "Tekst wersji drugiej.", "1111-2"),
    ):
        entries[f"{folder}/package.opf"] = PACKAGE.format(title=title, uuid=uuid).encode()
        entries[f"{folder}/nav.xhtml"] = MODERN_NAV.encode()
        entries[f"{folder}/chapter.xhtml"] = PAGE.format(body=body).encode()
    return write_zip(str(path), entries)


def everything_in(path: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return b"".join(archive.read(name) for name in archive.namelist())


def rules_of(report) -> set[str]:
    return {f.rule for f in report.findings if f.rule}


class TestF025TheContainerIsAskedWhatItOffers:
    def test_every_rootfile_is_seen(self, tmp_path):
        source = two_renditions(tmp_path / "two.epub")
        with zipfile.ZipFile(source) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        offered = rootfiles(entries)
        assert [r.path for r in offered] == ["reflow/package.opf", "fixed/package.opf"]

    def test_and_what_the_publisher_called_them(self, tmp_path):
        source = two_renditions(tmp_path / "labels.epub")
        with zipfile.ZipFile(source) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        assert [r.label for r in rootfiles(entries)] == ["Tekst", "Album"]

    def test_a_rootfile_naming_a_file_that_is_not_there_is_not_a_rendition(self, tmp_path):
        """A broken container, not an offer. `_locate_opf` reports it as one."""
        source = two_renditions(tmp_path / "broken.epub")
        with zipfile.ZipFile(source) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        entries.pop("fixed/package.opf")
        assert len(rootfiles(entries)) == 1

    def test_an_ordinary_book_offers_exactly_one(self, tmp_path):
        from tests.factory import make_modern_epub

        source = make_modern_epub(str(tmp_path / "one.epub"))
        with zipfile.ZipFile(source) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        assert len(rootfiles(entries)) == 1


class TestF025EachOneIsRebuiltIntoItsOwnFile:
    def test_two_files_come_out(self, tmp_path):
        results = rebuild_all(
            two_renditions(tmp_path / "src.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert len(results) == 2
        assert all(r.status.wrote_a_file for r in results)

    def test_the_first_goes_exactly_where_it_was_asked_to(self, tmp_path):
        """Nothing changes for the person who dropped one book on the window."""
        destination = str(tmp_path / "out.epub")
        results = rebuild_all(
            two_renditions(tmp_path / "src2.epub"), destination, Policy.preset("preserve")
        )
        assert results[0].output_path == destination

    def test_the_others_are_named_after_what_the_container_calls_them(self, tmp_path):
        results = rebuild_all(
            two_renditions(tmp_path / "src3.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert results[1].output_path.endswith("out.Album.epub")

    def test_each_file_holds_its_own_publication_and_not_the_other(self, tmp_path):
        """The defect, stated as bytes: one book plus somebody else's chapters."""
        results = rebuild_all(
            two_renditions(tmp_path / "src4.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        first, second = (everything_in(r.output_path) for r in results)
        assert "wersji pierwszej".encode() in first
        assert "wersji drugiej".encode() not in first
        assert "wersji drugiej".encode() in second
        assert "wersji pierwszej".encode() not in second

    def test_and_each_carries_its_own_metadata(self, tmp_path):
        results = rebuild_all(
            two_renditions(tmp_path / "src5.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert [r.book.metadata.title for r in results] == ["Wersja tekstowa", "Wersja albumowa"]

    def test_a_file_both_renditions_use_is_in_both(self, tmp_path):
        """Shared resources are shared. Only what belongs to *another*
        rendition and not to this one is left to its own output."""
        results = rebuild_all(
            two_renditions(tmp_path / "src6.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        for result in results:
            with zipfile.ZipFile(result.output_path) as archive:
                assert any(name.endswith(".png") for name in archive.namelist())

    def test_the_report_says_which_files_were_left_to_the_sibling(self, tmp_path):
        results = rebuild_all(
            two_renditions(tmp_path / "src7.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "reader.other-rendition-skipped" in rules_of(results[0].report)

    def test_an_ordinary_book_produces_exactly_one_result(self, tmp_path):
        """`rebuild_all` is `rebuild` for every book but a handful, and the
        handful is the point — this is the assertion that the handful did not
        become everybody."""
        from tests.factory import make_modern_epub

        source = make_modern_epub(str(tmp_path / "one.epub"))
        results = rebuild_all(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert len(results) == 1
        assert results[0].output_path == str(tmp_path / "out.epub")

    @pytest.mark.parametrize("mode", ["preserve", "strict", "minimal"])
    def test_in_every_mode(self, tmp_path, mode):
        results = rebuild_all(
            two_renditions(tmp_path / f"{mode}.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset(mode),
        )
        assert len(results) == 2
        assert all(r.status.wrote_a_file for r in results)


class TestF025ThePlainRebuildStillSaysSomethingHappened:
    def test_it_still_produces_one_file(self, tmp_path):
        result = rebuild(
            two_renditions(tmp_path / "plain.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert result.status is not Status.FAILED
        assert result.output_path

    def test_and_the_report_names_the_renditions(self, tmp_path):
        """A caller that asked for one file gets one file — and is told the
        container held more than one book, which is the part that was missing."""
        result = rebuild(
            two_renditions(tmp_path / "plain2.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "reader.renditions-offered" in rules_of(result.report)
        finding = next(
            f for f in result.report.findings if f.rule == "reader.renditions-offered"
        )
        assert finding.values["count"] == 2
        assert "Album" in finding.values["names"]

    def test_it_does_not_drop_the_other_renditions_files(self, tmp_path):
        """No sibling file is being written here, so leaving them out would be
        a loss with nowhere to land. They stay, and the warning above is what
        tells somebody to use the other path."""
        result = rebuild(
            two_renditions(tmp_path / "plain3.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve"),
        )
        assert "wersji drugiej".encode() in everything_in(result.output_path)

    def test_reading_one_rendition_by_name_is_possible_on_its_own(self, tmp_path):
        source = two_renditions(tmp_path / "byname.epub")
        report = Report(source=source)
        book = read_epub(source, report, rendition="fixed/package.opf")
        assert book.metadata.title == "Wersja albumowa"
        assert len(book.renditions) == 2


class TestF025ItIsReachable:
    def test_the_command_line_can_ask_for_one_file(self):
        from epubforge.cli import build_parser

        parsed = build_parser().parse_args(["build", "x.epub", "--first-rendition-only"])
        assert parsed.first_rendition_only

    def test_and_defaults_to_all_of_them(self):
        from epubforge.cli import build_parser

        assert not build_parser().parse_args(["build", "x.epub"]).first_rendition_only

    def test_the_window_rebuilds_every_rendition(self):
        import pathlib

        source = (
            pathlib.Path(__file__).resolve().parent.parent / "epubforge" / "gui" / "app.py"
        ).read_text(encoding="utf-8")
        assert "rebuild_all(" in source
        assert "package.renditions-written" in source
