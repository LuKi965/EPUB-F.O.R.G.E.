"""The stage that changes text on purpose, and the check that it did not lose it.

Every other stage moves markup around a text it may not touch. This one edits
the text, so the interesting tests are not "does the rule work" — they are
"what happens when a rule is wrong", and the answer has to be that the document
comes back exactly as it arrived.
"""

from __future__ import annotations

import zipfile

import pytest

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
        report has to say so."""
        from epubforge.stages import typography as stage

        def eats(root, language, marks):
            for element, attribute in stage.typography.text_nodes(root):
                text = getattr(element, attribute)
                if text and "zniknie" in text:
                    setattr(element, attribute, text.replace("zniknie", ""))
                    return (1, 0, 0)
            return (0, 0, 0)

        monkeypatch.setattr(stage.TypographyStage, "_repair", staticmethod(eats))
        result, html = forge(tmp_path, "<p>To slowo zniknie stad.</p>", name="k")
        assert "zniknie" in html
        assert "typography.reverted" in {f.rule for f in result.report.findings}

    def test_the_revert_is_a_warning_not_a_silent_no_op(self, tmp_path, monkeypatch):
        from epubforge.stages import typography as stage

        def eats(root, language, marks):
            for element, attribute in stage.typography.text_nodes(root):
                text = getattr(element, attribute)
                if text and text.strip():
                    setattr(element, attribute, text[:-3])
                    return (1, 0, 0)
            return (0, 0, 0)

        monkeypatch.setattr(stage.TypographyStage, "_repair", staticmethod(eats))
        result, _ = forge(tmp_path, "<p>Zdanie ktore straci ogon.</p>", name="l")
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
