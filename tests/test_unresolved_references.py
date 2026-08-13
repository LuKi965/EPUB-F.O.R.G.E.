"""F-010: a link whose anchor does not exist, and what may be done about it.

The defect this file exists for is not a crash and not a lost file. It is a
*successful* rebuild that produced a working link to the wrong place, and a
report that called it a repair::

    <a href="przypisy.xhtml#fn-17" epub:type="noteref">17</a>   before
    <a href="przypisy.xhtml"       epub:type="noteref">17</a>   after

Tapping footnote seventeen now lands on footnote one. The validator is quiet —
that was the point of the change — and no reader, and no report, can tell that
apart from a book whose footnotes work.

So the program keeps three states and no others (`epubforge/references.py`):

* ``PRESERVED`` — target and anchor both exist. Nothing happens.
* ``REPAIRED`` — the reference changed under a mapping this rebuild produced
  and can point at: a file it moved, an id it renamed, a document it
  regenerated under a mapping it wrote itself.
* ``UNRESOLVED`` — everything else. Kept exactly as the publisher wrote it,
  reported as a defect inherited from the source, and never rewritten to buy a
  validator's silence.

`preserve` publishes such a book and says so; `strict` refuses to publish it.
And where somebody is at the window, the program asks rather than guessing —
which is the owner's rule for this whole project, stated when this change was
authorised: *if the application cannot do something itself, let us involve the
user.* A human answer is evidence the program does not have.

The six cases below numbered in the review that prompted the rewrite are marked
`case N` in their docstrings.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import references
from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy
from epubforge.references import Answers, Decision, Unresolved
from tests.factory import MODERN_NAV, MODERN_OPF, png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">
  <head><meta charset="utf-8"/><title>Rozdzia&#x142;</title></head>
  <body>{body}</body>
</html>
"""

#: The notes document has notes — just not the one the chapter asks for. That
#: is the shape of the real defect: a PDF reflow that gave only some of the
#: notes an id, not a file that is missing.
NOTES = PAGE.format(body='<aside id="fn-1">jeden</aside><aside id="fn-2">dwa</aside>')


def two_documents(path, *, marker: str = '<a href="przypisy.xhtml#fn-17" epub:type="noteref">17</a>') -> str:
    package = MODERN_OPF.format(title="Test", extra_metadata="").replace(
        "</manifest>",
        '<item id="notes" href="przypisy.xhtml" media-type="application/xhtml+xml"/></manifest>',
    ).replace("</spine>", '<itemref idref="notes"/></spine>')
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": package.encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": PAGE.format(body=f"<p>Tekst{marker}</p>").encode(),
            "OEBPS/przypisy.xhtml": NOTES.encode(),
            "OEBPS/picture.png": png_bytes(),
        },
    )


def built(source, tmp_path, mode: str = "preserve", resolver=None, name: str = "out.epub"):
    return rebuild(source, str(tmp_path / name), Policy.preset(mode), resolver=resolver)


def document(result, ending: str) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(ending))
        return archive.read(name).decode("utf-8")


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


