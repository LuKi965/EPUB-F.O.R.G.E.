"""Images without a usable text alternative: found, sorted by evidence, asked.

The largest thing left on the shelf after 0.3.1, measured rather than
estimated (record 037, then 038's follow-up on 160 books): **1 140 image
places in 109 books** carry no text alternative a screen reader could use —
no `alt`, an empty `alt` nobody vouched for, or an `alt` that repeats the file
name. The accessibility stage has counted them honestly for a long time and
declined to claim `alternativeText` over them. This stage is the other half:
it does something about them, and the thing it does is **ask**.

What it will never do is describe a picture. A description is somebody's
sentence about what the picture shows, and this program has no way of
knowing; inventing one would be exactly the false claim the accessibility
stage exists to refuse. What it *can* do is sort the pictures by evidence a
person would use anyway, put each one to that person with the evidence
attached, and recommend:

* **an ornament** — the same file standing alone (no running text beside it)
  in three or more documents. On the shelf that is a rose over every chapter
  title, a brush stroke under every heading, a scroll between scenes: 339
  places. Recommended: mark decorative.
* **a tiny picture** — a hundred pixels or less on its longer side, or under
  two kilobytes. Separators and chevrons, mostly — but also a signature, a
  publisher's logo, a symbol the story uses (148 places, and those three
  were in them). Recommended decorative only when it stands alone; inside a
  line of text it is more often a symbol, and the recommendation is to leave
  it for the person to judge.
* **everything else** is an illustration (649 places, half of them in five
  books), and the only honest recommendation is to leave it: the person can
  type a description, and nothing else can.

The cover is not here: the content stage already describes it with the
book's own title, a fact the package states, and adds an empty `alt` to every
picture that had none — which is why this stage sees `empty` far more often
than `missing`, and treats both as the same unanswered question.

One question per image *file*, not per place — the rose asked about once
covers all seven chapters — with a group that carries the book's identifier
(D-046's shape): "all of them" means the same kind of picture in this book,
and stops at this book. Nothing changes without an answer (S-05). Marking
decorative writes both `alt=""` and `role="presentation"`, because a bare
empty `alt` is exactly the unverifiable claim the accessibility stage refuses
to read as one. No character of the text changes; K1 has nothing to say.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .. import paths, xhtml
from ..decisions import IMAGE, KEEP, Option, Preview, Question
from ..question_texts import say
from ..report import Action, Automation, Level, Risk
from .accessibility import is_placeholder_alt
from .base import Context, Stage

#: An image standing alone in this many documents or more is an ornament.
#: Three, from the shelf: two is a frontispiece repeated on a half-title,
#: three is a habit running through the chapters.
ORNAMENT_USES = 3

#: …and no bigger than this. The first run on real books called a 1 635 px,
#: 2.2 MB picture repeated in five documents an ornament, and recommended
#: hiding it: a full-page plate reused at every part opening, or a map, is
#: content however often it recurs. On the shelf the rose over the chapter
#: titles is 341 px and 33 kB; nothing an eye would call an ornament came
#: near these bounds. A repeated picture over them is asked about as an
#: illustration — with its repetition still in the evidence — and the
#: recommendation is to leave it.
ORNAMENT_MAX_SIDE = 800
ORNAMENT_MAX_BYTES = 200 * 1024

#: A picture no larger than this on its longer side, or lighter than this in
#: bytes, is tiny. Both from the shelf's own distribution (record 037: 237
#: places under two kilobytes; 038: 205 of 241 tiny files at or under a
#: hundred pixels), and neither is a claim about what the picture *is*.
TINY_SIDE = 100
TINY_BYTES = 2048

ORNAMENT = "ornament"
TINY = "tiny"
ILLUSTRATION = "illustration"
#: The order questions are asked in: the confident ones first.
KINDS = (ORNAMENT, TINY, ILLUSTRATION)

#: Elements that hold a picture's running text, if it has any. A picture whose
#: nearest one of these carries no text stands alone.
_BLOCKS = frozenset({
    "p", "div", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
    "figure", "figcaption", "blockquote", "section", "article", "aside",
    "body", "dd", "dt", "pre", "caption",
})

#: Where the question shows the picture: this many documents by name.
SHOWN_PLACES = 3


def dimensions(data: bytes) -> "tuple[int, int] | None":
    """`(width, height)` read from the header of a PNG, GIF or JPEG.

    From the container, not by decoding: the question is only "how big", and
    a wrong answer here costs a wrong sorting, which the person sees.
    """
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            width, height = struct.unpack(">II", data[16:24])
            return width, height
        if data[:6] in (b"GIF87a", b"GIF89a"):
            width, height = struct.unpack("<HH", data[6:10])
            return width, height
        if data[:2] == b"\xff\xd8":
            index = 2
            while index < len(data) - 9:
                if data[index] != 0xFF:
                    index += 1
                    continue
                marker = data[index + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    index += 2
                    continue
                length = struct.unpack(">H", data[index + 2:index + 4])[0]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                              0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    height, width = struct.unpack(">HH", data[index + 5:index + 9])
                    return width, height
                index += 2 + length
    except (struct.error, IndexError):
        return None
    return None


def undescribed(element) -> "str | None":
    """Why this `<img>` has no usable text alternative, or None if it has one.

    The same three cases the accessibility stage counts, by the same rules:
    `missing`, `empty` (an empty `alt` with no `role="presentation"` or
    `aria-hidden="true"` vouching for it) and `placeholder` (the file name
    or a template word standing in for a description).
    """
    alt = element.get("alt")
    if alt is None:
        return "missing"
    if not alt.strip():
        role = (element.get("role") or "").strip().lower()
        hidden = (element.get("aria-hidden") or "").strip().lower()
        return None if role == "presentation" or hidden == "true" else "empty"
    if is_placeholder_alt(alt, element.get("src")):
        return "placeholder"
    return None


def _stands_alone(element) -> bool:
    """Whether the picture's nearest block carries no running text."""
    block = element.getparent()
    while block is not None and xhtml.local_name(block).lower() not in _BLOCKS:
        block = block.getparent()
    if block is None:
        return True
    return not "".join(block.itertext()).strip()


