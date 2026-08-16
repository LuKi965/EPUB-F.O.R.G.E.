"""The shop's leavings, and the publisher's page that must survive them.

WP-17 / D-019. Until now a *visible* watermark notice was always kept, on the
reasoning that a sentence the buyer is meant to read is the buyer's business.
The owner's answer was that it is his business precisely because he bought the
book — he has the receipts — and that the shop's sentence sits in the running
text of one of his books directly in front of the novel's first sentence, where
it spoils the page on every reader he owns.

So this deletes text somebody can read, which nothing else in the program does.
Three tests here matter more than the rest:

* the publisher's colophon is **not** touched — an editorial address, a phone
  number, an e-mail and an ISBN look superficially like a shop stamp and are the
  copyright page of somebody's book;
* the novel's first sentence survives a stamp glued to the front of it — which
  is why removal is by sentence and not by element;
* nothing happens at all unless somebody asked.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import watermark
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .test_dead_css_urls import book, rules_of

#: Word for word from Book 1, `OEBPS/Text/Section0000.xhtml`, where it is glued
#: to the front of the first sentence of the novel. The address is masked in the
#: book itself; it is masked again here because this file is public.
STAMP = (
    "This document is protected using an electronic watermark. "
    "Order ##46932 (l***k@example.com)"
)

#: Book 2, `OEBPS/Text/txt_0063.xhtml` — an ordinary publisher's colophon. It
#: carries an address, a telephone number, an e-mail and an ISBN, which is every
#: surface feature of a shop stamp, and it is the copyright page of a novel.
COLOPHON = (
    "Wydawnictwo Przykład sp. z o.o., ul. Testowa 12, 00-001 Warszawa. "
    "Telefon: 22 000 00 00. E-mail: biuro@przyklad.pl. ISBN 978-83-0000-000-0. "
    "Wszelkie prawa zastrzeżone."
)


def asked() -> Policy:
    policy = Policy.preset("preserve")
    policy.remove_shop_notices = True
    return policy


def page(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
        '<meta charset="utf-8"/><title>R</title></head>'
        f"<body>{body}</body></html>"
    ).encode("utf-8")


def text_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        return " ".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        )


def rebuilt(tmp_path, body: str, policy: Policy):
    source = book(
        tmp_path / "in.epub",
        "p { margin: 0 }",
        extra_files={"OEBPS/chapter.xhtml": page(body)},
    )
    return rebuild(source, str(tmp_path / "out.epub"), policy)


class TestTheDiscriminatorItself:
    """Before any plumbing: does the rule tell a sale from a book?"""

    @pytest.mark.parametrize(
        "sentence",
        [
            STAMP,
            "Order ##46932 (l***k@example.com)",
            "Zamówienie nr 12345",
            "Zakupione dla: Jan Kowalski",
            "Wygenerowane dla jan.kowalski@example.com",
            "Licensed to Jan Kowalski",
            "Purchased by Jan Kowalski",
            "Ten dokument jest chroniony znakiem wodnym",
        ],
    )
    def test_a_sentence_about_the_sale_is_the_shop(self, sentence):
        assert watermark.is_shop_notice(sentence) is True

    @pytest.mark.parametrize(
        "sentence",
        [
            COLOPHON,
            "Wszelkie prawa zastrzeżone.",
            "Copyright © 2020 by Jan Kowalski",
            "E-mail: biuro@przyklad.pl",
            "ISBN 978-83-0000-000-0",
            "Egzemplarz recenzencki",
            "This eBook is for the use of anyone anywhere at no cost",
            "Printed in Poland. First edition.",
            "Redakcja: Anna Nowak. Korekta: Piotr Wiśniewski.",
        ],
    )
    def test_a_sentence_about_the_book_is_not(self, sentence):
        """Every one of these was a candidate phrase that had to be left out.

        `copy` lives inside `copyright`; a Gutenberg volume says "license" at
        length about itself; "wszelkie prawa zastrzeżone" is the copyright
        notice. Matching any of them would delete a publisher's page.
        """
        assert watermark.is_shop_notice(sentence) is False


class TestTheFirstSentenceOfTheNovelSurvives:
    """The reason removal is by sentence rather than by element. In Book 1 the
    stamp is glued to the front of the opening line."""

    BODY = f"<p>{STAMP} Był chłodny, jasny dzień kwietnia.</p>"

    def test_the_stamp_goes(self, tmp_path):
        result = rebuilt(tmp_path, self.BODY, asked())
        assert result.status.wrote_a_file, result.report.to_text()
        assert "46932" not in text_of(result)
        assert "electronic watermark" not in text_of(result)

    def test_and_the_novel_stays(self, tmp_path):
        result = rebuilt(tmp_path, self.BODY, asked())
        assert "Był chłodny, jasny dzień kwietnia." in text_of(result)

    def test_the_paragraph_is_not_deleted_wholesale(self, tmp_path):
        """The failure this prevents: removing the element that contains the
        stamp, which would take the opening of the book with it."""
        result = rebuilt(tmp_path, self.BODY, asked())
        assert "<p" in text_of(result)


class TestThePublishersPageIsNotAShopNotice:
    """The negative test the whole feature stands or falls on."""

    def test_a_colophon_survives_with_the_switch_on(self, tmp_path):
        result = rebuilt(tmp_path, f"<p>{COLOPHON}</p>", asked())
        assert result.status.wrote_a_file, result.report.to_text()
        rebuilt_text = text_of(result)
        assert "biuro@przyklad.pl" in rebuilt_text
        assert "ISBN 978-83-0000-000-0" in rebuilt_text
        assert "Wszelkie prawa zastrzeżone" in rebuilt_text

    def test_and_nothing_is_reported_as_removed(self, tmp_path):
        result = rebuilt(tmp_path, f"<p>{COLOPHON}</p>", asked())
        assert "xhtml.shop-notice-removed" not in rules_of(result)

    def test_a_colophon_in_the_same_book_as_a_stamp_still_survives(self, tmp_path):
        """The realistic shape: both are in the book, and only one may go."""
        body = f"<p>{STAMP}</p><p>{COLOPHON}</p>"
        result = rebuilt(tmp_path, body, asked())
        rebuilt_text = text_of(result)
        assert "46932" not in rebuilt_text
        assert "biuro@przyklad.pl" in rebuilt_text


class TestNothingHappensUnlessAsked:
    BODY = f"<p>{STAMP} Był chłodny, jasny dzień kwietnia.</p>"

    def test_the_default_keeps_the_stamp(self, tmp_path):
        """S-02, and the reversal in D-019 does not touch the default: this is
        the only switch in the program that deletes readable text."""
        result = rebuilt(tmp_path, self.BODY, Policy.preset("preserve"))
        assert "46932" in text_of(result)

    def test_not_even_under_strict(self, tmp_path):
        """Conformance is not a reason to delete somebody's sentence, and a
        preset reaching this switch would be a preset deleting text."""
        result = rebuilt(tmp_path, self.BODY, Policy.preset("strict"))
        assert "46932" in text_of(result)

    def test_and_the_default_still_says_it_is_there(self, tmp_path):
        result = rebuilt(tmp_path, self.BODY, Policy.preset("preserve"))
        assert {"xhtml.watermark-kept", "xhtml.watermark-kept-personal-data"} & rules_of(
            result
        )


class TestTheReportNamesWhatWent:
    BODY = f"<p>{STAMP} Był chłodny, jasny dzień kwietnia.</p>"

    def test_the_removed_sentences_are_quoted_word_for_word(self, tmp_path):
        """The acceptance condition, and the right one: a count is not something
        anybody can check, and this deletes a person's book."""
        result = rebuilt(tmp_path, self.BODY, asked())
        said = next(
            f for f in result.report.findings if f.rule == "xhtml.shop-notice-removed"
        )
        assert "46932" in said.values["removed"]
        assert said.values["count"] >= 1
        assert said.values["documents"] == 1

    def test_it_is_not_also_reported_as_kept(self, tmp_path):
        """Two findings contradicting each other in one report is worse than
        either being absent."""
        result = rebuilt(tmp_path, self.BODY, asked())
        assert "xhtml.watermark-kept" not in rules_of(result)
        assert "xhtml.watermark-kept-personal-data" not in rules_of(result)


