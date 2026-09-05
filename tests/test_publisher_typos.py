"""A declaration broken by a slip of the publisher's finger, and the owner's
call on what to do about it (2026-08-22).

Six findings on the shelf survived every proof pillar A could make, because
none of them is a proof problem: they are typing mistakes, and the repair is
a *guess at what the author meant*. The owner's decision was to ask with the
proposal shown rather than to leave them on an exception list — the person
supplies the certainty the program does not have (D-033's line, from the
other side), and S-05 holds throughout: without an answer nothing changes.

Two shapes, both measured, both dead today because every reader rejects a
broken declaration whole:

* `margin-right: 2$` — `$` is a unit in no CSS that ever existed, and `%`
  is its neighbour on the keyboard. Three books of one series carry it.
* `border: 0px solid border-collapse: collapse` — one lost semicolon turns
  two declarations into one that says nothing. Two books carry it.

The third shape the owner asked about, `text-align="center"`, already had
its question (`style.equals`, pillar 4 of the 0.3 plan) and is not repeated
here.
"""

from __future__ import annotations

import zipfile

from epubforge.decisions import Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_class_translation import PAGE
from tests.test_shelf_refusals import make_book, rules_of


class Chooser:
    """Answers every question with one option, and keeps what it was asked."""

    def __init__(self, picked):
        self.picked = picked
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(option=self.picked)


def build(tmp_path, sheet, option=None):
    source = make_book(
        tmp_path / "in.epub",
        {"c0.xhtml": PAGE.format(body='<p class="jeden">Akapit z treścią.</p>')},
        extra_items='<item id="s" href="s.css" media-type="text/css"/>',
        extra_files={"OEBPS/s.css": sheet.encode()},
    )
    chooser = Chooser(option) if option else None
    result = rebuild(
        source, str(tmp_path / "out.epub"),
        Policy.preset("preserve", render_gate="off"), resolver=chooser,
    )
    return result, chooser


def sheet_of(result):
    """Every stylesheet concatenated — the first-match habit reads the wrong one."""
    texts = []
    with zipfile.ZipFile(result.output_path) as archive:
        for name in archive.namelist():
            if name.endswith(".css"):
                texts.append(archive.read(name).decode("utf-8"))
    if not texts:
        raise AssertionError("no stylesheet in the rebuild")
    return "\n".join(texts)


def typo_question(chooser):
    return next(q for q in chooser.asked if q.group == "style:typo")


class TestWithoutAnAnswerNothingChanges:
    """S-05, the same law the rest of the question families obey."""

    def test_nobody_answers_and_the_typo_stands(self, tmp_path):
        sheet = "hr.blue { border: 1px solid #0061a0; margin-right: 2$; }"
        result, _ = build(tmp_path, sheet)
        assert "2$" in sheet_of(result)
        assert "css.publisher-typo-left" in rules_of(result)
        assert "css.publisher-typo-kept" not in rules_of(result)
        assert "css.publisher-typo-fixed" not in rules_of(result)

    def test_keeping_it_keeps_it_and_says_it_was_an_answer(self, tmp_path):
        """EF-074 (independent audit 2026-09-04): a person who read the
        question and chose the recommended "keep" was told in the report
        that nobody answered. Two facts, two entries."""
        sheet = "hr.blue { border: 1px solid #0061a0; margin-right: 2$; }"
        result, _ = build(tmp_path, sheet, option="keep")
        assert "2$" in sheet_of(result)
        assert "css.publisher-typo-kept" in rules_of(result)
        assert "css.publisher-typo-left" not in rules_of(result)
        assert "css.publisher-typo-fixed" not in rules_of(result)


class TestTheTwoShapes:
    def test_the_dollar_becomes_the_percent_it_was_reaching_for(self, tmp_path):
        sheet = "hr.blue { border: 1px solid #0061a0; margin-right: 2$; }"
        result, _ = build(tmp_path, sheet, option="fix")
        out = sheet_of(result)
        assert "margin-right: 2%" in out
        assert "2$" not in out
        assert "css.publisher-typo-fixed" in rules_of(result)

    def test_the_lost_semicolon_is_put_back(self, tmp_path):
        sheet = "table.plain { border: 0px solid border-collapse: collapse }"
        result, _ = build(tmp_path, sheet, option="fix")
        out = sheet_of(result)
        assert "border: 0px solid;" in out
        assert "border-collapse: collapse" in out

    def test_the_proposal_is_shown_before_it_is_made(self, tmp_path):
        """The whole reason this is a question: the person is answering about
        a specific guess, not about a policy."""
        sheet = "hr.blue { margin-right: 2$; }"
        _, chooser = build(tmp_path, sheet, option="keep")
        question = typo_question(chooser)
        assert "margin-right: 2$" in question.detail
        assert "margin-right: 2%" in question.detail

    def test_the_repair_is_in_the_ledger_as_a_person_s_call(self, tmp_path):
        from epubforge.report import Automation

        sheet = "hr.blue { margin-right: 2$; }"
        result, _ = build(tmp_path, sheet, option="fix")
        entry = next(
            change for change in result.report.changes
            if change.rule == "css.publisher-typo-fixed"
        )
        assert entry.automation is Automation.ASKED
        assert "2$" in entry.before and "2%" in entry.after


