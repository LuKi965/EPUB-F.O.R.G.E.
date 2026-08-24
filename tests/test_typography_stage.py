"""The stage that changes text on purpose, and the check that it did not lose it.

Every other stage moves markup around a text it may not touch. This one edits
the text, so the interesting tests are not "does the rule work" — they are
"what happens when a rule is wrong", and the answer has to be that the document
comes back exactly as it arrived.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import typography
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Level

from tests.factory import write_zip


def book(tmp_path, language, body, name="in.epub"):
    package = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Proba</dc:title><dc:language>{language}</dc:language>
    <dc:identifier id="pub-id">urn:uuid:6b1d0f6e-0000-4000-8000-0000000000cc</dc:identifier>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="doc" href="doc.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="doc"/></spine>
</package>
"""
    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Spis</title>'
        '</head><body><nav epub:type="toc"><ol><li>'
        '<a href="doc.xhtml">Strona</a></li></ol></nav></body></html>\n'
    )
    document = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Strona</title>'
        f"</head><body>{body}</body></html>\n"
    )
    container = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/package.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
    )
    return write_zip(
        str(tmp_path / name),
        {
            "META-INF/container.xml": container.encode(),
            "OEBPS/package.opf": package.encode(),
            "OEBPS/nav.xhtml": nav.encode(),
            "OEBPS/doc.xhtml": document.encode(),
        },
    )


def forge(tmp_path, body, *, language="pl", typography=True, name="out"):
    source = book(tmp_path, language, body, name=f"{name}-in.epub")
    policy = Policy.preset("preserve", typography=typography)
    result = rebuild(source, str(tmp_path / f"{name}.epub"), policy)
    assert result.output_path, result.report.to_text()
    with zipfile.ZipFile(result.output_path) as archive:
        path = next(n for n in archive.namelist() if n.endswith("doc.xhtml"))
        return result, archive.read(path).decode()


class TestItIsOffUntilSomebodyAsks:
    """The one pass that changes the text. No preset reaches it."""

    @pytest.mark.parametrize("preset", ["preserve", "strict", "minimal"])
    def test_no_preset_turns_it_on(self, preset):
        assert Policy.preset(preset).typography is False

    def test_three_dots_survive_by_default(self, tmp_path):
        _, html = forge(tmp_path, "<p>Czekaj...</p>", typography=False, name="a")
        assert "Czekaj..." in html

    def test_container_only_mode_ignores_the_flag(self, tmp_path):
        """Byte-for-byte is a promise about the content files, and it outranks
        a switch."""
        source = book(tmp_path, "pl", "<p>Czekaj...</p>", name="min-in.epub")
        policy = Policy.preset("minimal", typography=True)
        result = rebuild(source, str(tmp_path / "min.epub"), policy)
        with zipfile.ZipFile(result.output_path) as archive:
            path = next(n for n in archive.namelist() if n.endswith("doc.xhtml"))
            assert "Czekaj..." in archive.read(path).decode()


class TestTheEllipsis:
    def test_three_dots_become_one_character(self, tmp_path):
        _, html = forge(tmp_path, "<p>Czekaj... juz ide.</p>", name="b")
        assert "Czekaj… juz ide." in html

    def test_four_dots_are_somebody_elses_punctuation(self, tmp_path):
        """An ellipsis is not longer than itself, and a run of four is a
        decision rather than a typing shortcut."""
        _, html = forge(tmp_path, "<p>Czekaj....</p>", name="c")
        assert "Czekaj...." in html

    def test_it_is_reported_with_a_count(self, tmp_path):
        result, _ = forge(tmp_path, "<p>A... b... c...</p>", name="d")
        found = [f for f in result.report.findings
                 if f.rule == "typography.ellipsis-normalised"]
        assert found and found[0].values["count"] == 3


