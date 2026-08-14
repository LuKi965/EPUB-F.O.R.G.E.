"""The whole way from a book to a changed word, and everywhere it stops short.

`test_hyphens.py` is the detector. This is the stage: what a rebuild reports,
what it asks, what it does with the answer, and — mostly — what it declines to
do without one.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.decisions import KEEP, Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import MODERN_NAV, write_zip

CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/package.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)

PACKAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:identifier id="i">urn:uuid:1</dc:identifier><dc:title>T</dc:title>'
    "<dc:language>pl</dc:language>"
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>'
    '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
    'properties="nav"/><item id="c" href="chapter.xhtml" '
    'media-type="application/xhtml+xml"/></manifest>'
    '<spine><itemref idref="c"/></spine></package>'
)


def book(path, body: str) -> str:
    page = (
        '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
        f'<meta charset="utf-8"/><title>Rozdział</title></head><body>{body}</body></html>'
    )
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": PACKAGE.encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": page.encode(),
        },
    )


#: One broken word, and the evidence for it twice over.
DAMAGED = (
    "<p>Stała przy oknie zupełnie obo-jętna na wszystko dookoła.</p>"
    "<p>Była obojętna wtedy i obojętna później.</p>"
)


def text_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        return "".join(
            archive.read(name).decode("utf-8", "replace")
            for name in archive.namelist()
            if name.endswith("chapter.xhtml") or "0000" in name
        )


def rules_of(result) -> set:
    return {finding.rule for finding in result.report.findings if finding.rule}


class Joins:
    """Somebody who joins whatever they are asked about."""

    def __init__(self):
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(option="join")


class Keeps:
    def ask(self, question):
        return Answer(option=KEEP)


def rebuild_with(source, tmp_path, asker=None, **policy):
    return rebuild(
        source,
        str(tmp_path / "out.epub"),
        Policy.preset("preserve", validate_before_publish="off", **policy),
        asker=asker,
    )


class TestItCountsWithoutBeingAsked:
    def test_the_report_says_how_many_there_are(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", DAMAGED),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert "hyphens.detected" in rules_of(result)

    def test_a_clean_book_says_nothing(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", "<p>Zwyczajne zdanie bez żadnych łączników.</p>"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert "hyphens.detected" not in rules_of(result)

    def test_the_switch_turns_detection_off(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", DAMAGED),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", detect_hyphens=False, validate_before_publish="off"),
        )
        assert "hyphens.detected" not in rules_of(result)


class TestNobodyAskedMeansNothingChanged:
    def test_the_word_keeps_its_hyphen(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", DAMAGED),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert "obo-jętna" in text_of(result)

    def test_and_the_report_says_it_was_left_alone(self, tmp_path):
        result = rebuild(
            book(tmp_path / "in.epub", DAMAGED),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert "hyphens.left-alone" in rules_of(result)

    def test_strict_does_not_join_them_either(self, tmp_path):
        """Strict is a promise the output conforms. A hyphen inside a word is
        not a conformance defect, and joining one to look tidier would be this
        program editing somebody's prose on its own authority."""
        result = rebuild(
            book(tmp_path / "in.epub", DAMAGED),
            str(tmp_path / "out.epub"),
            Policy.preset("strict", validate_before_publish="off"),
        )
        assert "obo-jętna" in text_of(result)


class TestAnsweringChangesTheWord:
    def test_join_writes_the_whole_word(self, tmp_path):
        result = rebuild_with(book(tmp_path / "in.epub", DAMAGED), tmp_path, Joins())
        assert result.status.wrote_a_file, result.report.to_text()
        text = text_of(result)
        assert "obo-jętna" not in text
        assert "obojętna na wszystko" in text

    def test_it_is_reported_as_a_fix(self, tmp_path):
        result = rebuild_with(book(tmp_path / "in.epub", DAMAGED), tmp_path, Joins())
        assert "hyphens.joined" in rules_of(result)

    def test_it_is_in_the_change_ledger_as_irreversible(self, tmp_path):
        """The only rule in this program that changes a word. Nothing in the
        rebuilt file records that it was once written otherwise."""
        result = rebuild_with(book(tmp_path / "in.epub", DAMAGED), tmp_path, Joins())
        entry = next(
            change for change in result.report.changes if change.rule == "hyphens.joined"
        )
        assert not entry.reversible
        assert entry.risk.value == "content"

    def test_keeping_it_deliberately_changes_nothing(self, tmp_path):
        result = rebuild_with(book(tmp_path / "in.epub", DAMAGED), tmp_path, Keeps())
        assert "obo-jętna" in text_of(result)

    def test_only_the_confirmed_ones_are_put_to_anybody(self, tmp_path):
        """The measurement that shaped this: 67 confirmed against 189 without
        evidence, nearly all of which are real words."""
        asker = Joins()
        rebuild_with(
            book(
                tmp_path / "in.epub",
                DAMAGED + "<p>Znał savoir-vivre i grał w ping-ponga.</p>",
            ),
            tmp_path,
            asker,
        )
        assert len(asker.asked) == 1
        assert "obo-jętna" in asker.asked[0].summary


