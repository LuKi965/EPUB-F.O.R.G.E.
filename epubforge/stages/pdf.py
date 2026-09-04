"""What a PDF brought along that a book does not carry: the running heads.

The reader (`epubforge.pdf`) keeps every line of the text layer, including
the ones it took for a running head or a page number — as paragraphs marked
`ef-pdf-running-head`, so that nothing leaves the text before somebody has
said so. This stage is where somebody says so: one question for all of them,
with examples, recommended to remove, and nothing removed without an answer
(S-02, S-05). `pdf_running_heads` in the policy is the standing answer for a
batch: `ask`, `keep` or `remove`. On a book that did not come from a PDF the
stage does nothing.
"""

from __future__ import annotations

from .. import pdf, typography, xhtml
from ..decisions import KEEP, METADATA, TEXT, Option, Question
from ..question_texts import say
from ..report import Action, Automation, Level, Risk
from ..transformation import PostconditionFailed, Transformation, carry_out
from .base import Context, Stage


class PdfStage(Stage):
    name = "pdf"
    mutates = True

    def run(self, ctx: Context) -> None:
        if ctx.book.source_version != "pdf":
            return
        self._ask_about_language(ctx)
        found: list[tuple[object, object, list]] = []
        examples: list[str] = []
        for resource in ctx.book.content_docs():
            try:
                root = ctx.take(resource).root
            except Exception:  # noqa: BLE001 — the content stage reports an unreadable document
                continue
            heads = [
                element for element in xhtml.iter_elements(root)
                if xhtml.local_name(element).lower() == "p"
                and pdf.RUNNING_HEAD_CLASS in (element.get("class") or "").split()
            ]
            if heads:
                found.append((resource, root, heads))
                for element in heads:
                    text = "".join(element.itertext()).strip()
                    if text and text not in examples and len(examples) < 5:
                        examples.append(text)
        count = sum(len(heads) for _, _, heads in found)
        if not count:
            return

        choice = ctx.policy.pdf_running_heads
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
            automation = Automation.ASKED
        else:
            automation = Automation.DETERMINISTIC

        if choice != "remove":
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
            return

        rejoined = 0
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
                rejoined += _rejoin(element)
            resource.data = xhtml.serialize(root)
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


def _rejoin(element) -> int:
    """Fold the second half of a paragraph into the first, now that nothing
    stands between them. Where the first half is not there any more — an
    image, a heading, the start of the document — the half stays a paragraph
    of its own, and only the mark goes."""
    previous = element.getprevious()
    if previous is None or xhtml.local_name(previous).lower() != "p":
        _drop_class(element, pdf.CONTINUED_CLASS)
        return 0
    text = element.text or ""
    children = list(element)
    if len(previous):
        last = previous[-1]
        last.tail = (last.tail or "") + " " + text
    else:
        previous.text = (previous.text or "") + " " + text
    for child in children:
        previous.append(child)
    parent = element.getparent()
    if element.tail:
        previous.tail = (previous.tail or "") + element.tail
    parent.remove(element)
    return 1


#: Polish letters per thousand characters above which the text reads as Polish.
#: Nine properly typeset Polish books measure far above; English ones at zero.
POLISH_LETTERS_PER_1000 = 5.0