class TestTheThreeStates:
    def test_an_anchor_that_exists_is_preserved(self, tmp_path):
        """case 1 — the target has the id, so there is nothing to decide."""
        source = two_documents(
            tmp_path / "ok.epub",
            marker='<a href="przypisy.xhtml#fn-1" epub:type="noteref">1</a>',
        )
        result = built(source, tmp_path)
        assert "#fn-1" in document(result, "chapter.xhtml")
        assert "xhtml.fragment-unresolved" not in rules_of(result)
        assert result.status is Status.SUCCEEDED

    def test_preserve_keeps_the_reference_and_reports_it(self, tmp_path):
        """case 2 — kept verbatim, reported as the source's defect."""
        result = built(two_documents(tmp_path / "keep.epub"), tmp_path)
        assert "przypisy.xhtml#fn-17" in document(result, "chapter.xhtml").replace(
            "../text/", ""
        ).replace("text/", "")
        assert "xhtml.fragment-unresolved" in rules_of(result)

    def test_and_the_finding_is_not_dressed_up_as_a_repair(self, tmp_path):
        """A defect inherited from the source is not a fix this tool made.

        The level is the claim. `PRESERVED` in this program means *a deviation
        kept on purpose because removing it would change how the book looks*,
        which is a decision with a reason behind it; this has no reason behind
        it beyond ignorance, and saying so is the whole finding.
        """
        result = built(two_documents(tmp_path / "level.epub"), tmp_path)
        finding = next(f for f in result.report.findings if f.rule == "xhtml.fragment-unresolved")
        assert finding.level.value == "warn"
        assert "fn-17" in (finding.detail or "") + str(finding.values)

    def test_a_book_carrying_one_does_not_come_back_reading_succeeded(self, tmp_path):
        """The status is a claim too, and `succeeded` would be a false one."""
        result = built(two_documents(tmp_path / "status.epub"), tmp_path)
        assert result.output_path is not None
        assert result.status is Status.SUCCEEDED_WITH_PROBLEMS

    def test_strict_refuses_the_book_instead_of_the_meaning(self, tmp_path):
        """case 3 — strict fails; it does not "fix" this by removing it.

        Strict promises a conforming file, not a tidy one. Dropping the
        fragment produces something that validates by having had meaning taken
        out of it, which is the opposite of what the mode is for.
        """
        result = built(two_documents(tmp_path / "strict.epub"), tmp_path, mode="strict")
        assert result.output_path is None
        assert result.status is Status.BLOCKED
        assert "package.unresolved-references" in rules_of(result)

    def test_the_refusal_names_the_link_and_the_document_holding_it(self, tmp_path):
        result = built(two_documents(tmp_path / "named.epub"), tmp_path, mode="strict")
        finding = next(
            f for f in result.report.findings if f.rule == "package.unresolved-references"
        )
        assert "fn-17" in finding.values["examples"]
        assert "chapter" in finding.values["examples"]

    def test_a_moved_document_is_repaired_and_keeps_its_anchor(self, tmp_path):
        """case 4 — the rebuild moved the file and holds the map that says where.

        `reorganize_files` renames every document; the reference has to follow,
        and following it is a real repair because the program can point at the
        transformation that makes it true. The anchor is not touched at all.
        """
        source = two_documents(
            tmp_path / "moved.epub",
            marker='<a href="przypisy.xhtml#fn-2" epub:type="noteref">2</a>',
        )
        result = built(source, tmp_path)
        chapter = document(result, "chapter.xhtml")
        assert "#fn-2" in chapter
        assert 'href="przypisy.xhtml' not in chapter, "the file was renamed; the link must follow"
        assert "xhtml.fragment-unresolved" not in rules_of(result)

    def test_a_renamed_id_carries_its_references_with_it(self, tmp_path):
        """The other deterministic repair: this rebuild renamed the anchor.

        An id that is not a valid XML name is rewritten by the content stage,
        which keeps `{old: new}` — so every link to it can be rewritten from
        evidence rather than guessed at.
        """
        source = two_documents(
            tmp_path / "renamed.epub",
            marker='<a href="chapter.xhtml#2 uwaga">tam</a></p><p id="2 uwaga">tam</p><p>',
        )
        result = built(source, tmp_path)
        chapter = document(result, "chapter.xhtml")
        assert "2 uwaga" not in chapter
        assert "xhtml.fragment-unresolved" not in rules_of(result)


class TestTheFalseRepairIsGone:
    """case 6 — the regression test the whole rewrite is for.

    Stated as a property rather than a scenario: there is no mode, and no
    combination of switches, in which this program turns `#missing` into
    nothing by itself. Only a person can ask for that.
    """

    @pytest.mark.parametrize("mode", ["minimal", "preserve", "strict"])
    def test_no_mode_quietly_drops_a_fragment(self, tmp_path, mode):
        result = built(two_documents(tmp_path / f"{mode}.epub"), tmp_path, mode=mode)
        if result.output_path is None:
            # Strict refuses the book. A refusal cannot have produced a
            # forged link, which is the point being made.
            assert result.status is Status.BLOCKED
            return
        assert "#fn-17" in document(result, "chapter.xhtml")

    def test_a_same_document_reference_is_not_deleted_either(self, tmp_path):
        """The worse half of the old behaviour: the attribute itself went.

        `href="#brak"` had the `href` removed outright — a link the publisher
        wrote, gone, and counted as a fix. It stays now.
        """
        source = two_documents(
            tmp_path / "same.epub", marker='<a href="#brak">gdzieś</a>'
        )
        result = built(source, tmp_path)
        chapter = document(result, "chapter.xhtml")
        assert 'href="#brak"' in chapter
        assert "gdzieś" in chapter


