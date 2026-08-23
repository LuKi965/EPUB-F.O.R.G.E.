"""Pillar C of the 0.4 plan: the report opens with a summary a person can read.

The owner's own words for what was wrong: *„dla czytającego to zupa"*.
Measured on four books of his shelf before a line was written — 39, 61, 94
and 122 findings — so what somebody met first was between forty and a
hundred and twenty lines of stage names, bracketed level tags and repeated
rules, and nowhere among them the sentence anybody opens a report for:
**is my book all right**.

The summary is not a new source of truth. It counts the findings that are
already there, which is what keeps it from drifting: a reader who does not
believe a sentence can go down the page and count.
"""

from __future__ import annotations

import json

from epubforge.report import Level, Report


def report_with(*findings, output="out.epub", **stats) -> Report:
    report = Report(source="in.epub", output=output)
    for stage, level, message in findings:
        report.add(stage, level, message)
    report.stats.update(stats)
    return report


class TestTheFirstSentenceAnswersTheFirstQuestion:
    """Whatever else it says, a person learns whether the book is all right."""

    def test_a_clean_book_is_called_healthy(self):
        lines = report_with(("css", Level.FIX, "css.empty-noise-removed")).summary("pl")
        assert "zdrowa" in lines[1]

    def test_a_warning_is_not_hidden_behind_the_word_healthy(self):
        lines = report_with(
            ("xhtml", Level.WARN, "xhtml.alt-missing"),
        ).summary("pl")
        assert "zdrowa" not in lines[1]
        assert "WARN" in lines[1]

    def test_an_error_outranks_a_warning_in_the_verdict(self):
        lines = report_with(
            ("xhtml", Level.WARN, "xhtml.alt-missing"),
            ("css", Level.ERROR, "css.mend-unverified"),
        ).summary("pl")
        assert "ERROR" in lines[1]

    def test_a_book_that_was_not_written_says_so_first(self):
        """The one case where the reader's question is not "is it good" but
        "where is my file". The mutation that reads the verdict off the
        findings alone fails here: this report has none."""
        lines = report_with(output="").summary("pl")
        assert "Plik nie powstał" in lines[1]


class TestWhatWasRepairedIsSaidByArea:
    def test_the_areas_are_named_in_words_not_stage_ids(self):
        lines = report_with(
            ("css", Level.FIX, "a"), ("css", Level.FIX, "b"),
            ("xhtml", Level.FIX, "c"),
        ).summary("pl")
        fixed = next(line for line in lines if "Naprawiono" in line)
        assert "arkusze stylów (2)" in fixed
        assert "treść stron (1)" in fixed
        assert "css" not in fixed and "xhtml" not in fixed

    def test_a_stage_nobody_taught_it_keeps_its_own_name(self):
        """Honest and ugly beats friendly and invented. The mutation that
        makes up a word for an unknown stage fails here."""
        lines = report_with(("nowyetap", Level.FIX, "a")).summary("pl")
        assert "nowyetap" in next(line for line in lines if "Naprawiono" in line)

    def test_only_the_three_largest_areas_are_listed(self):
        """A summary that lists eleven areas is the soup again."""
        lines = report_with(
            *[(stage, Level.FIX, "x") for stage in
              ("css", "xhtml", "fonts", "navigation", "metadata")]
        ).summary("pl")
        fixed = next(line for line in lines if "Naprawiono" in line)
        assert fixed.count("(") == 3


class TestNothingIsClaimedThatIsNotCounted:
    def test_a_report_with_nothing_repaired_does_not_mention_repairs(self):
        lines = report_with(("css", Level.INFO, "a")).summary("pl")
        assert not [line for line in lines if "Naprawiono" in line]

    def test_the_counts_match_the_findings_below(self):
        report = report_with(
            ("css", Level.FIX, "a"), ("css", Level.PRESERVED, "b"),
            ("css", Level.INFO, "c"), ("css", Level.INFO, "d"),
        )
        lines = report.summary("pl")
        assert "Naprawiono 1 " in " ".join(lines)
        assert "1 rzecz zostawiono" in " ".join(lines)
        assert "2 sprawy są tylko do wiadomości" in " ".join(lines)

    def test_waiting_is_read_from_the_record_and_not_from_rule_names(self):
        """The line that says something waits for you is the one a person
        acts on, so it comes from the queue's own count of unanswered
        questions. A report that never asked anything must not claim it.
        The mutation that guesses this from `-kept`/`-left` rule names fails
        here: this report is full of them and nothing was asked."""
        quiet = report_with(
            ("css", Level.PRESERVED, "css.reader-property-kept"),
            ("css", Level.PRESERVED, "css.malformed-declaration-left"),
            questions_unanswered=0,
        )
        assert not [line for line in quiet.summary("pl") if "czeka" in line]

        asked = report_with(("css", Level.FIX, "a"), questions_unanswered=3)
        waiting = next(line for line in asked.summary("pl") if "czeka" in line)
        assert "3 pytania czekają" in waiting


