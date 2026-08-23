"""The one stage that changes text on purpose — and checks that it did not.

Roadmap [7]. Every other stage moves markup around a text it is forbidden to
touch; this one edits the text, so it is the only place K1 — *no character of
the book's text is lost* — cannot be enforced as written.

It is not switched off here. It is **replaced by a stronger arrangement**: the
stage folds the document's text to a canonical form before and after its own
work and compares the two, and a document that fails goes back exactly as it
came in. A rule cannot ship a defect past that, only a reverted document and a
warning saying so.

Off by default and reached by no preset. That is the class-2 flag the roadmap
asks for, and the owner's standing rule about anything that changes a book
without being asked.

**Two rules to start with, chosen by measurement rather than by ease.** The
roadmap's risk classes were written before there were numbers; the numbers say
class 1 (control characters, zero-width, double spaces) and class 3
(reconstruction) have almost no customers — 0 books out of 93 and 10 out of
2 200 for zero-width characters, 0 and 1 for mojibake. What both shelves do
have is `...` typed where `…` belongs, and single-letter conjunctions left to
fall off the end of a line.

The third rule is the quotes, and it took the longest to be safe. Only the
straight `"` is retyped, because a curly mark already says which end of a pair
it is and a straight one says nothing — and it is also the one a book gets
wrong, since it is what a keyboard produces. It is retyped into **the book's
own convention**, never into the typographically correct one: a book set in
`«…»` has made a decision and the job is to repair inconsistency, not taste
(K5). A book with no settled convention is left alone and told so.
"""

from __future__ import annotations

import re

from .. import typography, xhtml
from ..decisions import KEEP, Option, Question, TEXT
from ..question_texts import say
from ..report import Level, Risk
from .base import Context, Stage

#: The three rules, named once so the question, the answer, the repair and the
#: report cannot drift apart into four spellings of the same thing.
ELLIPSIS = "ellipsis"
CONJUNCTIONS = "conjunctions"
QUOTES = "quotes"

#: How many places a question shows before it stops showing and starts
#: counting. Three, because these are one-line excerpts and the question is
#: about a habit running through a whole book, not about the excerpts.
SAMPLES = 3

#: The straight quote, as an expression, so the sample finder can treat all
#: three rules the same way.
_STRAIGHT = re.compile(r'"')

#: Three dots, and not four or two. A run of four is somebody's own punctuation
#: and an ellipsis is not longer than itself.
_THREE_DOTS = re.compile(r"(?<!\.)\.\.\.(?!\.)")

#: A Polish single-letter conjunction, and the space that convention binds to
#: the following word. Written to match only where the letter stands alone:
#: preceded by the start of the run, whitespace or an opening bracket or quote,
#: and followed by exactly one space and then a word character.
#:
#: `(?<![^\s(„«"])` rather than `\b`, because `\b` is true in the middle of
#: `a-b` and after a full stop, and neither is a conjunction standing on its
#: own.
_CONJUNCTION = re.compile(r"(?<![^\s(„«\"])([aiouwzAIOUWZ]) (?=\w)")

NBSP = " "


#: How much of the sentence a sample carries on each side of what was found.
AROUND = 34


def _around(text: str, expression) -> str:
    """One short excerpt showing the first place *expression* matches.

    A count says how much; an excerpt says what. Both are needed: "1 174
    places" is answerable, and "1 174 places, the first of them here" is
    answerable with confidence.
    """
    found = expression.search(text)
    if found is None:
        return ""
    excerpt = text[max(0, found.start() - AROUND): found.end() + AROUND]
    return " ".join(excerpt.split())