class TestTheConjunctions:
    def test_a_single_letter_conjunction_is_bound_to_its_word(self, tmp_path):
        _, html = forge(tmp_path, "<p>Poszedl w las i zniknal.</p>", name="e")
        assert "w las" in html
        assert "i zniknal" in html

    def test_it_is_a_polish_rule_and_asks_the_book_first(self, tmp_path):
        """Bound single letters are Polish typographic convention. An English
        book saying "a cat" has not made a mistake."""
        _, html = forge(tmp_path, "<p>A cat and a dog.</p>", language="en", name="f")
        assert " " not in html

    def test_a_letter_inside_a_word_is_not_a_conjunction(self, tmp_path):
        _, html = forge(tmp_path, "<p>biało-czerwony i ptak</p>", name="g")
        assert "biało-czerwony" in html

    def test_what_is_already_bound_is_not_bound_twice(self, tmp_path):
        result, html = forge(tmp_path, "<p>Poszedl w las.</p>", name="h")
        assert html.count("w las") == 1
        assert not [f for f in result.report.findings
                    if f.rule == "typography.conjunctions-bound"]


class TestItDoesNotReachWhereItMayNot:
    def test_code_keeps_its_dots(self, tmp_path):
        _, html = forge(tmp_path, "<p><code>range(1...5)</code></p>", name="i")
        assert "range(1...5)" in html

    def test_a_foreign_language_span_is_left_alone(self, tmp_path):
        body = '<p>Polski...</p><p xml:lang="en">English...</p>'
        _, html = forge(tmp_path, body, name="j")
        assert "Polski…" in html
        assert "English..." in html


class TestTheCheckIsTheWholePoint:
    """K1 is not switched off for this stage, it is replaced by something that
    can survive a rule which edits text. These tests are the replacement."""

    def test_a_rule_that_eats_text_reverts_the_document(self, tmp_path, monkeypatch):
        """The failure this stage exists to make impossible: a rule that loses
        a word. The document has to come back exactly as it arrived, and the
        report has to say so.

        The sentence carries three dots so that the pass has a reason to run at
        all: since filar E each rule is asked about and a rule with no
        candidates never reaches the document. That is the honest shape of this
        test — the guard is exercised on a pass that was actually invited in."""
        from epubforge.stages import typography as stage

        def eats(root, language, marks, agreed):
            for element, attribute in stage.typography.text_nodes(root):
                text = getattr(element, attribute)
                if text and "zniknie" in text:
                    setattr(element, attribute, text.replace("zniknie", ""))
                    return (1, 0, 0)
            return (0, 0, 0)

        monkeypatch.setattr(stage.TypographyStage, "_repair", staticmethod(eats))
        result, html = forge(tmp_path, "<p>To slowo zniknie stad... i tyle.</p>", name="k")
        assert "zniknie" in html
        assert "typography.reverted" in {f.rule for f in result.report.findings}

    def test_the_revert_is_a_warning_not_a_silent_no_op(self, tmp_path, monkeypatch):
        from epubforge.stages import typography as stage

        def eats(root, language, marks, agreed):
            for element, attribute in stage.typography.text_nodes(root):
                text = getattr(element, attribute)
                if text and text.strip():
                    setattr(element, attribute, text[:-3])
                    return (1, 0, 0)
            return (0, 0, 0)

        monkeypatch.setattr(stage.TypographyStage, "_repair", staticmethod(eats))
        result, _ = forge(tmp_path, "<p>Zdanie ktore straci ogon... i juz.</p>", name="l")
        found = [f for f in result.report.findings if f.rule == "typography.reverted"]
        assert found and found[0].level is Level.WARN

    def test_an_honest_rule_is_not_reverted(self, tmp_path):
        result, html = forge(tmp_path, "<p>Czekaj... w lesie.</p>", name="m")
        assert "typography.reverted" not in {f.rule for f in result.report.findings}
        assert "Czekaj…" in html