class TestTheTextIsCheckedAfterwards:
    def test_a_word_written_by_hand_is_accepted(self, tmp_path):
        class Writes:
            def ask(self, _question):
                return Answer(option="write", value="obojętna")

        result = rebuild_with(book(tmp_path / "in.epub", DAMAGED), tmp_path, Writes())
        assert "obojętna na wszystko" in text_of(result)

    def test_an_empty_hand_written_answer_changes_nothing(self, tmp_path):
        class Blank:
            def ask(self, _question):
                return Answer(option="write", value="")

        result = rebuild_with(book(tmp_path / "in.epub", DAMAGED), tmp_path, Blank())
        assert "obo-jętna" in text_of(result)

    def test_a_front_end_that_falls_over_leaves_the_book_alone(self, tmp_path):
        class Broken:
            def ask(self, _question):
                raise RuntimeError("okno się zamknęło")

        result = rebuild_with(book(tmp_path / "in.epub", DAMAGED), tmp_path, Broken())
        assert "obo-jętna" in text_of(result)
        assert result.status.wrote_a_file


class TestAnswersSurviveToTheNextRebuild:
    def test_the_second_run_does_not_ask_again(self, tmp_path):
        from epubforge import decisions

        source = book(tmp_path / "in.epub", DAMAGED)
        asker = Joins()
        result = rebuild_with(source, tmp_path, asker)
        assert len(asker.asked) == 1
        assert result.status.wrote_a_file

        # The pipeline does not write the store itself — the front end does,
        # once the person has finished. Simulated here.
        queue = decisions.Queue()
        queue.given = [(asker.asked[0], Answer(option="join"))]
        queue.save(decisions.answers_path(source), source=source)

        class Never:
            def ask(self, _question):
                raise AssertionError("asked a question that was already answered")

        again = rebuild_with(source, tmp_path, Never())
        assert "obojętna na wszystko" in text_of(again)

    def test_a_changed_book_makes_the_store_unusable_and_says_so(self, tmp_path):
        from epubforge import decisions

        source = book(tmp_path / "in.epub", DAMAGED)
        asker = Joins()
        rebuild_with(source, tmp_path, asker)
        queue = decisions.Queue()
        queue.given = [(asker.asked[0], Answer(option="join"))]
        queue.save(decisions.answers_path(source), source=source)

        book(tmp_path / "in.epub", DAMAGED + "<p>Nowy akapit.</p>")
        result = rebuild_with(source, tmp_path, Keeps())
        assert "decisions.store-unusable" in rules_of(result)
        assert "obo-jętna" in text_of(result)

    def test_the_switch_turns_remembering_off(self, tmp_path):
        from epubforge import decisions

        source = book(tmp_path / "in.epub", DAMAGED)
        asker = Joins()
        rebuild_with(source, tmp_path, asker)
        queue = decisions.Queue()
        queue.given = [(asker.asked[0], Answer(option="join"))]
        queue.save(decisions.answers_path(source), source=source)

        result = rebuild_with(source, tmp_path, Keeps(), remember_decisions=False)
        assert "obo-jętna" in text_of(result)


class TestTheTextInvariantStillHolds:
    def test_nothing_but_the_agreed_words_moved(self, tmp_path):
        """K1 says no character of the text is lost, and joining a word loses
        one on purpose — so the invariant is restated rather than dropped: the
        before text with exactly the agreed replacements applied must equal the
        after text."""
        from epubforge.stages.hyphens import HyphenStage

        planned = [(type("C", (), {"word": "obo-jętna"})(), "obojętna")]
        assert HyphenStage._only_the_hyphens_went(
            "Była obo-jętna dziś.", "Była obojętna dziś.", planned
        )

    def test_a_pass_that_did_more_than_agreed_is_caught(self, tmp_path):
        from epubforge.stages.hyphens import HyphenStage

        planned = [(type("C", (), {"word": "obo-jętna"})(), "obojętna")]
        assert not HyphenStage._only_the_hyphens_went(
            "Była obo-jętna dziś.", "Była obojętna wczoraj.", planned
        )