class TestBothLanguagesAndBothConsumers:
    def test_the_summary_stands_above_the_technical_account(self):
        text = report_with(("css", Level.FIX, "a")).to_text("pl")
        lines = text.splitlines()
        assert lines[2] == "W skrócie"
        assert lines.index("W skrócie") < next(
            i for i, line in enumerate(lines) if "source:" in line
        )

    def test_english_says_the_same_things(self):
        lines = report_with(("css", Level.FIX, "a")).summary("en")
        assert lines[0] == "In short"
        assert "healthy" in lines[1]
        assert "stylesheets (1)" in lines[2]

    def test_polish_agreement_is_the_reports_own(self):
        """`rules.fill` and not `str.format`, so "1 pytanie czeka" and
        "5 pytań czeka" agree here exactly as they do in every finding."""
        for count, expected in ((1, "1 pytanie czeka"), (3, "3 pytania czekają"),
                                (7, "7 pytań czeka")):
            lines = report_with(("css", Level.FIX, "a"),
                                questions_unanswered=count).summary("pl")
            assert expected in " ".join(lines)

    def test_a_front_end_gets_the_same_sentences(self):
        """The window must not compose its own summary out of the counts —
        two summaries that can disagree is worse than one."""
        report = report_with(("css", Level.FIX, "a"))
        data = json.loads(report.to_json("pl"))
        assert data["in_short"] == report.summary("pl")[1:]
        # and the field that was already called `summary` still means what it
        # meant, because a consumer is reading it
        assert data["summary"] == {level.value: report.count(level) for level in Level}


class TestTheWholeShelfGetsTheSameTreatment:
    """Pillar C's second half. After a run over a hundred and sixty books the
    question stops being *what does this book say* and becomes *which of these
    do I have to look at* — the argument `batch_to_dict` was already written
    on, carried from the JSON to the person."""

    @staticmethod
    def shelf():
        healthy = report_with(("css", Level.FIX, "a"))
        warned = report_with(("xhtml", Level.WARN, "w"), ("css", Level.FIX, "a"))
        broken = report_with(("fonts", Level.ERROR, "e"))
        refused = report_with(output="")
        asking = report_with(("css", Level.FIX, "a"), questions_unanswered=2)
        return [healthy, warned, broken, refused, asking]

    def test_it_counts_books_not_findings(self):
        """`survey.py`'s rule and the right one here for its reason: one book
        with forty of something is a curiosity, forty books with one each is a
        fact about the shelf. The mutation that totals findings fails here —
        one book carries four style repairs and three others carry one each."""
        from epubforge.report import batch_summary

        crowded = report_with(*[("css", Level.FIX, str(i)) for i in range(40)])
        plain = [report_with(("xhtml", Level.FIX, "a")) for _ in range(3)]
        line = next(
            l for l in batch_summary([crowded] + plain, "pl") if "Najczęściej" in l
        )
        assert "treść stron (3)" in line
        assert "arkusze stylów (1)" in line

    def test_every_kind_of_book_is_accounted_for(self):
        from epubforge.report import batch_summary

        lines = " ".join(batch_summary(self.shelf(), "pl"))
        assert "Przebudowano 5 książek" in lines
        # Two: the plain one and the one with questions waiting. A book nobody
        # has answered yet has nothing *wrong* with it — S-05 means nothing
        # about it changed — so it is healthy and it is also on the waiting
        # line below. Those are two different facts about one book.
        assert "2 z nich są zdrowe" in lines
        assert "1 książka nie powstała" in lines
        assert "1 książka ma błąd" in lines
        assert "W 1 książce są sprawy warte obejrzenia" in lines
        assert "W 1 książce pytania czekają" in lines

    def test_a_book_with_an_error_is_not_also_counted_as_merely_worth_a_look(self):
        """Each book lands in exactly one bucket, or the numbers stop adding
        up to the total and the summary starts lying quietly."""
        from epubforge.report import batch_summary

        both = report_with(("x", Level.ERROR, "e"), ("x", Level.WARN, "w"))
        lines = " ".join(batch_summary([both], "pl"))
        assert "1 książka ma błąd" in lines
        assert "warte obejrzenia" not in lines

    def test_an_empty_run_says_so_rather_than_dividing_by_nothing(self):
        from epubforge.report import batch_summary

        assert "Nie przebudowano" in " ".join(batch_summary([], "pl"))

    def test_a_front_end_gets_the_same_sentences(self):
        from epubforge.report import batch_summary, batch_to_dict

        data = batch_to_dict(self.shelf(), "pl")
        assert data["in_short"] == batch_summary(self.shelf(), "pl")[1:]