class TestTheQuotes:
    """Only the straight `"` is retyped: a curly mark already says which end of
    a pair it is, a straight one says nothing, and it is also the one a book
    gets wrong because it is what a keyboard produces."""

    #: Enough curly Polish quotes to settle a convention, plus straight ones
    #: that contradict it.
    MIXED = (
        "<p>„Tak” powiedział.</p>" * 12
        + '<p>Potem dodał "moze" i wyszedl.</p>'
    )

    def test_a_straight_pair_becomes_the_books_own_convention(self, tmp_path):
        result, html = forge(tmp_path, self.MIXED, name="q1")
        assert "„moze”" in html
        found = [f for f in result.report.findings if f.rule == "typography.quotes-retyped"]
        assert found and found[0].values["convention"] == "polish"

    def test_the_curly_ones_it_already_had_are_untouched(self, tmp_path):
        _, html = forge(tmp_path, self.MIXED, name="q2")
        assert html.count("„Tak”") == 12

    def test_a_quotation_crossing_an_element_still_closes(self, tmp_path):
        """`<p>"He said <em>no</em>,"</p>` — a rule looking only at the
        characters either side inside one text node gets the second mark wrong
        every time."""
        body = "<p>„Tak” powiedział.</p>" * 12 + '<p>"Nie <em>chce</em> tego"</p>'
        _, html = forge(tmp_path, body, name="q3")
        assert "„Nie " in html and 'tego”' in html

    def test_a_book_with_no_settled_convention_is_left_alone(self, tmp_path):
        """Two conventions in equal measure is a fact about the book, and
        picking one would impose an opinion on half of it."""
        body = "<p>„Tak” rzekl.</p>" * 10 + "<p>«Tak» rzekl.</p>" * 10 + '<p>"Tak"</p>'
        result, html = forge(tmp_path, body, name="q4")
        assert '"Tak"' in html
        assert "typography.quotes-unsettled" in {f.rule for f in result.report.findings}

    def test_a_book_that_only_ever_used_straight_quotes_is_left_alone(self, tmp_path):
        """That book has not made a mistake, and retyping a convention into
        itself is not a repair."""
        body = '<p>"Tak" rzekl.</p>' * 12
        _, html = forge(tmp_path, body, name="q5")
        assert html.count('"Tak"') == 12

    def test_the_book_decides_and_not_the_typographic_ideal(self, tmp_path):
        """A book set in guillemets has made a decision (K5)."""
        body = "<p>«Tak» rzekl.</p>" * 12 + '<p>Potem "nie".</p>'
        _, html = forge(tmp_path, body, name="q6")
        assert "«nie»" in html


# ---------------------------------------------------------------------------
# Filar E: the pass asks instead of being switched on, and counts the prose
# rather than the stylesheet.
# ---------------------------------------------------------------------------


class Answering:
    """Answers every typography question the same way, and remembers them."""

    def __init__(self, option: str = "repair"):
        self.option = option
        self.asked: list = []

    def ask(self, question):
        self.asked.append(question)
        from epubforge.decisions import Answer

        return Answer(option=self.option, apply_to_group=True)


def ask_about(tmp_path, body, *, option="repair", language="pl", name="ask", **policy):
    """Rebuild with somebody at the window and the flag *off*."""
    source = book(tmp_path, language, body, name=f"{name}-in.epub")
    answering = Answering(option)
    result = rebuild(
        source,
        str(tmp_path / f"{name}.epub"),
        Policy.preset("preserve", typography=False, **policy),
        resolver=answering,
    )
    assert result.output_path, result.report.to_text()
    with zipfile.ZipFile(result.output_path) as archive:
        path = next(n for n in archive.namelist() if n.endswith("doc.xhtml"))
        return result, archive.read(path).decode(), answering


def ours(answering) -> list:
    return [q for q in answering.asked if q.group.startswith("typography:")]