class TestWhatIsNotATypo:
    """The guards, each one a shape that would be damaged by a repair."""

    def test_a_property_name_inside_somebody_s_text_is_text(self, tmp_path):
        """`content` carries words, and words may spell a property. Split on
        that and a run-together repair cuts a sentence in half. The first
        fixture here was `content: "2$"`, which measured nothing — the unit
        pattern never matched it — so it is this shape instead. The mutation
        that reads values regardless of their quotes fails here."""
        sheet = 'p.jeden::before { content: "zobacz border: dalej"; }'
        result, chooser = build(tmp_path, sheet, option="fix")
        assert '"zobacz border: dalej"' in sheet_of(result)
        assert not [q for q in chooser.asked if q.group == "style:typo"]

    def test_an_inline_svg_in_a_data_url_is_not_a_declaration(self, tmp_path):
        """A data URI carries a whole document, and that document has its own
        colons. Written with a `;` the declaration pattern cuts the value long
        before this pass sees it — which is why the fixture has none, and why
        the first version of it measured nothing. The mutation that reads
        inside `url(` fails here."""
        sheet = (
            "p.jeden { background-image: "
            "url(data:image/svg+xml,<svg font-size: 2px></svg>); }"
        )
        result, chooser = build(tmp_path, sheet, option="fix")
        assert "<svg font-size: 2px>" in sheet_of(result)
        assert not [q for q in chooser.asked if q.group == "style:typo"]

    def test_a_colon_whose_head_is_no_property_is_left_unread(self, tmp_path):
        """A run-together is only a run-together when what follows the space
        is a property this program knows. Anything else is a value it does
        not understand, and an unread value is safer than a guessed one. The
        mutation that drops the property check fails here."""
        sheet = "div.x { border: 0px solid nietoperz: fruwa }"
        result, chooser = build(tmp_path, sheet, option="fix")
        assert "nietoperz: fruwa" in sheet_of(result)
        assert not [q for q in chooser.asked if q.group == "style:typo"]

    def test_what_a_converter_signed_is_swept_in_preserve_too(self, tmp_path):
        """The third shape the owner listed, and where measuring it led.

        A declaration written `text-align="center"` inside a rule a converter
        signed is not asked about — that is the anti-flood exception (S-02).
        What it *was* doing was surviving `preserve` in total silence: the
        output carried a line no reader applies and the report did not name
        it. Measured on the shelf: exactly one such declaration in 160 books.

        Then the owner asked the question that settles it — *czy po Sigilu
        też nie powinniśmy sprzątać* — and his own D-029 already answers it:
        `remove_dead` divides the modes over deviations **a reader can see**,
        and a declaration CSS cannot parse draws nothing anywhere. So it goes
        with the generator basket, in both modes.

        The mutation that hangs this on `remove_dead` again fails here.
        """
        sheet = 'p.sgc-1 { text-align="center" }'
        result, chooser = build(tmp_path, sheet, option="fix")
        assert not [q for q in chooser.asked if q.group == "style:equals"], (
            "a converter's own class is not asked about — that is the exception"
        )
        assert 'text-align="center"' not in sheet_of(result)
        assert "css.malformed-declaration-dropped" in rules_of(result)

    def test_the_tick_that_keeps_the_junk_keeps_this_too(self, tmp_path):
        """S-02 requires an opt-out for every removal, and this removal is
        behind the one the rest of the style sweep is behind. The mutation
        that sweeps regardless of the tick fails here."""
        from epubforge.pipeline import rebuild as _rebuild

        sheet = 'p.sgc-1 { text-align="center" }'
        source = make_book(
            tmp_path / "in.epub",
            {"c0.xhtml": PAGE.format(body='<p class="sgc-1">Akapit.</p>')},
            extra_items='<item id="s" href="s.css" media-type="text/css"/>',
            extra_files={"OEBPS/s.css": sheet.encode()},
        )
        policy = Policy.preset("preserve", render_gate="off")
        policy.sweep_style_blocks = False
        result = _rebuild(source, str(tmp_path / "out.epub"), policy)
        assert 'text-align="center"' in sheet_of(result)
        assert "css.malformed-declaration-converter-kept" in rules_of(result)

    def test_a_healthy_sheet_asks_nothing(self, tmp_path):
        sheet = "p.jeden { margin-right: 2%; border: 0px solid; }"
        result, chooser = build(tmp_path, sheet, option="fix")
        assert not [q for q in chooser.asked if q.group == "style:typo"]
        assert "css.publisher-typo-left" not in rules_of(result)
        assert "css.publisher-typo-fixed" not in rules_of(result)
