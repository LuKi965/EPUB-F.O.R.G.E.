"""Prose put in a table: found, listed, and told to assistive software on request.

Record 040 measured the 97 tables without header cells that the accessibility
stage had counted on the shelf, and found them to be two different things.
Sixty-six are tables of data with no trace of a header row — a timeline whose
first row is 1982, a letter square from a puzzle, a song in two languages —
and there is nothing honest to do about those: promoting a row to `<th>`
would tell a screen reader that "1982" heads a column of fifty years. The
other **thirty-one, in seven books, are not tables at all**: a paragraph of
prose that somebody put in a one-cell table to get a border or a margin.
To the eye it is a paragraph. A screen reader announces "table, one row,
one column" before reading it, every time.

There is a standard way to say "this is layout, read the content": WCAG's
technique for layout tables, `role="presentation"` on the `<table>`. Nothing
changes for a sighted reader. The owner's decision (2026-09-02): build it —
*"nielogiczne jest wspieranie WCAG bez wspierania WCAG"*.

The shape is the pictures stage's: evidence, a question, nothing without an
answer (S-05). A table is a layout table here when it has no header cell and
no row with more than one cell — nothing in it stands beside anything else,
so there is no relation for a header to name. One question per book with the
whole list (D-046's shape: the list is this book's and the group carries its
identifier), recommended "mark as layout", and the answer writes the role
onto every table in the list. No character of the text changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import xhtml
from ..decisions import KEEP, TABLE, Option, Question
from ..question_texts import say
from ..report import Action, Automation, Level, Risk
from .base import Context, Stage

#: How many tables the question shows in full; the rest are counted.
SHOWN = 8
#: How much of a table's text the question shows.
EXCERPT = 60

_SPACE = re.compile(r"\s+")


def _role(table) -> str:
    return (table.get("role") or "").strip().lower()


def declared_layout(table) -> bool:
    """Whether the markup already says this table is layout, in either of
    the two words ARIA accepts for it."""
    return _role(table) in ("presentation", "none")


def is_layout(table) -> bool:
    """A table that is not a table.

    No header cell, no nested table, and no row with more than one cell:
    nothing in it stands beside anything else, so there is no relation a
    header could name and nothing a screen reader gains from announcing the
    grid. A one-cell box around a paragraph and a one-column stack of
    paragraphs both qualify; a two-column timeline does not, whatever it
    lacks.
    """
    rows = 0
    for element in table.iter():
        if element is table or not isinstance(element.tag, str):
            continue
        name = xhtml.local_name(element).lower()
        if name in ("th", "table"):
            return False
        if name == "tr":
            rows += 1
            cells = sum(
                1 for child in element
                if isinstance(child.tag, str) and xhtml.local_name(child).lower() in ("td", "th")
            )
            if cells > 1:
                return False
    return rows >= 1


@dataclass
class Place:
    """One layout table: where it is, and what a person needs to recognise it."""

    path: str
    #: Its position among the document's tables, which is how the apply
    #: phase finds it again in the tree it owns.
    index: int
    rows: int
    excerpt: str


def _excerpt(table) -> str:
    """What the table holds, for the list a person reads.

    Its text, cut to a line — and when it has none, what stands there
    instead: on the shelf the box around a paragraph has a sibling, the box
    around a picture, and a list line reading `""` says nothing about it.
    """
    text = _SPACE.sub(" ", "".join(table.itertext())).strip()
    if text:
        return text if len(text) <= EXCERPT else text[:EXCERPT - 1] + "…"
    if any(xhtml.local_name(e).lower() in ("img", "svg", "image") for e in table.iter()):
        return say("tables.layout.image")
    return say("tables.layout.empty")


class TableStage(Stage):
    """Ask about prose put in a table, and mark it as layout on request."""

    name = "tables"

    def run(self, ctx: Context) -> None:
        if not ctx.policy.rewrite_content or not ctx.policy.detect_layout_tables:
            return
        places = self._survey(ctx)
        if not places:
            return
        documents = {place.path for place in places}
        self.note(
            ctx, Level.INFO, "tables.layout-found",
            values={"count": len(places), "docs": len(documents)},
        )
        answer = ctx.decide(self._question(ctx, places))
        if answer.option != "layout":
            self.note(
                ctx, Level.PRESERVED, "tables.layout-left-alone",
                values={"count": len(places), "docs": len(documents)},
            )
            return
        marked = self._apply(ctx, places)
        if marked:
            self.note(ctx, Level.FIX, "tables.layout-marked", values={"count": marked})
            self.changed(
                ctx, Action.ADDED, "table-layout-roles",
                before=f"{marked} table(s) holding prose in one column, announced as tables",
                after='role="presentation", on a person\'s word; the text is unchanged',
                automation=Automation.ASKED, risk=Risk.NONE, reversible=True,
                rule="tables.layout-marked",
            )

    # ---------------------------------------------------------------- survey
    def _survey(self, ctx: Context) -> "list[Place]":
        """Every undeclared layout table, in reading order. Read-only: shared
        parse trees, nothing but paths, indexes and text kept from them."""
        found: list[Place] = []
        for resource in ctx.book.content_docs():
            try:
                root = ctx.parsed(resource).root
            except Exception:
                continue
            for index, table in enumerate(_tables(root)):
                if declared_layout(table) or not is_layout(table):
                    continue
                rows = sum(1 for e in table.iter() if xhtml.local_name(e).lower() == "tr")
                found.append(Place(resource.path, index, rows, _excerpt(table)))
        return found

    # -------------------------------------------------------------- question
    @staticmethod
    def _group(ctx: Context) -> str:
        """"All of them" is this book's list, not the shelf's (D-046)."""
        named = [
            one.value for one in (ctx.book.metadata.identifiers or []) if one.value
        ]
        which = named[0] if named else (ctx.book.nav_path or "?")
        return f"tables:layout:{which}"

    def _question(self, ctx: Context, places: "list[Place]") -> Question:
        shown = "\n".join(
            say("tables.layout.line", where=place.path, rows=place.rows, text=place.excerpt)
            for place in places[:SHOWN]
        )
        left = len(places) - SHOWN
        more = say("tables.layout.more", count=left) if left > 0 else ""
        count = len(places)
        return Question(
            kind=TABLE,
            where=places[0].path,
            summary=say("tables.layout.summary", count=count),
            detail=say("tables.layout.detail", count=count, shown=shown, more=more),
            options=(
                Option(KEEP, say("tables.layout.keep"), say("tables.layout.keep.why")),
                Option("layout", say("tables.layout.mark"), say("tables.layout.mark.why", count=count)),
            ),
            recommended="layout",
            reversible=True,
            risk=Risk.NONE,
            group=self._group(ctx),
            subject=f"{count} tables",
        )

    # ----------------------------------------------------------------- apply
    def _apply(self, ctx: Context, places: "list[Place]") -> int:
        wanted: dict[str, set[int]] = {}
        for place in places:
            wanted.setdefault(place.path, set()).add(place.index)
        marked = 0
        for path, indexes in wanted.items():
            resource = ctx.book.get(path)
            if resource is None:
                continue
            root = ctx.take(resource).root
            touched = False
            for index, table in enumerate(_tables(root)):
                if index not in indexes or declared_layout(table) or not is_layout(table):
                    continue
                table.set("role", "presentation")
                touched = True
                marked += 1
            if touched:
                resource.data = xhtml.serialize(root)
        return marked


def _tables(root):
    return [e for e in xhtml.iter_elements(root) if xhtml.local_name(e).lower() == "table"]
