"""What a PDF brought along that a book does not carry: the running heads.

The reader (`.reader`) keeps every line of the text layer, including
the ones it took for a running head or a page number — as paragraphs marked
`ef-pdf-running-head`, so that nothing leaves the text before somebody has
said so. This stage is where somebody says so: one question for all of them,
with examples, recommended to remove, and nothing removed without an answer
(S-02, S-05). `policy.pdf.running_heads` is the standing answer for a
batch: `ask`, `keep` or `remove`. On a book that did not come from a PDF the
stage does nothing.
"""

from __future__ import annotations

from .. import typography, xhtml
from . import reader as pdf
from ..decisions import KEEP, METADATA, TEXT, Option, Question
from ..question_texts import say
from ..report import Action, Automation, Level, Risk
from ..transformation import PostconditionFailed, Transformation, carry_out
from ..stages.base import Context, Stage


class PdfStage(Stage):
    name = "pdf"
    mutates = True

    def run(self, ctx: Context) -> None:
        if ctx.book.source_version != "pdf":
            return
        self._ask_about_language(ctx)
        if ctx.book.rendition.get("layout") == "pre-paginated":
            # The fixed-layout mode drew every line where the source drew it,
            # and a running head taken out of such a page does not close up
            # behind itself: it leaves a hole exactly where it stood. The page
            # is the thing that mode promised to keep, so the question is not
            # asked and the answer is said instead.
            self._keep_the_page_whole(ctx)
            return
        found, examples = self._running_heads(ctx)
        count = sum(len(heads) for _, _, heads in found)
        if not count:
            return
        choice, automation = self._answer(ctx, found, examples, count)
        if choice != "remove":
            self._keep(ctx, found, count)
            return
        self._take_out(ctx, found, automation)

    def _keep_the_page_whole(self, ctx: Context) -> None:
        """Say how many lines of furniture the fixed pages carry, and that they
        stay. Counted off the mark the reader put on them, which in this mode
        sits on a positioned line — a `div` — rather than on a paragraph."""
        found, _ = self._running_heads(ctx, tag="div")
        count = sum(len(heads) for _, _, heads in found)
        if count:
            self.note(ctx, Level.PRESERVED, "pdf.running-heads-kept-fixed",
                      values={"count": count})

    def _running_heads(self, ctx: Context, tag: str = "p") -> "tuple[list, list]":
        """Every element the reader marked as a running head, per document, and
        up to five of them read as examples for the question.

        *tag* is what such a line is in this book: a paragraph in a reflowable
        one, a positioned `div` in a fixed-layout one.
        """
        found: list[tuple[object, object, list]] = []
        examples: list[str] = []
        for resource in ctx.book.content_docs():
            try:
                root = ctx.take(resource).root
            except Exception:  # noqa: BLE001 — the content stage reports an unreadable document
                continue
            heads = [
                element for element in xhtml.iter_elements(root)
                if xhtml.local_name(element).lower() == tag
                and pdf.RUNNING_HEAD_CLASS in (element.get("class") or "").split()
            ]
            if heads:
                found.append((resource, root, heads))
                for element in heads:
                    text = "".join(element.itertext()).strip()
                    if text and text not in examples and len(examples) < 5:
                        examples.append(text)
        return found, examples

    def _answer(self, ctx: Context, found: list, examples: list, count: int) -> "tuple[str, object]":
        """The standing answer of the batch, or one question for all of them."""
        choice = ctx.policy.pdf.running_heads
        if choice == "ask":
            question = Question(
                kind=TEXT,
                where=found[0][0].path,
                summary=say("pdf.running-heads.summary", count=count),
                detail=say("pdf.running-heads.detail", count=count,
                           documents=len(found), examples=" | ".join(examples)),
                options=(
                    Option(KEEP, say("pdf.running-heads.keep"), say("pdf.running-heads.keep.why")),
                    Option("remove", say("pdf.running-heads.remove"), say("pdf.running-heads.remove.why")),
                ),
                recommended="remove",
                reversible=False,
                risk=Risk.CONTENT,
                group="pdf:running-heads",
                subject=f"{count} lines",
            )
            choice = "remove" if ctx.decide(question).option == "remove" else "keep"
            return choice, Automation.ASKED
        return choice, Automation.DETERMINISTIC

    def _keep(self, ctx: Context, found: list, count: int) -> None:
        """Nothing leaves the book: only the marks the reader put on, which have
        done their work."""
        for resource, root, heads in found:
            for element in heads:
                # The mark has done its work; the text stays as ordinary prose.
                _drop_class(element, pdf.RUNNING_HEAD_CLASS)
            # The halves a head cut apart stay apart: that is the page's
            # order, and the head is still standing between them.
            for element in _continuations(root):
                _drop_class(element, pdf.CONTINUED_CLASS)
            resource.data = xhtml.serialize(root)
        self.note(ctx, Level.PRESERVED, "pdf.running-heads-kept", values={"count": count})

    def _take_out(self, ctx: Context, found: list, automation) -> None:
        rejoined = orphaned = 0
        removed = 0
        documents = 0
        for resource, root, heads in found:
            # On the transformation contract (BA-2026-003), as every change
            # that takes readable text out of a book is: the removal is
            # described before it happens, and if what is left is not a
            # subsequence of what was there — something added, something
            # moved — the document goes back to the bytes it had and the
            # heads stay, said in the report.
            before = _prose(root)
            texts = ["".join(element.itertext()) for element in heads]
            step = Transformation(
                rule="pdf.running-heads-removed",
                target=resource.path,
                precondition=lambda heads=heads: bool(heads),
                postcondition=lambda root=root, before=before, texts=texts: (
                    _is_subsequence(_prose(root), before)
                    and all(text in before for text in texts)
                    and not any(
                        pdf.RUNNING_HEAD_CLASS in (element.get("class") or "").split()
                        for element in xhtml.iter_elements(root)
                    )
                ),
                reversible=False,
            )
            snapshot = xhtml.serialize(root)
            try:
                taken = carry_out(
                    step,
                    snapshot=lambda snapshot=snapshot: snapshot,
                    restore=lambda data: None,  # the parsed tree is dropped below; the bytes are what stand
                    mutate=lambda root=root, heads=heads: _remove(root, heads),
                )
            except PostconditionFailed:
                resource.data = snapshot
                self.note(ctx, Level.WARN, "pdf.running-heads-left",
                          values={"count": len(heads), "document": resource.path})
                continue
            removed += taken
            documents += 1
            for element in _continuations(root):
                joined, lost = _rejoin(element)
                rejoined += joined
                orphaned += lost
            resource.data = xhtml.serialize(root)
        if orphaned:
            # Two pages beginning inside one paragraph is the only shape where
            # the anchor cannot travel, and it is said rather than swallowed:
            # the entry still finds the document, no longer the place in it.
            self.note(ctx, Level.WARN, "pdf.anchor-not-carried",
                      values={"count": orphaned})
        if not removed:
            return
        self.note(ctx, Level.FIX, "pdf.running-heads-removed",
                  values={"count": removed, "documents": documents, "rejoined": rejoined})
        self.changed(
            ctx,
            Action.REMOVED,
            "text",
            before=f"{removed} × zywa pagina albo numer strony z PDF-a",
            after="usuniete",
            automation=automation,
            risk=Risk.CONTENT,
            reversible=False,
            rule="pdf.running-heads-removed",
        )

    def _ask_about_language(self, ctx: Context) -> None:
        """A PDF rarely says what language it is in, and the language is a
        claim about the book (K4): proposed from the text, applied only on a
        person's word; without one the policy's default stands, as for any
        book that came without a language."""
        book = ctx.book
        if (book.metadata.language or "").strip():
            return
        sample: list[str] = []
        for resource in book.content_docs():
            try:
                sample.append("".join(ctx.parsed(resource).root.itertext()))
            except Exception:  # noqa: BLE001
                continue
            if sum(len(part) for part in sample) > 200_000:
                break
        text = " ".join(sample)
        share = typography.polish_share(text) if text.strip() else 0.0
        proposal = "pl" if share >= POLISH_LETTERS_PER_1000 else "en"
        default = ctx.policy.default_language
        question = Question(
            kind=METADATA,
            where=book.spine[0].path if book.spine else "",
            summary=say("pdf.language.summary"),
            detail=say("pdf.language.detail", proposal=proposal, share=f"{share:.1f}", default=default),
            options=(
                Option(KEEP, say("pdf.language.keep", default=default), say("pdf.language.keep.why")),
                Option("set", say("pdf.language.set", proposal=proposal), say("pdf.language.set.why")),
            ),
            recommended="set",
            reversible=True,
            risk=Risk.NONE,
            group="pdf:language",
            subject=proposal,
        )
        if ctx.decide(question).option == "set":
            book.metadata.language = proposal
            self.note(ctx, Level.FIX, "pdf.language-set",
                      values={"language": proposal, "share": f"{share:.1f}"})
        else:
            self.note(ctx, Level.INFO, "pdf.language-default", values={"language": default})


