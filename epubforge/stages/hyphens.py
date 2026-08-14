"""Finding hyphens a conversion left inside words, and asking about them.

BA-2026-001. The detector is in `epubforge/hyphens.py` and does not decide
anything; this is the stage that runs it over a book, puts the confirmed
candidates to whoever is there to answer, and applies what comes back.

Three things about the shape, each of which is a decision rather than an
accident:

**Detection is not gated on the typography flag.** That flag guards a stage that
*edits* text without being asked. Counting broken words edits nothing, and a
book with forty-six of them should say so whether or not anybody has switched
typography on — measured on the owner's shelf, one book had forty-six and the
report had no way to mention it.

**Only `CONFIRMED` candidates become questions.** Measured across thirty-two
books: 67 confirmed, 101 likely and 88 uncertain. Reading the second and third
lists, almost every entry is a real word — `marksizm-leninizm`, `savoir-vivre`,
`ping-pong`, `Karol-wybawca`. A queue of a hundred and ninety questions that are
mostly not defects is a queue nobody finishes, and the audit's own warning about
this finding was the risk of an over-eager future heuristic. The counts are
reported; only the evidenced ones are asked about.

**Nothing is joined without an answer.** `recommended` on a confirmed candidate
is `join`, and a recommendation is an opinion. A batch run, the corpus and any
library caller change nothing at all.
"""

from __future__ import annotations

from .. import hyphens, typography, xhtml
from ..decisions import KEEP
from ..report import Action, Level, Risk
from .base import Context, Stage


class HyphenStage(Stage):
    """Hyphens inside words: counted always, changed only when somebody says."""

    name = "hyphens"

    def run(self, ctx: Context) -> None:
        if not ctx.policy.detect_hyphens:
            return
        if not ctx.policy.rewrite_content:
            # Container-only mode promises the content files come out byte for
            # byte, and it cannot keep that promise while asking questions whose
            # answers would edit them.
            return

        documents = []
        for resource in ctx.book.content_docs():
            if resource.path == ctx.book.nav_path:
                continue
            try:
                documents.append((resource, ctx.parsed(resource).root))
            except Exception:  # noqa: BLE001 — the content stage reports this
                continue
        if not documents:
            return

        # Over the whole book, because that is where the evidence is: a word
        # broken in chapter four is written whole in chapter nine.
        words = hyphens.vocabulary("".join(root.itertext()) for _, root in documents)

        found: dict[str, int] = {}
        confirmed: list[tuple[object, hyphens.Candidate]] = []
        for resource, root in documents:
            for element, attribute in typography.text_nodes(root):
                text = getattr(element, attribute)
                if not text or "-" not in text:
                    continue
                for candidate in hyphens.find(text, where=resource.path, words=words):
                    found[candidate.confidence] = found.get(candidate.confidence, 0) + 1
                    if candidate.confidence == hyphens.CONFIRMED:
                        confirmed.append((resource, candidate))

        if not found:
            return
        self._report_counts(ctx, found)
        if confirmed:
            self._ask_and_apply(ctx, confirmed)

    def _report_counts(self, ctx: Context, found: dict) -> None:
        self.note(
            ctx,
            Level.INFO,
            "hyphens.detected",
            values={
                "confirmed": found.get(hyphens.CONFIRMED, 0),
                "likely": found.get(hyphens.LIKELY, 0),
                "uncertain": found.get(hyphens.UNCERTAIN, 0),
            },
        )

    def _ask_and_apply(self, ctx: Context, confirmed: list) -> None:
        """One question per confirmed candidate, then whatever was answered.

        The text is edited through the same guard the typography stage uses: the
        document is folded to a canonical form before and after, and one that
        does not match goes back exactly as it came in. A rule that edits text
        and cannot show it kept the text has no business having edited it — and
        this rule edits *words*, which is further than any other rule here goes.
        """
        replacements: dict[str, list] = {}
        asked = 0
        for resource, candidate in confirmed:
            answer = ctx.decide(hyphens.question_for(candidate))
            asked += 1
            if answer.option == KEEP:
                continue
            replacement = (
                candidate.joined if answer.option == "join" else answer.value
            )
            if not replacement:
                continue
            replacements.setdefault(resource.path, []).append((candidate, replacement))

        if not replacements:
            self._report_unanswered(ctx, asked)
            return

        joined = reverted = 0
        for resource in ctx.book.content_docs():
            planned = replacements.get(resource.path)
            if not planned:
                continue
            tree = ctx.take(resource)
            root = tree.root
            before = "".join(root.itertext())
            changed = 0
            for element, attribute in typography.text_nodes(root):
                text = getattr(element, attribute)
                if not text:
                    continue
                for candidate, replacement in planned:
                    if candidate.word in text:
                        text = text.replace(candidate.word, replacement)
                        changed += 1
                setattr(element, attribute, text)
            if not changed:
                continue
            after = "".join(root.itertext())
            if not self._only_the_hyphens_went(before, after, planned):
                reverted += 1
                continue
            resource.data = xhtml.serialize(root)
            joined += changed

        self._report_changes(ctx, joined, reverted)

    @staticmethod
    def _only_the_hyphens_went(before: str, after: str, planned: list) -> bool:
        """Did the document change in exactly the way it was supposed to?

        K1 says no character of the text is lost, and joining a word loses one
        on purpose — so the invariant is restated rather than dropped: apply the
        same replacements to the *before* text and require the result to be the
        after text, character for character. Anything else the pass did to the
        document shows up as a mismatch and the document goes back.
        """
        expected = before
        for candidate, replacement in planned:
            expected = expected.replace(candidate.word, replacement)
        return typography.unchanged(expected, after)

    def _report_unanswered(self, ctx: Context, asked: int) -> None:
        self.note(
            ctx,
            Level.PRESERVED,
            "hyphens.left-alone",
            values={"count": asked},
        )

    def _report_changes(self, ctx: Context, joined: int, reverted: int) -> None:
        if joined:
            self.note(ctx, Level.FIX, "hyphens.joined", values={"count": joined})
            # In the ledger, because this is the only rule in the program that
            # changes a word. Irreversible from the output alone: nothing in the
            # rebuilt file records that `obojętna` was once written otherwise.
            self.changed(
                ctx,
                Action.REPLACED,
                "text",
                before=f"{joined} słowo/słowa z łącznikiem w środku",
                after="ta sama forma bez łącznika, wskazana przez człowieka",
                risk=Risk.CONTENT,
                reversible=False,
                rule="hyphens.joined",
            )
        if reverted:
            self.note(
                ctx, Level.WARN, "hyphens.reverted", values={"count": reverted}
            )
