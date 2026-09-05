"""K1 sharpened: a carried document's prose comes out identical, not merely unlost.

Today's K1 asks for a **subsequence** — no character of the source may be
missing, and anything at all may be added. That was written before anybody
had measured how much the rebuild actually changes. Measured since, on five
books and 279 carried documents: **278 come out character-identical**, and
the one that does not is a `<style>` block, which is a stylesheet rather than
the book's prose.

So the program already keeps the stronger promise, and the weaker one leaves
it blind in the other direction: a sentence *appearing* inside an existing
document passes today's K1 without a word. These tests are about that gap and
about the two ways the first attempt at measuring it went wrong.

The owner's instruction that led here, on being offered a second invariant
beside K1 for the correction subsystem: *„po prostu usprawnij K1"*.
"""

from __future__ import annotations

import zipfile

from epubforge import fidelity


def a_book(path, documents: "dict[str, bytes]"):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in documents.items():
            archive.writestr(name, data)
    return str(path)


def page(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">'
        "<head><meta charset=\"utf-8\"/><title>t</title></head>"
        f"<body>{body}</body></html>"
    ).encode()


def compare(tmp_path, before_body: str, after_body: str):
    source = a_book(tmp_path / "in.epub", {"OEBPS/a.xhtml": page(before_body)})
    output = a_book(tmp_path / "out.epub", {"EPUB/text/0000-a.xhtml": page(after_body)})
    return fidelity.prose_is_identical(
        source, output, {"OEBPS/a.xhtml": "EPUB/text/0000-a.xhtml"}
    )


class TestTheDirectionTodaysK1CannotSee:
    def test_a_sentence_that_appeared_is_caught(self, tmp_path):
        """The gap this exists for. `first_character_lost` compares a
        subsequence, so text *added* inside a carried document passes it
        without a word — and the correction subsystem is the last place that
        can be true."""
        found = compare(tmp_path, "<p>Ala ma kota.</p>", "<p>Ala ma kota. I psa.</p>")
        assert found, "an added sentence went unnoticed"
        assert "I psa" in found[0].after

        # ...and the old rule really does pass it, which is the measurement
        # rather than an assertion about my own reading of it.
        assert fidelity.first_character_lost("Ala ma kota.", "Ala ma kota. I psa.") == -1

    def test_a_sentence_that_vanished_is_caught_too(self, tmp_path):
        found = compare(tmp_path, "<p>Ala ma kota i psa.</p>", "<p>Ala ma kota.</p>")
        assert found

    def test_a_word_swapped_for_another_of_the_same_length(self, tmp_path):
        """Neither shorter nor longer, so nothing about the size gives it
        away."""
        found = compare(tmp_path, "<p>Ala ma kota.</p>", "<p>Ala ma kotu.</p>")
        assert found
        assert found[0].before.endswith("kota.")
        assert found[0].after.endswith("kotu.")


class TestWhatIsNotAChangeToTheBook:
    def test_reflowed_markup_is_not_a_difference(self, tmp_path):
        """Serialising a tree moves line breaks about. A book is not changed
        by that, and an invariant that said so would be switched off within a
        day."""
        assert not compare(tmp_path, "<p>Ala\n   ma kota.</p>", "<p>Ala ma kota.</p>")

    def test_a_stylesheet_inside_the_document_is_not_prose(self, tmp_path):
        """The single divergence the shelf measurement turned up: this
        program writes a comment into a `<style>` block, and `itertext()`
        cannot tell a stylesheet from a sentence. The mutation that drops the
        `NOT_PROSE` exclusion fails here."""
        assert not compare(
            tmp_path,
            "<style>p { margin: 0 }</style><p>Ala ma kota.</p>",
            "<style>p { margin: 0 } /* uwaga programu */</style><p>Ala ma kota.</p>",
        )

    def test_but_the_text_around_the_stylesheet_still_counts(self, tmp_path):
        """The exclusion skips what a `<style>` *says*, never what follows it
        — otherwise a sentence sitting after one would stop being read."""
        found = compare(
            tmp_path,
            "<style>p{}</style>Ala ma kota.",
            "<style>p{}</style>Ala ma psa.",
        )
        assert found

    def test_a_generated_document_is_not_a_changed_one(self, tmp_path):
        """A navigation document the rebuild wrote has no counterpart in the
        source, and comparing it against nothing would report every book as
        broken."""
        source = a_book(tmp_path / "in.epub", {"OEBPS/a.xhtml": page("<p>Tekst.</p>")})
        output = a_book(tmp_path / "out.epub", {
            "EPUB/text/0000-a.xhtml": page("<p>Tekst.</p>"),
            "EPUB/nav.xhtml": page("<nav><ol><li>Rozdział</li></ol></nav>"),
        })
        assert not fidelity.prose_is_identical(
            source, output, {"OEBPS/a.xhtml": "EPUB/text/0000-a.xhtml"}
        )


