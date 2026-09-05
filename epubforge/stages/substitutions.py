"""One letter standing for another all through a book, found and asked about.

Filar D, in the shape the measurement gave it. The detector is in
`epubforge/substitutions.py` and decides nothing; this is the stage that runs it
over a book, puts the one pattern it found to whoever is there to answer, and
applies what comes back.

**Why one question and not a hundred and nineteen.** Measured on 25 Polish
books, 12 264 words no dictionary knows: a third are capitalised names, a
quarter are the book's own vocabulary used three times or more, a quarter are
rare words with nothing near them. Correcting any of those would be vandalising
somebody's novel. What is left, 11%, is dominated by one shape — a single letter
standing for another, the same letter every time. One book on that shelf writes
`h` where it means `r`, and writes the correct form elsewhere.

So the evidence is not the word, it is the pattern, and the pattern is one
thing a person can answer. Asking about each word separately would be a hundred
and nineteen questions carrying the same single fact.

**Rare, and that is the finding.** One book in a hundred and sixty. A stage that
found a pattern in every second book would be a stage inventing them.
"""

from __future__ import annotations

from .. import substitutions, typography, xhtml
from ..decisions import ENCODING, KEEP, Option, Question
from ..question_texts import say
from ..report import Action, Level, Risk
from ..transformation import PostconditionFailed, Transformation, carry_out
from .base import Context, Stage, machinery_nav

#: How many of the words the question spells out before it starts counting.
#: The same number the hyphen review uses: enough to judge the pattern by,
#: short of a wall of text nobody reads.
SHOWN = 40


class SubstitutionStage(Stage):
    """A letter systematically written wrong: counted always, changed on answer."""

    name = "substitutions"

    def run(self, ctx: Context) -> None:
        if not ctx.policy.detect_substitutions:
            return
        if not ctx.policy.rewrite_content:
            # Container-only mode promises the content files come out byte for
            # byte, and it cannot keep that promise while asking questions whose
            # answers would edit them.
            return

        documents = []
        for resource in ctx.book.content_docs():
            if machinery_nav(ctx.book, resource):
                continue
            try:
                documents.append((resource, ctx.parsed(resource).root))
            except Exception:  # noqa: BLE001 — the content stage reports this
                continue
        if not documents:
            return

        # The book's own language. A Polish dictionary asked about a Dutch book
        # answers "not a word" to everything, and a pattern found that way would
        # be a pattern in the dictionary rather than in the book.
        tongue = (ctx.book.metadata.language or "").strip() or "pl_PL"

        pattern = substitutions.find(
            ["".join(root.itertext()) for _, root in documents], language=tongue
        )
        if pattern is None:
            return

        self.note(
            ctx,
            Level.WARN,
            "substitutions.pattern-found",
            values={
                "wrong": pattern.wrong,
                "right": pattern.right,
                "count": len(pattern.repairs),
                "evidence": pattern.count,
            },
        )
        answer = ctx.decide(self._question(pattern))
        if answer.option != "repair":
            values = {
                "wrong": pattern.wrong,
                "right": pattern.right,
                "count": len(pattern.repairs),
            }
            if answer.source == "unanswered":
                self.note(ctx, Level.PRESERVED, "substitutions.left-alone", values=values)
            else:
                self.note(ctx, Level.PRESERVED, "substitutions.kept", values=values)
            return
        self._apply(ctx, pattern, documents)

    def _question(self, pattern) -> Question:
        words = sorted(pattern.repairs)
        shown = ", ".join(
            f"„{word}” → „{pattern.repairs[word]}”" for word in words[:SHOWN]
        )
        more = (
            say("substitution.more", count=len(words) - SHOWN)
            if len(words) > SHOWN
            else ""
        )
        return Question(
            kind=ENCODING,
            where="",
            summary=say(
                "substitution.summary",
                wrong=pattern.wrong,
                right=pattern.right,
                count=len(words),
            ),
            detail=say(
                "substitution.detail",
                wrong=pattern.wrong,
                right=pattern.right,
                evidence=pattern.count,
                shown=shown,
                more=more,
            ),
            options=(
                Option(KEEP, say("substitution.keep"), say("substitution.keep.why")),
                Option(
                    "repair",
                    say("substitution.repair"),
                    say("substitution.repair.why", count=len(words)),
                ),
            ),
            # An opinion. The queue never acts on one by itself.
            recommended="repair",
            # The letter is gone from the output; nothing in the result says
            # what stood there before.
            reversible=False,
            risk=Risk.CONTENT,
            group="encoding:substitution",
            subject=f"{pattern.wrong}:{pattern.right}:{len(words)}",
        )

    def _apply(self, ctx: Context, pattern, documents) -> None:
        """The repair, document by document, each one able to be refused alone.

        The guard is the one the hyphen rule uses and for the same reason: this
        edits *words*, which is further than any other rule in this program
        goes. The invariant is *the document differs in nothing but the words on
        the agreed list*, and `substitutions.apart_from` is where it is stated.
        A sentence that went missing, a word repaired that nobody agreed to,
        anything at all the pass did beyond its list — each shows up as a
        mismatch and the document goes back exactly as it came in.
        """
        repaired = reverted = 0
        for resource, root in documents:
            before = list(root.itertext())
            whole = "".join(before)
            planned = {
                word: right
                for word, right in pattern.repairs.items()
                if word in whole
            }
            if not planned:
                continue

            def mutate(root=root, planned=planned, resource=resource) -> int:
                changed = 0
                for element, attribute in typography.text_nodes(root):
                    text = getattr(element, attribute)
                    if not text:
                        continue
                    written = substitutions.rewrite(text, planned)
                    if written != text:
                        setattr(element, attribute, written)
                        changed += 1
                if changed:
                    resource.data = xhtml.serialize(root)
                return changed

            step = Transformation(
                rule="substitutions.replaced",
                target=resource.path,
                precondition=lambda planned=planned: bool(planned),
                postcondition=lambda root=root, before=before, planned=planned: (
                    typography.unchanged(
                        substitutions.apart_from(before, planned),
                        substitutions.apart_from(root.itertext(), planned),
                    )
                ),
                reversible=False,
            )
            try:
                repaired += bool(
                    carry_out(
                        step,
                        snapshot=lambda resource=resource: resource.data,
                        restore=lambda data, resource=resource: setattr(
                            resource, "data", data
                        ),
                        mutate=mutate,
                    )
                )
            except PostconditionFailed:
                reverted += 1

        if repaired:
            self.note(
                ctx,
                Level.FIX,
                "substitutions.replaced",
                values={
                    "wrong": pattern.wrong,
                    "right": pattern.right,
                    "count": len(pattern.repairs),
                    "documents": repaired,
                },
            )
            # In the ledger, beside the hyphen rule and for the same reason:
            # this changes words. Irreversible from the output alone — nothing
            # in the rebuilt file records that `prawda` was once written with
            # the other letter.
            self.changed(
                ctx,
                Action.REPLACED,
                "text",
                before=f"„{pattern.wrong}” w {len(pattern.repairs)} słowach",
                after=f"„{pattern.right}”, wskazane przez człowieka",
                risk=Risk.CONTENT,
                reversible=False,
                rule="substitutions.replaced",
            )
        if reverted:
            self.note(
                ctx,
                Level.WARN,
                "substitutions.reverted",
                values={"count": reverted},
            )
