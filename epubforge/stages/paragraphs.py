"""Runs of empty paragraphs: a converter pushing text, behind a setting.

D-054, measured on the owner's shelf (20 213 empty paragraphs in 102
books): a **single** empty paragraph between two paragraphs of text is a
break between scenes — composition, untouched and unasked. A run of two or
more, a run at the edge of a document or a section, and a run beside a
heading are somebody pushing text onto a new page in a word processor, and
the converter carried the pushing along (1 044 runs, 11 450 pieces; the
runs of five and more average some fifty pieces each).

What becomes of the runs is `Policy.empty_paragraph_runs` — `keep` (the
default: nothing moves, the report counts), `ask` (one question per book,
with the neighbourhood of the runs shown), `remove` (the standing answer
for a batch). Removing a run between two blocks of text leaves **one**
empty paragraph standing, so that a break the writer may have meant is
still a break; a run at an edge or beside a heading goes whole, because a
blank line before a heading or after the last paragraph is nobody's
composition. The prose is identical before and after (K1 holds exactly,
there is no text in an empty paragraph), and the removal is a
transformation with a postcondition that says so; what changes is the
height of the page, which the render gate is told about
(`stats["space_removed"]`) so it can hold the document to its ink rather
than to its screens.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import fidelity, xhtml
from ..decisions import KEEP, STYLE, Option, Question
from ..question_texts import say
from ..report import Action, Automation, Level, Risk
from ..transformation import PostconditionFailed, Transformation, carry_out
from .base import Context, Stage

#: The block-level children a run is counted among — the same list the
#: measurement of 2026-09-05 used (`runs/audyt/narzedzia-2026-09-05/
#: puste-akapity.py`), so that the numbers in the report are the numbers
#: in D-054.
BLOCKS = frozenset({
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
    "ul", "ol", "table", "section", "hr", "figure",
})
#: Containers whose block children are read as one sequence.
CONTAINERS = frozenset({"body", "div", "section", "blockquote"})
HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
#: What a paragraph may hold and still be empty: nothing that draws.
DRAWS = frozenset({"img", "svg", "image", "video", "audio", "object", "canvas"})

#: Characters a preview shows on either side of a run.
_PREVIEW = 40
_PREVIEWS = 4


@dataclass
class Run:
    """One run of empty paragraphs and where it stands."""

    parent: object
    paragraphs: list
    #: The block before and after the run, or `None` at an edge.
    before: object = None
    after: object = None

    @property
    def shape(self) -> str:
        if self.before is None or self.after is None:
            return "edge"
        if _name(self.before) in HEADINGS or _name(self.after) in HEADINGS:
            return "heading"
        return "between"

    @property
    def is_a_break(self) -> bool:
        """A single empty paragraph between two blocks of text: a break
        between scenes, the writer's, and nobody's candidate."""
        return len(self.paragraphs) == 1 and self.shape == "between"

    @property
    def to_remove(self) -> list:
        """What `remove` takes: the whole run at an edge or beside a
        heading, all but one between two blocks of text."""
        if self.shape == "between":
            return self.paragraphs[1:]
        return self.paragraphs


@dataclass
class Found:
    runs: list = field(default_factory=list)
    breaks: int = 0

    @property
    def pieces(self) -> int:
        return sum(len(run.paragraphs) for run in self.runs)

    @property
    def removable(self) -> int:
        return sum(len(run.to_remove) for run in self.runs)


def _name(element) -> str:
    return xhtml.local_name(element).lower()


def is_empty(element) -> bool:
    """A `<p>` that draws nothing: no text once no-break spaces are
    folded, nothing inside it that draws."""
    if _name(element) != "p":
        return False
    if any(_name(child) in DRAWS for child in element.iter()):
        return False
    return "".join(element.itertext()).replace(" ", " ").strip() == ""


def find_runs(root) -> Found:
    """Every run of empty paragraphs in *root*, and how many single breaks
    were passed over."""
    found = Found()
    body = next((e for e in root.iter() if _name(e) == "body"), root)
    containers = [body] + [e for e in body.iter() if e is not body and _name(e) in CONTAINERS]
    for parent in containers:
        children = [child for child in parent if _name(child) in BLOCKS]
        index = 0
        while index < len(children):
            if not is_empty(children[index]):
                index += 1
                continue
            end = index
            while end < len(children) and is_empty(children[end]):
                end += 1
            run = Run(
                parent=parent,
                paragraphs=children[index:end],
                before=children[index - 1] if index > 0 else None,
                after=children[end] if end < len(children) else None,
            )
            if run.is_a_break:
                found.breaks += 1
            else:
                found.runs.append(run)
            index = end
    return found


def _edge_text(element, *, start: bool) -> str:
    text = " ".join("".join(element.itertext()).split())
    if not text:
        return ""
    if start:
        return text[:_PREVIEW] + ("…" if len(text) > _PREVIEW else "")
    return ("…" if len(text) > _PREVIEW else "") + text[-_PREVIEW:]


def preview(run: Run) -> str:
    """The neighbourhood of one run, as a person reads it: the end of what
    stands before, the run, the start of what stands after."""
    before = _edge_text(run.before, start=False) if run.before is not None else "⟨początek⟩"
    after = _edge_text(run.after, start=True) if run.after is not None else "⟨koniec⟩"
    count = len(run.paragraphs)
    return f"{before} ⏎ [{count} × pusty akapit] ⏎ {after}"


def remove(run: Run) -> int:
    """Take the run's removable paragraphs out, keeping every tail's text
    where a reader would find it."""
    taken = 0
    for paragraph in run.to_remove:
        parent = paragraph.getparent()
        if parent is None:
            continue
        tail = paragraph.tail or ""
        previous = paragraph.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
        parent.remove(paragraph)
        taken += 1
    return taken


class ParagraphStage(Stage):
    name = "paragraphs"
    mutates = True

    def run(self, ctx: Context) -> None:
        if not ctx.policy.rewrite_content:
            # `minimal` does not open the documents, and this would be the
            # only stage that did.
            return
        found: list[tuple[object, object, Found]] = []
        for resource in ctx.book.content_docs():
            try:
                root = ctx.parsed(resource).root
            except Exception:  # noqa: BLE001 — the content stage reports an unreadable document
                continue
            here = find_runs(root)
            if here.runs:
                found.append((resource, root, here))
        runs = sum(len(here.runs) for _, _, here in found)
        pieces = sum(here.pieces for _, _, here in found)
        breaks = sum(here.breaks for _, _, here in found)
        if not runs:
            return

        choice = ctx.policy.empty_paragraph_runs
        automation = Automation.DETERMINISTIC
        if choice == "ask":
            shown = []
            for _, _, here in found:
                for run in here.runs:
                    if len(shown) < _PREVIEWS:
                        shown.append(preview(run))
            shapes = {"edge": 0, "heading": 0, "between": 0}
            for _, _, here in found:
                for run in here.runs:
                    shapes[run.shape] += len(run.paragraphs)
            question = Question(
                kind=STYLE,
                where=found[0][0].path,
                summary=say("paragraphs.empty-runs.summary", count=pieces, runs=runs),
                detail=say(
                    "paragraphs.empty-runs.detail",
                    count=pieces, runs=runs, documents=len(found), breaks=breaks,
                    edge=shapes["edge"], heading=shapes["heading"], between=shapes["between"],
                    examples="\n".join(shown),
                ),
                options=(
                    Option(KEEP, say("paragraphs.empty-runs.keep"), say("paragraphs.empty-runs.keep.why")),
                    Option("remove", say("paragraphs.empty-runs.remove"), say("paragraphs.empty-runs.remove.why")),
                ),
                recommended="remove",
                reversible=False,
                risk=Risk.APPEARANCE,
                group="paragraphs:empty-runs",
                subject=f"{pieces} akapitów",
            )
            answer = ctx.decide(question)
            choice = "remove" if answer.option == "remove" else "keep"
            automation = Automation.ASKED
            if choice == "keep" and answer.source == "unanswered":
                self.note(ctx, Level.PRESERVED, "paragraphs.empty-runs-unanswered",
                          values={"count": pieces, "runs": runs, "breaks": breaks})
                return

        if choice != "remove":
            self.note(ctx, Level.PRESERVED, "paragraphs.empty-runs-kept",
                      values={"count": pieces, "runs": runs, "breaks": breaks})
            return

        removed = 0
        documents = 0
        removed_by_path: dict[str, int] = {}
        for resource, _, here in found:
            # Taken fresh and given up: the tree is about to change.
            root = ctx.take(resource).root
            here = find_runs(root)
            planned = here.removable
            if not planned:
                continue
            before_data = resource.data
            before_prose = fidelity.document_text(before_data)
            step = Transformation(
                rule="paragraphs.empty-runs-removed",
                target=resource.path,
                precondition=lambda planned=planned: planned > 0,
                # The prose is the same to the character, and exactly the
                # planned paragraphs went: nothing else may have moved.
                postcondition=lambda resource=resource, before_prose=before_prose, root=root, planned=planned, here=here: (
                    fidelity.document_text(resource.data) == before_prose
                    and _taken(here) == planned
                ),
                reversible=False,
            )
            taken = {"count": 0}

            def mutate(resource=resource, root=root, here=here, taken=taken):
                for run in here.runs:
                    taken["count"] += remove(run)
                resource.data = xhtml.serialize(root)
                return taken["count"]

            try:
                made = carry_out(
                    step,
                    snapshot=lambda before_data=before_data: before_data,
                    restore=lambda data, resource=resource: setattr(resource, "data", data),
                    mutate=mutate,
                )
            except PostconditionFailed:
                self.note(ctx, Level.WARN, "paragraphs.empty-runs-left",
                          values={"count": planned, "document": resource.path})
                continue
            if made:
                removed += made
                documents += 1
                removed_by_path[resource.path] = made
        if not removed:
            return
        self.note(ctx, Level.FIX, "paragraphs.empty-runs-removed",
                  values={"count": removed, "documents": documents, "breaks": breaks})
        ctx.report.stats["space_removed"] = removed_by_path
        self.changed(
            ctx,
            Action.REMOVED,
            "structure",
            before=f"{removed} × pusty akapit w ciagach, na brzegu albo przy naglowku",
            after="usuniete; pojedyncze przerwy miedzy akapitami zostaly",
            automation=automation,
            risk=Risk.APPEARANCE,
            reversible=False,
            rule="paragraphs.empty-runs-removed",
        )


def _taken(here: Found) -> int:
    """How many of the run's removable paragraphs are no longer in a tree."""
    return sum(
        1 for run in here.runs for paragraph in run.to_remove if paragraph.getparent() is None
    )