class TestTheTwoWaysMeasuringThisWentWrong:
    """Both kept as tests, because both produced a confident wrong number."""

    def test_an_entity_is_read_as_the_character_it_names(self, tmp_path):
        """The first shelf measurement read the source with a bare recovering
        parser, which does not resolve `&nbsp;`. The character vanished from
        the *before* side and 129 documents looked as though the rebuild had
        added text to them. It had not."""
        assert not compare(
            tmp_path,
            "<p>z&nbsp;Carvahall</p>",
            "<p>z Carvahall</p>",
        )

    def test_a_documents_title_is_not_the_reading_flow(self, tmp_path):
        """This test asserted the opposite an hour ago, on the strength of a
        sloppy fixture and my own reading. The shelf said otherwise: a
        `<title>` is shown by a reading system in its navigation, never in
        the text, and this program *fills an empty one in* — a repair it
        reports as `xhtml.title-filled`. Measured on 160 books: that repair
        alone accounted for 37 of the 39 divergences the first sharpened
        check reported. Reading a title as prose would have made the
        invariant fire on a fifth of the shelf over a repair named in every
        one of those reports."""
        retitled = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">'
            '<head><meta charset="utf-8"/><title>uzupelniony</title></head>'
            "<body><p>Tekst.</p></body></html>"
        ).encode()
        source = a_book(tmp_path / "in.epub", {"OEBPS/a.xhtml": page("<p>Tekst.</p>")})
        output = a_book(tmp_path / "out.epub", {"EPUB/text/0000-a.xhtml": retitled})
        assert not fidelity.prose_is_identical(
            source, output, {"OEBPS/a.xhtml": "EPUB/text/0000-a.xhtml"}
        )

    def test_a_control_character_no_epub_may_carry_is_not_text(self, tmp_path):
        """`U+008F` mid-sentence, which two books of the shelf actually
        carry. No decoding makes it text, no reading system draws it, and no
        conforming EPUB may hold it — so removing it is required rather than
        permitted, and today's K1 already folds it on both sides. The
        mutation that stops folding it fails here."""
        assert not compare(
            tmp_path, "<p>rzekł \u008fŹle</p>", "<p>rzekł Źle</p>"
        )

    def test_the_comparison_does_not_fold_a_quotation_mark_away(self, tmp_path):
        """`typography.canonical(relaxed=True)` folds quotes, dashes and
        ellipses — right for a typography pass checking its own work, and
        exactly wrong here, where the one job is to notice a change nobody
        approved. The mutation that reuses the relaxed comparison fails
        here."""
        found = compare(tmp_path, '<p>Powiedział "tak".</p>', "<p>Powiedział „tak”.</p>")
        assert found, "a changed quotation mark was folded away"