class TestAskingThePerson:
    """The owner's rule: where the program cannot decide, it may ask.

    Not a convenience. The alternative to asking is guessing, and the whole of
    F-010 is about what guessing costs — so the interaction is the *feature*,
    and the autonomy it spends is the price rather than the product.
    """

    class Answering:
        """A resolver standing in for the window."""

        def __init__(self, decision, *, record=None):
            self.decision = decision
            self.seen: list[Unresolved] = [] if record is None else record

        def resolve(self, question):
            self.seen.append(question)
            return self.decision

    def test_a_person_can_name_the_anchor_and_that_is_a_repair(self, tmp_path):
        resolver = self.Answering(Decision(references.REPOINT, fragment="fn-2"))
        result = built(two_documents(tmp_path / "ask.epub"), tmp_path, resolver=resolver)
        chapter = document(result, "chapter.xhtml")
        assert "#fn-2" in chapter
        assert "#fn-17" not in chapter
        assert "xhtml.fragment-repointed" in rules_of(result)
        assert "xhtml.fragment-unresolved" not in rules_of(result)

    def test_and_the_book_then_passes_strict(self, tmp_path):
        """Which is what makes asking worth having rather than merely polite."""
        resolver = self.Answering(Decision(references.REPOINT, fragment="fn-2"))
        result = built(
            two_documents(tmp_path / "askstrict.epub"), tmp_path, mode="strict", resolver=resolver
        )
        assert result.output_path is not None
        assert "package.unresolved-references" not in rules_of(result)

    def test_a_person_may_also_say_the_link_belongs_at_the_document(self, tmp_path):
        """The one route from a dead anchor to no anchor — through a human.

        Exactly the transformation the program is forbidden to make on its own.
        It is allowed here because somebody looked at the book and said so, and
        the report says that is what happened.
        """
        resolver = self.Answering(Decision(references.POINT_AT_DOCUMENT))
        result = built(two_documents(tmp_path / "top.epub"), tmp_path, resolver=resolver)
        chapter = document(result, "chapter.xhtml")
        assert "#fn-17" not in chapter
        assert "przypisy" in chapter or "notes" in chapter
        assert "xhtml.dead-fragment-dropped" in rules_of(result)

    def test_the_question_carries_what_is_needed_to_answer_it(self, tmp_path):
        """A dialog that shows only "a fragment is missing" cannot be answered.

        The link's own text is usually the footnote number, and the anchors the
        target document *does* have are the list to choose from.
        """
        resolver = self.Answering(None)
        built(two_documents(tmp_path / "q.epub"), tmp_path, resolver=resolver)
        question = next(q for q in resolver.seen if q.fragment == "fn-17")
        assert question.text == "17"
        assert "fn-1" in question.candidates and "fn-2" in question.candidates
        assert question.document.endswith(".xhtml")
        assert question.reference.endswith("#fn-17")

    def test_no_resolver_means_nothing_is_asked(self, tmp_path):
        """A batch run, the corpus, and every library caller. Silence is the
        default, and it keeps the publisher's reference."""
        result = built(two_documents(tmp_path / "silent.epub"), tmp_path)
        assert "#fn-17" in document(result, "chapter.xhtml")

    def test_a_front_end_that_breaks_does_not_break_the_rebuild(self, tmp_path):
        class Broken:
            def resolve(self, question):
                raise RuntimeError("the dialog fell over")

        result = built(two_documents(tmp_path / "broken.epub"), tmp_path, resolver=Broken())
        assert result.output_path is not None
        assert "#fn-17" in document(result, "chapter.xhtml")


class TestAnsweringOnceForTheWholeBook:
    """Two hundred questions is how a feature becomes a thing people switch off."""

    def test_a_standing_answer_is_not_asked_again(self):
        asked = []

        class Once:
            def resolve(self, question):
                asked.append(question)
                return Decision(references.KEEP, apply_to_all=True)

        answers = Answers()
        resolver = Once()
        for index in range(5):
            answers.ask(resolver, Unresolved("a.xhtml", "b.xhtml", f"fn-{index}"))
        assert len(asked) == 1

    def test_but_a_chosen_anchor_never_becomes_a_standing_answer(self):
        """"Point this one at `fn-2`" is a statement about one link.

        Applied to the rest of the book it would point every broken footnote
        marker at footnote two, which is the original defect with a human
        signature on it.
        """
        asked = []

        class Everywhere:
            def resolve(self, question):
                asked.append(question)
                return Decision(references.REPOINT, fragment="fn-2", apply_to_all=True)

        answers = Answers()
        resolver = Everywhere()
        for index in range(3):
            answers.ask(resolver, Unresolved("a.xhtml", "b.xhtml", f"fn-{index}"))
        assert len(asked) == 3

    def test_a_decision_that_points_nowhere_is_not_a_decision(self):
        with pytest.raises(ValueError):
            Decision(references.REPOINT)
        with pytest.raises(ValueError):
            Decision("delete-the-book")


class TestARegeneratedDocumentKeepsWhatItCan:
    """case 5 — `nav.xhtml#spis` when this program writes the nav itself.

    Regenerating a document does not by itself entitle the program to throw
    away the anchors pointing into it. The old navigation's table of contents
    and the new one's are the same thing under two names, and the stage knows
    both names — so `spis -> toc` is a fact about a transformation, not a guess.
    """

    @staticmethod
    def linking_into_the_nav(path) -> str:
        nav = MODERN_NAV.replace('<nav epub:type="toc">', '<nav epub:type="toc" id="spis">')
        package = MODERN_OPF.format(title="Test", extra_metadata="")
        return write_zip(
            str(path),
            {
                "META-INF/container.xml": CONTAINER.encode(),
                "OEBPS/package.opf": package.encode(),
                "OEBPS/nav.xhtml": nav.encode(),
                "OEBPS/chapter.xhtml": PAGE.format(
                    body='<p><a href="nav.xhtml#spis">Spis treści</a></p>'
                ).encode(),
                "OEBPS/picture.png": png_bytes(),
            },
        )

    def test_the_anchor_follows_the_document_that_replaced_it(self, tmp_path):
        result = built(self.linking_into_the_nav(tmp_path / "nav.epub"), tmp_path)
        chapter = document(result, "chapter.xhtml")
        assert "#toc" in chapter, "the link to the contents must still reach the contents"
        assert "#spis" not in chapter
        assert "nav.fragment-carried" in rules_of(result)

    def test_and_the_generated_navigation_really_has_that_anchor(self, tmp_path):
        result = built(self.linking_into_the_nav(tmp_path / "nav2.epub"), tmp_path)
        assert 'id="toc"' in document(result, "nav.xhtml")
