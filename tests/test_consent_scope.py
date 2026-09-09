"""Q08: a consent explains what it removed, or it explains nothing.

The quality roadmap of 2026-09-09 found that a PDF conversion could lose text
nobody agreed to lose and publish anyway, as long as *some* consented pass
appeared in the report. Its probe showed it on this checkout — consent to
`pdf.running-heads-removed` passed a synthetic loss of 500 characters of body
prose — and its first iteration asks for exactly one fix: account for the
approved scopes instead of taking the rule's name as a licence.

These are the seven cases it names, run through the **whole publication gate**
rather than the one function: *„Izolowany probe z paczki jest wskazówką;
potrzebny jest test pełnej bramy publikacji."*

The loss is injected by a stage that deletes a paragraph after the conversion
has built the book. That is a stand-in for a converter defect and not a
pretence about the source: the PDF really does draw those characters, the book
really does come out without them, and the gate really is the thing being
asked. Nothing here weakens a gate, and no fixture expectation was lowered.
"""

from __future__ import annotations

import pathlib
import zipfile
from functools import partial

import pytest

from epubforge import pipeline, xhtml
from epubforge.pdfconv import gate, service
from epubforge.pdfconv.settings import PdfSettings
from epubforge.pdfconv.stage import PdfStage
from epubforge.policy import Policy
from epubforge.report import Report
from epubforge.stages.base import Stage
from tests.test_pdf import make_pdf

pytest.importorskip("pdfminer.high_level")

#: The head every page carries, and a body that repeats one of its words. The
#: repetition is case 5: a word that exists in both places must not let the
#: head's consent pay for the body's loss.
HEAD = "Instrukcja obslugi"
#: Six pages, because a line repeating on three is not yet a running head:
#: `reader.RUNNING_HEAD_MIN_PAGES` is 4, and a fixture under it produces no
#: consent at all — which is how the first draft of this file came to test
#: nothing (every case refused, none of them for the reason it claimed).
BODY = (
    "Instrukcja mowi, ze zbiornik nalezy wyjmowac od frontu.",
    "Woda powinna siegac oznaczenia MAX i nie wyzej.",
    "Tacke ociekowa oprozniaj, zanim plywak sie podniesie.",
    "Pojemnik na fusy wyjmuje sie po otwarciu drzwiczek.",
    "Dysze pary przetrzyj sciereczka po kazdym uzyciu.",
    "Panel sterowania czysc na sucho, bez detergentow.",
)


def manual(tmp_path: pathlib.Path, name: str = "manual.pdf") -> pathlib.Path:
    """Three pages, each with a running head, a page number and its own prose."""
    pages = []
    for number, sentence in enumerate(BODY, start=1):
        lines = [(72, 760, 10.0, HEAD)]
        lines.append((72, 700, 12.0, sentence))
        lines.append((72, 680, 12.0, f"Akapit {number} ciagnie sie dalej w tej samej linii."))
        lines.append((300, 40, 10.0, str(number)))
        pages.append(lines)
    return make_pdf(tmp_path / name, pages, title="Instrukcja", language="pl")


class LosesAParagraph(Stage):
    """A converter defect, stood in for: one paragraph of body prose goes.

    Deliberately *not* a running head — the point of every case below is
    whether a consent about heads reaches text that is not one.
    """

    name = "test-loses-a-paragraph"
    mutates = True

    def __init__(self, marker: str = "Akapit 2") -> None:
        self.marker = marker

    def run(self, ctx) -> None:
        for resource in ctx.book.content_docs():
            root = ctx.take(resource).root
            gone = False
            for element in list(xhtml.iter_elements(root)):
                if self.marker in "".join(element.itertext()):
                    parent = element.getparent()
                    if parent is not None:
                        parent.remove(element)
                        gone = True
            if gone:
                resource.data = xhtml.serialize(root)


def convert(source, destination, *, heads="remove", extra=(), policy=None):
    """One document through the production composition, plus *extra* stages.

    Mirrors `service.convert_document` — the same reader, the same stage order
    — because a test that assembled its own pipeline would be asking a
    different program.
    """
    settings = PdfSettings(running_heads=heads)
    report = Report(source=str(source), output=str(destination))
    stages = (partial(PdfStage, settings),) + pipeline.DEFAULT_STAGES + tuple(extra)
    result = pipeline.produce(
        str(source), str(destination),
        policy or Policy.preset("preserve", validate_before_publish="off",
                                render_gate="off", render_sample=0),
        report, read=partial(service._read, settings), stages=stages,
    )
    return result, report


def refusals(report: Report) -> "list[str]":
    from epubforge.report import Level

    return [f.rule for f in report.findings if f.level is Level.ERROR]


