"""The apparatus roadmap [7] needs before a single character may be touched.

Typography is the one stage that changes text on purpose, which makes it the
one stage K1 — *no character of the book's text is lost* — cannot police in its
current form. Turning K1 off for it would be trading the only invariant that
has ever caught a silent data defect for the convenience of the stage most
likely to cause one. So instead: **fold both sides to a canonical form and
compare that.** A curly quote folded to a straight one still has to be there;
a lost word still shows up as a lost word.

Nothing in this module edits a book. It answers three questions the rules will
ask, and it exists first, deliberately, so the safety net is older than what it
catches.

**Where may a rule reach?** :func:`text_nodes`. Enforced by one iterator rather
than by a condition inside every rule, because "did you remember to skip
`<code>`" is a question that gets the right answer nine times and ships on the
tenth.

**Did the text survive?** :func:`canonical` and :func:`unchanged`.

**What does this book already do?** :func:`dominant`. The normal form is the
book's own, not the typographic ideal — a book that consistently uses `«…»` has
made a decision (K5), and the job is to repair inconsistency, not taste. When
no form clearly wins, the answer is "leave it", and that is what the function
returns.

---

**What the shelf says.** 93 real books, measured on 0.2.16, because the
roadmap's three risk classes were written before there were any numbers:

| trace | books | total |
|---|---|---|
| zero-width characters | 0 | 0 |
| mojibake | 0 | 0 |
| hyphens frozen at a line end | 0 above the floor | 25 |
| `...` typed for `…`, and dominant | 34 | — |
| mixes two quote forms | 35 | — |
| more than 20 unbound conjunctions | 39 | — |
| soft hyphens | 4 | 213 591 |

Class 1 (safe repairs) and class 3 (reconstruction) have between them almost no
customers here; class 2 — the typographic one, behind its own flag — has
thirty-something for each of its three rules. So the order the roadmap implies,
easiest class first, would have shipped the machinery for defects this shelf
does not have. The evidence says start with quotes, the ellipsis and the
conjunctions.

The soft hyphens are the surprise: a fifth of a million of them, in four books,
which is a publisher pre-computing hyphenation points on purpose. They are not
damage and nothing here removes them.
"""

from __future__ import annotations

import re
import unicodedata

#: Elements whose text is not prose and must never be retyped. `pre` and `code`
#: hold whitespace that means something; `script` and `style` are not text at
#: all; `ruby` annotations are positioned against the characters underneath, so
#: changing one without the other breaks the pairing.
PROTECTED_TAGS = frozenset(
    {"pre", "code", "kbd", "samp", "var", "script", "style", "textarea", "ruby",
     "rt", "rp"}
)

#: Namespaces that are not XHTML and not ours to retype. MathML text is an
#: expression and SVG text is drawn at coordinates.
PROTECTED_NAMESPACES = (
    "http://www.w3.org/1998/Math/MathML",
    "http://www.w3.org/2000/svg",
)

#: `white-space` values that make whitespace significant. A publisher who sets
#: one has said "print this exactly", and collapsing two spaces there is not a
#: repair.
PRESERVING_WHITESPACE = frozenset({"pre", "pre-wrap", "pre-line", "break-spaces"})

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

#: What the invariant ignores. Every one of these is a decision about *shape*
#: that a typography rule is allowed to make, and none of them is a character
#: of the book in any sense a reader would recognise.
_FOLD = {
    "„": '"', "“": '"', "”": '"', "‟": '"',   # „ “ ” ‟
    "«": '"', "»": '"',                                   # « »
    "‘": "'", "’": "'", "‚": "'", "‛": "'",     # ‘ ’ ‚ ‛
    "–": "-", "—": "-", "‒": "-", "―": "-",     # – — ‒ ―
    " ": " ", " ": " ", " ": " ", " ": " ",     # nbsp, thin
    "­": "", "​": "", "‌": "", "‍": "",         # soft hyphen, zero width
    "﻿": "",
}
_FOLD_TABLE = str.maketrans(_FOLD)

_ELLIPSIS = re.compile(r"\.\.\.")
_WHITESPACE = re.compile(r"\s+")


def is_protected(element) -> bool:
    """True for an element a typography rule may not reach into.

    Ancestry is the caller's business — :func:`text_nodes` walks it — because a
    `<span>` inside `<code>` is protected and the span itself says nothing
    about that.
    """
    tag = element.tag
    if not isinstance(tag, str):  # comment or processing instruction
        return True
    if tag.startswith("{"):
        namespace = tag[1:].partition("}")[0]
        if namespace in PROTECTED_NAMESPACES:
            return True
        local = tag.rpartition("}")[2]
    else:
        local = tag
    return local.lower() in PROTECTED_TAGS


