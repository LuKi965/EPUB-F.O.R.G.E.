"""Stage protocol and the shared context threaded through the rebuild."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..budget import Budget
from ..model import Book
from ..policy import Policy
from ..references import Answers, Decision, Resolver, Unresolved
from ..report import Level, Report


@dataclass
class Context:
    book: Book
    policy: Policy
    report: Report
    #: Maps every original container path to its current one. Built once the
    #: path-mutating stages have finished, so href rewriting has a single source
    #: of truth even after several renames.
    path_map: dict[str, str] = field(default_factory=dict)
    #: The unique identifier as found in the source, captured before metadata
    #: normalisation because font deobfuscation is keyed on it.
    original_identifier: str | None = None

    #: What this book is allowed to cost. One per rebuild, because the deadline
    #: it carries starts when it is made — a shared default would measure how
    #: long the process has been running rather than how long this book took.
    budget: Budget = field(default_factory=Budget)

    #: Stylesheets that must gain the consolidated watermark rule, because a
    #: document they style had its repeated inline styling removed.
    watermark_stylesheets: set[str] = field(default_factory=set)

    #: Every id present in each finished document, so navigation can check
    #: that the fragments it points at actually exist.
    document_ids: dict[str, set[str]] = field(default_factory=dict)

    #: What the book is like as a whole, measured once by `ProfileStage` and
    #: read by nothing yet. Points [4], [5] and [7] of the roadmap each need the
    #: same answer to "is this the rule in this book or the exception", and one
    #: shared measurement is the difference between three consistent rules and
    #: three that guess separately.
    profile: object | None = None

    #: Every class and id that appears anywhere in the book's markup, collected
    #: while the content stage has the documents open. The stylesheet stage
    #: needs it to answer "can this rule ever match anything here", and parsing
    #: every document a second time to ask would double the cost of a rebuild.
    used_classes: set[str] = field(default_factory=set)
    used_ids: set[str] = field(default_factory=set)

    #: True when any document carries a script. A script can add a class at
    #: runtime, which makes "this selector matches nothing" a statement about
    #: the book as it sits on disk and not about the book as it is read.
    scripted: bool = False

    #: Documents where out-of-flow positioning was translated into an in-flow
    #: equivalent that renders the same way. The content stage does the work —
    #: it is the only stage that can see whether a rule's target is the whole
    #: page — and the style stage needs to know, because a declaration that has
    #: been given a working equivalent is neither kept nor removed: it is
    #: superseded, and the report should say so.
    positioning_translated: set[str] = field(default_factory=set)

    #: Documents holding an absolutely positioned element whose containing block
    #: is an ancestor the publisher positioned on purpose — a caption over a
    #: picture, a badge on a cover. That construct never escapes pagination,
    #: because it cannot leave the box that contains it, so the reasoning behind
    #: removing out-of-flow positioning does not apply to it at all.
    positioning_contained: set[str] = field(default_factory=set)

    #: What made this book, most confident first — see :mod:`epubforge.fingerprint`.
    #: Filled by the profile stage and read by nothing yet; roadmap [7] is where
    #: a rule first decides how careful to be based on it.
    fingerprint: list = field(default_factory=list)

    #: Per-document ``{old_id: new_id}`` for ids that were not valid XML names.
    #: Navigation targets are fragments too, so they need the same remapping.
    id_map: dict[str, dict[str, str]] = field(default_factory=dict)

    #: References whose anchor this program could not honestly resolve — see
    #: :mod:`epubforge.references`. Kept on the context rather than counted and
    #: forgotten, because two things outside the stage need them: `strict`
    #: refuses to publish a book that has any, and the window lists them.
    unresolved: list[Unresolved] = field(default_factory=list)

    #: Who to ask when the program cannot decide. `None` — a batch run, the
    #: corpus, a library caller — means nobody is there, and nothing is asked.
    resolver: Resolver | None = None

    #: What was asked and answered during this rebuild.
    answers: Answers = field(default_factory=Answers)

    def ask(self, question: Unresolved) -> Decision:
        """Put one unresolvable reference to the person, if there is one.

        Always returns a decision; `Decision()` — leave it alone — is what
        comes back when nobody is there to ask, which is the default.
        """
        return self.answers.ask(self.resolver, question)

    def remap_fragment(self, target: str | None) -> str | None:
        if not target or "#" not in target:
            return target
        path, _, fragment = target.partition("#")
        renamed = self.id_map.get(path, {}).get(fragment)
        return f"{path}#{renamed}" if renamed else target

    def build_path_map(self) -> None:
        self.path_map = {
            (resource.original_path or resource.path): resource.path
            for resource in self.book.resources.values()
        }

    def remap(self, original_path: str) -> str | None:
        return self.path_map.get(original_path)


class Stage:
    """One transformation pass over the book."""

    name = "stage"

    def run(self, ctx: Context) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def note(
        self,
        ctx: Context,
        level: Level,
        rule: str,
        *,
        values: dict | None = None,
        location: str | None = None,
        detail: str | None = None,
    ):
        ctx.report.add(
            self.name, level, rule, values=values, location=location, detail=detail
        )


__all__ = ["Context", "Stage", "Level", "Policy", "Report", "Book"]
