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
    stages = (partial(PdfStage, settings),) + service.PDF_STAGES + tuple(extra)
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
        stages = ((lambda: ForgetsToAccount(settings)),) + service.PDF_STAGES
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

    def test_a_consent_that_removed_nothing_does_not_block_one_that_accounted(self):
        """The eighth case, which the seven did not cover and the fix needed.

        „No entry in the ledger" was reading as „no accounting", and a pass
        that *moved* text — `xhtml.watermark-relocated` is the shape — removes
        nothing and therefore had nothing to write. Two consents, one of them
        explaining the whole loss, and the book was refused because the other
        one had been quiet.

        So a pass that runs writes an entry either way, and an empty one is an
        answer: *this rule took nothing out of this document*. Absence still
        means no accounting and still refuses; it just stops meaning two
        different things at once.
        """
        from epubforge.fidelity import Check

        report = Report()
        report.stats[gate.REMOVAL_LEDGER] = [
            {"rule": "pdf.running-heads-removed", "document": "text/a.xhtml", "text": "abc"},
            {"rule": "xhtml.watermark-relocated", "document": "text/a.xhtml", "text": ""},
        ]
        check = Check("K1-PDF", False, "3 znaki", {"missing": {"a": 1, "b": 1, "c": 1}})
        refusal = gate.note_second_opinion(
            report, check, ["pdf.running-heads-removed", "xhtml.watermark-relocated"]
        )
        assert not refusal, refusal

        # And a rule that never wrote anything at all is still refused.
        quiet = Report()
        quiet.stats[gate.REMOVAL_LEDGER] = [
            {"rule": "pdf.running-heads-removed", "document": "text/a.xhtml", "text": "abc"},
        ]
        assert gate.note_second_opinion(
            quiet, check, ["pdf.running-heads-removed", "xhtml.watermark-relocated"]
        )

    def test_a_pass_that_took_nothing_out_still_says_so(self):
        """The other half, and the half the ledger above was hand-written past.

        The case above proves the *gate* reads an empty entry as an answer.
        This one proves the *recorder* writes one — without it the gate never
        sees the entry and the two consents case cannot arise in a real run at
        all. Asked of `text_changed` directly, because that is the one door
        every text-changing pass goes through.
        """
        from types import SimpleNamespace

        from epubforge.stages.base import REMOVAL_LEDGER, Stage

        page = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Tekst na miejscu.</p></body></html>'
        moved = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p class="mark">Tekst na miejscu.</p></body></html>'
        report = Report()
        ctx = SimpleNamespace(text_changes={}, report=report)
        Stage.text_changed(
            Stage(), ctx, "text/a.xhtml", "xhtml.watermark-relocated",
            before=page, after=moved,
        )
        entries = report.stats.get(REMOVAL_LEDGER) or []
        assert entries, "przebieg, ktory nic nie usunal, nie zostawil sladu"
        assert entries[0]["rule"] == "xhtml.watermark-relocated"
        assert entries[0]["text"] == "", entries

    def test_the_ledger_is_a_bag_of_characters_and_is_counted_as_one(self):
        """EF-102. The corpus test that removes Chromium's own running heads
        was refused for 138 characters *beyond* the consent — every one of
        them a full stop — on v0.4.4 and on every commit after it.

        The ledger entry's `text` is what a pass took out, written as a
        sorted bag: `"...............,,,---"`. The gate then folded that bag
        through `canonical` again, the way it folds prose — and `canonical`
        makes an ellipsis of three full stops in a row. A hundred and
        thirty-eight full stops from 138 `.xhtml` footers came back as 46
        ellipses, which paid for nothing the check had counted; the check
        had counted full stops, since on the page they stand a footer apart.
        The bag was folded once when it was written; counting it is all
        that is left to do.
        """
        from epubforge.fidelity import Check

        report = Report()
        report.stats[gate.REMOVAL_LEDGER] = [
            {"rule": "pdf.running-heads-removed", "document": "text/a.xhtml", "text": "...---"},
        ]
        check = Check("K1-PDF", False, "6 znakow", {"missing": {".": 3, "-": 3}})
        left, why = gate.account_for(report, check, ["pdf.running-heads-removed"])
        assert not why
        assert not left, dict(left)

    def test_the_recorder_and_the_gate_agree_on_full_stops(self):
        """The same thing end to end: a document that loses three lines, each
        ending in a full stop that stood alone on the page, and a gate that
        is paid for exactly those three."""
        from types import SimpleNamespace

        from epubforge.fidelity import Check
        from epubforge.stages.base import Stage

        page = (
            b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            b'<p class="head">a.</p><p>Tekst.</p><p class="head">b.</p><p class="head">c.</p>'
            b"</body></html>"
        )
        stripped = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Tekst.</p></body></html>'
        report = Report()
        ctx = SimpleNamespace(text_changes={}, report=report)
        Stage.text_changed(
            Stage(), ctx, "text/a.xhtml", "pdf.running-heads-removed", before=page, after=stripped,
        )
        check = Check("K1-PDF", False, "6 znakow", {"missing": {".": 3, "a": 1, "b": 1, "c": 1}})
        left, why = gate.account_for(report, check, ["pdf.running-heads-removed"])
        assert not why
        assert not left, dict(left)

    def test_7_an_ordinary_epub_rebuild_is_untouched_by_the_scope_rule(self, tmp_path):
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


#: The chapters of a manual, each on its own page and each named in the
#: outline, so the reflowable book comes out as one document per chapter —
#: which is what "the same fragment in two documents" needs (AC09).
CHAPTERS = ("Zbiornik na wode", "Tacka ociekowa", "Pojemnik na fusy",
            "Dysze pary", "Panel sterowania", "Odkamienianie")