def text_nodes(root, *, language: str | None = None, cascade=None):
    """Every editable text node under *root*, as ``(element, attribute)``.

    ``attribute`` is ``"text"`` or ``"tail"`` — lxml keeps a node's trailing
    text on the node itself, and a rule that forgets the tails edits half a
    paragraph.

    Three things stop the walk, and all three are the same principle: text that
    somebody has already made a decision about.

    * a protected element, and everything inside it;
    * an element in a different language from the publication, because quoting
      conventions are a property of a language and applying Polish rules to a
      French epigraph is not a repair;
    * an element whose computed `white-space` preserves it, when a cascade is
      supplied.

    A tail belongs to the *parent's* flow, not to the element it hangs off, so
    a protected element's tail is still editable — the text after `</code>` is
    ordinary prose and a rule that skipped it would leave a sentence half done.
    """

    def walk(element, protected: bool):
        blocked = protected or is_protected(element)
        if not blocked and _foreign(element, language):
            blocked = True
        if not blocked and cascade is not None and _preserves_whitespace(element, cascade):
            blocked = True
        if not blocked and element.text:
            yield element, "text"
        for child in element:
            yield from walk(child, blocked)
            # The tail is the *parent's* text, so it follows the parent's fate,
            # not the child's and not the grandparent's. Reading the incoming
            # flag instead of this element's own let `c` out of
            # `<code>a<span>b</span>c</code>` — the one character of a protected
            # block that a rule would then have been free to retype.
            if not blocked and child.tail:
                yield child, "tail"

    yield from walk(root, False)


def _foreign(element, language: str | None) -> bool:
    tag = element.get(_XML_LANG) or element.get("lang")
    if not tag or not language:
        return False
    return tag.split("-")[0].lower() != language.split("-")[0].lower()


def _preserves_whitespace(element, cascade) -> bool:
    from . import xhtml

    inline = element.get("style") or ""
    match = re.search(r"white-space\s*:\s*([a-z-]+)", inline, re.IGNORECASE)
    if match:
        return match.group(1).lower() in PRESERVING_WHITESPACE
    value, _ = cascade.lookup(
        "white-space",
        xhtml.local_name(element).lower(),
        frozenset((element.get("class") or "").split()),
        element.get("id"),
    )
    return (value or "").strip().lower() in PRESERVING_WHITESPACE


def canonical(text: str, *, relaxed: bool = True) -> str:
    """The form both sides are compared in.

    ``relaxed=False`` is what the safe class gets: NFC and whitespace folding
    only, so a rule in that class has to leave every visible character exactly
    where it was. ``relaxed=True`` additionally folds the shapes a typographic
    rule is allowed to change — quotes to a straight quote, every dash to a
    hyphen, `...` to `…`, and the invisible characters away entirely.

    What it deliberately does **not** fold: letters, digits, punctuation that
    carries meaning, and word boundaries. A lost word, a swallowed letter and
    two sentences run together all survive the folding and are still caught,
    which is the whole reason for folding rather than switching off.
    """
    folded = unicodedata.normalize("NFC", text)
    if relaxed:
        folded = _ELLIPSIS.sub("…", folded).translate(_FOLD_TABLE)
    return _WHITESPACE.sub(" ", folded).strip()


def unchanged(before: str, after: str, *, relaxed: bool = True) -> bool:
    """Whether a typography pass kept the text it was given."""
    return canonical(before, relaxed=relaxed) == canonical(after, relaxed=relaxed)


#: How far ahead the winner must be to count as the book's own convention.
#: Two thirds rather than a bare majority: at 51% a book is not consistent, it
#: is arguing with itself, and picking the winner would impose an opinion on
#: nearly half the text. The shelf has 35 books mixing two quote forms and the
#: point of this number is that not all 35 get touched.
DOMINANCE = 2 / 3

#: Below this a count is not evidence of a convention, it is a typo. A book
#: with four straight quotes among twelve hundred curly ones has not made a
#: decision about straight quotes.
ENOUGH = 20


def dominant(counts: dict[str, int]) -> str | None:
    """Which form this book actually uses, or None when it has not decided.

    None is a real answer and the common one. A rule that reads it must do
    nothing and say so, rather than fall back on what is typographically
    correct — correcting a book to a convention it never used is the failure
    this whole module is arranged around.
    """
    total = sum(counts.values())
    if total < ENOUGH:
        return None
    name, count = max(counts.items(), key=lambda item: item[1])
    return name if count >= total * DOMINANCE else None
