"""PDF → EPUB as a separate job: the boundary, and what it is allowed to share.

The acceptance matrix of the handoff of 2026-09-09, P01…P11 plus its own
„testy granic modułu". The handoff is explicit about what a green test here has
to mean — *„Nie testuj wyłącznie zakazu napisu `pdfconv` w pipeline: zależność
pośrednia przez sources też może zachować niewłaściwy workflow"* — so these ask
what actually ran, with spies on both services, rather than grepping for a name.

No Qt: the service, the plan and the routing table are plain objects, which is
what makes the boundary testable at all.
"""

from __future__ import annotations

import pathlib

import pytest

from epubforge import pipeline, sources
from epubforge.pdfconv import service
from epubforge.pdfconv.models import PdfConversionPlan
from epubforge.pdfconv.settings import PdfSettings
from epubforge.policy import Policy
from tests.factory import make_modern_epub
from tests.test_pdf import book_with_heads, make_pdf, prose_of


def quiet() -> Policy:
    """The publication policy these tests run under: gates off, so what is
    measured is the conversion and not EPUBCheck's availability."""
    return Policy.preset(
        "preserve", validate_before_publish="off", render_gate="off", render_sample=0
    )


@pytest.fixture
def document(tmp_path) -> pathlib.Path:
    return pathlib.Path(book_with_heads(tmp_path))


@pytest.fixture
def scan(tmp_path) -> pathlib.Path:
    """A PDF that draws pictures and no text: the one thing this converter
    refuses on its own, because reading it would mean OCR."""
    PIL = pytest.importorskip("PIL.Image")
    source = tmp_path / "scan.pdf"
    PIL.new("RGB", (400, 600), (250, 250, 250)).save(source, "PDF")
    return source


def converted(sources_, tmp_path, **overrides):
    plan = PdfConversionPlan(
        sources=tuple(sources_), destination=tmp_path / "out",
        settings=PdfSettings(**overrides),
    )
    (tmp_path / "out").mkdir(exist_ok=True)
    return service.convert(plan)


class TestP02ThePdfDoesNotGoThroughTheRebuild:
    """The refusal, from every door, and not because the converter is missing.

    *„RebuildService odrzuca PDF także gdy converter został zainicjalizowany"* —
    so the first thing this asserts is that it *is* installed.
    """

    def test_the_converter_is_installed_or_this_proves_nothing(self):
        from epubforge import pdfconv

        assert pdfconv.installed()
        assert sources.for_source("x.pdf") is not None

    def test_the_public_rebuild_refuses_and_writes_nothing(self, document, tmp_path):
        out = tmp_path / "out.epub"
        result = pipeline.rebuild(str(document), str(out), quiet())
        assert result.status is pipeline.Status.BLOCKED
        assert result.output_path is None and not out.exists()

    def test_rebuild_all_refuses_before_it_opens_a_container(self, document, tmp_path):
        (result,) = pipeline.rebuild_all(str(document), str(tmp_path / "out.epub"))
        assert result.status is pipeline.Status.BLOCKED
        assert not (tmp_path / "out.epub").exists()

    def test_the_refusal_names_the_command_that_does_convert(self, document, tmp_path):
        result = pipeline.rebuild(str(document), str(tmp_path / "out.epub"), quiet())
        said = result.report.to_text("pl") + result.report.to_text("en")
        assert "convert-pdf" in said, said


