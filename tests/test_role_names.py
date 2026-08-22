"""Pillar B (D-035): file names come from roles, plainly.

The owner's words: „jeżeli rozdział to chapter, jeżeli coś innego to coś
innego. Proste." Three rungs of evidence — landmarks/guide, `epub:type`,
and contents entries from the body start onward (positions, never titles)
— and a document no evidence names keeps its old stem, because a fallback
name is honest and a wrong concrete one is not (D-033's line).
"""

from __future__ import annotations

import zipfile

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of

DOC = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
    '<meta charset="utf-8"/><title>{title}</title></head>'
    "<body{attrs}><p>{title}. Treść strony.</p></body></html>"
)


def page(title, epub_type=None):
    attrs = ""
    markup = DOC
    if epub_type:
        markup = markup.replace(
            '<html xmlns="http://www.w3.org/1999/xhtml"',
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"',
        )
        attrs = f' epub:type="{epub_type}"'
    return markup.format(title=title, attrs=attrs)


NAV = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" '
    'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">'
    '<head><meta charset="utf-8"/><title>Spis</title></head><body>'
    '<nav epub:type="toc"><ol>{toc}</ol></nav>{landmarks}</body></html>'
)


def nav_with(toc_entries, landmarks=()):
    toc = "".join(f'<li><a href="{href}">{label}</a></li>'
                  for href, label in toc_entries)
    lm = ""
    if landmarks:
        items = "".join(
            f'<li><a epub:type="{kind}" href="{href}">{kind}</a></li>'
            for kind, href in landmarks
        )
        lm = f'<nav epub:type="landmarks"><ol>{items}</ol></nav>'
    return NAV.format(toc=toc, landmarks=lm)


def build(tmp_path, documents, nav):
    source = make_book(
        tmp_path / "in.epub", documents,
        extra_files={"OEBPS/nav.xhtml": nav.encode()},
    )
    return rebuild(source, str(tmp_path / "out.epub"),
                   Policy.preset("preserve", render_gate="off"))


def names_of(result):
    with zipfile.ZipFile(result.output_path) as archive:
        return sorted(
            name.rsplit("/", 1)[-1] for name in archive.namelist()
            if name.startswith("EPUB/text/")
        )


class TestTheLadder:
    def test_landmarks_toc_and_continuations(self, tmp_path):
        """The shelf's shape in miniature: a cover named by a landmark,
        a front page nothing names, and two chapters — the first split
        across two files, so its second file is the same chapter
        continued."""
        documents = {
            "okladka.xhtml": page("Okładka"),
            "przedtytul.xhtml": page("Przedtytuł"),
            "rozdz1.xhtml": page("Rozdział pierwszy"),
            "rozdz1b.xhtml": page("Ciąg dalszy"),
            "rozdz2.xhtml": page("Rozdział drugi"),
        }
        nav = nav_with(
            [("rozdz1.xhtml", "Rozdział I"), ("rozdz2.xhtml", "Rozdział II")],
            landmarks=[("cover", "okladka.xhtml"),
                       ("bodymatter", "rozdz1.xhtml")],
        )
        result = build(tmp_path, documents, nav)
        names = names_of(result)
        assert "0000-cover.xhtml" in names
        assert "0002-chapter-01.xhtml" in names
        assert "0003-chapter-01-2.xhtml" in names
        assert "0004-chapter-02.xhtml" in names
        # nothing names the front page — it keeps its own stem
        assert "0001-przedtytul.xhtml" in names
        assert "structure.role-named" in rules_of(result)

    def test_epub_type_names_chapters_without_any_contents(self, tmp_path):
        documents = {
            "a.xhtml": page("Jeden", epub_type="chapter"),
            "b.xhtml": page("Dalej"),
            "c.xhtml": page("Dwa", epub_type="chapter"),
        }
        nav = nav_with([("a.xhtml", "Jeden")])
        result = build(tmp_path, documents, nav)
        names = names_of(result)
        assert "0000-chapter-01.xhtml" in names
        assert "0001-chapter-01-2.xhtml" in names
        assert "0002-chapter-02.xhtml" in names


