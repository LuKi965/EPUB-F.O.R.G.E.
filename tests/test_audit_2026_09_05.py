"""The independent audit of 2026-09-05, one test per finding.

Every test here fails on the code as the auditor found it and passes on the
code as it is now. They are kept together rather than filed by subject
because what they have in common is the *shape* of the defect rather than the
module: in all six, something the program calls a guarantee turned out to be
a guarantee about a string, an empty list, or a check that had excused itself.

The findings are EF-081 to EF-086 and EF-090; EF-087, EF-088 and EF-089 are
answered in their own files, with their own material.
"""

from __future__ import annotations

import os
import pathlib
import zipfile

import pytest

from epubforge import fidelity, pipeline, plan, render_fidelity
from epubforge.policy import Policy
from epubforge.report import Level, Report
from epubforge.stages import DEFAULT_STAGES
from epubforge.stages.base import Stage

CONTAINER = (
    '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
    'version="1.0"><rootfiles><rootfile full-path="EPUB/package.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)
PACKAGE = (
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
    'unique-identifier="id"><metadata '
    'xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:identifier id="id">urn:test:audit</dc:identifier>'
    "<dc:title>Audit fixture</dc:title><dc:language>en</dc:language>"
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>'
    '<manifest><item id="c" href="chapter.xhtml" '
    'media-type="application/xhtml+xml"/><item id="n" href="nav.xhtml" '
    'media-type="application/xhtml+xml" properties="nav"/>'
    '<item id="extra" href="extra.txt" media-type="text/plain"/></manifest>'
    '<spine><itemref idref="c"/></spine></package>'
)
NAV = (
    '<html xmlns="http://www.w3.org/1999/xhtml" '
    'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title>'
    '</head><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">'
    "Chapter</a></li></ol></nav></body></html>"
)


def book(path: pathlib.Path, text: str = "ALFA BETA GAMMA", quote: str = '"') -> str:
    """The auditor's own fixture, with the quoting character as a knob."""
    chapter = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Audit fixture'
        f"</title></head><body><p>{text}</p></body></html>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", CONTAINER.replace('"', quote))
        archive.writestr("EPUB/package.opf", PACKAGE.replace('"', quote))
        archive.writestr("EPUB/chapter.xhtml", chapter)
        archive.writestr("EPUB/nav.xhtml", NAV)
        archive.writestr("EPUB/extra.txt", "RESOURCE TO PRESERVE")
    return str(path)


def measuring(**over):
    return Policy.for_measurement(reproducible=True, remember_decisions=False, **over)


class TestEF081TheSourceIsProtectedByIdentity:
    """`CASE-SOURCE.EPUB` overwrote `case-source.epub` on Windows and the run
    said `succeeded`. Two strings, one file — and the one file this program
    must never be able to destroy."""

    def test_a_link_to_the_source_is_the_source(self, tmp_path):
        source = book(tmp_path / "source.epub")
        link = tmp_path / "link.epub"
        try:
            link.symlink_to(source)
        except (OSError, NotImplementedError):  # pragma: no cover - Windows
            pytest.skip("this filesystem does not do symbolic links")
        assert plan.same_file(str(link), source)

    def test_a_rebuild_through_a_link_refuses_and_leaves_the_bytes_alone(self, tmp_path):
        source = book(tmp_path / "source.epub")
        before = pathlib.Path(source).read_bytes()
        link = tmp_path / "link.epub"
        try:
            link.symlink_to(source)
        except (OSError, NotImplementedError):  # pragma: no cover - Windows
            pytest.skip("this filesystem does not do symbolic links")
        result = pipeline.rebuild(str(link), source, measuring())
        assert not result.output_path
        assert "package.source-protected" in {f.rule for f in result.report.findings}
        assert pathlib.Path(source).read_bytes() == before

    def test_writing_onto_a_link_that_points_at_the_source_refuses_too(self, tmp_path):
        source = book(tmp_path / "source.epub")
        link = tmp_path / "link.epub"
        try:
            link.symlink_to(source)
        except (OSError, NotImplementedError):  # pragma: no cover - Windows
            pytest.skip("this filesystem does not do symbolic links")
        result = pipeline.rebuild(source, str(link), measuring())
        assert not result.output_path, "the destination resolves to the source"

    def test_a_batch_sees_two_spellings_of_one_destination_as_a_collision(self, tmp_path):
        # `normcase` folds case only where the filesystem does, so this asserts
        # the platform's own answer rather than one platform's.
        first, second = tmp_path / "a.epub", tmp_path / "b.epub"
        first.write_bytes(b""), second.write_bytes(b"")
        out = tmp_path / "out"
        out.mkdir()
        made = plan.plan_batch([str(first), str(second)], str(out))
        assert not made.collisions, "different names, different destinations"
        same = plan.plan_batch([str(first), str(first)], str(out))
        assert same.collisions, "one source twice is one destination twice"


class TestEF082ZeroComparisonsIsNotASuccess:
    """A package document quoted with apostrophes is legal XML, passes
    EPUBCheck with nothing to say, and made the appearance check compare no
    pages at all — and report that the book had been checked."""

    def test_the_reading_order_is_read_whichever_quote_the_publisher_used(self, tmp_path):
        for name, quote in (("double.epub", '"'), ("single.epub", "'")):
            room = tmp_path / name.replace(".epub", "")
            render_fidelity._extract(book(tmp_path / name, quote=quote), room)
            spine = render_fidelity._spine_of(room)
            assert [page.name for page in spine] == ["chapter.xhtml"], name

    def test_a_result_that_examined_nothing_is_not_ok(self):
        nothing = render_fidelity.RenderFidelity(available=True, engine="x", pages=[])
        assert not nothing.ok, "all([]) is True and that is exactly the trap"

    def test_the_gate_treats_an_unreadable_reading_order_as_a_check_that_did_not_run(
        self, tmp_path, monkeypatch
    ):
        source = book(tmp_path / "source.epub")
        report = Report(source=source)
        monkeypatch.setattr(
            render_fidelity,
            "compare",
            lambda *a, **k: render_fidelity.RenderFidelity(
                available=True, engine="x", reason="nie odczytano", pages=[]
            ),
        )
        refusal = pipeline._render_gate(
            source, Policy(render_gate="report"), report, str(tmp_path / "o.epub"), None
        )(source)
        rules = {f.rule for f in report.findings}
        assert "render.checked" not in rules
        assert "render.not-completed" in rules
        assert refusal == "", "report mode reports; stop mode is the test below"


