"""Pillar 4a of the 0.3 plan: `property="value"` in a rule nobody's generator signed.

EF-059 measured the machine case on the shelf — `p.sgc-1 {text-align="center"}`,
a converter's counter over a converter's typo — and that case keeps its old,
silent path: strict drops what no reader ever applied, preserve keeps it and
says so. The owner's call was about the *other* case: the same `=` in a rule
with no generator's signature could be a publisher's slip of the finger, and
the answer that happens without anybody to ask must be the one that changes
nothing. So a question, three options — leave it, remove it, or enable it
("the `=` becomes a `:`, and formatting nobody has ever seen starts applying,
on a person's word") — and an "enable" answer must never switch on the
generator junk standing beside it.
"""

from __future__ import annotations

from epubforge.decisions import Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of, style_of

#: One sheet, both worlds: `p.wstep` is nobody's generator, `p.sgc-1` is
#: Sigil's counter. Both classes are used in the body, so neither rule is the
#: unreachable sweep's business — what happens to each `=` is this feature's
#: doing alone.
MIXED = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title>"
    '<style>p.wstep {text-align="center"} p.sgc-1 {font-weight="bold"} '
    "p.wstep { color: black; }</style>"
    '</head><body><p class="wstep">Wstęp do rozdziału.</p>'
    '<p class="sgc-1">Tekst rozdziału.</p></body></html>'
)


class _Chooser:
    def __init__(self, option: str):
        self.option = option
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(option=self.option)


def build(tmp_path, *, markup=MIXED, option="keep", preset="strict", writes=True):
    source = make_book(tmp_path / "in.epub", {"chapter.xhtml": markup})
    chooser = _Chooser(option)
    result = rebuild(
        source, str(tmp_path / "out.epub"), Policy.preset(preset), resolver=chooser
    )
    if writes:
        assert result.status.wrote_a_file, result.report.to_text()
    return result, chooser


def equals_questions(chooser) -> list:
    return [q for q in chooser.asked if q.group == "style:equals"]


class TestThePersonDecidesTheHumanLine:
    def test_the_question_is_asked_and_keep_changes_nothing(self, tmp_path):
        result, chooser = build(tmp_path, option="keep", preset="preserve")
        (question,) = equals_questions(chooser)
        assert question.recommended == "keep"
        css = style_of(result)
        assert 'text-align="center"' in css
        assert "text-align: center" not in css
        assert "css.malformed-declaration-left" in rules_of(result)

    def test_strict_refuses_to_publish_a_kept_invalid_line(self, tmp_path):
        """`keep` in strict is a real choice with a real consequence: the line
        makes the file invalid, strict does not publish invalid files, and the
        honest outcome is a refusal — not a silent drop behind the person's
        answer. The mutation that drops the human line despite `keep` would
        publish here, and this test fails."""
        result, chooser = build(tmp_path, option="keep", writes=False)
        assert equals_questions(chooser)
        assert not result.status.wrote_a_file
        assert "css.malformed-declaration-left" in rules_of(result)

    def test_enable_turns_the_equals_into_a_colon(self, tmp_path):
        result, chooser = build(tmp_path, option="enable")
        assert equals_questions(chooser)
        css = style_of(result)
        assert "text-align: center;" in css
        assert 'text-align="center"' not in css
        assert "css.malformed-declaration-enabled" in rules_of(result)

    def test_drop_removes_the_line_it_was_asked_about(self, tmp_path):
        result, _ = build(tmp_path, option="drop")
        css = style_of(result)
        assert "text-align" not in css
        assert "color: black" in css  # the healthy declaration next door stays
        assert "css.malformed-declaration-dropped" in rules_of(result)

    def test_without_an_answer_nothing_changes_in_either_mode(self, tmp_path):
        """S-05 for this question: no resolver means the queue answers with
        its safe default, and the safe default here is `keep`. Preserve then
        publishes the book as it was; strict refuses to publish an invalid
        file — in both modes the line itself is untouched."""
        preserve = rebuild(
            make_book(tmp_path / "in-p.epub", {"chapter.xhtml": MIXED}),
            str(tmp_path / "out-p.epub"), Policy.preset("preserve"),
        )
        assert preserve.status.wrote_a_file, preserve.report.to_text()
        css = style_of(preserve)
        assert 'text-align="center"' in css
        assert "text-align: center" not in css

        strict = rebuild(
            make_book(tmp_path / "in-s.epub", {"chapter.xhtml": MIXED}),
            str(tmp_path / "out-s.epub"), Policy.preset("strict"),
        )
        assert not strict.status.wrote_a_file
        assert "css.malformed-declaration-left" in rules_of(strict)


class TestTheMachineSubsetKeepsItsSilentPath:
    def test_a_generator_signed_rule_is_never_asked(self, tmp_path):
        """The shelf's one measured case (`p.sgc-1`) is converter output —
        the anti-flood rule says it goes the old way without a question. The
        mutation that stops reading the selector's signature fails here."""
        only_machine = MIXED.replace('p.wstep {text-align="center"} ', "")
        result, chooser = build(tmp_path, markup=only_machine, option="enable")
        assert not equals_questions(chooser)
        css = style_of(result)
        assert "font-weight" not in css  # strict dropped it, as before

    def test_enable_never_switches_on_the_machine_junk(self, tmp_path):
        """One answer, two subsets: the person enabling their own line must
        not enable the converter's line beside it. The mutation that applies
        the answer to every match fails here."""
        result, _ = build(tmp_path, option="enable")
        css = style_of(result)
        assert "text-align: center" in css
        assert "font-weight" not in css

    def test_a_stamped_boilerplate_block_is_machine_whatever_its_names(self, tmp_path):
        """The same block in three documents is a converter stamping its
        template (D-028) — even a friendly selector name is not a person's
        hand there, and nobody is asked."""
        page = (
            '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
            '<meta charset="utf-8"/><title>R</title>'
            '<style>p.wstep {text-align="center"}</style>'
            '</head><body><p class="wstep">Tekst.</p></body></html>'
        )
        source = make_book(
            tmp_path / "in.epub",
            {"c0.xhtml": page, "c1.xhtml": page, "c2.xhtml": page},
        )
        chooser = _Chooser("enable")
        result = rebuild(
            source, str(tmp_path / "out.epub"), Policy.preset("strict"),
            resolver=chooser,
        )
        assert result.status.wrote_a_file, result.report.to_text()
        assert not equals_questions(chooser)
        assert "text-align" not in style_of(result)