class TypographyStage(Stage):
    """Repairs the text itself, once asked, and verifies its own work."""

    name = "typography"

    def run(self, ctx: Context) -> None:
        if not getattr(ctx.policy, "detect_typography", True) and not ctx.policy.typography:
            return
        if not ctx.policy.rewrite_content:
            # Container-only mode promises the content files come out byte for
            # byte. A stage that edits text has nothing to say there, and the
            # promise outranks the flag.
            return

        language = (ctx.book.metadata.language or "").strip().lower()

        # Parsed once and kept. The convention has to be decided over the whole
        # book before the first document is touched, and parsing everything
        # twice to do that would double the cost of the pass.
        documents = []
        for resource in ctx.book.content_docs():
            if resource.path == ctx.book.nav_path:
                continue
            try:
                documents.append((resource, xhtml.parse_document(resource.data, resource.path).root))
            except Exception:  # noqa: BLE001 — the content stage reports this
                continue

        convention, marks, straight = self._convention(documents)

        # Counted before anything is touched, because the question has to say
        # how much of the book it is about — "1 174 places" is something a
        # person can answer and "some typography" is not.
        found = self._survey(documents, language, marks)
        agreed = self._agree(ctx, found, convention)
        if not agreed:
            self._report(ctx, 0, 0, 0, convention, [], found, agreed, straight)
            return

        ellipses = conjunctions = quotes = 0
        reverted: list[str] = []
        for resource, root in documents:
            before = "".join(root.itertext())

            changed = self._repair(root, language, marks, agreed)
            if not any(changed):
                continue

            after = "".join(root.itertext())
            if not typography.unchanged(before, after):
                # Not "log it and carry on". The document goes back as it came
                # in, because a stage that cannot show it kept the text has no
                # business having edited it.
                reverted.append(resource.path)
                continue

            resource.data = xhtml.serialize(root)
            ellipses += changed[0]
            conjunctions += changed[1]
            quotes += changed[2]

        self._report(
            ctx, ellipses, conjunctions, quotes, convention, reverted, found,
            agreed, straight,
        )

    def _survey(self, documents, language: str, marks) -> "dict[str, dict]":
        """How many places each rule would touch, and a few of them to look at.

        Nothing is changed here. This is the half that lets the stage ask before
        it acts: a rule with no candidates puts no question, and a rule with
        candidates puts one that names them.
        """
        polish = language.startswith("pl")
        found: dict[str, dict] = {}

        def seen(rule: str, count: int, sample: str) -> None:
            entry = found.setdefault(rule, {"count": 0, "samples": []})
            entry["count"] += count
            if len(entry["samples"]) < SAMPLES and sample:
                entry["samples"].append(sample)

        for _, root in documents:
            for element, attribute in typography.text_nodes(
                root, language=language or None
            ):
                text = getattr(element, attribute)
                if not text:
                    continue
                hits = _THREE_DOTS.findall(text)
                if hits:
                    seen(ELLIPSIS, len(hits), _around(text, _THREE_DOTS))
                if polish:
                    hits = _CONJUNCTION.findall(text)
                    if hits:
                        seen(CONJUNCTIONS, len(hits), _around(text, _CONJUNCTION))
                if marks is not None and '"' in text:
                    seen(QUOTES, text.count('"'), _around(text, _STRAIGHT))
        return {rule: entry for rule, entry in found.items() if entry["count"]}

    def _agree(self, ctx: Context, found: dict, convention) -> "set[str]":
        """Which rules somebody said yes to. Never more than that.

        One question per rule rather than one for "typography", because the
        three are different in kind: an ellipsis typed as three dots is nobody's
        style, binding a single-letter conjunction is a Polish convention, and
        retyping a straight quote is repairing this book's inconsistency with
        itself. Somebody can want one and not another, and a single question
        would make that impossible to say.

        The policy flag is a standing yes given in advance — the same shape the
        mojibake repair uses — and not a fourth way of changing text unasked.
        """
        agreed = set()
        for rule in (ELLIPSIS, CONJUNCTIONS, QUOTES):
            entry = found.get(rule)
            if not entry:
                continue
            if ctx.policy.typography:
                agreed.add(rule)
                continue
            answer = ctx.decide(self._question(rule, entry, convention))
            if answer.option == "repair":
                agreed.add(rule)
        return agreed

    def _question(self, rule: str, entry: dict, convention) -> Question:
        shown = "\n".join(f"…{sample}…" for sample in entry["samples"])
        count = entry["count"]
        return Question(
            kind=TEXT,
            where="",
            summary=say(f"typography.{rule}.summary", count=count),
            detail=say(
                f"typography.{rule}.detail",
                count=count,
                shown=shown,
                convention=say(f"typography.convention.{convention}")
                if convention
                else "",
            ),
            options=(
                Option(
                    KEEP,
                    say(f"typography.{rule}.keep"),
                    say(f"typography.{rule}.keep.why"),
                ),
                Option(
                    "repair",
                    say(f"typography.{rule}.repair"),
                    say(f"typography.{rule}.repair.why", count=count),
                ),
            ),
            # An opinion, and the queue never acts on one by itself.
            recommended="repair",
            # The old shape is gone from the output; nothing in the result says
            # what stood there before.
            reversible=False,
            risk=Risk.CONTENT,
            group=f"typography:{rule}",
            subject=f"{rule}:{count}",
        )

    def _convention(self, documents):
        """The book's own quoting convention, over the whole book.

        Whole-book on purpose. A chapter of dialogue and a chapter of none are
        the same book, and deciding per document would retype one chapter into
        a convention the next one contradicts.

        Counted over the **text**, never the markup — and that distinction cost
        a debugging session. Reading the serialised document counts every
        attribute delimiter as a straight quote, so a Polish book set entirely
        in `„…”` came back with fourteen straight quotes it did not have, no
        convention reached two thirds, and the rule declined to fire on the book
        it was written for.

        **Counted over the prose, and `itertext` is not the prose.** The
        paragraph above records the first half of this lesson — reading the
        serialised document counts attribute delimiters as quotes — and the
        second half was still here afterwards: `itertext` yields the contents of
        `<style>` and `<script>` too, and a stylesheet is full of straight
        quotes. Measured on 160 books: **twelve get a different answer** once
        those are excluded. Nine that read as "straight" turn out to have no
        settled convention at all (the straight quotes were CSS), and three
        change to a real convention — including one the rule had been declining
        to serve. Both directions are wrong the same way: a convention read out
        of a stylesheet is not the book's.

        So the count walks the same nodes the repair walks. That is the point:
        the evidence and the edit have to be about the same text.
        """
        counts: dict[str, int] = {}
        for _, root in documents:
            prose = "".join(
                getattr(element, attribute) or ""
                for element, attribute in typography.text_nodes(root)
            )
            for shape, count in typography.count_quotes(prose).items():
                counts[shape] = counts.get(shape, 0) + count
        name = typography.convention(counts)
        straight = counts.get("straight", 0)
        if name is None or name == "straight":
            # "straight" is a settled convention and retyping it into itself is
            # not a repair; it is also what a book that simply never used curly
            # marks looks like, and that book has not made a mistake.
            return name, None, straight
        return name, typography.marks_for(name), straight

    def _repair(self, root, language: str, marks, agreed) -> tuple[int, int, int]:
        """Apply the agreed rules to every editable text node.

        *agreed* is the set somebody said yes to, and a rule outside it does not
        run at all — not "runs and is discarded". Returns what changed.
        """
        ellipses = conjunctions = quotes = 0
        polish = language.startswith("pl") and CONJUNCTIONS in agreed
        # Per document, not per book: an unbalanced quote in one chapter must
        # not invert every quotation in the next one.
        inside = False
        for element, attribute in typography.text_nodes(root, language=language or None):
            text = getattr(element, attribute)
            if not text:
                continue
            repaired = text
            if ELLIPSIS in agreed:
                repaired, count = _THREE_DOTS.subn("…", repaired)
                ellipses += count
            if polish:
                # Polish typographic convention, gated on the language the
                # *metadata stage settled* — which is the declared one unless
                # the text plainly contradicted it, in which case that stage
                # has already corrected it and said so. That ordering is the
                # whole reason this rule reaches the books it needs to: a
                # library of 2 200 Polish books declaring `en` would otherwise
                # be skipped by the rule written for them.
                repaired, count = _CONJUNCTION.subn(rf"\1{NBSP}", repaired)
                conjunctions += count
            if marks is not None and QUOTES in agreed:
                repaired, count, inside = typography.retype_quotes(
                    repaired, marks[0], marks[1], inside=inside
                )
                quotes += count
            if repaired != text:
                setattr(element, attribute, repaired)
        return ellipses, conjunctions, quotes

    def _report(
        self,
        ctx: Context,
        ellipses: int,
        conjunctions: int,
        quotes: int,
        convention: str | None,
        reverted: list[str],
        found: dict,
        agreed: set,
        straight: int,
    ) -> None:
        # What was found and not agreed to. Said first, because a rule that
        # declined to act has to say what it declined to act on — otherwise a
        # book with a thousand candidates and a book with none produce the same
        # silent report (S-05 leaves the book alone; it does not leave the
        # reader uninformed).
        for rule in (ELLIPSIS, CONJUNCTIONS, QUOTES):
            entry = found.get(rule)
            if not entry or rule in agreed:
                continue
            # Spelled out three times rather than built from `rule`. A computed
            # identifier is invisible to every tool that reads this source —
            # the catalogue check, the translation check, the survey that says
            # which stage reports what — and the project keeps that invariant
            # as a test. Three literals is the price and it is worth paying.
            count = {"count": entry["count"]}
            if rule == ELLIPSIS:
                self.note(ctx, Level.PRESERVED, "typography.ellipsis-left-alone", values=count)
            elif rule == CONJUNCTIONS:
                self.note(ctx, Level.PRESERVED, "typography.conjunctions-left-alone", values=count)
            else:
                self.note(ctx, Level.PRESERVED, "typography.quotes-left-alone", values=count)
        if ellipses:
            self.note(
                ctx, Level.FIX, "typography.ellipsis-normalised", values={"count": ellipses}
            )
        if conjunctions:
            self.note(
                ctx,
                Level.FIX,
                "typography.conjunctions-bound",
                values={"count": conjunctions},
            )
        if quotes:
            self.note(
                ctx,
                Level.FIX,
                "typography.quotes-retyped",
                values={"count": quotes, "convention": convention},
            )
        elif convention is None and straight:
            # Said out loud rather than skipped in silence: "this book has not
            # settled on a convention" is a fact about the book, and a rule that
            # declines to fire should say why it declined.
            #
            # **Only when there was something to decline.** Since filar E the
            # stage looks at every book instead of only the ones somebody
            # switched it on for, and without this second condition every book
            # with no straight quotes at all — most of them — would carry a line
            # explaining why a rule with no work did not do it. A report that
            # says something about every book says nothing.
            self.note(ctx, Level.INFO, "typography.quotes-unsettled")
        if reverted:
            # A warning rather than an error: the book is intact, which is what
            # the check is for. But a rule that cannot prove it kept the text is
            # a defect in this stage and the report should say so out loud
            # rather than leave a silent no-op.
            self.note(
                ctx,
                Level.WARN,
                "typography.reverted",
                values={"count": len(reverted)},
                location=reverted[0] if len(reverted) == 1 else f"{len(reverted)} documents",
            )
