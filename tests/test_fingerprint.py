"""Provenance detection: what made the book, and how sure of each answer.

The old detector lived in `inventory.py` as a flat table of patterns producing
a flat list of names. Every test here is about something that table could not
express — a weight, a place, or two of them corroborating.
"""

from __future__ import annotations

import pytest

from epubforge import fingerprint


def named(**kwargs) -> list[str]:
    return fingerprint.names(fingerprint.identify(**kwargs))


class TestAWeakTraceIsNotAnAnswer:
    """The old table scored `_idGenParaOverride` and the word `vellum` the
    same. One is a string InDesign invents and nobody types; the other is the
    word for parchment."""

    def test_the_word_vellum_in_a_chapter_says_nothing(self):
        markup = "<p>Rekopis spisano na vellum, oprawiono w skore.</p>"
        assert "vellum" not in named(markup=markup)

    def test_the_same_word_in_the_package_is_a_program_naming_itself(self):
        package = '<meta name="generator" content="Vellum 3.3"/>'
        assert "vellum" in named(package=package)

    def test_the_word_calibre_alone_is_below_the_floor(self):
        """A book about photography talking about the calibre of a lens is not
        a book converted by Calibre."""
        markup = "<p>Obiektyw najwyzszego calibre.</p>"
        assert "calibre" not in named(markup=markup)

    def test_but_the_word_plus_a_class_it_writes_is_an_answer(self):
        markup = '<p class="calibre3">Obiektyw najwyzszego calibre.</p>'
        assert "calibre" in named(markup=markup)


class TestCorroboration:
    def test_two_traces_are_worth_more_than_either(self):
        one = fingerprint.identify(markup='<p class="MsoNormal">a</p>')
        two = fingerprint.identify(
            markup='<p class="MsoNormal">a</p>', css="p { mso-pagination: none; }"
        )
        assert two[0].confidence > one[0].confidence

    def test_evidence_never_reaches_certainty(self):
        """Nothing here is ever a fact, and the arithmetic should not pretend
        otherwise. Adding weights would let three guesses outvote one."""
        material = (
            '<p class="MsoNormal">a</p><o:p></o:p><span id="docs-internal-guid-1">b</span>'
        )
        traces = fingerprint.identify(markup=material, css="p { mso-tab-count: 1; }")
        assert traces[0].confidence < 1.0

    def test_a_package_match_is_not_counted_twice(self):
        """The same pattern appears twice — tied to the package and to anywhere
        — and a package match satisfies both. Counting them as two independent
        traces would let the deliberately weakened variant push the confidence
        back up, which is the opposite of why it was written down separately."""
        package = '<meta name="generator" content="InDesign CC"/>'
        traces = fingerprint.identify(package=package)
        indesign = next(t for t in traces if t.name == "indesign")
        assert indesign.confidence == pytest.approx(0.8)

    def test_calibre_series_does_not_corroborate_itself(self):
        """`calibre:series` contains the word `calibre`, so the generic package
        pattern would fire on the very same bytes."""
        traces = fingerprint.identify(package='<meta name="calibre:series" content="x"/>')
        calibre = next(t for t in traces if t.name == "calibre")
        assert calibre.confidence == pytest.approx(0.9)


class TestLayeredFiles:
    """Files are layered — InDesign to Calibre to Sigil — and that is
    information, not an ambiguity to resolve."""

    def test_both_tools_are_reported(self):
        traces = fingerprint.identify(
            package='<meta name="calibre:series" content="Kroniki"/>',
            markup='<p class="_idGenParaOverride-1">a</p>',
        )
        assert {t.name for t in traces} == {"calibre", "indesign"}

    def test_the_most_confident_comes_first(self):
        traces = fingerprint.identify(
            package='<meta name="calibre:series" content="x"/>',
            markup='<p class="_idGenParaOverride-1">a</p>',
        )
        assert [t.confidence for t in traces] == sorted(
            (t.confidence for t in traces), reverse=True
        )

    def test_nothing_recognised_is_an_empty_list_not_a_guess(self):
        assert fingerprint.identify(markup="<p>Zwykly akapit.</p>") == []


class TestTheEvidenceIsCheckable:
    def test_every_trace_says_what_it_found(self):
        traces = fingerprint.identify(markup='<p class="calibre3">calibre</p>')
        assert traces[0].evidence

    def test_the_evidence_is_the_string_itself_not_a_sentence_about_it(self):
        """A reader who wants to check the claim searches the book for it, and
        the same string works in both report languages."""
        traces = fingerprint.identify(package='<meta name="calibre:series" content="x"/>')
        assert "calibre:series" in traces[0].evidence

    def test_describe_puts_the_confidence_beside_the_name(self):
        traces = fingerprint.identify(markup='<p class="MsoNormal">a</p>')
        assert fingerprint.describe(traces).startswith("word (0.9")


class TestTheTableItself:
    @pytest.mark.parametrize("name", sorted(fingerprint.SIGNATURES))
    def test_every_signal_is_declared_somewhere_real(self, name):
        for signal in fingerprint.SIGNATURES[name]:
            assert signal.place in fingerprint.PLACES, (name, signal.pattern)
            assert 0.0 < signal.weight <= 1.0, (name, signal.pattern)
            assert signal.note, (name, signal.pattern)

    @pytest.mark.parametrize("name", sorted(fingerprint.SIGNATURES))
    def test_a_needle_is_really_implied_by_its_pattern(self, name):
        """A needle that the pattern does not require switches the signal off
        and nothing says so — the detector simply stops finding that tool. The
        needles exist to skip regular expressions that cannot match; one that
        skips a regular expression that *would* have matched is a silent hole.
        """
        for signal in fingerprint.SIGNATURES[name]:
            literal = signal.pattern.replace("\\", "").lower()
            for needle in signal.needles:
                assert needle in literal, (name, signal.pattern, needle)

    @pytest.mark.parametrize("name", sorted(fingerprint.SIGNATURES))
    def test_every_generator_can_reach_the_floor_on_its_own(self, name):
        """A signature nothing can ever clear the floor with is a signature
        that has been switched off without anybody noticing."""
        best = max(signal.weight for signal in fingerprint.SIGNATURES[name])
        assert best >= fingerprint.FLOOR, name


class TestTheInventoryUsesThisOne:
    """One implementation of one idea. The watermark taught this the hard way:
    two detectors for the same thing disagreed by 25 books out of 32, and the
    disagreement was invisible until a real shelf."""

    def test_the_inventory_no_longer_carries_its_own_table(self):
        from epubforge import inventory

        assert not hasattr(inventory, "GENERATOR_SIGNATURES")

    def test_a_measured_book_carries_the_confidences_too(self, legacy_epub):
        import pathlib

        from epubforge.inventory import measure

        fields = measure(pathlib.Path(legacy_epub)).fields
        assert "generator_confidence" in fields
        assert set(fields["generator_confidence"]) == set(fields["generators"])
