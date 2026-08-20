"""Pillar 3 of the 0.3 plan: bare [N] footnote markers, asked about and linked.

The measured shape (2026-08-20, seven books, 205 markers): a converter linked
part of a notes section and abandoned the rest — bare `[N]` in running text,
a paragraph starting with `N` in a document that looks like notes. The design
promises tested here, in the plan's own words: a book without the defect is
never asked a single question (153 of 160 on the shelf); working footnotes
are never touched; nothing changes without an answer; and on "link" the text
is identical to the character — only markup is added, which is why K1 stays
silent.
"""

from __future__ import annotations

import re
import zipfile

from epubforge.decisions import Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of

CHAPTER = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    '<title>R</title></head><body>'
    "<p>Rycerz wypił eliksir[1] i ruszył w stronę zamku[2] nocą.</p>"
    '<p>Odnośnik działający<a href="przypisy.xhtml#stary">[3]</a> zostaje.</p>'
    "</body></html>"
)

NOTES = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    '<title>Przypisy</title></head><body>'
    "<p>1. Eliksir z jaskółczego ziela.</p>"
    "<p>2) Zamek nad urwiskiem.</p>"
    '<p id="stary">3. Nota już podlinkowana.</p>'
    "</body></html>"
)


class _Chooser:
    def __init__(self, option: str):
        self.option = option
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(option=self.option)


def build(tmp_path, *, chapter=CHAPTER, notes=NOTES, option="link", link=True):
    documents = {"c0.xhtml": chapter}
    if notes is not None:
        documents["przypisy.xhtml"] = notes
    source = make_book(tmp_path / "in.epub", documents)
    policy = Policy.preset("preserve", render_gate="off")
    policy.link_footnotes = link
    chooser = _Chooser(option)
    return rebuild(source, str(tmp_path / "out.epub"), policy, resolver=chooser), chooser


def documents_of(result) -> dict:
    with zipfile.ZipFile(result.output_path) as archive:
        return {
            name.rsplit("/", 1)[-1]: archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        }


class TestTheBridgeIsBuiltOnRequest:
    def test_link_joins_marker_and_note(self, tmp_path):
        result, chooser = build(tmp_path)
        assert result.status.wrote_a_file, result.report.to_text()
        assert [q for q in chooser.asked if q.group == "footnote"]
        docs = documents_of(result)
        chapter = next(d for d in docs.values() if "eliksir" in d)
        assert re.search(r'<a href="[^"]*#ef-note-1">\[1\]</a>', chapter)
        assert re.search(r'<a href="[^"]*#ef-note-2">\[2\]</a>', chapter)
        notes = next(d for d in docs.values() if "urwiskiem" in d)
        assert 'id="ef-note-1"' in notes and 'id="ef-note-2"' in notes
        assert "footnotes.linked" in rules_of(result)

    def test_the_text_is_unchanged_to_the_character(self, tmp_path):
        """The whole K1 argument, asserted directly: strip the markup and the
        reading order is byte-for-byte what it was."""
        result, _ = build(tmp_path)
        docs = documents_of(result)
        chapter = next(d for d in docs.values() if "eliksir" in d)
        text = re.sub(r"<[^>]+>", "", chapter[chapter.find("<body"):])
        assert "Rycerz wypił eliksir[1] i ruszył w stronę zamku[2] nocą." in text

    def test_a_working_footnote_is_never_touched(self, tmp_path):
        """[3] already lives inside a link — the measured promise is that the
        413 working markers on the shelf are not this stage's business."""
        result, _ = build(tmp_path)
        docs = documents_of(result)
        chapter = next(d for d in docs.values() if "eliksir" in d)
        # The rebuild renames files and repoints the existing link with them —
        # what must survive is the anchor and its target, not the old spelling.
        assert re.search(r'<a href="[^"]*przypisy\.xhtml#stary">\[3\]</a>', chapter)
        assert "ef-note-3" not in chapter
        notes = next(d for d in docs.values() if "urwiskiem" in d)
        assert 'id="stary"' in notes  # the existing id is not renamed


class TestNothingHappensUninvited:
    def test_keep_changes_nothing_and_counts(self, tmp_path):
        result, chooser = build(tmp_path, option="keep")
        assert chooser.asked
        docs = documents_of(result)
        chapter = next(d for d in docs.values() if "eliksir" in d)
        assert "eliksir[1]" in chapter and "ef-note-" not in chapter
        assert "footnotes.found" in rules_of(result)
        assert "footnotes.linked" not in rules_of(result)

    def test_no_notes_section_no_question(self, tmp_path):
        """153 of 160 books have nothing of the kind, and the plan's rule is
        absolute: they are never asked. The mutation that drops the
        notes-section requirement fails here."""
        result, chooser = build(tmp_path, notes=None)
        assert result.status.wrote_a_file, result.report.to_text()
        assert not [q for q in chooser.asked if q.group == "footnote"]

    def test_a_numbered_list_in_the_story_is_not_a_notes_section(self, tmp_path):
        """Three numbered paragraphs in an ordinarily named chapter are as
        likely a recipe as a notes section — below the threshold, in a file
        not named like notes, nobody is asked. The mutation that drops the
        threshold fails here."""
        listy = (
            '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
            '<meta charset="utf-8"/><title>L</title></head><body>'
            "<p>1. Wstań o świcie.</p><p>2. Nakarm konia.</p>"
            "<p>3. Ruszaj przed zmrokiem.</p></body></html>"
        )
        source = make_book(
            tmp_path / "in2.epub",
            {"c0.xhtml": CHAPTER, "c1.xhtml": listy},
        )
        policy = Policy.preset("preserve", render_gate="off")
        chooser = _Chooser("link")
        result = rebuild(source, str(tmp_path / "out2.epub"), policy, resolver=chooser)
        assert result.status.wrote_a_file, result.report.to_text()
        assert not [q for q in chooser.asked if q.group == "footnote"]
        docs = documents_of(result)
        assert "ef-note-" not in next(d for d in docs.values() if "eliksir" in d)

    def test_a_number_without_a_note_is_ignored(self, tmp_path):
        chapter = CHAPTER.replace("nocą.", "nocą[9].")
        result, _ = build(tmp_path, chapter=chapter)
        docs = documents_of(result)
        body = next(d for d in docs.values() if "eliksir" in d)
        assert "nocą[9]" in body and "ef-note-9" not in body

    def test_the_switch_declines_the_question_in_advance(self, tmp_path):
        result, chooser = build(tmp_path, link=False)
        assert result.status.wrote_a_file, result.report.to_text()
        assert not [q for q in chooser.asked if q.group == "footnote"]
        docs = documents_of(result)
        assert "ef-note-" not in next(d for d in docs.values() if "eliksir" in d)