class TestTheHonestFallback:
    def test_no_evidence_no_invented_names(self, tmp_path):
        """A book whose contents point nowhere useful and whose documents
        say nothing about themselves keeps its old stems. The mutation
        that numbers every document as a chapter fails here."""
        documents = {
            "pierwszy.xhtml": page("Pierwszy"),
            "drugi.xhtml": page("Drugi"),
        }
        nav = nav_with([("pierwszy.xhtml", "Coś")])
        # the single unroled entry sets the body start at itself — but a
        # front document BEFORE it must never be swept into chapters:
        documents = {
            "wstep.xhtml": page("Wstęp"),
            **documents,
        }
        nav = nav_with([("pierwszy.xhtml", "Coś"), ("drugi.xhtml", "Dalej")])
        result = build(tmp_path, documents, nav)
        names = names_of(result)
        assert "0000-wstep.xhtml" in names
        assert "0001-chapter-01.xhtml" in names
        assert "0002-chapter-02.xhtml" in names

    def test_an_unroled_entry_before_the_body_start_keeps_its_stem(self, tmp_path):
        """The contents list the title page too — but the landmarks say
        the body starts later, and a titled entry before that point is
        not a chapter. The mutation that ignores the body start fails
        here."""
        documents = {
            "tytulowa.xhtml": page("Strona tytułowa"),
            "tekst.xhtml": page("Tekst"),
        }
        nav = nav_with(
            [("tytulowa.xhtml", "Strona tytułowa"), ("tekst.xhtml", "Tekst")],
            landmarks=[("bodymatter", "tekst.xhtml")],
        )
        result = build(tmp_path, documents, nav)
        names = names_of(result)
        assert "0000-tytulowa.xhtml" in names
        assert "0001-chapter-01.xhtml" in names

    def test_the_tail_after_the_last_chapter_is_not_its_continuation(self, tmp_path):
        """Measured on the Gutenberg corpus: what follows the last chapter
        start is a title-page image wrap or the licence, not the chapter
        continued. A continuation needs evidence on both sides, and the end
        of the spine is not evidence. The mutation that sweeps the tail
        unbounded fails here."""
        documents = {
            "a.xhtml": page("Jeden", epub_type="chapter"),
            "b.xhtml": page("Dwa", epub_type="chapter"),
            "licencja.xhtml": page("Licencja"),
            "wrap.xhtml": page("Ilustracja"),
        }
        nav = nav_with([("a.xhtml", "Jeden")])
        result = build(tmp_path, documents, nav)
        names = names_of(result)
        assert "0000-chapter-01.xhtml" in names
        assert "0001-chapter-02.xhtml" in names
        assert "0002-licencja.xhtml" in names
        assert "0003-wrap.xhtml" in names

    def test_a_roled_document_closes_the_tail_and_grants_the_continuation(self, tmp_path):
        """The other side, so the tail rule cannot be tightened into "never":
        a colophon typed as such closes the last chapter's segment, and the
        plain file between them is the chapter continued after all."""
        documents = {
            "a.xhtml": page("Jeden", epub_type="chapter"),
            "b.xhtml": page("Dalej"),
            "k.xhtml": page("Kolofon", epub_type="colophon"),
        }
        nav = nav_with([("a.xhtml", "Jeden")])
        result = build(tmp_path, documents, nav)
        names = names_of(result)
        assert "0000-chapter-01.xhtml" in names
        assert "0001-chapter-01-2.xhtml" in names
        assert "0002-colophon.xhtml" in names

    def test_a_roled_document_ends_the_continuation(self, tmp_path):
        """A dedication typed as such stands between the chapter's file
        and a plain one — the plain file is not the chapter continued,
        because something else came between. The mutation that runs the
        continuation past a roled document fails here."""
        documents = {
            "a.xhtml": page("Jeden", epub_type="chapter"),
            "d.xhtml": page("Dedykacja", epub_type="dedication"),
            "b.xhtml": page("Luzem"),
            "c.xhtml": page("Dwa", epub_type="chapter"),
        }
        nav = nav_with([("a.xhtml", "Jeden")])
        result = build(tmp_path, documents, nav)
        names = names_of(result)
        assert "0000-chapter-01.xhtml" in names
        assert "0001-dedication.xhtml" in names
        assert "0002-b.xhtml" in names
        assert "0003-chapter-02.xhtml" in names