class TestItAsksInsteadOfBeingSwitchedOn:
    """The plan's word for filar E was *wyłącznie trybem pytań*, and until now
    the pass had no way of being asked — only of being switched on. A feature
    reachable by one tick that no preset sets and that changes text without
    a word is, in practice, a feature nobody uses and nobody consented to."""

    def test_three_dots_are_asked_about_and_repaired_on_a_yes(self, tmp_path):
        result, html, answering = ask_about(
            tmp_path, "<p>Czekaj... juz ide.</p>", name="r1"
        )
        assert [q.group for q in ours(answering)] == ["typography:ellipsis"]
        assert "Czekaj… juz ide." in html

    def test_a_no_leaves_every_character_alone(self, tmp_path):
        result, html, answering = ask_about(
            tmp_path, "<p>Czekaj... juz ide.</p>", option="keep", name="r2"
        )
        assert ours(answering)
        assert "Czekaj... juz ide." in html
        assert "typography.ellipsis-normalised" not in {
            f.rule for f in result.report.findings
        }

    def test_a_no_is_still_reported(self, tmp_path):
        """S-05 leaves the book alone; it does not leave the reader
        uninformed. A book with a thousand candidates and a book with none
        must not produce the same silent report."""
        result, _, _ = ask_about(
            tmp_path, "<p>A... b... c...</p>", option="keep", name="r3"
        )
        found = [
            f for f in result.report.findings
            if f.rule == "typography.ellipsis-left-alone"
        ]
        assert found and found[0].values["count"] == 3
        assert found[0].level is Level.PRESERVED

    def test_nobody_answering_changes_nothing(self, tmp_path):
        source = book(tmp_path, "pl", "<p>Czekaj... juz ide.</p>", name="r4-in.epub")
        result = rebuild(
            source, str(tmp_path / "r4.epub"), Policy.preset("preserve", typography=False)
        )
        with zipfile.ZipFile(result.output_path) as archive:
            path = next(n for n in archive.namelist() if n.endswith("doc.xhtml"))
            assert "Czekaj..." in archive.read(path).decode()

    def test_the_flag_is_a_standing_yes_and_asks_nothing(self, tmp_path):
        """Kept for a batch with nobody at the window — the same shape the
        mojibake repair uses, and the reason the old behaviour is not lost."""
        source = book(tmp_path, "pl", "<p>Czekaj... juz ide.</p>", name="r5-in.epub")
        answering = Answering("keep")
        result = rebuild(
            source,
            str(tmp_path / "r5.epub"),
            Policy.preset("preserve", typography=True),
            resolver=answering,
        )
        assert not ours(answering)
        with zipfile.ZipFile(result.output_path) as archive:
            path = next(n for n in archive.namelist() if n.endswith("doc.xhtml"))
            assert "Czekaj…" in archive.read(path).decode()

    def test_switching_the_detector_off_asks_nothing(self, tmp_path):
        _, html, answering = ask_about(
            tmp_path, "<p>Czekaj... juz ide.</p>", name="r6", detect_typography=False
        )
        assert not ours(answering)
        assert "Czekaj..." in html


