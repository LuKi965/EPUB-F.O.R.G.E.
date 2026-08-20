"""Pillar 4b of the 0.3 plan — EF-058: contents entries untangled by asking.

The measured book carried one id eleven times; the rebuild untangles the
copies but the eleven contents entries kept jumping to the first. The audit
drew the line this feature walks: assigning the n-th entry to the n-th
occurrence is probable and is not a fact, so `references.py`'s third verb —
ask — is the only honest path. Asked only when the counts agree; without an
answer every entry keeps jumping where it jumped yesterday.
"""

from __future__ import annotations

import re

from epubforge.decisions import Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import (
    BASE_ITEMS,
    CONTAINER,
    PACKAGE,
    documents_of,
    rules_of,
)
from tests.factory import write_zip

CHAPTER = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title></head><body>"
    '<h2 id="rozdz">Czas pierwszy</h2><p>Tekst pierwszego.</p>'
    '<h2 id="rozdz">Czas drugi</h2><p>Tekst drugiego.</p>'
    '<h2 id="rozdz">Czas trzeci</h2><p>Tekst trzeciego.</p>'
    "</body></html>"
)


def nav_with(entries: list[str]) -> str:
    items = "".join(
        f'<li><a href="chapter.xhtml#rozdz">{label}</a></li>' for label in entries
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">'
        '<head><meta charset="utf-8"/><title>Spis</title></head>'
        f'<body><nav epub:type="toc"><ol>{items}</ol></nav></body></html>'
    )


class _Chooser:
    def __init__(self, option: str):
        self.option = option
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(option=self.option)


def build(tmp_path, *, labels, option="keep", resolver=True):
    source = write_zip(
        str(tmp_path / "in.epub"),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": PACKAGE.format(
                items=BASE_ITEMS
                + '<item id="d0" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
                spine='<itemref idref="d0"/>',
                cover="",
            ).encode(),
            "OEBPS/nav.xhtml": nav_with(labels).encode(),
            "OEBPS/chapter.xhtml": CHAPTER.encode(),
        },
    )
    chooser = _Chooser(option)
    result = rebuild(
        source,
        str(tmp_path / "out.epub"),
        Policy.preset("preserve", render_gate="off"),
        resolver=chooser if resolver else None,
    )
    assert result.status.wrote_a_file, result.report.to_text()
    return result, chooser


def toc_of(result) -> str:
    for markup in documents_of(result).values():
        if 'epub:type="toc"' in markup:
            return markup
    raise AssertionError("no navigation document in the rebuild")


def toc_questions(chooser) -> list:
    return [q for q in chooser.asked if q.group == "toc:duplicate-target"]


THREE = ["Czas pierwszy", "Czas drugi", "Czas trzeci"]


class TestTheEntriesAreRepointedOnRequest:
    def test_repoint_gives_each_entry_its_own_target(self, tmp_path):
        result, chooser = build(tmp_path, labels=THREE, option="repoint")
        (question,) = toc_questions(chooser)
        assert question.recommended == "repoint"
        nav = toc_of(result)
        assert re.search(r'href="[^"]*#rozdz">Czas pierwszy<', nav)
        assert re.search(r'href="[^"]*#rozdz-2">Czas drugi<', nav)
        assert re.search(r'href="[^"]*#rozdz-3">Czas trzeci<', nav)
        assert "nav.entries-repointed" in rules_of(result)

    def test_the_question_previews_both_sides(self, tmp_path):
        _, chooser = build(tmp_path, labels=THREE, option="repoint")
        (question,) = toc_questions(chooser)
        assert "Czas drugi" in question.detail

    def test_the_ncx_follows_the_answer(self, tmp_path):
        result, _ = build(tmp_path, labels=THREE, option="repoint")
        with_ncx = documents_of(result)
        ncx = next(
            (m for name, m in with_ncx.items() if name.endswith(".ncx")), None
        )
        if ncx is None:  # the NCX lives outside documents_of's .xhtml filter
            import zipfile

            with zipfile.ZipFile(result.output_path) as archive:
                ncx = next(
                    archive.read(n).decode("utf-8")
                    for n in archive.namelist()
                    if n.endswith(".ncx")
                )
        assert "#rozdz-2" in ncx and "#rozdz-3" in ncx


class TestNothingMovesWithoutAnAnswer:
    def test_keep_leaves_every_entry_where_it_was(self, tmp_path):
        result, chooser = build(tmp_path, labels=THREE, option="keep")
        assert toc_questions(chooser)
        nav = toc_of(result)
        assert len(re.findall(r'#rozdz"', nav)) == 3
        assert "rozdz-2" not in nav
        assert "nav.duplicate-target-found" in rules_of(result)
        assert "nav.entries-repointed" not in rules_of(result)

    def test_nobody_at_the_window_means_keep(self, tmp_path):
        result, _ = build(tmp_path, labels=THREE, resolver=False)
        nav = toc_of(result)
        assert len(re.findall(r'#rozdz"', nav)) == 3
        assert "rozdz-2" not in nav

    def test_mismatched_counts_are_not_even_asked(self, tmp_path):
        """Two entries over three occurrences leave no ordering that is even
        probable — the report counts them and nobody is bothered. The
        mutation that drops the count guard fails here."""
        result, chooser = build(
            tmp_path, labels=["Czas pierwszy", "Czas drugi"], option="repoint"
        )
        assert not toc_questions(chooser)
        nav = toc_of(result)
        assert "rozdz-2" not in nav
        assert "nav.duplicate-target-found" in rules_of(result)

    def test_a_single_entry_is_no_group(self, tmp_path):
        result, chooser = build(tmp_path, labels=["Czas pierwszy"], option="repoint")
        assert not toc_questions(chooser)
        assert "nav.duplicate-target-found" not in rules_of(result)
        assert "nav.entries-repointed" not in rules_of(result)
