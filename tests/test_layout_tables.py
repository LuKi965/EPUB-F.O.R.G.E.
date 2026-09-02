"""Prose put in a table: listed, asked about, marked as layout on request.

Record 040 measured 97 tables without header cells on the shelf and found
31 of them, in 7 books, to be paragraphs in a one-cell or one-column table —
a border made of a table, announced to a screen reader as "table, one row,
one column". The owner's decision (2026-09-02): tell assistive software it
is layout, through a question, the way pictures are handled. The other 66
are tables of data and are never touched.
"""

from __future__ import annotations

import re
import zipfile

from epubforge.decisions import KEEP, Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><title>R</title></head>'
    "<body>{body}</body></html>"
)

BOXED_PROSE = (
    "<h1>Rozdział</h1><p>Tekst.</p>"
    "<table><tr><td>Marq słuchał w napięciu, jak obojętny głos wylicza ostatnie "
    "uderzenia.</td></tr></table>"
)
ONE_COLUMN = (
    "<h1>R</h1><table><tr><td>Pierwszy akapit w tabeli.</td></tr>"
    "<tr><td>Drugi akapit w tabeli.</td></tr><tr><td>Trzeci.</td></tr></table>"
)
TIMELINE = (
    "<h1>R</h1><table><tr><td>1982</td><td>Narodziny.</td></tr>"
    "<tr><td>1998</td><td>Połączenie.</td></tr></table>"
)
WITH_HEADER = "<h1>R</h1><table><tr><th>Rok</th></tr><tr><td>1982</td></tr></table>"
DECLARED = (
    '<h1>R</h1><table role="presentation"><tr><td>Już oznaczona.</td></tr></table>'
)


class Chooser:
    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return self.answer


def build(tmp_path, documents, *, chooser=None, policy=None):
    source = make_book(
        tmp_path / "in.epub",
        {name: PAGE.format(body=body) for name, body in documents.items()},
    )
    return rebuild(
        source, str(tmp_path / "out.epub"),
        policy or Policy.preset("preserve", render_gate="off"),
        resolver=chooser,
    )


def tables_of(result) -> list[dict]:
    """Every <table> of the rebuilt book, as its attributes, in document order."""
    found = []
    with zipfile.ZipFile(result.output_path) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".xhtml") or name.endswith("nav.xhtml"):
                continue
            text = archive.read(name).decode("utf-8")
            for tag in re.findall(r"<table\b[^>]*>", text):
                found.append(dict(re.findall(r'([a-z-]+)="([^"]*)"', tag)))
    return found


def table_questions(chooser):
    return [q for q in chooser.asked if q.kind == "table"]


class TestProseInATable:
    def test_is_listed_once_per_book_and_marked_on_yes(self, tmp_path):
        """Two documents, two layout tables, one question with both on it;
        "mark" writes role="presentation" on each, and the accessibility
        stage stops counting them as tables without headers."""
        chooser = Chooser(Answer(option="layout"))
        result = build(tmp_path, {"c0.xhtml": BOXED_PROSE, "c1.xhtml": ONE_COLUMN}, chooser=chooser)
        asked = table_questions(chooser)
        assert len(asked) == 1
        assert asked[0].recommended == "layout"
        assert asked[0].group.startswith("tables:layout:")
        assert asked[0].group != "tables:layout:"
        assert "Marq" in asked[0].detail and "Pierwszy akapit" in asked[0].detail
        assert all(t.get("role") == "presentation" for t in tables_of(result))
        assert "tables.layout-marked" in rules_of(result)
        assert "a11y.table-without-headers" not in rules_of(result)

    def test_nobody_answering_changes_nothing(self, tmp_path):
        """S-05: no answer, no change — and the report says so twice."""
        result = build(tmp_path, {"c0.xhtml": BOXED_PROSE})
        assert all("role" not in t for t in tables_of(result))
        assert "tables.layout-left-alone" in rules_of(result)
        assert "tables.layout-marked" not in rules_of(result)
        assert "a11y.table-without-headers" in rules_of(result)

    def test_keep_is_keep(self, tmp_path):
        chooser = Chooser(Answer(option=KEEP))
        result = build(tmp_path, {"c0.xhtml": BOXED_PROSE}, chooser=chooser)
        assert all("role" not in t for t in tables_of(result))
        assert "tables.layout-left-alone" in rules_of(result)

    def test_the_text_is_unchanged_to_the_character(self, tmp_path):
        chooser = Chooser(Answer(option="layout"))
        result = build(tmp_path, {"c0.xhtml": BOXED_PROSE}, chooser=chooser)
        with zipfile.ZipFile(result.output_path) as archive:
            text = "".join(
                archive.read(n).decode("utf-8") for n in archive.namelist()
                if n.endswith(".xhtml") and not n.endswith("nav.xhtml")
            )
        assert "Marq słuchał w napięciu, jak obojętny głos wylicza ostatnie uderzenia." in text


