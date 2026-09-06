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


class TestEF087TextInAFormXObjectIsReadAndCounted:
    """A page whose one visible sentence sits in a Form XObject converted to
    nothing, and K1 — reading through the same reader — passed it."""

    LONG = "This is a sufficiently long synthetic paragraph for the PDF conversion test to read."

    def _pdf(self, tmp_path):
        from tests.test_pdf import make_pdf

        return make_pdf(
            tmp_path / "form.pdf",
            [[(50, 700, 12, self.LONG), (50, 680, 12, self.LONG)]],
            title="Form fixture",
            language="en",
            forms={0: [[(50, 600, 12, "UNIQUE FORM TEXT MUST SURVIVE")]]},
        )

    def test_the_reader_sees_the_form_text(self, tmp_path):
        from epubforge import pdf

        assert "UNIQUE FORM TEXT MUST SURVIVE" in pdf.text_of(str(self._pdf(tmp_path)))

    def test_the_inventory_counts_it_whether_or_not_the_reader_does(self, tmp_path):
        from epubforge import pdf

        drawn = pdf.character_inventory(str(self._pdf(tmp_path)))
        assert drawn["U"] >= 2 and drawn["Q"] == 1, drawn

    def test_a_rebuild_carries_it(self, tmp_path):
        from epubforge import fidelity

        result = pipeline.rebuild(
            str(self._pdf(tmp_path)), str(tmp_path / "out.epub"), measuring()
        )
        assert result.output_path, result.report.to_text()
        assert "UNIQUE FORM TEXT MUST SURVIVE" in fidelity.spine_text_of(result.output_path)

    def test_the_second_reader_refuses_what_the_first_would_have_passed(self, tmp_path, monkeypatch):
        """Blind the line reader to the form again and the subsequence check
        holds vacuously — the character count does not."""
        from epubforge import fidelity, pdf

        source = self._pdf(tmp_path)
        real = pdf.text_of
        monkeypatch.setattr(
            pdf, "text_of", lambda path: real(path).replace("UNIQUE FORM TEXT MUST SURVIVE", "")
        )
        candidate = book(tmp_path / "candidate.epub", text=self.LONG + " " + self.LONG)
        assert fidelity.text_is_preserved(source, candidate).ok, "the blinded reader passes"
        assert not fidelity.pdf_characters_survive(source, candidate).ok
        report = Report(source=str(source))
        refusal = pipeline._text_gate(str(source), Policy(), report)(candidate)
        assert refusal.startswith("K1-PDF")
        assert "package.pdf-characters-lost" in {f.rule for f in report.findings}

    def test_the_inventory_walks_the_parse_the_reader_made(self, tmp_path, monkeypatch):
        """Three reads of one file cost one parse; a file that changed
        underneath is parsed again, not answered from memory."""
        import pdfminer.high_level
        from tests.test_pdf import make_pdf

        from epubforge import pdf

        parses = []
        real = pdfminer.high_level.extract_pages
        monkeypatch.setattr(
            pdfminer.high_level, "extract_pages", lambda *a, **k: parses.append(1) or real(*a, **k)
        )
        source = str(self._pdf(tmp_path))
        pdf._read(source)
        assert "UNIQUE FORM TEXT MUST SURVIVE" in pdf.drawn_text(source)
        assert pdf.character_inventory(source)["Q"] == 1
        assert len(parses) == 1, "the reader's parse serves the inventory"
        make_pdf(tmp_path / "form.pdf", [[(50, 700, 12, "A different page, written over the first.")]])
        assert "different page" in pdf.drawn_text(source)
        assert "UNIQUE" not in pdf.drawn_text(source)
        assert len(parses) == 2, "a changed file is parsed again"