@dataclass
class Picture:
    """One image file the book uses without describing, and its evidence."""

    target: str
    size: int = 0
    width: "int | None" = None
    height: "int | None" = None
    #: Documents that show it, in reading order, with how many times each.
    places: "dict[str, int]" = field(default_factory=dict)
    #: True while every place seen so far has no running text beside it.
    alone: bool = True
    #: The reasons seen, `missing` / `empty` / `placeholder`.
    reasons: "set[str]" = field(default_factory=set)
    #: An existing placeholder alt, shown so the person sees what stands there.
    placeholder: str = ""
    #: The picture itself, for the question to show. The book's own bytes,
    #: not a copy — a person asked to describe a picture has to see it
    #: (owner, 2026-09-02).
    media_type: str = ""
    data: bytes = b""

    @property
    def count(self) -> int:
        return sum(self.places.values())

    @property
    def kind(self) -> str:
        side = max(self.width or 0, self.height or 0)
        small_enough = side <= ORNAMENT_MAX_SIDE and self.size <= ORNAMENT_MAX_BYTES
        if len(self.places) >= ORNAMENT_USES and self.alone and small_enough:
            return ORNAMENT
        if (self.width and side <= TINY_SIDE) or self.size < TINY_BYTES:
            return TINY
        return ILLUSTRATION

    @property
    def recommended(self) -> str:
        kind = self.kind
        if kind == ORNAMENT or (kind == TINY and self.alone):
            return "decorative"
        return KEEP