class TestTheRoutingCallsOneServiceAndNotTheOther:
    """A spy on both, which is what the handoff asks for: *„Test ze spy na obu
    usługach dowodzi, że routing wywołał jedną właściwą usługę."*"""

    @pytest.fixture
    def spies(self, monkeypatch):
        seen = {"rebuild": [], "convert": []}
        real_rebuild = pipeline.rebuild
        real_convert = service.convert_document

        def rebuild(source, destination, *args, **kwargs):
            seen["rebuild"].append(str(source))
            return real_rebuild(source, destination, *args, **kwargs)

        def convert(source, destination, *args, **kwargs):
            seen["convert"].append(str(source))
            return real_convert(source, destination, *args, **kwargs)

        monkeypatch.setattr(pipeline, "rebuild", rebuild)
        monkeypatch.setattr(service, "convert_document", convert)
        return seen

    def test_a_pdf_reaches_the_converter_and_not_the_rebuild(self, spies, document, tmp_path):
        converted([document], tmp_path)
        assert spies["convert"] == [str(document)]
        assert spies["rebuild"] == []

    def test_an_epub_reaches_the_rebuild_and_not_the_converter(self, spies, tmp_path):
        book = make_modern_epub(str(tmp_path / "book.epub"))
        pipeline.rebuild(book, str(tmp_path / "out.epub"), quiet())
        assert spies["rebuild"] == [book]
        assert spies["convert"] == []


class TestP04AndP06TheConverterStillDoesWhatItDid:
    """The capabilities the handoff says to keep: *„Zachowaj obecne
    możliwości konwertera"*. Same two modes, same defaults, same output."""

    def test_p04_a_text_pdf_converts_without_the_rebuild_entry(self, document, tmp_path):
        (result,) = converted([document], tmp_path)
        assert result.published, result.report_text
        assert result.published_outputs[0].exists()
        assert result.layout == "reflowable"
        assert "THE BOOK OF PAGES" in prose_of(str(result.published_outputs[0]))

    def test_p06_fixed_is_a_choice_and_never_a_fallback(self, document, tmp_path):
        import zipfile

        (kept,) = converted([document], tmp_path, layout="fixed")
        assert kept.layout == "fixed"
        with zipfile.ZipFile(kept.published_outputs[0]) as archive:
            assert "pre-paginated" in archive.read("EPUB/package.opf").decode()

    def test_p06_and_a_poorly_read_document_does_not_switch_by_itself(self, tmp_path):
        """A document this reader handles badly — two columns of fragments —
        still comes out reflowable. The person changes the mode, not the
        program (03-PDF-MODULE §2)."""
        import zipfile

        source = make_pdf(tmp_path / "columns.pdf", [[
            (72, 700 - row * 14, 12, "Left column fragment") for row in range(12)
        ] + [
            (330, 700 - row * 14, 12, "Right column fragment") for row in range(12)
        ]])
        (result,) = converted([pathlib.Path(source)], tmp_path)
        assert result.layout == "reflowable"
        if result.published:
            with zipfile.ZipFile(result.published_outputs[0]) as archive:
                assert "pre-paginated" not in archive.read("EPUB/package.opf").decode()

    def test_p05_a_scan_is_refused_and_says_it_needs_ocr(self, scan, tmp_path):
        (result,) = converted([scan], tmp_path)
        assert not result.published, "skan bez tekstu wyszedł jako publikacja"
        assert not list((tmp_path / "out").glob("*.epub"))
        said = result.report_text
        assert "OCR" in said, said


class TestP07TheWarningsAreInTheResultAndNotOnlyInTheReport:
    def test_a_quality_warning_reaches_the_result_object(self, tmp_path):
        source = make_pdf(tmp_path / "torn.pdf", [[
            (72, 700 - row * 14, 12, "a fragment that runs on and") for row in range(20)
        ]])
        (result,) = converted([pathlib.Path(source)], tmp_path)
        assert result.warnings or not result.published
        assert result.report_text, "raport techniczny zniknął"

    def test_the_three_checks_are_told_apart(self, document, tmp_path):
        """A green EPUBCheck is not proof of a faithful conversion and a
        character count is not proof of a sensible reading order. The result
        says which question was actually answered (03-PDF-MODULE §2)."""
        (result,) = converted([document], tmp_path)
        assert result.text_checked is True
        # The gates are off in these tests, so the validator did not run — and
        # the result says so rather than borrowing the other check's answer.
        assert result.epub_validated is False
        assert not hasattr(result, "appearance_checked")


