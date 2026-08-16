"""BA-2026-002's third class of question: a metadata conflict.

The finding's closure criterion names three — a broken link, a hard hyphen and a
metadata conflict — on one API. The first two arrived with the queue; this is
the third, and it is the one that shows the API was worth building, because it
needed no new machinery at all.

The conflict is F-004's: a package document that only parsed after a tag-soup
recovery gives fields that are a *parser's reading* of somebody's book rather
than the book's own words. That has been reported since F-004 was closed, which
left a person holding a warning and no way to act on it in the same breath.
"""

from __future__ import annotations

import zipfile


from epubforge import decisions
from epubforge.decisions import KEEP, Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import write_zip

CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)

#: Crossed tags — the shape that forces the recovering parser and produces a
#: title nobody wrote.
BROKEN_OPF = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="i">'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:identifier id="i">urn:uuid:1</dc:identifier>'
    "<dc:title>Prawdziwy <b>Tytuł</dc:title></b>"
    "<dc:language>pl</dc:language></metadata>"
    '<manifest><item id="c" href="r.xhtml" media-type="application/xhtml+xml"/>'
    '</manifest><spine><itemref idref="c"/></spine></package>'
)


def book(path) -> str:
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/content.opf": BROKEN_OPF.encode(),
            "OEBPS/r.xhtml": (
                '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
                '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
                '<meta charset="utf-8"/><title>R</title></head>'
                "<body><p>Tekst.</p></body></html>"
            ).encode(),
        },
    )


def run(tmp_path, asker=None, **policy):
    return rebuild(
        book(tmp_path / "in.epub"),
        str(tmp_path / "out.epub"),
        Policy.preset(
            "preserve", validate_before_publish="off", render_gate="off",
            remember_decisions=False, **policy
        ),
        asker=asker,
    )


def rules_of(result) -> set:
    return {finding.rule for finding in result.report.findings if finding.rule}


def titles_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        return "".join(
            archive.read(name).decode("utf-8", "replace")
            for name in archive.namelist()
            if name.endswith(".opf")
        )


class Asks:
    def __init__(self, option=KEEP, value=""):
        self.seen = []
        self._answer = Answer(option=option, value=value)

    def ask(self, question):
        self.seen.append(question)
        return self._answer


class TestTheQuestionIsPut:
    def test_a_recovered_package_produces_a_metadata_question(self, tmp_path):
        asker = Asks()
        result = run(tmp_path, asker)
        assert result.status.wrote_a_file, result.report.to_text()
        assert any(q.kind == decisions.METADATA for q in asker.seen), [
            (q.kind, q.summary) for q in asker.seen
        ]

    def test_a_healthy_package_asks_nothing_about_metadata(self, tmp_path):
        from tests.factory import make_modern_epub

        asker = Asks()
        make_modern_epub(str(tmp_path / "ok.epub"), title="Zdrowa")
        rebuild(
            str(tmp_path / "ok.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset(
                "preserve", validate_before_publish="off", render_gate="off",
                remember_decisions=False,
            ),
            asker=asker,
        )
        assert not [q for q in asker.seen if q.kind == decisions.METADATA]

    def test_it_says_what_the_parser_read_and_why_that_matters(self, tmp_path):
        asker = Asks()
        run(tmp_path, asker)
        question = next(q for q in asker.seen if q.kind == decisions.METADATA)
        assert "odzysk" in question.detail
        assert question.recommended == KEEP

    def test_each_field_is_asked_about_separately(self, tmp_path):
        """A person may know the title and have no idea about the identifier.
        One question for the book would force one answer onto both."""
        asker = Asks()
        run(tmp_path, asker)
        metadata = [q for q in asker.seen if q.kind == decisions.METADATA]
        assert len({q.subject for q in metadata}) == len(metadata)


class TestNothingHappensWithoutAnAnswer:
    def test_nobody_asked_leaves_the_parser_s_reading_in_place(self, tmp_path):
        before = run(tmp_path).report
        assert "package.metadata-corrected" not in {
            f.rule for f in before.findings if f.rule
        }

    def test_keeping_it_deliberately_changes_nothing_either(self, tmp_path):
        result = run(tmp_path, Asks(option=KEEP))
        assert "package.metadata-corrected" not in rules_of(result)


class TestAnsweringCorrectsTheBook:
    def test_a_title_written_by_hand_reaches_the_package(self, tmp_path):
        result = run(tmp_path, Asks(option="write", value="Tytuł Poprawiony"))
        assert "Tytuł Poprawiony" in titles_of(result)

    def test_it_is_reported_with_both_readings(self, tmp_path):
        result = run(tmp_path, Asks(option="write", value="Tytuł Poprawiony"))
        assert "package.metadata-corrected" in rules_of(result)
        said = result.report.to_text()
        assert "Tytuł Poprawiony" in said

    def test_an_empty_answer_is_refused_by_the_queue(self, tmp_path):
        """`write` carries a value; the queue rejects one that does not.

        What follows from that changed with DELTA-2026-08-15-001 and is the
        same argument as BA-2026-002's: a front end that sent an empty box is
        not a person who decided. The queue records it as a failure and the
        rebuild treats it as unanswered — so the title is neither lost nor
        quietly replaced by the parser's reading, and no file is written for
        somebody to find the guess in later.
        """
        result = run(tmp_path, Asks(option="write", value=""))
        assert "package.metadata-corrected" not in rules_of(result)
        assert not result.output_path
        assert "package.metadata-unconfirmed" in rules_of(result)


class TestAllThreeClassesShareOneApi:
    """The closure criterion, stated as a test."""

    def test_the_vocabulary_holds_all_three(self):
        assert set(decisions.KINDS) == {
            decisions.REFERENCE,
            decisions.HYPHEN,
            decisions.METADATA,
            # DELTA-2026-08-15-001's fourth, and the one that is not about a
            # place in the book: whether a rebuild nobody could check may be
            # written at all.
            decisions.VERIFICATION,
        }

    def test_each_class_is_asked_through_the_same_queue(self, tmp_path):
        """One `Queue`, one `Question`, one `Answer`. A front end that can
        answer one can answer all three without knowing which it is."""
        from epubforge import hyphens
        from epubforge.decisions import Option, Question

        made = [
            Question(
                kind=decisions.METADATA, where="a.opf", summary="s", detail="d",
                options=(Option(KEEP, "k", "c"),), subject="x",
            ),
            hyphens.question_for(
                hyphens.Candidate(
                    word="obo-jętna", left="obo", right="jętna", where="r.xhtml",
                    context="…", confidence=hyphens.CONFIRMED, reason="…",
                    joined_elsewhere=2,
                )
            ),
        ]
        queue = decisions.Queue()
        for question in made:
            assert queue.ask(question).option == KEEP
        assert len(queue.given) == 2
        assert len({q.id for q, _ in queue.given}) == 2