class TestTheTextGateLetsItThroughAndOnlyThis:
    def test_a_consented_removal_does_not_block_publication(self, tmp_path):
        """K1 refuses any book that lost text, which is exactly right and would
        refuse this one too. The removal is consented, so it is listed rather
        than refused — and the listing is the whole safeguard."""
        from epubforge.pipeline import REMOVES_TEXT_ON_PURPOSE

        assert "xhtml.shop-notice-removed" in REMOVES_TEXT_ON_PURPOSE
        result = rebuilt(tmp_path, self.__class__.BODY, asked())
        assert result.status.wrote_a_file, result.report.to_text()

    BODY = f"<p>{STAMP} Był chłodny, jasny dzień kwietnia.</p>"


class TestNoPageIsEverRemoved:
    def test_an_element_left_empty_stays(self, tmp_path):
        """The owner corrected me on precisely this: the job is the shop's
        leavings in the text, not documents. A rebuild that silently drops a
        spine item is a different program."""
        result = rebuilt(tmp_path, f"<p>{STAMP}</p><p>Rozdział pierwszy.</p>", asked())
        assert result.status.wrote_a_file, result.report.to_text()
        assert "Rozdział pierwszy." in text_of(result)
        with zipfile.ZipFile(result.output_path) as archive:
            documents = [n for n in archive.namelist() if n.endswith(".xhtml")]
        assert len(documents) >= 2, "nav plus the chapter — nothing was dropped"


