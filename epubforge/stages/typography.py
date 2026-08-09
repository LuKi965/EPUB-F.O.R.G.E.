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

Quotes are the third rule and are not here yet, because normalising them means
deciding which of a pair each mark is, and a straight `"` does not say.
"""

from __future__ import annotations

import re

from .. import typography, xhtml
from ..report import Level
from .base import Context, Stage

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


class TypographyStage(Stage):
    """Repairs the text itself, behind a flag, and verifies its own work."""

    name = "typography"

    def run(self, ctx: Context) -> None:
        if not getattr(ctx.policy, "typography", False):
            return
        if not ctx.policy.rewrite_content:
            # Container-only mode promises the content files come out byte for
            # byte. A stage that edits text has nothing to say there, and the
            # promise outranks the flag.
            return

        language = (ctx.book.metadata.language or "").strip().lower()
        ellipses = conjunctions = 0
        reverted: list[str] = []

        for resource in ctx.book.content_docs():
            try:
                parsed = xhtml.parse_document(resource.data)
            except Exception:  # noqa: BLE001 — the content stage reports this
                continue
            root = parsed.root
            before = "".join(root.itertext())

            found = self._repair(root, language)
            if not any(found):
                continue

            after = "".join(root.itertext())
            if not typography.unchanged(before, after):
                # Not "log it and carry on". The document goes back as it came
                # in, because a stage that cannot show it kept the text has no
                # business having edited it.
                reverted.append(resource.path)
                continue

            resource.data = xhtml.serialize(root)
            ellipses += found[0]
            conjunctions += found[1]

        self._report(ctx, ellipses, conjunctions, reverted)

    def _repair(self, root, language: str) -> tuple[int, int]:
        """Apply the rules to every editable text node. Returns what changed."""
        ellipses = conjunctions = 0
        polish = language.startswith("pl")
        for element, attribute in typography.text_nodes(root, language=language or None):
            text = getattr(element, attribute)
            if not text:
                continue
            repaired, count = _THREE_DOTS.subn("…", text)
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
            if repaired != text:
                setattr(element, attribute, repaired)
        return ellipses, conjunctions

    def _report(self, ctx: Context, ellipses: int, conjunctions: int, reverted: list[str]) -> None:
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
