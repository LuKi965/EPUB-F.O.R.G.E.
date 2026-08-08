"""What a book is like as a whole, measured once and never acted on.

`cascade.py` answers questions about one element: what colour is this, is that
paragraph indented. It cannot answer the question every content rule actually
needs, which is **is this construction the rule in this book or the exception**.
A paragraph with a first-line indent means one thing in a book where nine
hundred others have one and quite another where it is the only one.

So this measures the book. `docs/ROADMAP.md` point [3]:

* what the body text looks like, and whether it is consistent at all;
* whether the book separates paragraphs by indent or by space — a book from one
  source does not mix the two, so `MIXED` is nearly always the trace of two;
* which classes are dead and which are duplicates of each other;
* where the scene breaks, the `<br/>` runs and the heading candidates are.

**It changes nothing.** That is a condition rather than a convention, and it has
its own test. The first release of a profile exists so that points [4], [5] and
[7] have one shared answer instead of three inconsistent guesses, and so that
every threshold in here can be calibrated against real books *before* anything
depends on it. Every number is a named constant for that reason: the first
contact with a real shelf will move them, and a number nobody can find is a
number nobody will move.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

from . import cascade as css_cascade
from . import xhtml

# --------------------------------------------------------------- thresholds

#: The share of block elements one shape must reach before it counts as *the*
#: body text. Below this the book has no dominant shape, and saying it does
#: would be the profile inventing the very consistency it exists to measure.
BODY_TEXT_SHARE = 0.60

#: How dominant one paragraph paradigm must be before the book is called
#: indented or spaced rather than mixed. Deliberately high: the interesting
#: signal is `MIXED`, and a threshold that swallows it is worth nothing.
PARADIGM_SHARE = 0.90

#: How many times a construction must appear before it is read as intent rather
#: than as an accident. Three is the smallest number that can show a pattern.
INTENT_OCCURRENCES = 3

#: Consecutive `<br/>` elements that mean "blank line" rather than "line break".
BREAK_RUN = 2

#: A paragraph this short, centred or otherwise set apart, is a scene break
#: rather than prose — "* * *", "⁂", a rule of asterisks.
SEPARATOR_LENGTH = 12

#: A first-line indent at or below this is not an indent. Publishers who space
#: their paragraphs still sometimes leave a hairline value behind.
INDENT_FLOOR_EM = 0.2

#: The same, for the space between paragraphs — and higher than the indent
#: floor on purpose. A quarter of an em is four pixels at a normal size: air,
#: not a paragraph break. Project Gutenberg's own stylesheet writes
#: `p { text-indent: 1em; margin: 0.25em }`, which is an indented book with a
#: little breathing room and was being read as a book that did both.
#:
#: Half an em is where a gap starts being one a reader sees. Measured against
#: the six Gutenberg books in this repository, which is thin: four of them set
#: `0.75em` and one sets `0.25em`, so anything between those two would sort them
#: identically and only a real shelf can say where the line belongs.
SPACING_FLOOR_EM = 0.5

#: Two class names are duplicates when their declaration blocks agree. Compared
#: as normalised text rather than parsed, because a difference this measurement
#: cannot see is a difference no reader can see either.
_DECLARATION = re.compile(r"([-\w]+)\s*:\s*([^;]+)")

#: Text that is a scene break and not a sentence.
_SEPARATOR_TEXT = re.compile(r"^[\s*·•—–\-~⁂✻✽∗#§]+$")

_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


# ------------------------------------------------------------------ results

@dataclass
class BodyText:
    """The shape most of the book's prose has, when it has one.

    `shape` is the tag and class a block carries — `("p", "para")` — because
    that pair is what a later rule would have to target. `share` is how much of
    the book agrees with it, and it is kept even when it is low: "no dominant
    shape, the best was 31%" is a finding, and rounding it to `None` throws away
    the only number that says how far off it was.
    """

    shape: tuple[str, str] | None = None
    blocks: int = 0
    agreeing: int = 0

    @property
    def share(self) -> float:
        return self.agreeing / self.blocks if self.blocks else 0.0

    @property
    def consistent(self) -> bool:
        return self.shape is not None and self.share >= BODY_TEXT_SHARE


@dataclass
class Paragraphs:
    """How the book separates one paragraph from the next.

    Four buckets, not two, and the fourth is the whole point. The first version
    counted a paragraph that was *both* indented and spaced on both sides, which
    turned "this book indents and also leaves a little air" into the same answer
    as "half this book is indented and the other half is spaced". Those are not
    the same fact: the first is one publisher's taste, the second is the trace
    of two files glued together, and only the second is worth reporting.

    Three of the six Gutenberg books in this repository came out `MIXED` under
    that rule. They are from one source by construction, which is what said the
    rule was wrong rather than the books.
    """

    indented: int = 0
    spaced: int = 0
    both: int = 0
    neither: int = 0

    @property
    def decided(self) -> int:
        return self.indented + self.spaced + self.both

    @property
    def paradigm(self) -> str:
        """`INDENTED`, `SPACED`, `BOTH`, `MIXED` or `UNKNOWN`.

        `BOTH` is a book that consistently does both — a decision. `MIXED` is a
        book that cannot make up its mind, which is nearly always a book that
        was two books.
        """
        if not self.decided:
            return "UNKNOWN"
        for count, name in (
            (self.indented, "INDENTED"),
            (self.spaced, "SPACED"),
            (self.both, "BOTH"),
        ):
            if count / self.decided >= PARADIGM_SHARE:
                return name
        return "MIXED"


@dataclass
class Profile:
    """Everything measured about one book. Read-only by construction."""

    body: BodyText = field(default_factory=BodyText)
    paragraphs: Paragraphs = field(default_factory=Paragraphs)
    #: Declared in CSS, used by nothing.
    dead_classes: tuple[str, ...] = ()
    #: Groups of class names whose declarations are identical.
    duplicate_classes: tuple[tuple[str, ...], ...] = ()
    #: Blocks that are a scene break rather than a sentence.
    separators: int = 0
    #: Runs of `<br/>` standing in for a paragraph break.
    break_runs: int = 0
    #: Blocks that look like a heading and are not marked as one.
    heading_candidates: int = 0
    documents: int = 0

    def to_dict(self) -> dict:
        """Counts only — the shape of a book, never a word of it."""
        return {
            "body_shape": ".".join(x for x in (self.body.shape or ()) if x) or None,
            "body_blocks": self.body.blocks,
            "body_share": round(self.body.share, 3),
            "body_consistent": self.body.consistent,
            "paradigm": self.paragraphs.paradigm,
            "indented": self.paragraphs.indented,
            "spaced": self.paragraphs.spaced,
            "both": self.paragraphs.both,
            "dead_classes": len(self.dead_classes),
            "duplicate_groups": len(self.duplicate_classes),
            "separators": self.separators,
            "break_runs": self.break_runs,
            "heading_candidates": self.heading_candidates,
            "documents": self.documents,
        }


# ----------------------------------------------------------------- measuring

def _class_of(element) -> str:
    """The one class a block carries, or "" — the shape wants a single name.

    A block with three classes has no single shape to speak of, and guessing
    which of the three is the one that matters is exactly the kind of invention
    this module is written to avoid.
    """
    names = (element.get("class") or "").split()
    return names[0] if len(names) == 1 else ""


def _length_em(value: str | None) -> float:
    """A CSS length in em, as far as one can be had without a layout engine.

    Anything not expressible in em — a percentage, a viewport unit — comes back
    as zero rather than as a guess. Under-reporting an indent costs a signal;
    over-reporting one puts a book in the wrong paradigm.
    """
    if not value:
        return 0.0
    match = re.match(r"\s*(-?[\d.]+)\s*(em|rem|ex|ch|pt|px|in|cm|mm)?\s*$", value)
    if not match:
        return 0.0
    try:
        number = float(match.group(1))
    except ValueError:
        return 0.0
    unit = match.group(2) or ""
    # Rough, and deliberately so: these only ever decide "is there an indent at
    # all", against a floor of a fifth of an em.
    factor = {
        "em": 1.0, "rem": 1.0, "ex": 0.5, "ch": 0.5,
        "pt": 1 / 12, "px": 1 / 16, "in": 6.0, "cm": 2.4, "mm": 0.24,
    }.get(unit, 0.0)
    return number * factor


def _declarations(block: str) -> frozenset[tuple[str, str]]:
    return frozenset(
        (name.strip().lower(), " ".join(value.split()).lower())
        for name, value in _DECLARATION.findall(block)
    )


def _duplicate_classes(css: str) -> tuple[tuple[str, ...], ...]:
    """Class names whose rule bodies say exactly the same thing.

    Only single-class selectors, and only where the whole selector *is* the
    class: `.a, .b { }` says two names share a body, and `.a p` says nothing
    about `.a` alone.
    """
    bodies: dict[frozenset, set[str]] = collections.defaultdict(set)
    for selector, block in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        declarations = _declarations(block)
        if not declarations:
            continue
        for part in selector.split(","):
            name = part.strip()
            if re.fullmatch(r"\.[-\w]+", name):
                bodies[declarations].add(name[1:])
    return tuple(
        tuple(sorted(names)) for names in bodies.values() if len(names) > 1
    )


def measure(documents, css: str) -> Profile:
    """Measure a book. *documents* is an iterable of parsed roots.

    Takes roots rather than resources so the caller decides what to parse and
    the profile parses nothing twice — the content stage is about to walk every
    one of these anyway.
    """
    profile = Profile()
    cascade = css_cascade.Cascade.parse([css]) if css else None
    shapes: collections.Counter = collections.Counter()
    used_classes: set[str] = set()

    for root in documents:
        profile.documents += 1
        body = root.find(xhtml.qname("body"))
        for element in xhtml.iter_elements(body if body is not None else root):
            tag = xhtml.local_name(element).lower()
            used_classes.update((element.get("class") or "").split())
            if tag == "br":
                if _run_of_breaks(element) >= BREAK_RUN:
                    profile.break_runs += 1
                continue
            if tag not in _BLOCK_TAGS:
                continue

            text = " ".join("".join(element.itertext()).split())
            if tag == "p":
                shapes[(tag, _class_of(element))] += 1
                profile.body.blocks += 1
                _count_paragraph(profile, element, cascade)
            if text and len(text) <= SEPARATOR_LENGTH and _SEPARATOR_TEXT.match(text):
                profile.separators += 1
            elif tag not in _HEADING_TAGS and _looks_like_a_heading(element, text):
                profile.heading_candidates += 1

    if shapes:
        shape, agreeing = shapes.most_common(1)[0]
        profile.body.shape = shape
        profile.body.agreeing = agreeing

    if css:
        declared = set(re.findall(r"\.([A-Za-z_][-\w]*)", css))
        profile.dead_classes = tuple(sorted(declared - used_classes))
        profile.duplicate_classes = _duplicate_classes(css)
    return profile


def _run_of_breaks(element) -> int:
    """How many `<br/>` this one starts, counting only forwards.

    Forwards only, so a run of three is counted once rather than three times:
    every member but the first has a `<br/>` immediately before it.
    """
    previous = element.getprevious()
    if previous is not None and xhtml.local_name(previous).lower() == "br":
        return 0
    run = 1
    following = element.getnext()
    while following is not None and xhtml.local_name(following).lower() == "br":
        run += 1
        following = following.getnext()
    return run


#: How the four sides come out of `margin`, by how many values it was given.
#: CSS: one value is every side, two are vertical then horizontal, three are
#: top, horizontal, bottom, and four run clockwise from the top.
_MARGIN_SIDES = {
    1: {"top": 0, "bottom": 0},
    2: {"top": 0, "bottom": 0},
    3: {"top": 0, "bottom": 2},
    4: {"top": 0, "bottom": 2},
}


def _margin(element, cascade, side: str) -> float:
    """The top or bottom margin, however the stylesheet chose to write it.

    The longhand first, then the shorthand expanded. Without the second half
    this measurement was blind to `margin: 1em 0`, which is how most people
    write it — twenty-nine books out of ninety-three came back with no paragraph
    paradigm at all for that reason alone. It never showed up on the six
    Project Gutenberg books used to build this, because their stylesheet writes
    `margin-top` and `margin-bottom` in full.
    """
    direct = _length_em(_property_for(element, cascade, f"margin-{side}"))
    if direct:
        return direct
    shorthand = _property_for(element, cascade, "margin")
    if not shorthand:
        return 0.0
    parts = shorthand.split()
    index = _MARGIN_SIDES.get(len(parts), {}).get(side)
    return _length_em(parts[index]) if index is not None else 0.0


def _count_paragraph(profile: Profile, element, cascade) -> None:
    indent = _length_em(_property_for(element, cascade, "text-indent"))
    spacing = max(_margin(element, cascade, "bottom"), _margin(element, cascade, "top"))
    indented = indent > INDENT_FLOOR_EM
    spaced = spacing > SPACING_FLOOR_EM
    if indented and spaced:
        profile.paragraphs.both += 1
    elif indented:
        profile.paragraphs.indented += 1
    elif spaced:
        profile.paragraphs.spaced += 1
    else:
        profile.paragraphs.neither += 1


def _property_for(element, cascade, prop: str) -> str | None:
    """Inline style first, then the cascade — the order a browser uses."""
    style = element.get("style") or ""
    if style:
        for name, value in _DECLARATION.findall(style):
            if name.strip().lower() == prop:
                return value.strip()
    if cascade is None:
        return None
    chain = [
        (
            xhtml.local_name(node).lower(),
            frozenset((node.get("class") or "").split()),
            node.get("id"),
        )
        for node in _ancestors(element)
    ]
    # `resolve` answers `(value, targeted, distance)`. The last two say whether
    # the publisher aimed a rule at this element or at something containing it,
    # which is the question a rule that *changes* a book has to ask. This one
    # changes nothing, so it wants the value and no more.
    value, _targeted, _distance = cascade.resolve(prop, chain)
    return value


def _ancestors(element):
    current = element
    while current is not None and isinstance(current.tag, str):
        yield current
        current = current.getparent()


def _looks_like_a_heading(element, text: str) -> bool:
    """A paragraph doing a heading's job without a heading's tag.

    Short, bold or centred, and not ending in a full stop. Deliberately narrow:
    this number is reported and acted on by nothing, and a loose rule would put
    a figure in the report that nobody could trust later.
    """
    if not text or len(text) > 80 or text.endswith((".", ",", ";", ":")):
        return False
    if any(xhtml.local_name(child).lower() in ("b", "strong") for child in element):
        return True
    style = (element.get("style") or "").lower()
    return "text-align: center" in style or "font-weight: bold" in style