class TestOneQuestionPerRule:
    """Three rules, three questions. Somebody can want the ellipsis and not
    the non-breaking spaces, and one question would make that impossible to
    say."""

    BOOK = "<p>„Tak” rzekl w lesie...</p>" * 12 + '<p>Potem "nie" i tyle.</p>'

    def test_each_rule_puts_its_own(self, tmp_path):
        _, _, answering = ask_about(tmp_path, self.BOOK, name="s1")
        assert {q.group for q in ours(answering)} == {
            "typography:ellipsis",
            "typography:conjunctions",
            "typography:quotes",
        }

    def test_a_rule_with_nothing_to_do_puts_none(self, tmp_path):
        _, _, answering = ask_about(
            tmp_path, "<p>Zdanie zupelnie zwyczajne.</p>", name="s2"
        )
        assert not ours(answering)

    def test_the_question_says_how_many_and_shows_some(self, tmp_path):
        """A count says how much; an excerpt says what. Both are needed to
        answer with any confidence."""
        _, _, answering = ask_about(tmp_path, "<p>A... b... c...</p>", name="s3")
        question = next(q for q in ours(answering) if q.group == "typography:ellipsis")
        assert "3" in question.summary
        assert "A… b… c…" not in question.detail, "the excerpt must show the source"
        assert "A... b..." in question.detail

    def test_answering_one_does_not_answer_another(self, tmp_path):
        """The whole reason for three questions rather than one."""

        class OnlyDots(Answering):
            def ask(self, question):
                self.asked.append(question)
                from epubforge.decisions import Answer

                return Answer(
                    option="repair" if question.group == "typography:ellipsis" else "keep",
                    apply_to_group=True,
                )

        source = book(tmp_path, "pl", "<p>Poszedl w las i zniknal...</p>", name="s4-in.epub")
        answering = OnlyDots()
        result = rebuild(
            source,
            str(tmp_path / "s4.epub"),
            Policy.preset("preserve", typography=False),
            resolver=answering,
        )
        with zipfile.ZipFile(result.output_path) as archive:
            path = next(n for n in archive.namelist() if n.endswith("doc.xhtml"))
            html = archive.read(path).decode()
        assert "zniknal…" in html, "the answered rule did not run"
        assert " " not in html, "the declined rule ran anyway"

    def test_and_the_same_the_other_way_round(self, tmp_path):
        """The mirror case, and it is here because its absence was a dead
        tooth. With only one rule in play a "no" makes the agreed set empty and
        the pass never reaches the document at all — so the guard *inside* the
        repair was never exercised, and a version that always normalised the
        ellipsis passed every test in this file. It has to be a book where one
        rule is agreed to and another refused."""

        class OnlySpaces(Answering):
            def ask(self, question):
                self.asked.append(question)
                from epubforge.decisions import Answer

                return Answer(
                    option="keep" if question.group == "typography:ellipsis" else "repair",
                    apply_to_group=True,
                )

        source = book(tmp_path, "pl", "<p>Poszedl w las i zniknal...</p>", name="s5-in.epub")
        answering = OnlySpaces()
        result = rebuild(
            source,
            str(tmp_path / "s5.epub"),
            Policy.preset("preserve", typography=False),
            resolver=answering,
        )
        with zipfile.ZipFile(result.output_path) as archive:
            path = next(n for n in archive.namelist() if n.endswith("doc.xhtml"))
            html = archive.read(path).decode()
        assert " " in html, "the answered rule did not run"
        assert "zniknal..." in html, "the declined rule ran anyway"

    def test_a_declined_quote_rule_leaves_the_stray_mark(self, tmp_path):
        """Third rule, same guard, and it needed its own case for the same
        reason as the one above: the quote rule is the only one that also needs
        a settled convention, so it is the only one whose guard can hide behind
        that condition."""

        class NotTheQuotes(Answering):
            def ask(self, question):
                self.asked.append(question)
                from epubforge.decisions import Answer

                return Answer(
                    option="keep" if question.group == "typography:quotes" else "repair",
                    apply_to_group=True,
                )

        body = "<p>\u201eTak\u201d rzekl.</p>" * 12 + '<p>Potem "nie", czekaj...</p>'
        source = book(tmp_path, "pl", body, name="s6-in.epub")
        answering = NotTheQuotes()
        result = rebuild(
            source,
            str(tmp_path / "s6.epub"),
            Policy.preset("preserve", typography=False),
            resolver=answering,
        )
        with zipfile.ZipFile(result.output_path) as archive:
            path = next(n for n in archive.namelist() if n.endswith("doc.xhtml"))
            html = archive.read(path).decode()
        assert "czekaj\u2026" in html, "the answered rule did not run"
        assert '"nie"' in html, "the declined rule ran anyway"


class TestTheConventionIsReadFromTheProseOnly:
    """Measured on 160 books: twelve get a different answer once `<style>` and
    `<script>` are excluded — nine that read as "straight" have no settled
    convention at all, and three change to a real one. A stylesheet is full of
    straight quotes, and a convention read out of one is not the book's."""

    def test_a_stylesheet_cannot_make_a_book_look_straight(self, tmp_path):
        css = "".join(
            'p.k%d:before{content:"x";font-family:"Serif"}' % n for n in range(40)
        )
        body = f"<style>{css}</style>" + "<p>„Tak” rzekl.</p>" * 12 + '<p>Potem "nie".</p>'
        _, html, _ = ask_about(tmp_path, body, name="t1")
        # With the CSS counted the book reads as "straight" and nothing is
        # retyped; counted over the prose it is Polish and the stray mark goes.
        assert "„nie”" in html

    def test_the_stylesheet_itself_is_never_retyped(self, tmp_path):
        css = 'p:before{content:"x"}'
        body = f"<style>{css}</style>" + "<p>„Tak” rzekl.</p>" * 12 + '<p>Potem "nie".</p>'
        _, html, _ = ask_about(tmp_path, body, name="t2")
        assert 'content:"x"' in html.replace(" ", "")