def chaptered(tmp_path: pathlib.Path, name: str = "chapters.pdf") -> pathlib.Path:
    pages, outline = [], []
    for number, (chapter, sentence) in enumerate(zip(CHAPTERS, BODY), start=1):
        pages.append([
            (72, 760, 10.0, HEAD),
            (72, 720, 18.0, chapter),
            (72, 690, 12.0, sentence),
            (72, 670, 12.0, f"Akapit {number} ciagnie sie dalej w tej samej linii."),
            (300, 40, 10.0, str(number)),
        ])
        outline.append((chapter, number - 1))
    return make_pdf(tmp_path / name, pages, title="Instrukcja", language="pl", outline=outline)


class MovesAParagraph(Stage):
    """A converter defect, stood in for: a paragraph leaves its document and
    turns up at the end of the one before it. Nothing is lost — every
    character is still in the book — and nothing is where it was.

    The shape matters: a *global* count of characters balances, and the
    subsequence check that notices the broken order is excused, on a run with
    any consented removal, as "a removal that closed up behind itself".
    """

    name = "test-moves-a-paragraph"
    mutates = True

    def __init__(self, marker: str = "Akapit 2") -> None:
        self.marker = marker

    def run(self, ctx) -> None:
        docs = list(ctx.book.content_docs())
        for index, resource in enumerate(docs):
            root = ctx.take(resource).root
            for element in list(xhtml.iter_elements(root)):
                if element.tag.rsplit("}", 1)[-1] != "p":
                    continue
                if self.marker in "".join(element.itertext()) and index > 0:
                    element.getparent().remove(element)
                    resource.data = xhtml.serialize(root)
                    previous = docs[index - 1]
                    home = ctx.take(previous).root
                    body = next(
                        node for node in xhtml.iter_elements(home)
                        if node.tag.rsplit("}", 1)[-1] == "body"
                    )
                    body.append(element)
                    previous.data = xhtml.serialize(home)
                    return


class TestConsentIsPerDocumentAndOccurrenceA14:
    """A14 of the 0.4.4 recovery audit, AC09: *the same fragment in two
    places; consent covers the document it was given for, and a change in
    the other one is detected.* The audit's probe fed `account_for` an entry
    from one page and a loss described as another and was not refused; that
    was a fact about one function. These are the whole gate.

    The defect stood in for is a **move**, because a loss the count can see
    is already refused (case 3 above): a paragraph that changes documents
    balances every total this gate had, and only a record per document says
    that neither document is what it was.
    """

    def test_a_paragraph_moved_between_documents_is_refused_under_a_consent(self, tmp_path):
        """Heads removed on a standing answer — a consented removal in every
        document — and a body paragraph moved from chapter 2 into chapter 1.
        Before the fix this was published with `pdf-characters-changed-on-
        request`: the count balanced and the consent excused the order."""
        source = chaptered(tmp_path)
        out = tmp_path / "out.epub"
        result, report = convert(source, out, heads="remove", extra=(MovesAParagraph,))
        assert not result.output_path, "zgoda na naglowki przepuscila akapit przeniesiony do innego dokumentu"
        assert not out.exists()
        assert "package.document-changed-unrecorded" in refusals(report)
        named = next(f for f in report.findings if f.rule == "package.document-changed-unrecorded")
        assert named.location and named.location.endswith(".xhtml"), "odmowa nie nazywa dokumentu"
        assert "bez wpisu" in (named.values.get("why") or "")

    def test_the_same_move_with_nothing_consented_is_still_refused(self, tmp_path):
        """No consent at all. The subsequence half refuses this first — the
        order broke and nothing excused it — and the per-document check is
        asked only behind the global halves, so a loss they can see keeps
        the refusal that says what is missing. The point here is the
        negative: the fix did not move the bar for a book nobody consented
        about."""
        source = chaptered(tmp_path)
        out = tmp_path / "out.epub"
        result, report = convert(source, out, heads="keep", extra=(MovesAParagraph,))
        assert not result.output_path
        assert {"package.text-lost", "package.document-changed-unrecorded"} & set(refusals(report))

    def test_the_consented_removal_alone_still_publishes_every_chapter(self, tmp_path):
        """The positive case, so the fix cannot be "refuse every converted
        book": heads removed in six documents, each with its entry, and the
        book comes out with all six."""
        source = chaptered(tmp_path)
        out = tmp_path / "out.epub"
        result, report = convert(source, out, heads="remove")
        assert result.output_path, report.to_text("pl")
        assert "package.document-changed-unrecorded" not in refusals(report)
        with zipfile.ZipFile(out) as archive:
            chapters = [n for n in archive.namelist() if "/text/" in n and n.endswith(".xhtml")]
        assert len(chapters) == len(CHAPTERS), chapters
        recorded = report.stats.get("text_changes") or {}
        assert len(recorded) == len(CHAPTERS), "nie kazdy dokument ma wpis o usunieciu paginy"

    def test_the_record_is_taken_before_any_stage_runs(self, tmp_path):
        """`prose_as_read` is the *before* every chain starts from. It has
        to be the reader's output and nothing later — a record taken after
        the heads were removed would make the removal invisible."""
        source = chaptered(tmp_path)
        result, report = convert(source, tmp_path / "out.epub", heads="remove")
        as_read = report.stats.get(pipeline.PROSE_AS_READ) or {}
        assert set(as_read) == set(report.stats.get("text_changes") or {})
        for path, chain in (report.stats.get("text_changes") or {}).items():
            assert chain[0]["before"] == as_read[path], path