class TestWhatIsNeverAsked:
    def test_a_table_of_data_is_a_table(self, tmp_path):
        """Two columns: something stands beside something, and whatever the
        table lacks, hiding it from a screen reader is not the repair."""
        chooser = Chooser(Answer(option="layout"))
        result = build(tmp_path, {"c0.xhtml": TIMELINE}, chooser=chooser)
        assert not table_questions(chooser)
        assert all("role" not in t for t in tables_of(result))
        assert "a11y.table-without-headers" in rules_of(result)

    def test_a_table_with_a_header_cell_is_a_table(self, tmp_path):
        chooser = Chooser(Answer(option="layout"))
        result = build(tmp_path, {"c0.xhtml": WITH_HEADER}, chooser=chooser)
        assert not table_questions(chooser)
        assert all("role" not in t for t in tables_of(result))

    def test_a_table_already_declared_layout_is_left_and_not_counted(self, tmp_path):
        chooser = Chooser(Answer(option="layout"))
        result = build(tmp_path, {"c0.xhtml": DECLARED}, chooser=chooser)
        assert not table_questions(chooser)
        assert not [r for r in rules_of(result) if r.startswith("tables.")]
        assert "a11y.table-without-headers" not in rules_of(result)

    def test_switched_off_nothing_is_asked(self, tmp_path):
        policy = Policy.preset("preserve", render_gate="off")
        policy.detect_layout_tables = False
        chooser = Chooser(Answer(option="layout"))
        result = build(tmp_path, {"c0.xhtml": BOXED_PROSE}, chooser=chooser, policy=policy)
        assert not table_questions(chooser)
        assert all("role" not in t for t in tables_of(result))
        assert "a11y.table-without-headers" in rules_of(result)


class TestTheListAPersonReads:
    def test_a_box_around_a_picture_says_so(self, tmp_path):
        """On the shelf the box around a paragraph has a sibling, the box
        around a picture; a list line reading `""` would say nothing about
        it. The mutation that prints the empty text fails here."""
        from tests.factory import png_bytes

        source = make_book(
            tmp_path / "in.epub",
            {"c0.xhtml": PAGE.format(body='<h1>R</h1><table><tr><td><img src="o.png" alt="Róża"/></td></tr></table>')},
            extra_items='<item id="o" href="o.png" media-type="image/png"/>',
            extra_files={"OEBPS/o.png": png_bytes((30, 10))},
        )
        chooser = Chooser(Answer(option=KEEP))
        rebuild(source, str(tmp_path / "out.epub"),
                Policy.preset("preserve", render_gate="off"), resolver=chooser)
        asked = table_questions(chooser)
        assert len(asked) == 1
        assert "„”" not in asked[0].detail and '""' not in asked[0].detail
        assert "obraz" in asked[0].detail.lower() or "picture" in asked[0].detail.lower()


class TestTheSieveItself:
    def test_layout_and_data_by_shape(self):
        from lxml import etree

        from epubforge.stages.tables import is_layout

        def table(markup):
            return etree.fromstring(f"<table>{markup}</table>")

        assert is_layout(table("<tr><td>a</td></tr>"))
        assert is_layout(table("<tr><td>a</td></tr><tr><td>b</td></tr>"))
        assert not is_layout(table("<tr><td>a</td><td>b</td></tr>"))
        assert not is_layout(table("<tr><th>a</th></tr>"))
        assert not is_layout(table("<tr><td><table><tr><td>x</td></tr></table></td></tr>"))
        assert not is_layout(table(""))