class TestASeamIsNotAPlaceToGuess:
    """Two defects met here, and the second is why the first could not simply
    be loosened.

    A paragraph ending `poszukiwań.` and the next opening `...i wtedy` is a run
    of four dots to everything that reads the document as a stream — and both
    guards downstream do exactly that. Measured on 160 books: four documents
    came back reverted, one of them losing a hundred and forty honest repairs;
    and once the stage's own guard was corrected to compare piece by piece, the
    same seam refused the whole *book* at K1 instead, which is worse.

    So the rule declines at a seam it cannot see past. Conservative, and
    consistent: everything reading this text later reads it joined, and a rule
    may not be the only party with a different opinion.
    """

    #: A full stop, a paragraph break, and three dots.
    SEAM = "<p>Doszedł do celu poszukiwań.</p><p>...i wtedy zobaczył.</p>"

    def test_the_dots_at_the_seam_are_left_alone(self, tmp_path):
        result, html = forge(tmp_path, self.SEAM, name="u1")
        assert "<p>...i wtedy zobaczył.</p>" in html
        assert "poszukiwań.</p>" in html

    def test_and_the_book_is_written(self, tmp_path):
        """The point of declining rather than folding: K1 compares the whole
        reading order, and a dot followed by an ellipsis where the source had
        four dots is a book it refuses outright."""
        result, _ = forge(tmp_path, self.SEAM, name="u2")
        rules = {f.rule for f in result.report.findings}
        assert "package.text-lost" not in rules
        assert "typography.reverted" not in rules

    def test_the_rest_of_the_document_is_still_repaired(self, tmp_path):
        """The seam declines itself, not the document around it."""
        _, html = forge(
            tmp_path, self.SEAM + "<p>Czekaj... juz ide.</p>", name="u3"
        )
        assert "Czekaj… juz ide." in html
        assert "<p>...i wtedy zobaczył.</p>" in html

    def test_the_question_counts_what_the_answer_will_do(self, tmp_path):
        """A question saying "2 places" that then repairs one is a question
        somebody answered about something else."""
        _, _, answering = ask_about(
            tmp_path, self.SEAM + "<p>Czekaj... juz ide.</p>", name="u4"
        )
        question = next(q for q in ours(answering) if q.group == "typography:ellipsis")
        assert "1" in question.summary

    def test_a_rule_that_moves_text_between_nodes_is_still_refused(self, tmp_path, monkeypatch):
        """The guard compares piece by piece, which is *stricter* than the
        whole-document comparison it replaced: text carried from one node into
        another passes that one and fails this."""
        from epubforge.stages import typography as stage

        def moves(root, language, marks, agreed):
            nodes = [
                (element, attribute)
                for element, attribute in stage.typography.text_nodes(root)
                if getattr(element, attribute) and getattr(element, attribute).strip()
            ]
            if len(nodes) < 2:
                return (0, 0, 0)
            (one, first), (two, second) = nodes[0], nodes[1]
            text = getattr(one, first)
            setattr(one, first, text[:-6])
            setattr(two, second, text[-6:] + getattr(two, second))
            return (1, 0, 0)

        monkeypatch.setattr(stage.TypographyStage, "_repair", staticmethod(moves))
        result, html = forge(
            tmp_path, "<p>Pierwszy akapit...</p><p>Drugi akapit.</p>", name="u5"
        )
        assert "typography.reverted" in {f.rule for f in result.report.findings}
        assert "Pierwszy akapit..." in html


class TestTheSeamRuleItself:
    """`ellipses` in isolation, because the interesting cases are cheap here
    and expensive through a rebuild."""

    def test_three_dots_alone_are_folded(self):
        from epubforge.stages.typography import ellipses

        assert ellipses("Czekaj... juz") == ("Czekaj… juz", 1)

    def test_four_dots_are_left_alone(self):
        from epubforge.stages.typography import ellipses

        assert ellipses("Czekaj....") == ("Czekaj....", 0)

    def test_a_dot_in_the_node_before_makes_it_four(self):
        from epubforge.stages.typography import ellipses

        assert ellipses("...i wtedy", left=".") == ("...i wtedy", 0)

    def test_a_dot_in_the_node_after_makes_it_four(self):
        from epubforge.stages.typography import ellipses

        assert ellipses("wtedy...", right=".") == ("wtedy...", 0)

    def test_an_ordinary_neighbour_changes_nothing(self):
        from epubforge.stages.typography import ellipses

        assert ellipses("...i wtedy", left="a", right="b") == ("…i wtedy", 1)

    def test_the_neighbours_never_end_up_in_the_text(self):
        """The one way this could quietly corrupt a book: returning the padded
        string instead of the slice of it that belongs to this node."""
        from epubforge.stages.typography import ellipses

        assert ellipses("a... b... c", left="X", right="Y") == ("a… b… c", 2)