class TestTheSevenCasesOfConsentScope:
    def test_1_a_loss_with_no_consent_is_not_published(self, tmp_path):
        """The case that already worked, kept so the fix cannot be mistaken for
        a loosening: nothing consented, text gone, nothing written.

        Which of the two text gates says so is not the point and is not
        asserted: with no consent the subsequence half refuses first and the
        character count never gets its turn. The point is that the book does
        not come out and the report says text was lost.
        """
        source = manual(tmp_path)
        out = tmp_path / "out.epub"
        result, report = convert(source, out, heads="keep", extra=(LosesAParagraph,))
        assert not result.output_path, "opublikowano mimo ubytku bez zgody"
        assert not out.exists()
        assert {"package.text-lost", "package.pdf-characters-lost"} & set(refusals(report))

    def test_2_consent_to_exactly_what_was_removed_passes_this_gate(self, tmp_path):
        """Heads removed on a standing answer and nothing else lost: the book
        is published, and it is *this* gate that let it — the others still ran
        and had their own say."""
        source = manual(tmp_path)
        out = tmp_path / "out.epub"
        result, report = convert(source, out, heads="remove")
        assert result.output_path, report.to_text("pl")
        assert out.exists()
        rules = {f.rule for f in report.findings}
        assert "pdf.running-heads-removed" in rules
        assert "package.pdf-characters-lost-beyond-consent" not in rules
        # And the ledger the accounting spends is actually there, holding what
        # left rather than a count of it. It is a character multiset per
        # document — the gate spends characters, and a copy of the prose is
        # not carried for the same reason `fidelity.prose_digest` does not
        # carry one — so what is asserted is that the heads and the page
        # numbers are in it, with the right multiplicity.
        from collections import Counter

        entries = report.stats.get(gate.REMOVAL_LEDGER) or []
        assert entries, "usuniecie nie zapisalo, co usunelo"
        assert {entry["rule"] for entry in entries} == {"pdf.running-heads-removed"}
        recorded = Counter()
        for entry in entries:
            recorded += Counter(entry["text"])
        heads = Counter(c for c in HEAD * len(BODY) if not c.isspace())
        assert not (heads - recorded), (
            "w rozliczeniu nie ma wszystkich usunietych naglowkow", recorded
        )
        assert not (Counter("123456") - recorded), "nie rozliczono numerow stron"

    def test_3_the_same_consent_does_not_pay_for_an_independent_loss(self, tmp_path):
        """The roadmap's finding, end to end: the heads were removed with an
        answer behind them, a body paragraph went missing as well, and the
        second loss is not covered by the first consent."""
        source = manual(tmp_path)
        out = tmp_path / "out.epub"
        result, report = convert(source, out, heads="remove", extra=(LosesAParagraph,))
        assert not result.output_path, "zgoda na naglowki przepuscila obcy ubytek"
        assert not out.exists()
        assert "package.pdf-characters-lost-beyond-consent" in refusals(report)

    def test_4_a_consent_without_an_accounting_refuses(self, tmp_path):
        """*„Ta sama nazwa reguły, ale inna strona/element albo zmieniony
        plik → brak nieuprawnionego przepuszczenia."*

        The rule's name is in the report and the ledger it should have written
        is not — the shape a stale or foreign consent takes once the licence
        is the accounting rather than the name. Missing data refuses; it does
        not wave through.
        """
        source = manual(tmp_path)
        out = tmp_path / "out.epub"

        class ForgetsToAccount(PdfStage):
            def _take_out(self, ctx, found, automation):
                super()._take_out(ctx, found, automation)
                ctx.report.stats.pop(gate.REMOVAL_LEDGER, None)

        settings = PdfSettings(running_heads="remove")
        report = Report(source=str(source), output=str(out))
        stages = ((lambda: ForgetsToAccount(settings)),) + pipeline.DEFAULT_STAGES
        result = pipeline.produce(
            str(source), str(out),
            Policy.preset("preserve", validate_before_publish="off",
                          render_gate="off", render_sample=0),
            report, read=partial(service._read, settings), stages=stages,
        )
        assert not result.output_path, "zgoda bez rozliczenia przepuscila ubytek"
        assert "package.pdf-characters-lost-beyond-consent" in refusals(report)

    def test_5_a_word_in_both_the_head_and_the_body_is_paid_for_once(self, tmp_path):
        """The head and the first sentence share a word. Removing three heads
        pays for three copies of it, not for a fourth that left the body — the
        accounting is a multiset, not a set of characters that appear."""
        source = manual(tmp_path)
        out = tmp_path / "out.epub"
        # The paragraph that goes begins with the very word the head carries.
        result, report = convert(source, out, heads="remove",
                                 extra=(partial(LosesAParagraph, "Instrukcja mowi"),))
        assert not result.output_path, (
            "powtorzone slowo z naglowka rozliczylo ubytek w tresci"
        )
        assert "package.pdf-characters-lost-beyond-consent" in refusals(report)

    def test_6_a_refusal_leaves_the_source_and_the_last_good_result_alone(self, tmp_path):
        """Nothing is written over: not the PDF, and not a book from an earlier
        run standing where this one would have gone."""
        source = manual(tmp_path)
        before = source.read_bytes()
        out = tmp_path / "out.epub"

        good, _ = convert(source, out, heads="remove")
        assert good.output_path and out.exists()
        kept = out.read_bytes()

        bad, report = convert(source, out, heads="remove", extra=(LosesAParagraph,))
        assert not bad.output_path
        assert source.read_bytes() == before, "zrodlo zostalo naruszone"
        assert out.read_bytes() == kept, "poprzedni poprawny wynik zostal nadpisany"

    def test_7_an_ordinary_epub_rebuild_is_untouched(self, tmp_path):
        """The change is in the importer's path. A book that was never a PDF
        goes through the gate it always did, and still comes out."""
        from tests.factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "legacy.epub"))
        out = tmp_path / "rebuilt.epub"
        result = pipeline.rebuild(
            source, str(out),
            Policy.preset("preserve", validate_before_publish="off",
                          render_gate="off", render_sample=0),
        )
        assert result.output_path, result.report.to_text("pl")
        with zipfile.ZipFile(out) as archive:
            assert archive.namelist()
