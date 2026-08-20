"""Footnotes a converter abandoned halfway: found, shown, and linked on request.

Pillar 3 of the 0.3 plan — the owner's third example from the product-vision
conversation, measured before it was designed (2026-08-20, on rebuilt output):
19 books on the shelf have *working* footnotes (413 linked markers — never
touched here), and the dominant defect is a converter that linked part of a
notes section and dropped the rest: one publisher's trilogy carries 247
linked markers beside **196 bare `[N]`** in running text. Seven books, 205
markers in all; the other 153 books have nothing of the kind, and the design
rule from the plan is absolute: a book without the defect is never asked
a single question.

The shape this targets is exactly the measured one: a bare `[N]` in a body
paragraph, and a paragraph beginning with `N` in a document that looks like
a notes section. Everything else — superscripts without a notes section,
numbers that match no note — is left alone: linking is a repair only when
both ends of the bridge already exist.

Nothing changes without an answer (S-05). The question is one per book,
carries previews of both ends, and its safe option is "leave it". On "link",
the marker's own characters are wrapped in an anchor — the text is identical
before and after, which is why K1 has nothing to say about it — and the note
paragraph receives an id when it has none.

Two phases on purpose: detection reads shared parse trees and keeps only
numbers and paths, never element references; the apply phase `take`s each
document it will change and re-finds its markers in the tree it owns. The
cache's contract is that a mutated tree never sits under a clean key — and
two byte-identical documents share one tree, so mutating during detection
would edit a document this stage never meant to touch.
"""

from __future__ import annotations

import re

from .. import paths, xhtml
from ..decisions import KEEP, REFERENCE, Option, Question
from ..question_texts import say
from ..report import Action, Level, Risk
from .base import Context, Stage

#: A document that is probably the notes section, by name. The census that
#: sized this feature used the same stems; they are hints, not requirements —
#: a file named differently still qualifies by its paragraphs.
_NOTES_NAME = re.compile(r"przypis|footnote|endnote|\bnotes?\b|\bnoty\b", re.IGNORECASE)

#: A paragraph that opens a note: its visible text starts with a small number
#: and a separator. `1.`, `2)`, `[3]`, `4:` — the shapes the shelf showed.
_NOTE_OPENING = re.compile(r"^\s*\[?(\d{1,3})[\].):]\s")

#: A bare marker in running text: `[N]` with nothing linking it.
_MARKER = re.compile(r"\[(\d{1,3})\]")

#: How many note-shaped paragraphs make a document a notes section even when
#: its name says nothing. Five, from the census — below that the pattern is
#: as likely a numbered list in the story itself.
_NOTES_THRESHOLD = 5

_XHTML = "{http://www.w3.org/1999/xhtml}"


def _tag(element) -> str:
    return element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""


def _note_id(number: int) -> str:
    return f"ef-note-{number}"