class TestRangesAreAskedPlaceByPlace:
    """The owner's decision, against my recommendation: *„pytanie jest zawsze
    najlepsze w takich kwestiach. Human in the loop."*

    So the rule exists — and everything below is what makes a question worth
    answering. Measured over 160 books: 200 candidates by shape, of which the
    form sieves reject 158, leaving 42 in 17 books, at most twelve in one and
    usually two or three. Among those forty-two: real ranges (`w latach
    1996-2001`, dates on a gravestone) and real non-ranges (a licence plate,
    a grade of motor oil, a police radio code). No form test separates those,
    so the program shows them and asks.
    """

    #: One of each: a range, a postal code, a telephone number, a score, a
    #: label, and a time that is not two whole numbers.
    BOOK = (
        "<p>W latach 1996-2001 mieszkał tam.</p>"
        "<p>Adres: 60-171 Poznań, tel. 621-9288.</p>"
        "<p>Wynik meczu 27-18, rozdział 1-2: Tytuł.</p>"
        "<p>Godziny 10-11.30 rano.</p>"
    )

    def test_only_the_range_is_offered(self, tmp_path):
        _, _, answering = ask_about(tmp_path, self.BOOK, option="keep", name="w1")
        question = next(
            q for q in ours(answering) if q.group.startswith("typography:ranges")
        )
        assert "1" in question.summary
        assert "1996-2001" in question.detail
        for other in ("60-171", "621-9288", "27-18", "1-2", "10-11"):
            assert other not in question.detail, other

    def test_a_yes_changes_the_range_and_nothing_else(self, tmp_path):
        _, html, _ = ask_about(tmp_path, self.BOOK, name="w2")
        assert "1996–2001" in html
        for untouched in ("60-171", "621-9288", "27-18", "1-2:", "10-11.30"):
            assert untouched in html, untouched

    def test_a_no_leaves_the_hyphen(self, tmp_path):
        result, html, _ = ask_about(tmp_path, self.BOOK, option="keep", name="w3")
        assert "1996-2001" in html
        assert "typography.ranges-left-alone" in {f.rule for f in result.report.findings}

    def test_every_place_is_shown_not_a_sample(self, tmp_path):
        """Three examples would be asking somebody to vouch for a list after
        seeing part of it. The other three rules show three; this one shows
        them all."""
        body = "".join(
            f"<p>W latach {1900 + n}-{1910 + n} coś się działo.</p>" for n in range(7)
        )
        _, _, answering = ask_about(tmp_path, body, option="keep", name="w4")
        question = next(
            q for q in ours(answering) if q.group.startswith("typography:ranges")
        )
        assert question.detail.count("…") >= 14, question.detail

    def test_the_answer_stops_at_this_book(self, tmp_path):
        """The whole reason this group is not `typography:ranges`. A list of
        numeric ranges is a different list in every book, so "yes to all of
        them" cannot mean the next book's list — which will contain somebody's
        licence plate."""
        _, _, answering = ask_about(tmp_path, self.BOOK, option="keep", name="w5")
        question = next(
            q for q in ours(answering) if q.group.startswith("typography:ranges")
        )
        assert question.group != "typography:ranges"
        assert question.group.startswith("typography:ranges:")

    def test_the_other_rules_still_share_one_group(self, tmp_path):
        """The other side of it: an ellipsis is the same thing in every book and
        one answer must still settle the shelf."""
        _, _, answering = ask_about(
            tmp_path, "<p>Czekaj... juz ide.</p>", option="keep", name="w6"
        )
        groups = {q.group for q in ours(answering)}
        assert "typography:ellipsis" in groups


