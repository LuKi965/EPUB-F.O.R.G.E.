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
for a batch). What `remove` takes is `Run.to_remove` and the boundary is
`KEEP_HEIGHT`: between two blocks of text a run of up to three keeps its
height, because that is as likely to be a caesura the writer set as a
converter's leavings; a taller one comes down to a single blank line; and
a run at an edge or beside a heading goes whole, because a blank line
before a heading or after the last paragraph is nobody's composition.

The prose is identical before and after (K1 holds exactly, there is no
text in an empty paragraph), and the removal is a transformation with a
postcondition that says so; what changes is the height of the page, which
the render gate is told about (`stats["space_removed"]`) so it can hold
the document to its ink rather than to its screens.
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

#: How tall a run between two blocks of text may be and still be read as
#: **composition** — a caesura the writer set on purpose — rather than as a
#: converter carrying somebody's page pushing.
#:
#: The owner's call of 2026-09-06, and it is what `DROGA-DO-1.0` 3.4 asked
#: for in the first place: *„przy `remove` przerwy liczone tak, żeby dwie
#: puste linie zostały dwiema"*. A run of two or three in mid-chapter is
#: often a deliberate larger break — a jump in time, the edge of a part —
#: and bringing it down to one makes it look like an ordinary scene break:
#: that is changing the look of the page, not preserving it. Runs of dozens
#: are the other thing entirely (measured: 133 runs of ten and more on the
#: thirteen books looked at, one of them 53 high), and those come down to
#: one blank line.
#:
#: Measured on the shelf before this line was drawn, on those thirteen
#: books: 693 runs between paragraphs, **551 of them two or three high**
#: (548 exactly two) — so this boundary is the difference between a rebuild
#: that reshapes almost every caesura in four of those books and one that
#: touches only what nobody set on purpose.
KEEP_HEIGHT = 3


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
        """What `remove` takes.

        A run at a document edge or beside a heading goes **whole**: a blank
        line before a heading or after the last paragraph is nobody's
        composition. Between two blocks of text the height decides
        (`KEEP_HEIGHT`): up to three stays exactly as it is, taller comes
        down to a single blank line.
        """
        if self.shape != "between":
            return self.paragraphs
        if len(self.paragraphs) <= KEEP_HEIGHT:
            return []
        return self.paragraphs[1:]


@dataclass
class Tally:
    """What a removal actually did, in the terms a person asks about.

    The owner's rule for this entry (2026-09-06): *„wpis w raporcie ma
    podawać liczby, nie sam fakt — ile ciągów skrócono i z ilu do ilu"*.
    A visible change made on somebody's word has to be nameable (K6), and
    „skrócono ciąg z pięćdziesięciu trzech" is a different fact from
    „usunięto 181 akapitów".

    Counted per run rather than derived from the rule, so that a change to
    what `Run.to_remove` returns is reflected here without a second edit:
    a run nothing is taken from is `untouched`, one that keeps some of its
    height is `shortened`, one that goes entirely is `dropped`.
    """

    pieces: int = 0
    shortened: int = 0
    dropped: int = 0
    untouched: int = 0
    #: The tallest run that was shortened, as it stood before.
    longest: int = 0
    #: The most a shortened run came down to (1 today, for every one).
    left: int = 0

    def saw(self, run: "Run") -> None:
        going = len(run.to_remove)
        staying = len(run.paragraphs) - going
        self.pieces += going
        if not going:
            self.untouched += 1
        elif staying:
            self.shortened += 1
            self.longest = max(self.longest, len(run.paragraphs))
            self.left = max(self.left, staying)
        else:
            self.dropped += 1

    def add(self, other: "Tally") -> None:
        self.pieces += other.pieces
        self.shortened += other.shortened
        self.dropped += other.dropped
        self.untouched += other.untouched
        self.longest = max(self.longest, other.longest)
        self.left = max(self.left, other.left)


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
        # What an answer of "remove" would actually take — never the whole
        # count, since a caesura of up to `KEEP_HEIGHT` keeps its height.
        removable = sum(here.removable for _, _, here in found)
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
                    removable=removable, height=KEEP_HEIGHT,
                    examples="\n".join(shown),
                ),
                options=(
                    Option(KEEP, say("paragraphs.empty-runs.keep"), say("paragraphs.empty-runs.keep.why")),
                    Option(
                        "remove",
                        say("paragraphs.empty-runs.remove"),
                        say("paragraphs.empty-runs.remove.why", height=KEEP_HEIGHT),
                    ),
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
                          values={"count": pieces, "runs": runs, "breaks": breaks,
                                  "removable": removable, "height": KEEP_HEIGHT})
                return

        if choice != "remove":
            self.note(ctx, Level.PRESERVED, "paragraphs.empty-runs-kept",
                      values={"count": pieces, "runs": runs, "breaks": breaks,
                              "removable": removable, "height": KEEP_HEIGHT})
            return

        removed = 0
        documents = 0
        removed_by_path: dict[str, int] = {}
        tally = Tally()
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
            here_tally = Tally()

            def mutate(resource=resource, root=root, here=here, taken=taken, here_tally=here_tally):
                for run in here.runs:
                    # Counted before the removal, while the run still knows
                    # its height; merged into the book's tally only if the
                    # contract lets the change stand.
                    here_tally.saw(run)
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
                tally.add(here_tally)
        if not removed:
            return
        self.note(
            ctx, Level.FIX, "paragraphs.empty-runs-removed",
            values={
                "count": removed,
                "documents": documents,
                "breaks": breaks,
                "shortened": tally.shortened,
                "longest": tally.longest,
                "left": tally.left,
                "dropped": tally.dropped,
                "untouched": tally.untouched,
            },
        )
        ctx.report.stats["space_removed"] = removed_by_path
        self.changed(
            ctx,
            Action.REMOVED,
            "structure",
            before=(
                f"{removed} × pusty akapit: {tally.shortened} ciąg(ów) między akapitami "
                f"(najdłuższy {tally.longest}), {tally.dropped} na brzegu albo przy nagłówku"
            ),
            after=(
                f"ciąg między akapitami → {tally.left} pusta linia; "
                f"{tally.untouched} ciąg(ów) zostawionych bez zmiany wysokości; "
                f"{breaks} pojedynczych przerw nietkniętych"
            ),
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