def _prose(root) -> str:
    return " ".join("".join(root.itertext()).split())


def _is_subsequence(kept: str, whole: str) -> bool:
    position = 0
    for character in kept:
        position = whole.find(character, position)
        if position < 0:
            return False
        position += 1
    return True


def _remove(root, heads) -> int:
    taken = 0
    for element in heads:
        parent = element.getparent()
        if parent is None:
            continue
        tail = element.tail
        previous = element.getprevious()
        if tail:
            if previous is not None:
                previous.tail = (previous.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
        parent.remove(element)
        taken += 1
    return taken


def _continuations(root) -> list:
    return [
        element for element in xhtml.iter_elements(root)
        if xhtml.local_name(element).lower() == "p"
        and pdf.CONTINUED_CLASS in (element.get("class") or "").split()
    ]


def _drop_class(element, name: str) -> None:
    classes = [c for c in (element.get("class") or "").split() if c != name]
    if classes:
        element.set("class", " ".join(classes))
    else:
        element.attrib.pop("class", None)


def _rejoin(element) -> "tuple[int, int]":
    """Fold the second half of a paragraph into the first, now that nothing
    stands between them, and carry its anchor across.

    Returns `(joined, anchors that could not travel)`. Where the first half is
    not there any more — an image, a heading, the start of the document — the
    half stays a paragraph of its own, and only the mark goes.

    **The anchor is the part that was missing.** The second half carries the
    `id` for the page it begins, and the table of contents points at it;
    joining removed the element and took the anchor with it. Found on the
    owner's manual through EPUBCheck rather than through the report: twenty
    entries of a hundred and twenty-five lost their place, the navigation stage
    did what it says it does — kept them pointing at the file — and the contents
    then ran backwards, because a bare document link stands before every anchor
    in that document (`NAV-011`, eight of ten documents). Nothing in the report
    said a word about it; `pdf.running-heads-removed` said 484 lines had gone
    and the anchors were somebody else's business.

    The anchor moves to the paragraph the half is folded into, which is where
    that page now begins — the same answer `_render` gives for any paragraph
    that runs over a fold. It can only fail to move when the paragraph it joins
    already carries one, which is two pages beginning inside one paragraph:
    zero times in the manual's 27 carried anchors, and counted rather than
    assumed away.
    """
    previous = element.getprevious()
    if previous is None or xhtml.local_name(previous).lower() != "p":
        _drop_class(element, pdf.CONTINUED_CLASS)
        return 0, 0
    orphaned = 0
    anchor = element.get("id")
    if anchor:
        if previous.get("id"):
            orphaned = 1
        else:
            previous.set("id", anchor)
    text = element.text or ""
    children = list(element)
    # A word the typesetter broke at the foot of the page, with the running
    # head standing between its halves: joined the way the reader joins a
    # line end — no space after a hyphen — so it reaches the hyphen stage
    # in the same shape as every other break (`prze-konaniem`).
    before = (previous[-1].tail if len(previous) else previous.text) or ""
    glue = "" if (before.endswith("-") and len(before) > 1 and before[-2].isalnum() and text[:1].isalpha()) else " "
    if len(previous):
        last = previous[-1]
        last.tail = (last.tail or "") + glue + text
    else:
        previous.text = (previous.text or "") + glue + text
    for child in children:
        previous.append(child)
    parent = element.getparent()
    if element.tail:
        previous.tail = (previous.tail or "") + element.tail
    parent.remove(element)
    return 1, orphaned


#: Polish letters per thousand characters above which the text reads as Polish.
#: Nine properly typeset Polish books measure far above; English ones at zero.
POLISH_LETTERS_PER_1000 = 5.0