class TestTheSieveItself:
    """Each rejection is by form, never by meaning — there is no list of words
    here and there is not going to be one. Tested one sieve at a time so a
    failure names which."""

    def test_a_plain_range_survives(self):
        assert typography.ranges("w latach 1996-2001 i potem") == [(9, 18)]

    def test_a_label_is_rejected(self):
        assert typography.ranges("rozdział 1-2: Tytuł") == []

    def test_a_postal_code_is_rejected(self):
        """By the length sieve, not by a sieve of its own: `dd-ddd` is uneven
        by definition. A separate postcode test used to run first and could
        never change an outcome — only the reason string — which is why it is
        gone."""
        assert typography.ranges("kod 60-171 Poznań") == []

    def test_uneven_endpoints_are_rejected(self):
        assert typography.ranges("tel. 621-9288") == []

    def test_endpoints_that_do_not_count_up_are_rejected(self):
        assert typography.ranges("wynik 27-18") == []
        assert typography.ranges("wynik 18-18") == []

    def test_a_decimal_after_it_is_rejected(self):
        assert typography.ranges("godziny 10-11.30") == []

    def test_glued_to_a_word_is_rejected(self):
        assert typography.ranges("numer X20-513") == []
        assert typography.ranges("1971-1974a") == []

    def test_part_of_a_longer_run_is_rejected(self):
        assert typography.ranges("61-867-47-0") == []

    def test_the_reason_is_named(self):
        """The sieve says *why*, because a rule that rejects without a reason
        is a rule nobody can check."""
        import re

        found = re.search(r"(\d+)-(\d+)", "kod 60-171")
        assert typography.not_a_range("kod 60-171", found) == "uneven"

    def test_dashing_replaces_only_the_hyphen_between_the_numbers(self):
        text = "w latach 1996-2001 i tel. 621-9288"
        assert typography.dashed(text, typography.ranges(text)) == (
            "w latach 1996–2001 i tel. 621-9288"
        )

    def test_several_places_in_one_string_all_change(self):
        """Deliberately not claiming more than it checks: an en dash is as long
        as a hyphen, so nothing here can prove the back-to-front rebuild
        matters. It is in the code for the day the replacement stops being the
        same length, and that is said in the code rather than pretended here."""
        text = "1996-2001, 2001-2005, 2005-2012"
        assert typography.dashed(text, typography.ranges(text)) == (
            "1996–2001, 2001–2005, 2005–2012"
        )


class TestTheGateAccountsForTheDash:
    """Found by probing what the shelf could not show. On a real book the
    ranges rule fires beside the ellipsis and the conjunctions, both of which
    K1 already knows about — so their names covered this rule's difference and
    everything passed. A book whose *only* typographic change is a dash was
    refused outright."""

    #: No three dots and no single-letter conjunction anywhere: those two rules
    #: are already named in the gate, and a fixture that lets them fire has the
    #: dash covered by their names. The first version of this test did exactly
    #: that and passed with the rule removed.
    ONLY_A_RANGE = "<p>Mieszkal tam w latach 1996-2001 oraz pisal ksiazki.</p>" * 6

    @staticmethod
    def _only_ranges(tmp_path, name):
        source = book(tmp_path, "pl", TestTheGateAccountsForTheDash.ONLY_A_RANGE,
                      name=f"{name}-in.epub")

        class OnlyRanges:
            def ask(self, question):
                from epubforge.decisions import Answer

                return Answer(
                    option="repair"
                    if question.group.startswith("typography:ranges")
                    else "keep",
                    apply_to_group=True,
                )

        result = rebuild(
            source, str(tmp_path / f"{name}.epub"),
            Policy.preset("preserve", typography=False), resolver=OnlyRanges(),
        )
        return result

    def test_a_book_changed_only_by_a_dash_is_still_written(self, tmp_path):
        result = self._only_ranges(tmp_path, "x1")
        assert result.output_path, result.report.to_text()
        said = {f.rule for f in result.report.findings}
        assert "typography.ranges-dashed" in said
        assert "typography.conjunctions-bound" not in said, "fixture is not isolated"
        assert "typography.ellipsis-normalised" not in said, "fixture is not isolated"
        assert "package.prose-changed" not in said

    def test_and_the_report_says_the_prose_changed_on_request(self, tmp_path):
        """Named rather than passed over: the invariant no longer holds
        character for character and the person reading is entitled to know."""
        result = self._only_ranges(tmp_path, "x2")
        assert "package.prose-changed-on-request" in {
            f.rule for f in result.report.findings
        }

    def test_the_rule_is_named_in_the_set_the_prose_half_reads(self):
        from epubforge import pipeline

        assert (
            "typography.ranges-dashed"
            in pipeline.CHANGES_TEXT_SHAPE_ON_PURPOSE | pipeline.REMOVES_TEXT_ON_PURPOSE
        )