class TestAtTheGate:
    """Wired in front of the writer, beside the subsequence rule it sharpens.

    Measured before wiring, on the owner's 160 books: every carried document
    already comes out character for character, so this refuses nothing that
    runs today. What it closes is the direction the correction subsystem
    cannot leave open (D-020).
    """

    @staticmethod
    def _book(tmp_path):
        from tests.test_class_translation import PAGE
        from tests.test_shelf_refusals import make_book

        return make_book(
            tmp_path / "in.epub",
            {"c0.xhtml": PAGE.format(body="<p>Ala ma kota i psa.</p>")},
        )

    def test_a_clean_rebuild_is_published(self, tmp_path):
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        result = rebuild(
            self._book(tmp_path), str(tmp_path / "out.epub"),
            Policy.preset("preserve", render_gate="off", validate_before_publish="off"),
        )
        assert result.output_path, result.report.to_text()
        assert "package.prose-changed" not in {
            f.rule for f in result.report.findings if f.rule
        }

    def test_a_document_whose_text_changed_is_refused(self, tmp_path, monkeypatch):
        """The gate's whole point, forced by making the check report a
        divergence nobody consented to. The mutation that reports it and
        publishes anyway fails here."""
        from epubforge import fidelity
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        monkeypatch.setattr(
            fidelity,
            "prose_is_identical",
            lambda *_args, **_kw: [
                fidelity.TextDivergence("a.xhtml", "b.xhtml", 7, "kota", "kotu")
            ],
        )
        result = rebuild(
            self._book(tmp_path), str(tmp_path / "out.epub"),
            Policy.preset("preserve", render_gate="off", validate_before_publish="off"),
        )
        assert result.output_path is None, "a changed book was published"
        assert "package.prose-changed" in {
            f.rule for f in result.report.findings if f.rule
        }

    def test_a_change_the_person_asked_for_is_reported_not_refused(
        self, tmp_path, monkeypatch
    ):
        """Removing a shop's watermark takes text out on purpose. The
        invariant stops holding character for character and the report says
        so — refusing there would refuse the feature."""
        from epubforge import fidelity
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy
        from epubforge.report import Level

        monkeypatch.setattr(
            fidelity,
            "prose_is_identical",
            lambda *_args, **_kw: [
                fidelity.TextDivergence("a.xhtml", "b.xhtml", 0, "znak wodny", "")
            ],
        )
        real = rebuild

        def with_consent(*args, **kwargs):
            result = real(*args, **kwargs)
            return result

        source = self._book(tmp_path)
        policy = Policy.preset("preserve", render_gate="off", validate_before_publish="off")
        # The consent the gate looks for is a finding, so put one in the way
        # the stage would have.
        from epubforge import pipeline

        original = pipeline._text_gate

        def gate_with_a_consent(src, pol, report, book=None):
            report.add("xhtml", Level.FIX, "xhtml.watermark-removed")
            return original(src, pol, report, book)

        monkeypatch.setattr(pipeline, "_text_gate", gate_with_a_consent)
        result = with_consent(source, str(tmp_path / "out.epub"), policy)
        assert result.output_path, result.report.to_text()
        assert "package.prose-changed-on-request" in {
            f.rule for f in result.report.findings if f.rule
        }


class TestDocumentOrderIsNotIterationOrder:
    """The bug this code shipped with for an hour, kept as a test.

    `iter()` walks elements; a *tail* belongs after the element's whole
    subtree, not next to its text. Appending the two together put a span's
    tail in front of its own child's text — so a document whose markup this
    program legitimately unwrapped read as changed prose and the gate refused
    it. Found by `test_stylesheet.py::test_text_around_a_span_keeps_its_order`,
    which exists because the unwrap helper made the identical mistake first.
    """

    def test_a_tail_follows_the_whole_subtree(self, tmp_path):
        nested = "<p>przed <span>w <em>srodku</em> koniec</span> po</p>"
        assert fidelity.document_text(page(nested)) == "przed w srodku koniec po"

    def test_unwrapping_a_span_is_not_a_change_of_prose(self, tmp_path):
        """What the rebuild actually does to a span that says nothing, and
        what the gate must not call damage."""
        assert not compare(
            tmp_path,
            "<p>przed <span>w <em>srodku</em> koniec</span> po</p>",
            "<p>przed w <em>srodku</em> koniec po</p>",
        )

    def test_and_a_real_reordering_is_still_caught(self, tmp_path):
        """The other side, so the fix cannot be a blanket forgiveness: two
        words genuinely swapped are still a difference."""
        found = compare(
            tmp_path,
            "<p>przed w srodku koniec po</p>",
            "<p>przed w koniec srodku po</p>",
        )
        assert found


class TestABlockBoundaryIsNotAWord:
    """A repair that moves a paragraph moves it away from its indentation.

    Measured on the suite's own fixture: a paragraph a converter left in
    `<head>` is moved to the top of the body, and the whitespace that sat
    between the tags does not travel with it. The source then reads
    `…akapit. Rozdział…` and the output `…akapit.Rozdział…` — one space, and
    no reader can see it, because two blocks are two blocks whatever
    separates their tags.
    """

    def test_two_paragraphs_read_the_same_however_their_tags_are_spaced(self, tmp_path):
        assert not compare(
            tmp_path,
            "<p>Zabłąkany akapit.</p>\n   <p>Rozdział drugi</p>",
            "<p>Zabłąkany akapit.</p><p>Rozdział drugi</p>",
        )

    def test_an_inline_element_gets_no_separator(self, tmp_path):
        """The other side, and the one that matters: inserting a boundary
        inside a word would invent the damage this exists to detect. The
        mutation that treats every element as a block fails here."""
        assert fidelity.document_text(page("<p>sro<em>d</em>ku</p>")) == "srodku"

    def test_a_word_that_really_lost_its_space_is_still_caught(self, tmp_path):
        """Two words run together *inside* one block is a change a reader
        sees, and no boundary rule may forgive it."""
        found = compare(tmp_path, "<p>Ala ma kota</p>", "<p>Alama kota</p>")
        assert found