class TestEF083ConsentIsPerDocument:
    """A hyphen joined in chapter four used to excuse a sentence missing from
    chapter nine: the gate looked for a rule name anywhere in the report."""

    TWO = {
        "EPUB/a.xhtml": "ALFA BETA GAMMA",
        "EPUB/b.xhtml": "DELTA EPSILON ZETA",
    }

    def _book(self, path: pathlib.Path) -> str:
        package = PACKAGE.replace(
            '<item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
            '<item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="b" href="b.xhtml" media-type="application/xhtml+xml"/>',
        ).replace('<itemref idref="c"/>', '<itemref idref="a"/><itemref idref="b"/>')
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", CONTAINER)
            archive.writestr("EPUB/package.opf", package)
            for name, text in self.TWO.items():
                archive.writestr(
                    name,
                    '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title>'
                    f"</head><body><p>{text}</p></body></html>",
                )
            archive.writestr("EPUB/nav.xhtml", NAV.replace("chapter.xhtml", "a.xhtml"))
            archive.writestr("EPUB/extra.txt", "x")
        return str(path)

    class LoseAWordInB(Stage):
        """Takes `EPSILON` out of b and, as the audit's probe did, drops a
        consented rule into the report — here honestly bound to document a."""

        name = "probe"
        mutates = True
        bind_to = "a"

        def run(self, ctx):
            for resource in ctx.book.content_docs():
                if b"EPSILON" in resource.data:
                    resource.data = resource.data.replace(b"EPSILON ", b"")
                    lost_in = resource.path
            self.note(ctx, Level.FIX, "hyphens.joined", values={"count": 1})
            target = {"a": [p for p in ctx.book.resources if p.endswith("a.xhtml")][0],
                      "b": lost_in}[self.bind_to]
            self.text_changed(ctx, target, "hyphens.joined")

    class LoseAWordInBBoundToB(LoseAWordInB):
        bind_to = "b"

    def test_consent_in_one_document_does_not_excuse_a_loss_in_another(self, tmp_path):
        result = pipeline.rebuild(
            self._book(tmp_path / "in.epub"), str(tmp_path / "out.epub"), measuring(),
            stages=[*DEFAULT_STAGES, self.LoseAWordInB],
        )
        assert not result.output_path, result.report.to_text()
        rules = {f.rule for f in result.report.findings}
        assert "package.text-lost" in rules or "package.prose-changed" in rules

    def test_consent_in_the_document_itself_is_honoured(self, tmp_path):
        result = pipeline.rebuild(
            self._book(tmp_path / "in.epub"), str(tmp_path / "out.epub"), measuring(),
            stages=[*DEFAULT_STAGES, self.LoseAWordInBBoundToB],
        )
        assert result.output_path, result.report.to_text()
        assert "package.text-changed-on-request" in {f.rule for f in result.report.findings}


class TestEF084TheBalanceHoldsResourcesByIdentity:
    """A generated NCX made up the number for a lost text file: one `other`
    out, one `other` in, and the balance closed on a book that had lost a
    resource nobody had asked to remove."""

    def test_a_loss_the_ledger_does_not_name_is_found_whatever_else_was_added(self, tmp_path):
        class DropResource(Stage):
            name = "probe"
            mutates = True

            def run(self, ctx):
                for path, resource in list(ctx.book.resources.items()):
                    if resource.media_type == "text/plain":
                        del ctx.book.resources[path]

        source = book(tmp_path / "source.epub")
        result = pipeline.rebuild(
            source, str(tmp_path / "out.epub"), measuring(), stages=[*DEFAULT_STAGES, DropResource]
        )
        balance = result.report.balance
        assert balance is not None
        assert balance.unexplained_paths == ["EPUB/extra.txt"], balance.as_dict()
        assert not result.output_path, "a loss by identity is a refusal, whatever the counts say"
        assert "package.balance-unexplained" in {f.rule for f in result.report.findings}

    def test_a_removal_the_ledger_names_is_explained(self, tmp_path):
        from epubforge.report import Action

        class DropAndSay(Stage):
            name = "probe"
            mutates = True

            def run(self, ctx):
                for path, resource in list(ctx.book.resources.items()):
                    if resource.media_type == "text/plain":
                        del ctx.book.resources[path]
                        self.changed(
                            ctx, Action.REMOVED, path, before=path, after="",
                            rule="structure.orphan-removed",
                        )

        source = book(tmp_path / "source.epub")
        result = pipeline.rebuild(
            source, str(tmp_path / "out.epub"), measuring(), stages=[*DEFAULT_STAGES, DropAndSay]
        )
        assert result.report.balance.unexplained_paths == []
        assert result.output_path, result.report.to_text()