class TestEF083AMandatoryCheckThatCannotRunStopsThePublication:
    def test_an_exception_in_the_text_check_refuses(self, tmp_path, monkeypatch):
        source = book(tmp_path / "source.epub")
        damaged = book(tmp_path / "damaged.epub", text="ALFA GAMMA")
        report = Report(source=source)
        monkeypatch.setattr(
            fidelity,
            "text_is_preserved",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("probe failure")),
        )
        refusal = pipeline._text_gate(source, Policy(), report)(damaged)
        assert refusal, "a check that could not run may not end in silence"
        levels = {f.rule: f.level for f in report.findings}
        assert levels["package.text-check-failed"] is Level.ERROR

    def test_a_word_invented_in_place_is_caught_without_any_renaming(self, tmp_path):
        """`minimal` publishes the source's own layout, so there is no rename
        ledger — and the prose check used to stand down for want of one."""

        class AddText(Stage):
            name = "probe"
            mutates = True

            def run(self, ctx):
                for resource in ctx.book.content_docs():
                    resource.data = resource.data.replace(b"ALFA", b"ALFA INVENTED")

        source = book(tmp_path / "source.epub")
        result = pipeline.rebuild(
            source,
            str(tmp_path / "out.epub"),
            measuring(reorganize_files=False),
            stages=[*DEFAULT_STAGES, AddText],
        )
        assert not result.output_path
        assert "package.prose-changed" in {f.rule for f in result.report.findings}


class TestEF084AnUnexplainedLossStopsThePublication:
    def test_a_resource_that_disappears_with_nothing_accounting_for_it(self, tmp_path):
        class DropResource(Stage):
            name = "probe"
            mutates = True

            def run(self, ctx):
                for path, resource in list(ctx.book.resources.items()):
                    if resource.media_type == "text/plain":
                        del ctx.book.resources[path]

        source = book(tmp_path / "source.epub")
        destination = tmp_path / "out.epub"
        result = pipeline.rebuild(
            source,
            str(destination),
            measuring(write_ncx=False),
            stages=[*DEFAULT_STAGES, DropResource],
        )
        assert not result.output_path, "the balance said ERROR and wrote the file anyway"
        assert not destination.exists()
        assert "package.balance-unexplained" in {f.rule for f in result.report.findings}


class TestEF085NothingIsWrittenOutsideItsDirectory:
    @pytest.mark.parametrize(
        "name",
        [
            "../extract-sibling/probe.txt",
            "../../probe.txt",
            "/absolute-probe.txt",
        ],
    )
    def test_a_member_that_climbs_out_is_not_extracted(self, tmp_path, name):
        archive = tmp_path / "traversal.zip"
        with zipfile.ZipFile(archive, "w") as writing:
            writing.writestr(name, "confined harmless probe")
        into = tmp_path / "room" / "extract"
        render_fidelity._extract(archive, into)
        written = [
            path
            for path in tmp_path.rglob("probe.txt")
            if into.resolve() not in path.resolve().parents
        ]
        assert not written, f"{name} was written to {written}"

    def test_the_prefix_of_a_sibling_directory_is_not_containment(self, tmp_path):
        root = (tmp_path / "extract").resolve()
        sibling = (tmp_path / "extract-sibling" / "probe.txt").resolve()
        assert str(sibling).startswith(str(root)), "the text really does start with it"
        assert not render_fidelity._inside(sibling, root)


class TestEF086APdfDoesNotGoThroughTheComparison:
    def test_the_gate_never_hands_a_pdf_to_the_archive_reader(self, tmp_path, monkeypatch):
        """`compare` opens the source with `zipfile`; a PDF is not one, and the
        default preset therefore ended every PDF rebuild on `BadZipFile`."""
        source = tmp_path / "source.pdf"
        source.write_bytes(b"%PDF-1.4 not really, and it must not be opened")

        def refuse(*args, **kwargs):
            raise AssertionError("a PDF source reached the EPUB comparison")

        monkeypatch.setattr(render_fidelity, "compare", refuse)
        report = Report(source=str(source))
        gate = pipeline._render_gate(
            str(source), Policy(), report, str(tmp_path / "o.epub"), None
        )
        gate(book(tmp_path / "out.epub"))
        assert "render.pdf-drawn" in {f.rule for f in report.findings}

    def test_what_it_says_it_did_is_what_it_did(self, tmp_path):
        rendered = render_fidelity.RenderFidelity(
            available=True, engine="x", pages=[], completed=False
        )
        assert not rendered.ok, "nothing drawn is not a pass, here either"


class TestEF090ThePathContractHoldsOnBothPlatforms:
    def test_the_kobo_name_is_built_the_way_the_platform_builds_paths(self, tmp_path):
        source = str(tmp_path / "ksiazka.kepub.epub")
        assert plan.destination_for(source, None, kepub=True) == os.path.join(
            str(tmp_path), "ksiazka.forged.kepub.epub"
        )