class AltTextStage(Stage):
    """Ask about every undescribed image, sorted by evidence; act on answers."""

    name = "pictures"

    def run(self, ctx: Context) -> None:
        if not ctx.policy.rewrite_content or not ctx.policy.detect_undescribed_images:
            return
        pictures = self._survey(ctx)
        if not pictures:
            return
        self.note(
            ctx, Level.INFO, "pictures.undescribed-found",
            values={"count": sum(p.count for p in pictures), "files": len(pictures)},
        )
        marked = described = 0
        left: list[Picture] = []
        for picture in pictures:
            answer = ctx.decide(self._question(ctx, picture))
            if answer.option == "decorative":
                marked += self._apply(ctx, picture, {"alt": "", "role": "presentation"})
            elif answer.option == "describe" and answer.value.strip():
                described += self._apply(ctx, picture, {"alt": answer.value.strip()})
            else:
                left.append(picture)

        if marked:
            self.note(ctx, Level.FIX, "pictures.decorative-marked", values={"count": marked})
            self.changed(
                ctx, Action.ADDED, "image-decorative-marks",
                before=f"{marked} image place(s) with no text alternative",
                after='alt="" and role="presentation", on a person\'s word',
                automation=Automation.ASKED, risk=Risk.CONTENT, reversible=True,
                rule="pictures.decorative-marked",
            )
        if described:
            self.note(ctx, Level.FIX, "pictures.described", values={"count": described})
            self.changed(
                ctx, Action.ADDED, "image-descriptions",
                before=f"{described} image place(s) with no text alternative",
                after="the description a person supplied",
                automation=Automation.ASKED, risk=Risk.NONE, reversible=True,
                rule="pictures.described",
            )
        if left:
            self.note(
                ctx, Level.PRESERVED, "pictures.left-alone",
                values={
                    "count": sum(p.count for p in left),
                    "files": len(left),
                    "examples": ", ".join(_basename(p.target) for p in left[:4]),
                },
            )

    # ---------------------------------------------------------------- survey
    def _survey(self, ctx: Context) -> "list[Picture]":
        """Every undescribed image file, with the evidence about it.

        Read-only: shared parse trees, and nothing but paths and numbers kept
        out of them — the apply phase takes its own tree per document.
        """
        pictures: dict[str, Picture] = {}
        for resource in ctx.book.content_docs():
            try:
                root = ctx.parsed(resource).root
            except Exception:
                continue
            for element in xhtml.iter_elements(root):
                if xhtml.local_name(element).lower() != "img":
                    continue
                reason = undescribed(element)
                if reason is None:
                    continue
                src = element.get("src") or ""
                target = paths.resolve(resource.path, src) if src else None
                if not target:
                    continue
                picture = pictures.get(target)
                if picture is None:
                    image = ctx.book.get(target)
                    data = image.data if image is not None else b""
                    dims = dimensions(data) if data else None
                    picture = Picture(
                        target=target, size=len(data),
                        width=dims[0] if dims else None,
                        height=dims[1] if dims else None,
                        media_type=(image.media_type if image is not None else ""),
                        data=data,
                    )
                    pictures[target] = picture
                picture.places[resource.path] = picture.places.get(resource.path, 0) + 1
                picture.alone = picture.alone and _stands_alone(element)
                picture.reasons.add(reason)
                if reason == "placeholder" and not picture.placeholder:
                    picture.placeholder = (element.get("alt") or "").strip()
        order = {kind: index for index, kind in enumerate(KINDS)}
        return sorted(pictures.values(), key=lambda p: (order[p.kind], p.target))

    # -------------------------------------------------------------- question
    @staticmethod
    def _group(ctx: Context, kind: str) -> str:
        """"All of them" means the same kind of picture in **this book**.

        D-046's shape: the list of pictures is different in every book and
        cannot be judged from another one's, so the group carries the book's
        identifier and a standing answer stops at the book it was given
        about — a "mark all ornaments decorative" here is not one there.
        """
        named = [
            one.value for one in (ctx.book.metadata.identifiers or []) if one.value
        ]
        which = named[0] if named else (ctx.book.nav_path or "?")
        return f"images:{kind}:{which}"

    def _question(self, ctx: Context, picture: Picture) -> Question:
        kind = picture.kind
        shown = ", ".join(list(picture.places)[:SHOWN_PLACES])
        left = len(picture.places) - SHOWN_PLACES
        more = say("images.more", count=left) if left > 0 else ""
        values = {
            "file": _basename(picture.target),
            "px": (f"{picture.width}×{picture.height} px" if picture.width
                   else say("images.px.unknown")),
            "size": _human(picture.size),
            "uses": len(picture.places),
            "count": picture.count,
            "where": shown,
            "more": more,
            "alt": (say("images.placeholder", alt=picture.placeholder)
                    if picture.placeholder else ""),
            "text": say("images.alone") if picture.alone else say("images.in.text"),
        }
        # Three literal keys per kind rather than one computed one, so that
        # every text the queue can show is greppable from here.
        if kind == ORNAMENT:
            summary = say("images.ornament.summary", **values)
            detail = say("images.ornament.detail", **values)
        elif kind == TINY:
            summary = say("images.tiny.summary", **values)
            detail = say("images.tiny.detail", **values)
        else:
            summary = say("images.illustration.summary", **values)
            detail = say("images.illustration.detail", **values)
        return Question(
            kind=IMAGE,
            where=next(iter(picture.places)),
            summary=summary,
            detail=detail,
            options=(
                Option(KEEP, say("images.keep"), say("images.keep.why")),
                Option("decorative", say("images.decorative"), say("images.decorative.why")),
                Option("describe", say("images.describe"), say("images.describe.why"),
                       needs_value=True),
            ),
            recommended=picture.recommended,
            reversible=True,
            risk=Risk.CONTENT,
            group=self._group(ctx, kind),
            subject=picture.target,
            preview=(Preview(picture.media_type, picture.data) if picture.data else None),
        )

    # ----------------------------------------------------------------- apply
    def _apply(self, ctx: Context, picture: Picture, attributes: "dict[str, str]") -> int:
        """Set *attributes* on every undescribed `<img>` showing this file."""
        done = 0
        for path in picture.places:
            resource = ctx.book.get(path)
            if resource is None:
                continue
            root = ctx.take(resource).root
            touched = False
            for element in xhtml.iter_elements(root):
                if xhtml.local_name(element).lower() != "img":
                    continue
                src = element.get("src") or ""
                if not src or paths.resolve(path, src) != picture.target:
                    continue
                if undescribed(element) is None:
                    continue
                for name, value in attributes.items():
                    element.set(name, value)
                touched = True
                done += 1
            if touched:
                resource.data = xhtml.serialize(root)
        return done


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _human(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} kB"
    return f"{size} B"