class TestTheReportIsExactRatherThanApproximate:
    """Found by probing rather than by a test, and worth pinning because the
    first version got it wrong in the direction that matters.

    `Zakupione dla: Jan Kowalski` had the name removed along with the phrase —
    correctly — and reported only `Zakupione dla`. An understatement in the one
    message whose entire job is to let somebody check this feature.
    """

    def test_what_is_listed_is_what_actually_went(self):
        kept, removed = watermark.without_shop_notices("Zakupione dla: Jan Kowalski")
        assert kept == ""
        assert removed == ["Zakupione dla: Jan Kowalski"]

    def test_every_removed_fragment_is_absent_from_what_stays(self):
        text = (
            "This document is protected using an electronic watermark. "
            "Order ##46932 (l***k@example.com) Był chłodny, jasny dzień."
        )
        kept, removed = watermark.without_shop_notices(text)
        for fragment in removed:
            assert fragment not in kept

    def test_and_what_stays_is_absent_from_what_was_removed(self):
        """The other direction: a report that quoted a surviving sentence as
        removed would be just as useless, and harder to notice."""
        text = "Zakupione dla: Jan Kowalski. Rozdział pierwszy zaczyna się tutaj."
        kept, removed = watermark.without_shop_notices(text)
        assert kept == "Rozdział pierwszy zaczyna się tutaj."
        assert not any(kept in fragment for fragment in removed)


class TestAStampWrittenMidSentence:
    def test_the_shops_own_words_in_front_of_it_go_too(self):
        """`Ten egzemplarz zakupiony przez …` — the two words in front of the
        phrase belong to the shop's sentence, not to the book, and leaving them
        strands a fragment in the middle of a page."""
        kept, removed = watermark.without_shop_notices(
            "Ten egzemplarz zakupiony przez jan@example.com. Wszelkie prawa zastrzeżone."
        )
        assert kept == "Wszelkie prawa zastrzeżone."
        assert removed == ["Ten egzemplarz zakupiony przez jan@example.com."]

    def test_but_real_prose_in_front_of_it_stays(self):
        """The limit of the rule above. Where the words before the phrase are
        somebody's writing, they are kept — this errs towards keeping text,
        because a stranded fragment is visible and a deleted sentence is not."""
        kept, _ = watermark.without_shop_notices(
            "Anna otworzyła plik i zobaczyła napis zakupione dla: Jan Kowalski"
        )
        assert "Anna otworzyła plik i zobaczyła napis" in kept