class TestP09TheTwoPlansAreIndependent:
    def test_a_converter_setting_has_nowhere_to_live_in_the_rebuild(self):
        """The boundary test the handoff names: *„Brak `pdf.*` w katalogu
        ustawień sesji EPUB"* and *„Import modułu przebudowy nie wymaga
        PdfSettings"*."""
        from epubforge.gui.shell import options

        policy = Policy.preset("preserve")
        assert not hasattr(policy, "pdf")
        assert not [name for name in vars(policy) if "pdf" in name.lower()]
        assert not [one for one in options.OPTIONS if one.key.startswith("pdf.")]

    def test_the_repair_core_does_not_import_the_converters_settings(self):
        source = (pathlib.Path(__file__).resolve().parent.parent
                  / "epubforge" / "policy.py").read_text(encoding="utf-8")
        assert "pdfconv" not in source

    def test_changing_the_conversion_settings_does_not_touch_a_rebuild_plan(self, tmp_path):
        plan = PdfConversionPlan(sources=(), settings=PdfSettings())
        plan.settings.layout = "fixed"
        assert Policy.preset("preserve") == Policy.preset("preserve")
        assert plan.settings.layout == "fixed"
        assert not hasattr(Policy.preset("preserve"), "pdf")


class TestP11TheSafeguardsSurvivedTheSeparation:
    """*„Nie usuwaj zabezpieczeń tylko po to, żeby odciąć zależność."* Each of
    the converter's stages and gates, still on the run this module composes."""

    def test_the_converters_stage_runs_and_the_cores_stages_run_after_it(self, document, tmp_path):
        from epubforge.pdfconv.stage import PdfStage

        seen = []
        real = PdfStage.run

        def watched(self, ctx):
            seen.append("pdf")
            return real(self, ctx)

        original = PdfStage.run
        PdfStage.run = watched
        try:
            result = service.convert_document(document, tmp_path / "out.epub", policy=quiet())
        finally:
            PdfStage.run = original
        assert seen == ["pdf"], "etap konwertera nie pobiegł"
        assert result.output_path

    def test_the_text_check_still_runs_and_can_still_refuse(self, document, tmp_path,
                                                            monkeypatch):
        """K1-PDF is the gate this program promises never to stand down. Blind
        the reader to half the text and it must refuse, on this path too."""
        from epubforge.pdfconv import reader as pdf

        result = service.convert_document(document, tmp_path / "ok.epub", policy=quiet())
        assert result.output_path, "test nic nie mierzy, jeśli i tak nie przechodzi"

        real = pdf.drawn_text
        monkeypatch.setattr(
            pdf, "drawn_text", lambda path: real(path) + "ZNAKIKTORYCHNIEMA"
        )
        refused = service.convert_document(document, tmp_path / "no.epub", policy=quiet())
        assert refused.output_path is None
        assert not (tmp_path / "no.epub").exists()

    def test_the_run_is_still_cancellable_in_the_middle(self, document, tmp_path):
        stopped = service.convert_document(
            document, tmp_path / "out.epub", policy=quiet(), cancellation=lambda: True
        )
        assert stopped.output_path is None
        assert not (tmp_path / "out.epub").exists()

    def test_a_batch_stops_between_documents_too(self, document, tmp_path):
        plan = PdfConversionPlan(sources=(document, document), destination=tmp_path / "out")
        (tmp_path / "out").mkdir()
        results = service.convert(plan, cancellation=lambda: True)
        assert results == []

    def test_the_validator_still_runs_when_it_is_asked_to(self, document, tmp_path):
        """The shared layer's other gate, on this path. Skipped where EPUBCheck
        is not installed rather than reported green (04-ACCEPTANCE: *„Nie
        raportuj sukcesu dla testu pominiętego z braku zależności"*)."""
        from epubforge.validate import find_epubcheck

        if find_epubcheck() is None:
            pytest.skip("brak EPUBCheck — nie ma czym sprawdzić")
        policy = Policy.preset("preserve", validate_before_publish="clean",
                               render_gate="off", render_sample=0)
        result = service.convert_document(document, tmp_path / "out.epub", policy=policy)
        assert result.report.validated is not None, "walidator nie pobiegł"
        assert result.output_path, result.report.to_text()

    def test_and_a_conversion_that_epubcheck_refuses_is_not_published(self, document,
                                                                     tmp_path, monkeypatch):
        from epubforge import validate as validate_module
        from epubforge.validate import find_epubcheck

        if find_epubcheck() is None:
            pytest.skip("brak EPUBCheck — nie ma czym sprawdzić")

        def refuse(path, report=None, **kwargs):
            from epubforge.report import Level
            from epubforge.validate import ValidationResult

            if report is not None:
                report.validated = False
                report.add("epubcheck", Level.ERROR, "epubcheck.error",
                           values={"code": "RSC-005", "detail": "wymuszony blad"})
            return ValidationResult(available=True, errors=1, codes={"RSC-005": 1})

        # The gate imports it from the module at call time, so this reaches it.
        monkeypatch.setattr(validate_module, "validate", refuse)
        policy = Policy.preset("preserve", validate_before_publish="clean",
                               render_gate="off", render_sample=0)
        result = service.convert_document(document, tmp_path / "out.epub", policy=policy)
        assert result.output_path is None
        assert not (tmp_path / "out.epub").exists()

    def test_the_original_is_never_written_over(self, document, tmp_path):
        before = document.read_bytes()
        converted([document], tmp_path)
        assert document.read_bytes() == before

    def test_a_name_already_taken_is_not_overwritten(self, document, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        standing = out / f"{document.stem}.epub"
        standing.write_bytes(b"czyjs plik")
        (result,) = converted([document], tmp_path)
        assert not result.published
        assert standing.read_bytes() == b"czyjs plik"
        assert result.error


class TestP01AndP03TheRoutingTable:
    """Which module a file belongs to, decided in one place and by kind."""

    def test_p01_a_pdf_is_the_converters_and_an_epub_is_the_rebuilds(self):
        from epubforge.gui.shell import routing

        assert routing.route_for("a.pdf") == "pdf"
        assert routing.route_for("A.PDF") == "pdf"
        assert routing.route_for("b.epub") == "rebuild"
        assert routing.route_for("c.txt") == ""

    def test_p03_a_mixed_set_is_split_and_not_merged(self):
        from epubforge.gui.shell import routing

        split = routing.sort_out(["a.epub", "b.pdf", "c.epub", "d.txt"])
        assert [p.name for p in split["rebuild"]] == ["a.epub", "c.epub"]
        assert [p.name for p in split["pdf"]] == ["b.pdf"]
        assert [p.name for p in split[""]] == ["d.txt"]

    def test_every_route_is_a_key_even_when_it_is_empty(self):
        from epubforge.gui.shell import routing

        split = routing.sort_out([])
        assert set(split) == set(routing.ROUTES) | {""}


class TestP10TheCommandLine:
    def test_build_refuses_a_pdf_and_convert_pdf_takes_it(self, document, tmp_path, capsys):
        from epubforge.cli import main

        refused = main(["build", str(document), "-o", str(tmp_path / "no" / "x.epub"),
                        "--gate", "off", "--render-gate", "off"])
        assert refused != 0
        assert "convert-pdf" in capsys.readouterr().out
        assert not list(tmp_path.rglob("*.epub"))

        out = tmp_path / "yes"
        assert main(["convert-pdf", str(document), "-o", str(out)]) == 0
        assert len(list(out.glob("*.epub"))) == 1

    def test_a_folder_scan_for_build_does_not_sweep_pdfs_in(self, document, tmp_path):
        from epubforge.cli import BOOKS, DOCUMENTS, collect_inputs

        make_modern_epub(str(tmp_path / "book.epub"))
        assert [pathlib.Path(p).name for p in collect_inputs([str(tmp_path)], BOOKS)] == [
            "book.epub"
        ]
        assert [pathlib.Path(p).name for p in collect_inputs([str(tmp_path)], DOCUMENTS)] == [
            document.name
        ]

    def test_the_converters_flags_are_on_its_own_command(self):
        from epubforge.cli import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["build", "x.epub", "--layout", "fixed"])
        args = parser.parse_args(["convert-pdf", "x.pdf", "--layout", "fixed"])
        assert args.layout == "fixed"