class FootnoteStage(Stage):
    """Ask about bare footnote markers whose notes exist, and link on request."""

    name = "footnotes"

    def run(self, ctx: Context) -> None:
        if not ctx.policy.rewrite_content or not ctx.policy.link_footnotes:
            return

        documents = ctx.book.content_docs()
        notes = self._notes_map(ctx, documents)
        if not notes:
            return
        note_paths = {path for path, _, _ in notes.values()}

        bare: dict[str, list[int]] = {}
        previews: list[str] = []
        for resource in documents:
            if resource.path in note_paths or b"[" not in resource.data:
                continue
            numbers = self._bare_markers(ctx.parsed(resource).root, notes)
            if numbers:
                bare[resource.path] = numbers
                for number in numbers[:3 - len(previews)]:
                    previews.append(f"[{number}] … {notes[number][2][:80]}")
        count = sum(len(numbers) for numbers in bare.values())
        if not count:
            return

        question = Question(
            kind=REFERENCE,
            where=next(iter(bare)),
            summary=say("footnote.summary", count=count),
            detail=say("footnote.detail", count=count, shown="\n".join(previews)),
            options=(
                Option(KEEP, say("footnote.keep"), say("footnote.keep.why")),
                Option("link", say("footnote.link"), say("footnote.link.why", count=count)),
            ),
            recommended="link",
            reversible=True,
            risk=Risk.NONE,
            group="footnote",
            subject=f"{count} markers",
        )
        answer = ctx.decide(question)
        if answer.option != "link":
            self.note(ctx, Level.INFO, "footnotes.found", values={"count": count})
            return

        linked = 0
        linked_numbers: set[int] = set()
        for path, numbers in bare.items():
            resource = ctx.book.get(path)
            root = ctx.take(resource).root
            for number in numbers:
                notes_path = notes[number][0]
                href = f"{paths.relative(path, notes_path)}#{_note_id(number)}"
                if self._wrap_first(root, number, href):
                    linked += 1
                    linked_numbers.add(number)
            resource.data = xhtml.serialize(root)

        for notes_path in {notes[n][0] for n in linked_numbers}:
            resource = ctx.book.get(notes_path)
            root = ctx.take(resource).root
            for paragraph in root.iter(f"{_XHTML}p", "p"):
                text = "".join(paragraph.itertext())
                match = _NOTE_OPENING.match(text)
                if match and int(match.group(1)) in linked_numbers:
                    if not paragraph.get("id"):
                        paragraph.set("id", _note_id(int(match.group(1))))
                    linked_numbers.discard(int(match.group(1)))
            resource.data = xhtml.serialize(root)

        self.note(ctx, Level.FIX, "footnotes.linked", values={"count": linked})
        self.changed(
            ctx, Action.ADDED, "footnote-links",
            before=f"{linked} bare [N] marker(s) with a matching note",
            after="wrapped in links to their notes; the text is unchanged",
            risk=Risk.NONE, reversible=True,
            rule="footnotes.linked",
        )

    # ---------------------------------------------------------------- pieces
    def _notes_map(self, ctx: Context, documents) -> dict:
        """number → (notes document path, has_id, preview text).

        A document qualifies by name or by carrying `_NOTES_THRESHOLD`
        note-shaped paragraphs; the map holds each number's *first* paragraph,
        because a duplicate number is exactly the ambiguity this program does
        not resolve by guessing.
        """
        collected: dict = {}
        for resource in documents:
            named = bool(_NOTES_NAME.search(resource.path.rsplit("/", 1)[-1]))
            root = ctx.parsed(resource).root
            openings = []
            for paragraph in root.iter(f"{_XHTML}p", "p"):
                text = "".join(paragraph.itertext())
                match = _NOTE_OPENING.match(text)
                if match:
                    openings.append((int(match.group(1)), bool(paragraph.get("id")), text.strip()))
            if not openings or (not named and len(openings) < _NOTES_THRESHOLD):
                continue
            for number, has_id, text in openings:
                collected.setdefault(number, (resource.path, has_id, text))
        return collected

    def _bare_markers(self, root, notes: dict) -> "list[int]":
        """Every `[N]` in this tree with a matching note and no link around it."""
        found: list[int] = []
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            for attribute in ("text", "tail"):
                value = getattr(element, attribute) or ""
                if "[" not in value:
                    continue
                if self._inside_anchor(element, attribute):
                    continue
                found += [
                    int(m.group(1)) for m in _MARKER.finditer(value)
                    if int(m.group(1)) in notes
                ]
        return found

    @staticmethod
    def _inside_anchor(element, attribute: str) -> bool:
        """Whether text at this position is already inside a link.

        `text` belongs to the element itself; `tail` belongs to the space
        after it, whose owner is the parent. Both walks stop at the first
        anchor — a marker that is already a link is a working footnote, and
        this stage's measured promise is to never touch those.
        """
        current = element if attribute == "text" else element.getparent()
        while current is not None:
            if _tag(current) == "a":
                return True
            current = current.getparent()
        return False

    @staticmethod
    def _wrap_first(root, number: int, href: str) -> bool:
        """Wrap one bare `[number]` in this tree in an anchor.

        The marker's characters move into the link unchanged — split text,
        new `<a>`, remainder as its tail — so the reading order K1 measures
        is identical before and after.
        """
        token = f"[{number}]"
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            for attribute in ("text", "tail"):
                value = getattr(element, attribute) or ""
                position = value.find(token)
                if position < 0:
                    continue
                if FootnoteStage._inside_anchor(element, attribute):
                    continue
                anchor = element.makeelement(f"{_XHTML}a", {"href": href})
                anchor.text = token
                anchor.tail = value[position + len(token):]
                if attribute == "text":
                    element.text = value[:position]
                    element.insert(0, anchor)
                else:
                    parent = element.getparent()
                    if parent is None:
                        continue
                    element.tail = value[:position]
                    parent.insert(parent.index(element) + 1, anchor)
                return True
        return False
