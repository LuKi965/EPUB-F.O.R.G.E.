"""Pillar 2 of the 0.3 plan: Word's `page: SectionN` plumbing is removed.

Measured before it was decided (the D-031 conversation): 7 694 live rules of
the shape `div.Section2 { page: Section2 }` across the owner's 160 books —
Word's mapping of document sections onto named print pages, which no EPUB
reading system applies to reflowing text. The owner's decision was one word:
eliminate. The boundaries are the tests below: `page-break-*` is styling
readers honour and is never touched; a pre-paginated publication keeps its
`page:` untouched; the sweep's opt-out reaches this removal too.
"""

from __future__ import annotations

import zipfile

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    '<title>R</title><link rel="stylesheet" type="text/css" href="s.css"/></head>'
    '<body><div class="Section2"><p class="rozdzial">Tekst rozdziału.</p></div></body></html>'
)

#: The shelf's exact shape, plus the two neighbours that must survive:
#: `page-break-after` is real styling, and the margin on `.rozdzial` must
#: outlive the removal of the `page:` declaration sharing its rule.
SHEET = (
    "div.Section2 { page: Section2; } "
    "p.rozdzial { page: Section2; margin-top: 1em; } "
    "p.rozdzial { page-break-after: always; }"
)


def build(tmp_path, *, sweep: bool = True, mode: str = "preserve", layout: str = ""):
    cover = (
        '<meta property="rendition:layout">pre-paginated</meta>'
        if layout == "pre-paginated" else ""
    )
    source = make_book(
        tmp_path / "in.epub",
        {"c0.xhtml": PAGE},
        extra_items='<item id="s" href="s.css" media-type="text/css"/>',
        extra_files={"OEBPS/s.css": SHEET.encode()},
        cover=cover,
    )
    policy = Policy.preset(mode)
    policy.sweep_style_blocks = sweep
    return rebuild(source, str(tmp_path / "out.epub"), policy)


def sheet_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        for name in archive.namelist():
            if name.endswith(".css") and "rozdzial" in archive.read(name).decode("utf-8"):
                return archive.read(name).decode("utf-8")
    raise AssertionError("no stylesheet in the rebuild")


class TestThePlumbingGoes:
    def test_the_declaration_goes_and_the_rule_it_shared_stays(self, tmp_path):
        result = build(tmp_path)
        assert result.status.wrote_a_file, result.report.to_text()
        sheet = sheet_of(result)
        assert "page: Section2" not in sheet and "page:Section2" not in sheet
        assert "margin-top: 1em" in sheet
        assert "css.page-plumbing-removed" in rules_of(result)

    def test_a_rule_left_empty_goes_whole(self, tmp_path):
        """`div.Section2 { page: Section2 }` had nothing else to say."""
        result = build(tmp_path)
        assert "Section2 {" not in sheet_of(result).replace("  ", " ")

    def test_page_break_is_styling_and_survives(self, tmp_path):
        """The hyphen is the boundary: readers honour `page-break-*`. The
        mutation that loosens the property match to `page[a-z-]*` fails here."""
        result = build(tmp_path)
        assert "page-break-after: always" in sheet_of(result)

    def test_both_modes_remove_it(self, tmp_path):
        for mode in ("preserve", "strict"):
            (tmp_path / mode).mkdir()
            result = build(tmp_path / mode, mode=mode)
            assert "page: Section2" not in sheet_of(result), mode


class TestTheBoundaries:
    def test_the_opt_out_keeps_it_and_counts(self, tmp_path):
        result = build(tmp_path, sweep=False)
        assert result.status.wrote_a_file, result.report.to_text()
        assert "page: Section2" in sheet_of(result)
        assert "css.page-plumbing-found" in rules_of(result)
        assert "css.page-plumbing-removed" not in rules_of(result)

    def test_a_prepaginated_book_keeps_its_page_property(self, tmp_path):
        """Fixed layout is paged media — there `page:` is in its element,
        and this program has no business deciding otherwise."""
        result = build(tmp_path, layout="pre-paginated")
        assert result.status.wrote_a_file, result.report.to_text()
        assert "page: Section2" in sheet_of(result)
        assert "css.page-plumbing-removed" not in rules_of(result)
