"""Stylesheets: repointing them, repairing them, and reporting what will not survive.

Split out of `stages/content.py` (EF-031), which had reached 3865 lines and two
unrelated jobs. The boundary is the one the tests already drew: everything here
takes CSS text in and gives CSS text back.

**Where that boundary had to move, and why (EF-059).** It used to say that
nothing here touches a content document, and that a `<style>` element inside a
document was `ContentStage`'s business. Read as a division of labour it was
tidy; read as a description of what the book gets, it meant a book's CSS was
repaired in one place and left alone in another. A `<style>` block got exactly
two things — remote `@import` stripping and url repointing — and none of the
repairs below: no dead-url neutralisation, no `font-style: regular`, no vendor
hacks, no font stacks. Measured on the owner's shelf, two of nine refusals came
out of that gap, one of them the very defect F-017 exists to prevent.

So this stage now reaches into documents for one purpose: their `<style>`
elements go through the chain a stylesheet file goes through, `_mend` — every
repair but one. The exception is the unreachable-rule sweep, and `_inline_blocks`
says why: at this scale it is a change of a different kind, and it needs its own
decision rather than a lift on somebody else's.

It has to happen **here** rather than next door, and not for tidiness: the
repairs that ask what the book uses need a census `ContentStage` only finishes at
the end of its own run — asking mid-way would answer with half a book.

The split moved code and changed none of it. The proof required by WP-14 is that
the corpus signatures come out byte-identical, which is a stronger claim than a
green suite: it says that thirteen public books and six from Gutenberg rebuild to
the same bytes, with the same findings, in all three modes.
"""

from __future__ import annotations

import re
from collections import Counter

import cssutils

from .. import fonts_meta, paths, stylesheet, watermark, xhtml
from ..css_properties import KNOWN_PROPERTIES
from ..decisions import KEEP, STYLE, Option, Question
from ..question_texts import say
from ..report import Action, Automation, Level, Risk
from .base import Context, Stage
from .content import strip_remote_imports

cssutils.log.setLevel(50)  # cssutils logs every minor deviation at WARNING.
#: Anything a font stack may legally end with instead of a concrete font.
GENERIC_FAMILIES = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded", "math", "emoji",
    "fangsong", "inherit", "initial", "unset", "revert", "revert-layer",
}

#: `regular` is not a CSS value for either property; the whole declaration is
#: dropped by every parser, so the publisher's intent never applied at all.
_REGULAR_VALUE_RE = re.compile(r"(font-(?:style|weight)\s*:\s*)regular\b", re.IGNORECASE)

#: Whether a document is worth opening for its CSS at all, asked of the bytes.
#: See `_inline_blocks` for why this is a correctness question and not a
#: micro-optimisation.
_STYLE_ELEMENT = re.compile(rb"<\s*style[\s>]", re.IGNORECASE)

#: Class and id names that a converter invented, recognisable by prefix. The
#: whole list was measured before it was written: over 66 186 unreachable rules
#: in the shelf's `<style>` blocks, every one that fell to no other bucket was
#: examined by hand and traced to one of these tools (Sigil's sgc-, Calibre,
#: Word's mso/Mso, Google Docs' kix, and the section/block counters of
#: docx-to-epub mills). A name matching none of them is *not* assumed to be
#: junk — it is kept and reported, which is what makes this list safe to be
#: incomplete.
_GENERATOR_NAME = re.compile(
    r"^(sgc-|sgd-|calibre|pcalibre|mso|Mso|lst-kix|kix-|Section\d|block_|text_|para\d)",
    re.IGNORECASE,
)

#: Every class and id a selector names, for asking which of them are missing.
#: Deliberately the same shape `stylesheet.names_nothing_here` parses, so the
#: two never disagree about what a selector says.
_SEL_NAME = re.compile(r"[.#]([A-Za-z_-][\w-]*)")

#: The text of each `<style>` element, asked of raw bytes — the boilerplate
#: census must not pay for a parse of every document.
_STYLE_TEXT = re.compile(rb"<\s*style[^>]*>(.*?)</\s*style\s*>", re.S | re.I)


def _block_key(text: str) -> bytes:
    """One normalisation for the boilerplate census and for the block itself.

    The census reads serialised bytes, where an XML writer has escaped `<`,
    `>` and `&`; the block arrives as an element's *text*, where they are
    literal. Word's stylesheets open with `<!--`, so on the shelf the two
    spellings never matched, every stamped Word block missed the boilerplate
    bucket, and 52 121 machine counters were mistaken for typo candidates —
    one book of 135 documents then blew its time budget searching them. Both
    sides now go through this one function, so they cannot disagree again.
    """
    literal = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return " ".join(literal.split()).encode("utf-8", "replace")

#: A declaration written the way an HTML attribute is written: `text-align=
#: "center"` where CSS wants a colon. The lead is `{` or `;` on purpose — it is
#: what keeps this away from an attribute selector (`a[href="x"]`), from a
#: media query, and from an `=` inside a `url()` string, none of which can be
#: preceded by the start of a declaration.
_MALFORMED_DECL_RE = re.compile(
    r"(?P<lead>[{;]\s*)(?P<prop>-?[A-Za-z][A-Za-z0-9-]*)\s*=\s*"
    r"(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)\s*;?"
)

#: One declaration, anchored on the block/statement boundary before it, so a
#: selector's `a:hover` and a `url(data:…)` value can never look like one.
#: The boundary is a lookbehind on purpose: a consuming `[{;]` would eat the
#: very semicolon the *next* declaration anchors on, and `a: 1; b: 2; c: 3`
#: would match only every other declaration. The match span is exactly what
#: removal cuts — declaration plus its own terminating `;` when it has one.
#: The property's first character is a bare letter **by construction**: a
#: vendor-prefixed name (`-epub-hyphens`, or a reader's private property no
#: catalogue can enumerate) never even reaches the judgement below. And the
#: value walks over quoted strings whole — `_skip_noise`'s own lesson,
#: relearned the hard way on the shelf: Word writes
#: `mso-style-name:"Koptekst 2;Kop 2"`, a semicolon inside the quotes, and
#: a string-blind value pattern cut that declaration in half, left an
#: unbalanced quote behind, and blinded the rule scanner to 194 rules of
#: one book. The count guard refused the sheet, which is how this was found.
_DECLARATION_RE = re.compile(
    r"(?<=[{;])\s*(?P<prop>[A-Za-z][A-Za-z0-9-]*)\s*:\s*"
    r"(?P<value>(?:[^;}\"']|\"[^\"]*\"|'[^']*')*?)\s*(?:;|(?=\}))"
)

#: The values every CSS validator has accepted since CSS1, by property — the
#: proof `_duplicate_properties` cuts on. An earlier in-block duplicate is
#: dead only when **no** reader can reject the later value: a reader that
#: rejects `display: flex` falls back to the earlier `display: block`, so
#: that pair is a working fallback and stays. A plain CSS1 length for
#: `margin-bottom` has no reader to fall back for — Word writes
#: `margin-bottom: 0cm` and `margin-bottom: .0001pt` into one block 948
#: times across the shelf, and the earlier line never won anywhere. Every
#: row of this table is here because CSS1 itself lists the value for the
#: property; a property whose CSS1 grammar is narrower than its modern one
#: (`vertical-align` took lengths only in CSS2) earns no row at all.
_CSS1_LENGTH_PROPS = frozenset({
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "text-indent", "font-size", "line-height", "letter-spacing", "word-spacing",
    "width", "height",
    "border-width", "border-top-width", "border-right-width",
    "border-bottom-width", "border-left-width",
})
#: `auto` is CSS1 for exactly these.
_CSS1_AUTO_PROPS = frozenset({
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "width", "height",
})
_CSS1_KEYWORDS = {
    "font-weight": frozenset({
        "normal", "bold", "bolder", "lighter",
        "100", "200", "300", "400", "500", "600", "700", "800", "900",
    }),
    "font-style": frozenset({"normal", "italic", "oblique"}),
    "text-align": frozenset({"left", "right", "center", "justify"}),
}
#: A CSS1 length token: a number with a CSS1 unit or percent, or a bare zero.
#: A bare non-zero number is deliberately not one — CSS1 requires the unit,
#: so a strict validator may reject `margin: 12` and wake the fallback.
_CSS1_LENGTH = re.compile(
    r"(?:[-+]?(?:\d+\.?\d*|\.\d+)(?:pt|px|pc|cm|mm|in|em|ex|%)"
    r"|[-+]?(?:0+\.?0*|\.0+))\Z"
)
_CSS1_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)\Z")
#: Only the margin and padding shorthands took several lengths in CSS1.
_CSS1_MULTI = frozenset({"margin", "padding"})

_IMPORTANT_RE = re.compile(r"!\s*important\s*\Z", re.IGNORECASE)

#: What a shorthand resets: every longhand it covers, the omitted ones
#: included — that is what a shorthand *is*. The map also names families
#: (`font`, `background`…) whose values the CSS1 argument below cannot
#: certify; their pairs are detected and counted, never cut.
_SHORTHAND_RESETS = {
    "margin": frozenset({"margin-top", "margin-right", "margin-bottom", "margin-left"}),
    "padding": frozenset({"padding-top", "padding-right", "padding-bottom", "padding-left"}),
    "border-width": frozenset({"border-top-width", "border-right-width",
                               "border-bottom-width", "border-left-width"}),
    "border-style": frozenset({"border-top-style", "border-right-style",
                               "border-bottom-style", "border-left-style"}),
    "border-color": frozenset({"border-top-color", "border-right-color",
                               "border-bottom-color", "border-left-color"}),
    "border-top": frozenset({"border-top-width", "border-top-style", "border-top-color"}),
    "border-right": frozenset({"border-right-width", "border-right-style", "border-right-color"}),
    "border-bottom": frozenset({"border-bottom-width", "border-bottom-style", "border-bottom-color"}),
    "border-left": frozenset({"border-left-width", "border-left-style", "border-left-color"}),
    "border": frozenset({
        "border-width", "border-style", "border-color",
        "border-top", "border-right", "border-bottom", "border-left",
        "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
        "border-top-style", "border-right-style", "border-bottom-style", "border-left-style",
        "border-top-color", "border-right-color", "border-bottom-color", "border-left-color",
    }),
    "font": frozenset({"font-style", "font-variant", "font-weight",
                       "font-size", "line-height", "font-family", "font-stretch"}),
    "background": frozenset({"background-color", "background-image", "background-repeat",
                             "background-attachment", "background-position", "background-size"}),
    "list-style": frozenset({"list-style-type", "list-style-position", "list-style-image"}),
    "outline": frozenset({"outline-width", "outline-style", "outline-color"}),
}

_CSS1_BORDER_STYLES = frozenset({
    "none", "dotted", "dashed", "solid", "double",
    "groove", "ridge", "inset", "outset",
})
_CSS1_BORDER_WIDTHS = frozenset({"thin", "medium", "thick"})

#: The `font` shorthand's vocabulary as CSS1 defined it:
#:
#:     font: [ <style> || <variant> || <weight> ]? <size> [ / <height> ]? <family>
#:
#: Size and family are required and ordered; the three optional keywords may
#: come in any order but only once each. CSS2's system fonts (`font: menu`)
#: are deliberately absent — a CSS1 validator rejects them, and a rejected
#: shorthand is the one case where an overridden longhand still matters.
_CSS1_FONT_STYLES = frozenset({"normal", "italic", "oblique"})
_CSS1_FONT_VARIANTS = frozenset({"normal", "small-caps"})
_CSS1_FONT_WEIGHTS = frozenset({
    "normal", "bold", "bolder", "lighter",
    "100", "200", "300", "400", "500", "600", "700", "800", "900",
})
_CSS1_FONT_SIZES = frozenset({
    "xx-small", "x-small", "small", "medium", "large", "x-large", "xx-large",
    "larger", "smaller",
})
#: A bare family name: CSS1 allows it unquoted, and a multi-word one unquoted
#: too (`font-family: New Century Schoolbook`).
_BARE_FAMILY_WORD = re.compile(r"[A-Za-z][A-Za-z0-9-]*\Z")
_CSS1_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)\Z")
#: The sixteen colour names CSS1 itself listed; anything newer is a value
#: an old validator may reject, which is exactly what disqualifies it.
_CSS1_COLOR_NAMES = frozenset({
    "black", "silver", "gray", "white", "maroon", "red", "purple", "fuchsia",
    "green", "lime", "olive", "yellow", "navy", "teal", "blue", "aqua",
})
_CSS1_HEX = re.compile(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?\Z")


def _css1_shorthand_safe(prop: str, value: str) -> bool:
    """True when no validator since CSS1 rejects *value* for shorthand *prop*.

    Strict about grammar, not just vocabulary: `border: solid solid` uses
    two CSS1 words and is still invalid — a validator may reject it, and
    a rejected shorthand is the one case where the overridden longhand
    still matters.
    """
    tokens = value.lower().split()
    if not tokens:
        return False
    if prop in ("margin", "padding"):
        return _css1_safe(prop, value)
    if prop == "border-width":
        return len(tokens) <= 4 and all(
            t in _CSS1_BORDER_WIDTHS or _CSS1_LENGTH.match(t) for t in tokens)
    if prop == "border-style":
        return len(tokens) <= 4 and all(t in _CSS1_BORDER_STYLES for t in tokens)
    if prop == "border-color":
        return len(tokens) <= 4 and all(
            t in _CSS1_COLOR_NAMES or _CSS1_HEX.match(t) for t in tokens)
    if prop in ("border", "border-top", "border-right", "border-bottom", "border-left"):
        if len(tokens) > 3:
            return False
        seen = set()
        for token in tokens:
            if token in _CSS1_BORDER_STYLES:
                category = "style"
            elif token in _CSS1_BORDER_WIDTHS or _CSS1_LENGTH.match(token):
                category = "width"
            elif token in _CSS1_COLOR_NAMES or _CSS1_HEX.match(token):
                category = "colour"
            else:
                return False
            if category in seen:
                return False
            seen.add(category)
        return True
    if prop == "font":
        return _css1_font_shorthand_safe(value)
    return False


def _css1_font_shorthand_safe(value: str) -> bool:
    """True when no validator since CSS1 rejects this `font` shorthand.

    Written 2026-08-22 in answer to the owner's question about the last two
    exceptions on the gate's list — *is this some early compatibility thing?*
    It is not. Nothing about the two declarations needed a reader's mercy;
    the proof for this shorthand had simply never been written, so `font`
    fell through to `False` beside the shorthands that had one, and the
    findings were reported as unprovable rather than as unexamined.

    The grammar is the whole of the argument, and it is strict about order,
    because that is where a shorthand gets rejected: the optional style,
    variant and weight keywords come first and once each, then a size, then
    an optional `/line-height`, then at least one family. Anything outside
    that — a CSS2 system font, a second size, a stray token — is a value
    some validator may reject, and then the longhand it overrode is still
    somebody's fallback and must stay.
    """
    text = " ".join(value.split())
    if not text or "," in text.split("/")[0].split()[0]:
        return False
    # The family may be quoted and may contain anything, so split the head
    # (keywords, size, line-height) from the family list on the first comma
    # or the first quote — whichever the value reaches first.
    tokens = text.split()
    index = 0
    seen: set[str] = set()
    while index < len(tokens):
        token = tokens[index].lower()
        if token.startswith(("'", '"')):
            break
        category = None
        # `normal` is legal for style, variant and weight alike; it says
        # nothing about which, so it is charged to the first slot free.
        for name, vocabulary in (
            ("style", _CSS1_FONT_STYLES),
            ("variant", _CSS1_FONT_VARIANTS),
            ("weight", _CSS1_FONT_WEIGHTS),
        ):
            if token in vocabulary and name not in seen:
                category = name
                break
        if category is None:
            break
        seen.add(category)
        index += 1
    if index >= len(tokens):
        return False  # keywords and no size: not a font shorthand at all
    size, slash, height = tokens[index].partition("/")
    if not (size.lower() in _CSS1_FONT_SIZES or _CSS1_LENGTH.match(size)):
        return False
    if slash and not height:
        return False  # `12pt/ Arial` — a slash promising a height and no height
    if height and not (
        height.lower() == "normal"
        or _CSS1_NUMBER.match(height)
        or _CSS1_LENGTH.match(height)
    ):
        return False
    family = " ".join(tokens[index + 1:]).strip()
    if not family:
        return False
    for name in family.split(","):
        name = name.strip()
        if not name:
            return False
        if name[0] in "'\"":
            if len(name) < 2 or name[-1] != name[0] or name[0] in name[1:-1]:
                return False
            continue
        if not all(_BARE_FAMILY_WORD.match(word) for word in name.split()):
            return False
    return True


#: The gate's reading of `no-descending-specificity`, probed and calibrated
#: against Calibre's own bundle until the shelf's 586 findings reproduced
#: exactly (zero books divergent). Selectors are compared per *key*: the
#: last compound selector with its pseudo-classes and pseudo-elements
#: stripped, as an exact string — `a.x` never pairs with `a`, `.foo`
#: pairs with `.foo` behind any prelude, `a:hover` pairs with `a`.
_PSEUDO_RE = re.compile(r"::?[-\w]+(\([^)]*\))?")
_COMBINATOR_RE = re.compile(r"\s*[\s>+~]\s*")


def _nds_key(branch: str) -> str:
    last = _COMBINATOR_RE.split(branch.strip())[-1]
    return _PSEUDO_RE.sub("", last) or "*"


def _selector_specificity(branch: str) -> "tuple[int, int, int]":
    """Standard CSS specificity of one selector branch: (ids, classes, types)."""
    text = re.sub(r"\[[^\]]*\]", "[a]", branch)
    text = re.sub(r"::[-\w]+", "::e", text)
    ids = len(re.findall(r"#[-\w]+", text))
    classes = (len(re.findall(r"\.[-\w]+", text)) + text.count("[")
               + len(re.findall(r":(?!:)[-\w()]+", text)))
    types = (len(re.findall(r"(?:^|[\s>+~(])([A-Za-z][-\w]*)", text))
             + text.count("::e"))
    return (ids, classes, types)


def _last_type(branch: str) -> "str | None":
    """The concrete element type the branch's last compound demands, if any.

    Two branches whose last compounds demand *different* types can never
    match the same element — the cheapest of the tie disproofs.
    """
    last = _COMBINATOR_RE.split(branch.strip())[-1]
    matched = re.match(r"([A-Za-z][-\w]*)", last)
    return matched.group(1).lower() if matched else None


#: The simple descendant language the document disproof can read: chains of
#: `type.class.class` compounds joined by descendant combinators, nothing
#: else. A branch outside it offers nothing to disprove a tie with, so the
#: tie blocks — conservative by construction.
_SIMPLE_COMPOUND = re.compile(r"^([A-Za-z][-\w]*)?((?:\.[-\w]+)*)$")


def _simple_chain(branch: str):
    if re.search(r"[>+~\[\]:#*]", branch):
        return None
    chain = []
    for part in branch.split():
        matched = _SIMPLE_COMPOUND.match(part)
        if not matched:
            return None
        classes = frozenset(re.findall(r"\.([-\w]+)", matched.group(2)))
        chain.append((matched.group(1), classes))
    return chain or None


def _declared_values(body: str) -> dict:
    """Property → its winning value in *body*, as every parser reads them.

    The value is whitespace-collapsed, `!important` and all — two rules
    whose shared property carries the same string compute the same thing
    whichever wins, and that is exactly the question the conflict test
    asks. The last occurrence wins within a body, like everywhere else.
    A malformed line (`text-align="center"`) is dropped by every parser,
    so it conflicts with nothing and is rightly absent here.
    """
    return {
        match.group("prop").lower(): " ".join(match.group("value").split())
        for match in _DECLARATION_RE.finditer("{" + body + "}")
    }


def _properties_conflict(some: dict, other: dict) -> bool:
    """Whether two rules could fight over any property — and mean it.

    A specificity tie is decided by order only where the two rules
    declare a common property **with different values**: a tie over
    `margin: 2em` on both sides has no winner for order to flip, which
    is the owner's own point — the whole book is at hand, so read it.
    "Common" still has to respect shorthands: `margin` and `margin-top`
    reach the same slot, every `border-*` pair can, `font` resets
    `line-height`, `all` resets everything — and across *different*
    names the values are not comparable, so those always conflict.
    The rule of thumb is a dash-prefix; the named exceptions are the
    families the prefix cannot see. False positives only cost a skipped
    move.
    """
    for a, a_value in some.items():
        for b, b_value in other.items():
            if a == b:
                if a_value != b_value:
                    return True
                continue
            if a == "all" or b == "all":
                return True
            if a.startswith(b + "-") or b.startswith(a + "-"):
                return True
            if a.startswith("border") and b.startswith("border"):
                return True
            if {a, b} == {"font", "line-height"}:
                return True
            if a.endswith("gap") and b.endswith("gap"):
                return True
    return False


def _compound_matches(element, compound) -> bool:
    element_type, classes = compound
    if element_type and element.tag.rsplit("}", 1)[-1] != element_type:
        return False
    if classes and not classes <= set((element.get("class") or "").split()):
        return False
    return True


def _css1_safe(prop: str, value: str) -> bool:
    """True when no validator since CSS1 rejects *value* for *prop*."""
    keywords = _CSS1_KEYWORDS.get(prop)
    if keywords is not None:
        return value.lower() in keywords
    if prop not in _CSS1_LENGTH_PROPS:
        return False
    tokens = value.lower().split()
    if not tokens or (len(tokens) > 1 and prop not in _CSS1_MULTI) or len(tokens) > 4:
        return False
    for token in tokens:
        if token == "auto" and prop in _CSS1_AUTO_PROPS:
            continue
        if prop == "line-height" and _CSS1_NUMBER.match(token):
            continue
        if _CSS1_LENGTH.match(token):
            continue
        return False
    return True

#: What the element would have to be inheriting for correcting `regular` to
#: change the page (EF-033). `regular` is dropped, so the element inherits; the
#: correction says `normal`, which *overrides*. Those two agree everywhere the
#: inherited value is already normal, and disagree exactly here.
_INHERITABLE_EMPHASIS_RE = re.compile(
    r"font-style\s*:\s*(?:italic|oblique)"
    r"|font-weight\s*:\s*(?:bold|bolder|[6-9]00)"
    r"|font\s*:[^;{}]*\b(?:italic|oblique|bold)\b",
    re.IGNORECASE,
)

#: A font size given in a unit the reader cannot scale (EF-029). `pt` belongs
#: here with `px`: it is an absolute unit in CSS, fixed at 4/3 px, and reaches
#: EPUB from print stylesheets rather than from anybody's intent about screens.
_ABSOLUTE_FONT_SIZE_RE = re.compile(
    r"font-size\s*:\s*(\d+(?:\.\d+)?)\s*(px|pt)\b", re.IGNORECASE
)

#: Whether the sheet decides the root font size itself. `rem` resolves against
#: the root element, so a sheet that sets the root in pixels has already fixed
#: every `rem` under it and the conversion below would buy nothing.
_ROOT_FONT_SIZE_RE = re.compile(
    r"(?:^|[\s,}])(?:html|:root)[^{}]*\{[^{}]*font-size\s*:\s*\d+(?:\.\d+)?\s*(?:px|pt)",
    re.IGNORECASE,
)

#: The CSS initial font size, and the base every conversion here is measured
#: against. Not a guess: `medium` is 16px in every engine, and it is the number
#: a reader's font-size setting moves.
_INITIAL_FONT_SIZE_PX = 16.0

#: One CSS point, in pixels. Fixed by the specification, not by the device.
_PX_PER_PT = 4.0 / 3.0

#: Word's paged-media plumbing: `page: Section2` names an `@page` rule the
#: block was meant to print on. No EPUB reading system applies it to
#: reflowing text — it is print-composition machinery that survived the
#: conversion, not styling. Measured on the owner's shelf before the decision
#: (D-031 conversation, 2026-08-19): 7 694 live rules of exactly this shape,
#: none of which draws anything on any reader. The lead `[{;]` is what keeps
#: this away from `page-break-*`, which readers *do* honour — the hyphen
#: after `page` fails the `\s*:` that must follow.
_PAGE_PLUMBING_RE = re.compile(r"(?P<lead>[{;]\s*)page\s*:\s*[^;}]+;?", re.IGNORECASE)

#: Out-of-flow positioning in a reflowable book. Legitimate in fixed-layout,
#: where the viewport is known; in reflowable it detaches content from
#: pagination and readers clip, overlap or lose it.
_OUT_OF_FLOW_RE = re.compile(
    r"([;{]\s*|^\s*)position\s*:\s*(?:absolute|fixed)\s*;?", re.IGNORECASE | re.MULTILINE
)

#: The two properties EPUB 3 forbids a style sheet from carrying at all
#: (`CSS-001`). Text direction belongs to the markup — the `dir` attribute and
#: `page-progression-direction` — because a reading system has to know it before
#: it has resolved any CSS, and half of them never resolve this one.
#: The separator is matched by a lookbehind rather than consumed, so two of
#: these written back to back are two matches — consuming the `;` would hide the
#: second one behind the first. It also anchors the property to the start of a
#: declaration, which is what keeps `flex-direction: column` and the selector
#: `a.direction:hover` out of this.
_DIRECTION_RE = re.compile(
    r"(?<=[;{])(\s*)(direction|unicode-bidi)\s*:\s*([^;}]*)(;?)", re.IGNORECASE
)

#: The value each of them has when nothing is said. A declaration setting the
#: default is the whole of the observed defect: Word and Sigil write
#: `direction: ltr` into a boilerplate sheet for every book they touch.
_DIRECTION_DEFAULT = {"direction": "ltr", "unicode-bidi": "normal"}

_FONT_FACE_RE = re.compile(r"@font-face\s*\{[^}]*\}", re.IGNORECASE)

#: `src` as a descriptor of its own, not the word inside some other value.
#: Anchored to the start of a declaration so that `font-family: "src"` and a
#: url containing `src` cannot pass for one.
_DECLARES_SRC = re.compile(r"(?:^|[;{])\s*src\s*:", re.IGNORECASE)

_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}]+)", re.IGNORECASE)

#: Adobe Digital Editions inventions; unprefixed, so validators call them unknown.
_ADOBE_PROPERTY_RE = re.compile(
    r"([;{]\s*|^\s*)(adobe-[a-z-]+)\s*:\s*[^;}]*;?", re.IGNORECASE | re.MULTILINE
)

#: `a , b` and `a,b` are one selector written two ways, and a CSS parser
#: normalises the spacing while a text scanner reports what it read. Comparing
#: the two without agreeing on that first reported three real books as damaged
#: when nothing had happened to them.
def _normal_selector(selector: str) -> str:
    return re.sub(r"\s*,\s*", ",", " ".join(selector.split()))

def _split_top_level(value: str) -> list[str]:
    """Split a CSS value on commas that are not inside brackets or quotes.

    `url(a,b.png), url(c.png)` is two candidates, not three: a naive `split(",")`
    cuts inside the first `url()` and produces two halves of one reference.
    """
    parts: list[str] = []
    depth = 0
    quote = ""
    current: list[str] = []
    for character in value:
        if quote:
            current.append(character)
            if character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
            current.append(character)
        elif character == "(":
            depth += 1
            current.append(character)
        elif character == ")":
            depth = max(0, depth - 1)
            current.append(character)
        elif character == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
    if current:
        parts.append("".join(current))
    return [part for part in parts if part.strip()]

def _drop_declaration(css_text: str, start: int, end: int, prop: str) -> str:
    """Remove one declaration, and the `@font-face` around it if it was `src`.

    A face with no source can load nothing, so leaving the rule behind leaves a
    `font-family` name that resolves to a font that does not exist — which is
    the same defect one level along, and the one that makes a page fall back to
    a system font without saying why.
    """
    if prop != "src":
        return css_text[:start] + css_text[end:]

    opening = css_text.rfind("{", 0, start)
    at_rule = css_text.rfind("@", 0, opening) if opening != -1 else -1
    if at_rule != -1 and css_text[at_rule:opening].strip().lower().startswith("@font-face"):
        closing = css_text.find("}", end)
        if closing != -1:
            return css_text[:at_rule] + css_text[closing + 1 :]
    return css_text[:start] + css_text[end:]

def _structurally_sound(css_text: str) -> bool:
    """Braces balanced, strings and comments closed — the cheap half of the
    guard on any text surgery. A bad cut breaks structure, and structure is
    one O(n) walk; whether the result is still grammatical CSS is cssutils's
    question, asked once per mended text at the end of `_mend` instead of at
    every step — the difference between 235 parses and one book blowing its
    time budget (the shelf measured it), and honest guards that still bite.
    """
    return stylesheet.structurally_sound(css_text)


def _parses_as_css(css_text: str) -> bool:
    """Whether cssutils can still read this. The expensive half of the guard,
    asked once per mended text (see `_structurally_sound`)."""
    try:
        sheet = cssutils.parseString(css_text, validate=False)
    except Exception:  # noqa: BLE001 — an unreadable sheet is the answer
        return False
    return sheet is not None

def _rule_model(css_text: str) -> "Counter":
    """Every top-level style rule as (selector, declarations), counted.

    What a renderer would care about and nothing else: not the order, not the
    formatting, not the comments. Used to check a removal against a second
    opinion — `cssutils` reads the sheet, the scanner cuts it, and neither is
    asked to confirm its own work.
    """
    sheet = cssutils.parseString(css_text, validate=False)
    model: Counter = Counter()
    for rule in sheet:
        if rule.type != rule.STYLE_RULE or not rule.selectorText or not rule.style:
            continue
        model[
            (_normal_selector(rule.selectorText), " ".join(rule.style.cssText.split()))
        ] += 1
    return model

def _css_texts(sheets, documents) -> list[str]:
    """Every stylesheet's text, then every `<style>` block of every document."""
    texts: list[str] = [sheet.text() for sheet in sheets]
    for document in documents:
        texts += [
            found.group(1).decode("utf-8", "replace")
            for found in _STYLE_TEXT.finditer(document.data)
        ]
    return texts


def _declarations_by_class(css_texts, first_use) -> tuple[dict[str, list], dict[str, int]]:
    """Each class's declarations, read off every rule that names it, and how
    many rules name it."""
    declarations_of: dict[str, list] = {name: [] for name in first_use}
    rules_of: dict[str, int] = {name: 0 for name in first_use}
    for text in css_texts:
        for span in stylesheet.top_level_rules(text):
            named = set(_SEL_NAME.findall(span.selector)) & set(first_use)
            if not named:
                continue
            body = text[span.start:span.end]
            inner = body[body.find("{") + 1:body.rfind("}")]
            declarations = [
                (part.partition(":")[0].strip().lower(),
                 " ".join(part.partition(":")[2].split()).lower())
                for part in inner.split(";") if ":" in part
            ]
            for name in named:
                declarations_of[name] += declarations
                rules_of[name] += 1
    return declarations_of, rules_of


def _new_class_names(naming, first_use, tags_of, declarations_of, rules_of, *, used) -> dict[str, str]:
    """Old name → new name, in order of first use: a role name where the
    generator's own name carries one (D-033), a merge where two single-rule
    classes have identical bodies (D-031), a speaking name where one can
    carry the whole truth, a numbered one otherwise."""
    # Always English (D-034), whatever the window speaks: identifiers in
    # source code are international, and one spelling per book forever is
    # also one less thing a reproducible build has to pin.
    language = "en"
    taken: set = set()
    counters: dict[str, int] = {}
    identical: dict[tuple, str] = {}
    renames: dict[str, str] = {}
    for old in first_use:
        declarations = declarations_of[old]
        category = naming.categorize(
            tags_of.get(old, set()),
            {prop for prop, _ in declarations},
            declarations,
        )
        # D-033: a role word in the generator's own name — its record of
        # what it generated — outranks everything below, and stays out of
        # the identical-bodies merge in both directions: a role name must
        # never be handed to a class that merely shares a rule body, and
        # a role-carrying class must never dissolve into a numbered one.
        role = naming.role_name(old, tags_of.get(old, set()), language)
        if role is not None:
            new = role
            suffix = 2
            while new in taken or new in used:
                new = f"{role}-{suffix}"
                suffix += 1
            taken.add(new)
            renames[old] = new
            continue
        body_key = (category, tuple(sorted(declarations)))
        if rules_of[old] == 1 and declarations and body_key in identical:
            renames[old] = identical[body_key]  # D-031: identical bodies merge
            continue
        new = None
        if rules_of[old] == 1:
            new = naming.speaking_name(declarations, language)
        if new is None or new in taken or new in used:
            stem = f"ef-{naming.word(category, language)}"
            counters[category] = counters.get(category, 0) + 1
            new = f"{stem}-{counters[category]}"
            while new in taken or new in used:
                counters[category] += 1
                new = f"{stem}-{counters[category]}"
        taken.add(new)
        renames[old] = new
        if rules_of[old] == 1 and declarations:
            identical[body_key] = new
    return renames


def _rename_css(text: str, renames: dict[str, str]) -> str:
    for old, new in renames.items():
        text = re.sub(r"\." + re.escape(old) + r"(?![\w-])", "." + new, text)
    return text


def _renamed_sheets(sheets, renames) -> "list[str] | None":
    """Every stylesheet rewritten, or `None` when one of them would not come
    back with the same number of rules or would not parse as CSS."""
    before_texts = [sheet.text() for sheet in sheets]
    new_sheets = [_rename_css(text, renames) for text in before_texts]
    for before, after in zip(before_texts, new_sheets):
        if len(stylesheet.top_level_rules(before)) != len(
            stylesheet.top_level_rules(after)
        ) or not _parses_as_css(after):
            return None
    return new_sheets


def _duplicate_declarations(css_text: str) -> tuple[list, int, int, list]:
    """Every declaration block scanned for a property declared twice:
    `(cuts, kept, total, askable)` — the spans that provably never win, how
    many duplicates are somebody's fallback and stay, how many duplicates
    there are in all, and the mixed-importance groups that are a question."""
    cuts: list = []
    kept = 0
    total = 0
    askable: list = []
    for body_start, body_end in stylesheet.declaration_blocks(css_text):
        wrapped = "{" + css_text[body_start:body_end] + "}"
        groups: dict = {}
        for match in _DECLARATION_RE.finditer(wrapped):
            groups.setdefault(match.group("prop").lower(), []).append(match)
        for prop, occurrences in groups.items():
            if len(occurrences) < 2:
                continue
            total += len(occurrences) - 1
            parsed = []
            for match in occurrences:
                value = match.group("value").strip()
                important = bool(_IMPORTANT_RE.search(value))
                bare = _IMPORTANT_RE.sub("", value).strip()
                parsed.append((match, " ".join(bare.split()), important))
            values = {value for _, value, _ in parsed}
            important_ones = [entry for entry in parsed if entry[2]]
            if len(values) == 1:
                winner = (important_ones or parsed)[-1]
                losers = [entry for entry in parsed if entry is not winner]
            elif important_ones:
                # D-037: mixed importance over different values is a real
                # divergence — modern readers compute the last important
                # value, importance-blind ones the last plain — and which
                # of the two the book *means* is a person's call, not a
                # proof's. Collected here, asked past the opt-out gate.
                askable.append((prop, parsed, body_start))
                continue
            elif _css1_safe(prop, parsed[-1][1]):
                losers = parsed[:-1]
            else:
                kept += len(occurrences) - 1
                continue
            cuts.extend(
                (body_start - 1 + match.start(), body_start - 1 + match.end())
                for match, _, _ in losers
            )
    return cuts, kept, total, askable


def _without_spans(text: str, spans: list) -> str:
    """The text with every `(start, end)` span cut out."""
    pieces: list = []
    cursor = 0
    for start, end in sorted(spans):
        pieces.append(text[cursor:start])
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def _stack_verdict(families: list, embedded: dict, named: dict) -> tuple[str, "str | None"]:
    """What a font stack without a generic family can be given, in order of
    authority: `embedded` (the book's own font says in numbers), `symbol`
    (nothing — no generic draws pictures), `self-named` (the embedded
    font's own name says, for a person to confirm), `well-known` (common
    knowledge, for a person to confirm), or `unknown`."""
    generic = None
    # The whole stack is searched, not only its last entry: a stack is a
    # list of preferences and any one of them being an embedded font
    # settles what kind of type this is meant to be.
    for family in families:
        generic = embedded.get(family.lower())
        if generic:
            break
    if generic:
        return "embedded", generic
    if any(f.lower() in fonts_meta.SYMBOL_FAMILIES for f in families):
        return "symbol", None
    said = None
    for family in families:
        said = named.get(family.lower())
        if said:
            break
    if said:
        return "self-named", said
    known = None
    for family in families:
        known = fonts_meta.well_known(family)
        if known:
            break
    if known:
        return "well-known", known
    return "unknown", None


class StyleStage(Stage):
    """Repoints stylesheet URLs and reports rules that will not survive."""

    name = "css"

    def run(self, ctx: Context) -> None:
        if not ctx.policy.rewrite_content:
            return
        self._add_watermark_rule(ctx)
        for resource in ctx.book.by_type("style"):
            source_path = resource.original_path or resource.path
            text = resource.text()
            rewritten, remote_imports = strip_remote_imports(text)
            if remote_imports:
                self.note(
                    ctx,
                    Level.FIX,
                    "css.remote-import-removed",
                    values={"count": remote_imports},
                    location=resource.path,
                )
            rewritten, unresolved = self._rewrite_urls(
                ctx, rewritten, source_path, resource.path
            )
            rewritten, unresolved = self._mend(
                ctx, rewritten, source_path, resource, unresolved
            )
            resource.data = rewritten.encode("utf-8")

            # EPUB 3 wants `remote-resources` on the manifest item of *any*
            # resource that reaches outside the container, and this program was
            # computing it for documents only. A stylesheet with
            # `background-image: url(https://…)` is exactly such a resource, and
            # leaving the property off is an error EPUBCheck names — found by a
            # fixture written for something else, which is the usual way.
            if any(
                paths.is_remote(match.group(2))
                for match in re.finditer(
                    r"url\(\s*(['\"]?)(.*?)\1\s*\)", rewritten, flags=re.IGNORECASE
                )
            ):
                resource.properties.add("remote-resources")

            if unresolved:
                self.note(
                    ctx,
                    Level.WARN,
                    "css.url-unresolved",
                    values={"count": unresolved},
                    location=resource.path,
                )
            self._validate(ctx, resource)

        self._inline_blocks(ctx)
        self._translate_class_names(ctx)
        self._merge_after_translation(ctx)

    def _mend(
        self,
        ctx: Context,
        css_text: str,
        source_path: str,
        resource,
        unresolved: int,
        *,
        sweep_unreachable: bool = True,
        boilerplate: bool = False,
    ) -> tuple[str, int]:
        """Every repair this stage knows, in order, whatever the CSS lives in.

        One chain and one caller apiece: a stylesheet file, and a `<style>`
        element inside a document. Written as a method rather than left inline
        in `run` because a book's CSS being repaired in one place and untouched
        in another is the whole of EF-059, and two copies of this order would
        drift apart the same way.

        `sweep_unreachable` is the one difference between the two callers, and
        it is a difference on purpose rather than an oversight — see
        `_inline_blocks`.
        """
        original_text, original_unresolved = css_text, unresolved
        if unresolved and ctx.policy.remove_dead:
            css_text, neutralised = self._neutralise_dead_urls(
                ctx, css_text, source_path, resource.path, resource
            )
            unresolved -= neutralised
        css_text = self._comment_shield(ctx, css_text, resource)
        css_text = self._strip_vendor_hacks(ctx, css_text, resource)
        css_text = self._repair(ctx, css_text, resource)
        css_text = self._malformed_declarations(ctx, css_text, resource, boilerplate=boilerplate)
        css_text = self._publisher_typos(ctx, css_text, resource)
        css_text = self._unknown_properties(ctx, css_text, resource)
        css_text = self._merge_duplicate_selectors(ctx, css_text, resource)
        css_text = self._duplicate_properties(ctx, css_text, resource)
        css_text = self._shorthand_overrides(ctx, css_text, resource)
        css_text = self._ascending_specificity(ctx, css_text, resource)
        css_text = self._empty_noise(ctx, css_text, resource)
        css_text = self._faces_that_load_nothing(ctx, css_text, resource)
        css_text = self._page_plumbing(ctx, css_text, resource)
        css_text = self._absolute_font_sizes(ctx, css_text, resource)
        css_text = self._vendor_properties(ctx, css_text, resource)
        if sweep_unreachable:
            css_text = self._unreachable_rules(ctx, css_text, resource)
        css_text = self._font_stacks(ctx, css_text, resource)
        css_text = self._readable_format(ctx, css_text, resource)
        # The expensive half of every repair's guard, paid once: whatever the
        # chain produced still has to read as CSS to a full parser. On a
        # failure the whole mend is handed back — a chain whose product does
        # not parse has no step worth keeping, and which step broke it is a
        # question for the suite, not for a reader's book.
        if css_text != original_text and not _parses_as_css(css_text):
            self.note(ctx, Level.WARN, "css.mend-unverified", location=resource.path)
            return original_text, original_unresolved
        return css_text, unresolved

    def _inline_blocks(self, ctx: Context) -> None:
        """Put every `<style>` element in the book through the same chain.

        Runs after the stylesheet loop, and after `ContentStage` has finished,
        for the reason in the module docstring: the repairs that ask what the
        book uses need the whole book to have been read.

        The url rewriting is **not** repeated here — `ContentStage` already did
        it for these blocks, relative to the document, which is the right frame
        of reference. What comes in is therefore already repointed, and
        `_neutralise_dead_urls` asks its question of both layouts anyway.

        **And one repair is deliberately left out: the unreachable-rule sweep.**
        Not because it would be wrong here — the question it asks, "can this
        selector match anything in this book", is the same question — but
        because of what it does at this scale. Measured over the owner's 160
        books, running it on `<style>` blocks takes the shelf from **6 303
        removed rules to 72 219**, with one book contributing 49 545: a
        converter writes the same boilerplate block into all 135 of its
        documents, and almost none of it is reachable.

        That may well be the right thing to do. It is not something to start
        doing as a side effect of a fix for two dead urls. The owner's standing
        rule is that whatever this program removes is either optional or asked
        about, and a change of that size arrives with its own decision to make,
        its own measurement and its own audit. Until then a `<style>` block gets
        every repair except this one, and the difference is written down here
        rather than left for somebody to find in a diff.
        """
        # The boilerplate census, from bytes: the same normalised block text in
        # three or more documents of one book is a converter stamping its
        # template, and per D-028 that bucket may go without a question.
        stamped: Counter = Counter()
        if ctx.policy.sweep_style_blocks:
            for resource in ctx.book.content_docs():
                for found in _STYLE_TEXT.finditer(resource.data):
                    stamped[_block_key(found.group(1).decode("utf-8", "replace"))] += 1

        for resource in ctx.book.content_docs():
            # Asked of the bytes before the tree, and not as an optimisation for
            # its own sake: `ctx.take` **evicts** the parse from the cache,
            # because a tree about to be mutated must not stay under a key that
            # says "this is what those bytes parse to". Taking every document
            # here would therefore make every later stage parse the book a
            # second time — for the documents, the large majority, that have no
            # `<style>` element at all.
            #
            # This reads the bytes rather than the tree, so it is only true
            # while `ContentStage` writes every document back before this stage
            # runs — which it does, unconditionally, at the end of its own loop.
            # If that ever becomes conditional, a `<style>` element *inserted*
            # by that stage would be invisible here.
            if not _STYLE_ELEMENT.search(resource.data):
                continue
            blocks = []
            tree = ctx.take(resource)
            root = tree.root
            for element in root.iter(xhtml.qname("style")):
                text = element.text or ""
                if text.strip():
                    blocks.append(element)
            if not blocks:
                continue
            source_path = resource.original_path or resource.path
            touched = False
            for element in blocks:
                before = element.text or ""
                # A dead url here is dead in the same sense as in a sheet, and
                # the count exists only so `_mend` knows whether to look.
                unresolved = 1 if "url(" in before else 0
                after, _ = self._mend(
                    ctx, before, source_path, resource, unresolved,
                    sweep_unreachable=False,
                    boilerplate=stamped.get(_block_key(before), 0) >= 3,
                )
                if ctx.policy.sweep_style_blocks:
                    after = self._sweep_style_block(
                        ctx, after, resource,
                        boilerplate=stamped.get(_block_key(before), 0) >= 3,
                    )
                else:
                    # The unticked box still counts — `--keep-style-junk`
                    # promised it in its help text before the code kept the
                    # promise, and the sixth audit caught the difference. The
                    # same line the sheet sweep uses for "found, not removed".
                    found = [
                        span
                        for span in stylesheet.top_level_rules(after)
                        if stylesheet.names_nothing_here(
                            span.selector, ctx.used_classes, ctx.used_ids
                        )
                    ]
                    if found:
                        self.note(
                            ctx, Level.INFO, "css.unreachable-rules-found",
                            values={
                                "count": len(found),
                                "share": round(100 * sum(s.end - s.start for s in found) / max(len(after), 1)),
                                "total": len(stylesheet.top_level_rules(after)),
                            },
                            location=resource.path,
                        )
                if after != before:
                    element.text = after
                    touched = True
            if touched:
                resource.data = xhtml.serialize(root)

    def _sweep_style_block(
        self, ctx: Context, css_text: str, resource, *, boilerplate: bool
    ) -> str:
        """The unreachable-rule sweep, for one `<style>` block, two buckets.

        D-028, narrowed again by D-030. The owner's rule about removal draws
        the line at *significant* changes versus code errors (D-026), so:

        * a rule whose dead name is a **converter's** (`_GENERATOR_NAME`), or
          whose whole block is boilerplate pasted into three or more documents
          of this book, is a code error and goes — with a report line;
        * anything else dead is kept and counted, because a list of generator
          prefixes is safe only while matching none of them means keeping.

        There used to be a third bucket — a dead name one edit away from a
        used one became a "possible typo" question. D-030 removed it, on the
        owner's own challenge ("po co szukamy literówek skoro i tak
        odbudowujemy książkę"): a dead rule never drew anything, so removing
        or keeping it looks identical, and the only thing the question could
        *do* — repair the name so the rule starts applying — changes how the
        book looks, against this program's own promise. Measured before the
        removal: 160 books, zero typo questions ever asked, while the
        machinery itself produced two real defects (EF-064's 30 224 false
        candidates, a quadratic search that blew one book's time budget).

        The same guards as the sheet sweep where they still apply: a scripted
        book is left alone entirely, and the cut is verified by re-parsing
        before it is kept. One guard deliberately does **not** apply since
        D-029: this sweep is not gated on `remove_dead`, because that switch
        divides preserve from strict over deviations a reader can see, and a
        rule no selector reaches is visible nowhere. The sweep's own switch is
        the opt-out.
        """
        spans = stylesheet.top_level_rules(css_text)
        dead = [
            span for span in spans
            if stylesheet.names_nothing_here(span.selector, ctx.used_classes, ctx.used_ids)
        ]
        if not dead:
            return css_text
        if ctx.scripted:
            self.note(ctx, Level.INFO, "css.unreachable-rules-scripted",
                      values={"count": len(dead)}, location=resource.path)
            return css_text
        share = round(100 * sum(s.end - s.start for s in dead) / max(len(css_text), 1))
        # Not gated on `remove_dead`, on purpose (D-029): that switch divides
        # preserve from strict over deviations a reader can *see*, and a rule
        # no selector reaches is visible nowhere. The owner's line draws the
        # boundary at the book versus the converter's litter — preserve keeps
        # the book. The sweep's own switch is the opt-out S-02 requires.

        used = ctx.used_classes | ctx.used_ids
        junk: list = []
        unmatched = 0
        for span in dead:
            missing = {n for n in set(_SEL_NAME.findall(span.selector)) if n not in used}
            if boilerplate or any(_GENERATOR_NAME.match(n) for n in missing):
                junk.append(span)
            else:
                unmatched += 1

        if junk:
            result = stylesheet.without(css_text, junk)
            # The cut is checked rather than trusted, same as the sheet sweep:
            # the result must still be a stylesheet holding exactly the rules
            # that were not cut.
            if not _structurally_sound(result) or (
                len(stylesheet.top_level_rules(result)) != len(spans) - len(junk)
            ):
                self.note(ctx, Level.WARN, "css.unreachable-rules-unverified",
                          values={"count": len(junk)}, location=resource.path)
            else:
                css_text = result
                self.note(ctx, Level.FIX, "css.style-junk-removed",
                          values={"count": len(junk), "share": share, "total": len(spans)},
                          location=resource.path)
                self.changed(
                    ctx, Action.REMOVED, resource.path,
                    before=f"{len(junk)} converter-leftover rule(s) matching nothing",
                    after="removed from the document's <style> block",
                    risk=Risk.NONE, reversible=False,
                    rule="css.style-junk-removed",
                )
        if unmatched:
            self.note(ctx, Level.INFO, "css.style-unmatched-kept",
                      values={"count": unmatched}, location=resource.path)
        return css_text

    #: Every tag that carries a class, asked of serialized bytes — the naming
    #: census walks every document and must not pay for a parse of each.
    _TAG_CLASS_RE = re.compile(rb'<([A-Za-z][A-Za-z0-9]*)\b[^>]*?\bclass="([^"]*)"')

    #: A whole tag, for rewriting class attributes **inside tags only**. The
    #: first shelf run with the translation on found the counterexample this
    #: guards: a book whose visible text contains a *literal, broken* tag —
    #: `span class="sgc-5">` with its `<` lost somewhere in the source's own
    #: conversion — and a bare `class="…"` pattern renamed the book's text.
    #: K1 refused the file, which is exactly what K1 is for.
    _TAG_RE = re.compile(rb"<[A-Za-z][^>]*>")

    _CLASS_ATTR_RE = re.compile(rb'\bclass="([^"]*)"')

    def _translate_class_names(self, ctx: Context) -> None:
        """Rename a converter's class names to the epubforge dictionary (D-031).

        Pillar 1 of the 0.3 plan, the shape negotiated with the owner across
        six conversations: `ef-<category>-<number>` — category from what the
        class is *attached to* in this book (ambiguity lands in `inne`, never
        in a wrong specific category), number from the order of first use in
        reading order, a speaking name (`ef-kursywa`) where one to three
        atomic declarations can carry the whole truth. The rule's **values are
        never touched**: the composition the converter recorded — every
        indent, every margin — survives byte for byte; only the name changes,
        in the stylesheet and in every `class` attribute together.

        The names are **always English**, whatever language the window
        speaks (D-034). The first design followed the interface language —
        the owner's own argument about hand-editing in Calibre — and the
        owner reversed it after living with it: identifiers in source code
        are international by convention, and Polish ones would keep making
        trouble downstream. The window and the report keep speaking Polish;
        the report's map and the help's dictionary are where a Polish reader
        learns what `ef-paragraph-3` means.

        Two whole-book guards, both absolute: a **scripted** book is left
        alone (a script may hold class names in strings this program cannot
        see into), and a book whose CSS uses **attribute selectors on class**
        (`[class~=…]`) is left alone too — those reach classes by a route the
        rewrite below does not travel. On by default in both modes (D-032);
        the opt-out is `--keep-class-names` and the window's tick.

        D-033, after the seventh audit and the owner's own example: a role
        word the generator wrote into its own name (`sgc-toc-title`) is the
        tool's record of what it generated — the same class of fact as the
        cover repair's marker — and is translated rather than discarded:
        `ef-contents`, with a toc level's own digit carried over. And a
        block class whose declarations style like a heading is `inne`, not
        `akapit` — the category that cannot lie about a title composed out
        of `<div>`.
        """
        if not ctx.policy.translate_class_names:
            return
        from .. import naming

        if ctx.scripted:
            self.note(ctx, Level.INFO, "css.class-translation-scripted", values={})
            return

        documents = ctx.book.content_docs()
        sheets = list(ctx.book.by_type("style"))
        css_texts = _css_texts(sheets, documents)
        if any("[class" in text for text in css_texts):
            self.note(ctx, Level.INFO, "css.class-translation-attr-selector", values={})
            return

        tags_of, first_use = self._class_census(documents)
        if not first_use:
            return
        declarations_of, rules_of = _declarations_by_class(css_texts, first_use)
        renames = _new_class_names(
            naming, first_use, tags_of, declarations_of, rules_of,
            used=set(tags_of) | set(ctx.used_classes),
        )
        if not renames:
            return

        # Build every rewritten text first, verify, and only then commit —
        # a half-renamed book is worse than an untouched one.
        new_sheets = _renamed_sheets(sheets, renames)
        if new_sheets is None:
            self.note(ctx, Level.WARN, "css.class-translation-unverified", values={})
            return
        for sheet, text in zip(sheets, new_sheets):
            sheet.data = text.encode("utf-8")
        for document in documents:
            document.data = self._rename_classes_in_document(document.data, renames)

        listed = "\n".join(f"{old} → {new}" for old, new in renames.items())
        self.note(
            ctx, Level.FIX, "css.classes-renamed",
            values={"count": len(renames), "language": "en"},
            detail=listed,
        )
        self.changed(
            ctx, Action.REPLACED, "class-names",
            before=f"{len(renames)} converter-named class(es): "
                   + ", ".join(list(renames)[:5]) + ("…" if len(renames) > 5 else ""),
            after="renamed to the epubforge dictionary; the report carries the full map",
            risk=Risk.NONE, reversible=False,
            rule="css.classes-renamed",
        )

    def _class_census(self, documents) -> tuple[dict[str, set], list[str]]:
        """Which tags carry each class, and the order classes first appear in
        reading order. Serialized bytes, double-quoted attributes — which is
        what this program's own writer produces by this point."""
        tags_of: dict[str, set] = {}
        first_use: list[str] = []
        for document in documents:
            for found in self._TAG_CLASS_RE.finditer(document.data):
                tag = found.group(1).decode("ascii", "replace").lower()
                for name in found.group(2).decode("utf-8", "replace").split():
                    tags_of.setdefault(name, set()).add(tag)
                    if name not in first_use and _GENERATOR_NAME.match(name):
                        first_use.append(name)
        return tags_of, first_use

    def _rename_classes_in_document(self, data: bytes, renames: dict[str, str]) -> bytes:
        """Every `class` attribute and every `<style>` block of one document."""
        def attribute(match: "re.Match") -> bytes:
            tokens = match.group(1).decode("utf-8", "replace").split()
            return (
                'class="' + " ".join(renames.get(t, t) for t in tokens) + '"'
            ).encode("utf-8")

        def tag(match: "re.Match") -> bytes:
            return self._CLASS_ATTR_RE.sub(attribute, match.group(0))

        data = self._TAG_RE.sub(tag, data)

        def block(match: "re.Match") -> bytes:
            renamed = _rename_css(
                match.group(1).decode("utf-8", "replace"), renames
            ).encode("utf-8")
            # Spliced by position, not by `str.replace` — the block's text
            # could coincide with a fragment of the element's own tag.
            start, end = match.span(1)
            offset = match.start(0)
            return (
                match.group(0)[: start - offset]
                + renamed
                + match.group(0)[end - offset:]
            )

        return _STYLE_TEXT.sub(block, data)

    def _comment_shield(self, ctx: Context, css_text: str, resource) -> str:
        """Strip the `<!-- … -->` shield an HTML-era converter left in the CSS.

        Pillar A of the 0.4 plan, first slice. The shield hid CSS from
        browsers that predate 1997; every CSS parser since ignores the
        `<!--`/`-->` tokens at the top level of a stylesheet, so removing
        them cannot change a parse — and leaving them is what 312 of the 314
        parse errors in the Calibre-lint baseline were. Top level **only**:
        a `-->` inside a rule is somebody's content and stays. The first
        version anchored on the sheet's edges and the very first shelf run
        measured it doing nothing — Word opens with `/**/` *before* the
        shield, so the walk is the stylesheet module's, not a regex.
        """
        stripped, removed = stylesheet.strip_html_shields(css_text)
        if not removed:
            return css_text
        if not _structurally_sound(stripped) or len(
            stylesheet.top_level_rules(stripped)
        ) != len(stylesheet.top_level_rules(css_text)):
            return css_text
        self.note(ctx, Level.FIX, "css.comment-shield-removed",
                  values={"count": removed}, location=resource.path)
        return stripped

    def _publisher_typos(self, ctx: Context, css_text: str, resource) -> str:
        """A declaration broken by a slip of the publisher's finger, with a
        proposal the program can be honest about (the owner's decision,
        2026-08-22: ask with the proposal shown; without an answer nothing
        changes, S-05).

        Two shapes, both measured on the shelf and both dead today — every
        reader rejects a broken line whole:

        * **a number wearing `$` for a unit** (`margin-right: 2$`): `$` is
          no unit in any CSS, `%` is its keyboard neighbour and the only
          one-character unit — the proposal swaps the sign;
        * **a lost semicolon** (`border: 0px solid border-collapse:
          collapse`): a *known property name* with a colon inside a value
          is two declarations run together — the proposal re-inserts the
          `;`. Every run-together head must be a known property, or the
          colon is part of a value this pass does not understand and the
          line is left unread.

        Both proposals are guesses at intent, which is exactly why they go
        through a question rather than through a repair (D-033 — and here
        the person supplies the missing certainty). Values carrying strings
        or `url(` are left alone unread: a `$` inside quoted content is
        somebody's text, not a unit.
        """
        proposals: list[tuple[int, int, str, str, str]] = []
        for body_start, body_end in stylesheet.declaration_blocks(css_text):
            wrapped = "{" + css_text[body_start:body_end] + "}"
            for match in _DECLARATION_RE.finditer(wrapped):
                prop = match.group("prop").lower()
                value = match.group("value").strip()
                if prop not in KNOWN_PROPERTIES:
                    continue
                if '"' in value or "'" in value or "url(" in value.lower():
                    continue
                fixed = None
                unit = re.fullmatch(r"(\d*\.?\d+)\s*\$", value)
                if unit:
                    fixed = unit.group(1) + "%"
                else:
                    pieces = re.split(r"\s+(?=[a-z-]{3,}\s*:)", value)
                    heads = [
                        re.match(r"([a-z-]{3,})\s*:", piece) for piece in pieces[1:]
                    ]
                    if len(pieces) > 1 and heads and all(
                        head and head.group(1) in KNOWN_PROPERTIES for head in heads
                    ):
                        fixed = "; ".join(pieces)
                if fixed is None or fixed == value:
                    continue
                start = body_start - 1 + match.start("value")
                end = body_start - 1 + match.end("value")
                proposals.append(
                    (start, end, fixed, f"{prop}: {value}", f"{prop}: {fixed}")
                )
        if not proposals:
            return css_text
        shown = "\n".join(
            f"{before}  →  {after}" for _, _, _, before, after in proposals[:3]
        )
        question = Question(
            kind=STYLE,
            where=resource.path,
            summary=say("style.typo.summary", count=len(proposals)),
            detail=say("style.typo.detail", where=resource.path,
                       count=len(proposals), shown=shown),
            options=(
                Option(KEEP, say("style.typo.keep"), say("style.typo.keep.why")),
                Option("fix", say("style.typo.fix"),
                       say("style.typo.fix.why", count=len(proposals))),
            ),
            recommended=KEEP,
            reversible=False,
            risk=Risk.APPEARANCE,
            group="style:typo",
            subject=f"{len(proposals)} declarations",
        )
        if ctx.decide(question).option != "fix":
            self.note(ctx, Level.PRESERVED, "css.publisher-typo-left",
                      values={"count": len(proposals)}, location=resource.path)
            return css_text
        mended = css_text
        for start, end, fixed, _, _ in sorted(proposals, reverse=True):
            mended = mended[:start] + fixed + mended[end:]
        self.note(ctx, Level.FIX, "css.publisher-typo-fixed",
                  values={"count": len(proposals),
                          "names": "; ".join(
                              f"{before} → {after}"
                              for _, _, _, before, after in proposals[:3]
                          )},
                  location=resource.path)
        for _, _, _, before, after in proposals:
            self.changed(
                ctx, Action.REPLACED, resource.path,
                before=before, after=after,
                automation=Automation.ASKED,
                risk=Risk.APPEARANCE, reversible=False,
                rule="css.publisher-typo-fixed",
            )
        return mended

    def _unknown_properties(self, ctx: Context, css_text: str, resource) -> str:
        """Remove declarations naming properties CSS does not have.

        Pillar A of the 0.4 plan, and the largest single mountain in its
        baseline: 36 791 of 41 997 lint findings on the shelf are
        `property-no-unknown`, 36 562 of them Word's `mso-*` inside two
        copies of one book's `@font-face` blocks. A declaration whose
        property name no parser knows is dropped whole by **every**
        conforming CSS parser before any reader sees it — the same argument
        the `=` declarations rest on — so removal cannot change a pixel,
        and the render gate still verifies that per book.

        The authority is deliberately the gate's own: `KNOWN_PROPERTIES` is
        the dataset stylelint's rule reads (see `css_properties`). Two
        doors stay open on purpose: a **vendor-prefixed** name (leading `-`)
        is never judged — `-epub-hyphens` is honoured by real readers and
        the lint rule skips prefixes too — and `panose-1` is kept, a CSS 2.1
        font descriptor Calibre itself writes and suppresses in its own
        lint. Behind the sweep's opt-out; without it the report counts.
        """
        # No prefix check here: `_DECLARATION_RE` refuses a leading `-` by
        # construction, so a vendor-prefixed name never reaches this filter.
        # `adobe-*` is excluded although it is bare and unlisted: old RMSDK
        # engines — PocketBooks among them, and the owner has one — honour
        # those inventions, and `_vendor_properties` below owns them with its
        # mode-aware keep/remove. "No parser knows it" must stay literally
        # true for everything cut here.
        matches = [
            m for m in _DECLARATION_RE.finditer(css_text)
            if m.group("prop").lower() not in KNOWN_PROPERTIES
            and m.group("prop").lower() != "panose-1"
            and not m.group("prop").lower().startswith("adobe-")
        ]
        if not matches:
            return css_text
        if not ctx.policy.sweep_style_blocks:
            self.note(ctx, Level.INFO, "css.unknown-properties-found",
                      values={"count": len(matches)}, location=resource.path)
            return css_text
        names = sorted({m.group("prop").lower() for m in matches})
        pieces: list[str] = []
        cursor = 0
        for match in matches:
            pieces.append(css_text[cursor:match.start()])
            cursor = match.end()
        pieces.append(css_text[cursor:])
        cleaned = "".join(pieces)
        rules_before = len(stylesheet.top_level_rules(css_text))
        emptied = [
            span for span in stylesheet.top_level_rules(cleaned)
            if not cleaned[cleaned.index("{", span.start) + 1:span.end].strip("} \t\r\n")
        ]
        if emptied:
            cleaned = stylesheet.without(cleaned, emptied)
        # An at-rule emptied by the removal goes whole too — `@font-face {}`
        # would only trade one lint finding for another.
        cleaned = re.sub(r"@[A-Za-z-]+[^{};]*\{\s*\}", "", cleaned)
        if not _structurally_sound(cleaned) or (
            len(stylesheet.top_level_rules(cleaned)) != rules_before - len(emptied)
        ):
            self.note(ctx, Level.WARN, "css.unknown-properties-unverified",
                      values={"count": len(matches)}, location=resource.path)
            return css_text
        self.note(ctx, Level.FIX, "css.unknown-properties-removed",
                  values={"count": len(matches), "names": ", ".join(names[:3]),
                          "rules": len(emptied)},
                  location=resource.path)
        self.changed(
            ctx, Action.REMOVED, resource.path,
            before=f"{len(matches)} declaration(s) of properties CSS does not have ({', '.join(names[:3])})",
            after="removed; every conforming parser was already dropping them",
            risk=Risk.NONE, reversible=False,
            rule="css.unknown-properties-removed",
        )
        return cleaned

    def _merge_duplicate_selectors(self, ctx: Context, css_text: str, resource) -> str:
        """Fold rules that repeat a selector into one, where the cascade proves it.

        Pillar A of the 0.4 plan, second slice. Two rules with the same
        selector tie on specificity, so **order is the whole cascade** —
        which is exactly why a merge must be proved, not assumed. Two proofs
        are cheap and certain, and only those two are used:

        * **Identical bodies:** every earlier copy loses every conflict to
          the last one anyway, so dropping all but the **last** occurrence
          moves no winner. Keeping the *first* instead would hoist its
          declarations above whatever stood between — a flip; the mutation
          that keeps the first is measured.
        * **A road proved clear:** an earlier body may move into the last
          occurrence (prepended, so the last body still wins intra-block,
          as it won inter-block) when nothing it crosses can be flipped by
          the move. Slice 2 proved that with grammar alone — any shared
          property name blocked, any at-rule blocked unread. Slice 8
          upgraded it at the owner's own prompting ("you have the whole
          books at hand"): an intermediate blocks only on a specificity
          **tie** over a property whose **value differs**, with a co-match
          neither the element types nor **this book's documents** can rule
          out; at-rules on the road are read, never cut, and their inner
          rules judged the same way. A refused copy standing between a
          mover and the last occurrence blocks everything above it — the
          mover may not jump a stuck sibling it conflicts with.

        Everything else stays and is counted (`css.duplicate-selectors-kept`)
        — a pair whose merge cannot be proved is the publisher's cascade,
        and pillar A's line is proof or nothing. Behind the sweep's opt-out.
        """
        spans = stylesheet.top_level_rules(css_text)
        groups: dict[str, list] = {}
        for span in spans:
            groups.setdefault(span.selector, []).append(span)
        doubled = {sel: g for sel, g in groups.items() if len(g) > 1}
        if not doubled:
            return css_text
        extra = sum(len(g) - 1 for g in doubled.values())
        if not ctx.policy.sweep_style_blocks:
            self.note(ctx, Level.INFO, "css.duplicate-selectors-found",
                      values={"count": extra}, location=resource.path)
            return css_text

        def declarations_of(span) -> "list[str] | None":
            """The body as declarations — or `None` for a body this reading
            does not fully account for. `p.sgc-1 {text-align="center"}` has
            an `=` where the pattern wants a colon, parses as zero
            declarations, and a merge that believed that would quietly drop
            the very line `_malformed_declarations` just asked a person
            about. Opaque bodies take no part in any fold."""
            body = css_text[css_text.index("{", span.start) + 1:span.end]
            body = body[:body.rfind("}")]
            found = []
            wrapped = "{" + body + "}"
            cursor = 1
            for match in _DECLARATION_RE.finditer(wrapped):
                gap = re.sub(r"/\*.*?\*/", "", wrapped[cursor:match.start()], flags=re.S)
                if gap.strip("; \t\r\n"):
                    return None
                found.append(f"{match.group('prop')}: {match.group('value')}")
                cursor = match.end()
            tail = re.sub(r"/\*.*?\*/", "", wrapped[cursor:-1], flags=re.S)
            if tail.strip("; \t\r\n"):
                return None
            return found

        def normalized(declarations: "list[str]") -> "tuple[str, ...]":
            return tuple(" ".join(d.split()).lower() for d in declarations)

        def values_of(declarations: "list[str]") -> dict:
            return {
                d.partition(":")[0].strip().lower():
                " ".join(d.partition(":")[2].split())
                for d in declarations
            }

        def branch_info(selector_text: str) -> list:
            return [(b, _selector_specificity(b))
                    for b in [p.strip() for p in selector_text.split(",") if p.strip()]]

        road_cache: dict = {}

        def conflicting(some: dict, other: dict) -> str:
            names = sorted(
                name for name in set(some) & set(other)
                if some[name] != other[name]
            )
            if names:
                name = names[0]
                return f"{name}: {some[name]} / {other[name]}"
            return "wspólna rodzina skrótów"

        def road_blocker(earlier, last, moved_values: dict):
            """None for a clear road, or `(mover branch, blocking selector,
            contested property)` — the sentence a question needs. An opaque
            body blocks namelessly (nothing to reason with, nothing to ask
            about) and is reported as itself."""
            earlier_branches = branch_info(earlier.selector)
            partners = []
            for other in spans:
                if earlier.end <= other.start < last.start and other.selector != earlier.selector:
                    other_declarations = declarations_of(other)
                    if other_declarations is None:
                        return (earlier.selector, other.selector, None)
                    partners.append((branch_info(other.selector),
                                     values_of(other_declarations), other.selector))
            crossed = css_text[earlier.end:last.start]
            partners.extend(
                (branch_info(selector), _declared_values(body), f"@… {selector}")
                for selector, body in stylesheet.conditional_rules(crossed)
            )
            for partner_branches, partner_values, partner_name in partners:
                if not _properties_conflict(partner_values, moved_values):
                    continue
                for branch_t, spec_t in partner_branches:
                    for branch_e, spec_e in earlier_branches:
                        if spec_t != spec_e:
                            continue
                        type_t, type_e = _last_type(branch_t), _last_type(branch_e)
                        if type_t and type_e and type_t != type_e:
                            continue
                        chain_t = _simple_chain(branch_t)
                        chain_e = _simple_chain(branch_e)
                        if chain_t is None or chain_e is None:
                            return (branch_e, partner_name,
                                    conflicting(moved_values, partner_values))
                        if self._element_hits(ctx, branch_t, chain_t, road_cache) \
                                & self._element_hits(ctx, branch_e, chain_e, road_cache):
                            return (branch_e, partner_name,
                                    conflicting(moved_values, partner_values))
            return None

        to_drop: list = []
        prepend: dict[int, list] = {}
        resolved_merges: list = []
        kept = 0
        for selector, group in doubled.items():
            last = group[-1]
            last_declarations = declarations_of(last)
            if last_declarations is None:
                kept += len(group) - 1
                continue
            last_norm = normalized(last_declarations)
            # Decisions run nearest-to-last first: a refused copy blocks
            # every non-identical copy above it, which must not jump a
            # stuck sibling it shares the selector — and every tie — with.
            approved: list = []
            blocked_below = False
            for earlier in reversed(group[:-1]):
                earlier_declarations = declarations_of(earlier)
                if earlier_declarations is None:
                    kept += 1
                    blocked_below = True
                    continue
                if normalized(earlier_declarations) == last_norm:
                    to_drop.append(earlier)
                    continue
                blocker = None
                if not blocked_below:
                    blocker = road_blocker(
                        earlier, last, values_of(earlier_declarations)
                    )
                    if blocker is None:
                        approved.append((earlier, earlier_declarations, False))
                        continue
                # D-037: a pair the prover refuses over a readable conflict
                # becomes a person's question — merging moves the earlier
                # declarations past the blocker, and from then on they win
                # where the blocker used to. An opaque blocker (None
                # contest) has nothing to ask about and stays silent.
                if (not blocked_below) and blocker and blocker[2] is not None:
                    question = Question(
                        kind=STYLE,
                        where=resource.path,
                        summary=say("style.dupsel.summary", selector=selector),
                        detail=say("style.dupsel.detail", where=resource.path,
                                   selector=selector, blocker=blocker[1],
                                   contest=blocker[2]),
                        options=(
                            Option(KEEP, say("style.dupsel.keep"),
                                   say("style.dupsel.keep.why")),
                            Option("merge", say("style.dupsel.merge"),
                                   say("style.dupsel.merge.why",
                                       blocker=blocker[1])),
                        ),
                        recommended=KEEP,
                        reversible=False,
                        risk=Risk.APPEARANCE,
                        group="style:dupsel",
                        subject=selector,
                    )
                    if ctx.decide(question).option == "merge":
                        approved.append((earlier, earlier_declarations, True))
                        continue
                kept += 1
                blocked_below = True
            for earlier, earlier_declarations, asked in reversed(approved):
                to_drop.append(earlier)
                if asked:
                    resolved_merges.append(earlier)
                if earlier_declarations:
                    prepend.setdefault(last.start, []).extend(earlier_declarations)
        if not to_drop:
            self.note(ctx, Level.PRESERVED, "css.duplicate-selectors-kept",
                      values={"count": kept}, location=resource.path)
            return css_text

        drop_spans = sorted(to_drop, key=lambda s: s.start)
        cleaned_parts: list = []
        cursor = 0
        for span in sorted(spans, key=lambda s: s.start):
            if span in drop_spans:
                cleaned_parts.append(css_text[cursor:span.start])
                cursor = span.end
                continue
            if span.start in prepend:
                brace = css_text.index("{", span.start)
                cleaned_parts.append(css_text[cursor:brace + 1])
                cleaned_parts.append(" " + "; ".join(prepend[span.start]) + ";")
                cursor = brace + 1
        cleaned_parts.append(css_text[cursor:])
        cleaned = "".join(cleaned_parts)

        if not _structurally_sound(cleaned) or (
            len(stylesheet.top_level_rules(cleaned)) != len(spans) - len(to_drop)
        ):
            self.note(ctx, Level.WARN, "css.duplicate-selectors-unverified",
                      values={"count": len(to_drop)}, location=resource.path)
            return css_text
        self.note(ctx, Level.FIX, "css.duplicate-selectors-merged",
                  values={"count": len(to_drop)}, location=resource.path)
        if resolved_merges:
            self.note(ctx, Level.FIX, "css.duplicate-selectors-resolved",
                      values={"count": len(resolved_merges)},
                      location=resource.path)
            self.changed(
                ctx, Action.REMOVED, resource.path,
                before=f"{len(resolved_merges)} repeated-selector rule(s) the cascade could not release",
                after="folded past the contested road, on a person's word",
                automation=Automation.ASKED,
                risk=Risk.APPEARANCE, reversible=False,
                rule="css.duplicate-selectors-resolved",
            )
        if kept:
            self.note(ctx, Level.PRESERVED, "css.duplicate-selectors-kept",
                      values={"count": kept}, location=resource.path)
        self.changed(
            ctx, Action.REMOVED, resource.path,
            before=f"{len(to_drop)} repeated-selector rule(s)",
            after="folded into the last occurrence; every cascade winner is the same",
            risk=Risk.NONE, reversible=False,
            rule="css.duplicate-selectors-merged",
        )
        return cleaned

    def _merge_after_translation(self, ctx: Context) -> None:
        """The merge again, after renaming — for the duplicates renaming makes.

        D-031's identical-bodies fold gives two generator classes one name,
        which leaves two byte-identical rules under one selector in the
        sheet; the shelf measured +30 of those the day slice 1 stripped the
        `mso-*` junk that had kept the bodies different. They only exist
        once translation has run, so `_mend`'s pass cannot see them.

        The in-block duplicate cut runs again here for the same reason:
        the merge prepends an earlier body into the selector's last block,
        and when both declared the same property that block now holds the
        pair — created after `_mend`'s own pass was over.
        """
        if not ctx.policy.rewrite_content:
            return
        for sheet in ctx.book.by_type("style"):
            before = sheet.text()
            after = self._merge_duplicate_selectors(ctx, before, sheet)
            after = self._duplicate_properties(ctx, after, sheet)
            after = self._shorthand_overrides(ctx, after, sheet)
            if after != before:
                sheet.data = after.encode("utf-8")
        for resource in ctx.book.content_docs():
            if not _STYLE_TEXT.search(resource.data):
                continue
            data = resource.data
            pieces: list = []
            cursor = 0
            touched = False
            for found in _STYLE_TEXT.finditer(data):
                text = found.group(1).decode("utf-8", "replace")
                merged = self._merge_duplicate_selectors(ctx, text, resource)
                merged = self._duplicate_properties(ctx, merged, resource)
                merged = self._shorthand_overrides(ctx, merged, resource)
                pieces.append(data[cursor:found.start(1)])
                pieces.append(merged.encode("utf-8"))
                cursor = found.end(1)
                touched = touched or merged != text
            pieces.append(data[cursor:])
            if touched:
                resource.data = b"".join(pieces)

    def _readable_format(self, ctx: Context, css_text: str, resource) -> str:
        """Rewrite a one-line sheet into one declaration per line.

        Pillar A of the 0.4 plan, seventh slice, and deliberately the
        smallest: the shelf holds exactly five sheets packed onto a
        single line (two from one publisher template, three from a
        converter) — the owner's original complaint opened on one of
        them. Only those are touched: a sheet with more than two rules
        per line carries no formatting of the publisher's to respect,
        while everything else is somebody's layout and stays byte-alone.
        The transform is pure whitespace (`stylesheet.readable`), guarded
        by the strongest equality this file has: both texts with every
        whitespace removed must match to the character.
        """
        rules = stylesheet.top_level_rules(css_text)
        lines = css_text.count("\n") + 1
        # Ten rules is the measured floor: the smallest one-liner on the
        # shelf packs 27, and a three-rule line is legible as it stands.
        if len(rules) < 10 or len(rules) <= 2 * lines:
            return css_text
        if not ctx.policy.sweep_style_blocks:
            self.note(ctx, Level.INFO, "css.single-line-found",
                      values={"rules": len(rules), "lines": lines},
                      location=resource.path)
            return css_text
        pretty = stylesheet.readable(css_text)
        if not _structurally_sound(pretty) or (
            len(stylesheet.top_level_rules(pretty)) != len(rules)
            or re.sub(r"\s+", "", pretty) != re.sub(r"\s+", "", css_text)
        ):
            self.note(ctx, Level.WARN, "css.reformat-unverified",
                      location=resource.path)
            return css_text
        self.note(ctx, Level.FIX, "css.reformatted",
                  values={"rules": len(rules), "lines": lines},
                  location=resource.path)
        self.changed(
            ctx, Action.REPLACED, resource.path,
            before=f"{len(rules)} rules packed onto {lines} line(s)",
            after="one declaration per line; every character outside whitespace identical",
            risk=Risk.NONE, reversible=False,
            rule="css.reformatted",
        )
        return pretty

    def _shorthand_overrides(self, ctx: Context, css_text: str, resource) -> str:
        """Cut a longhand a later shorthand in the same block resets anyway.

        Pillar A of the 0.4 plan, sixth slice — 42
        `declaration-block-no-shorthand-property-overrides` findings on
        the shelf, 43 of the 45 measured pairs one publisher template's:
        `border-top-color: #353237; … border: 1px solid;`. A shorthand
        resets **every** longhand it covers, the omitted ones included —
        `border: 1px solid` sets the colour back to its initial value in
        every parser since CSS1 — so the earlier colour was already being
        discarded everywhere.

        The proof is the same shape as the duplicate slice's: the cut is
        allowed only when no validator since CSS1 can reject the
        *shorthand's* value (`_css1_shorthand_safe`), because a rejected
        shorthand is the one case where the earlier longhand still
        matters. Importance follows the block's own law: a longhand with
        `!important` beats a plain shorthand for its slot and stays. The
        `font` findings stay too — that shorthand's grammar is beyond the
        CSS1 argument — kept and counted. Behind the sweep's opt-out.
        """
        cuts: list = []
        kept = 0
        total = 0
        for body_start, body_end in stylesheet.declaration_blocks(css_text):
            wrapped = "{" + css_text[body_start:body_end] + "}"
            declarations = list(_DECLARATION_RE.finditer(wrapped))
            for index, match in enumerate(declarations):
                shorthand = match.group("prop").lower()
                covered = _SHORTHAND_RESETS.get(shorthand)
                if not covered:
                    continue
                value = match.group("value").strip()
                shorthand_important = bool(_IMPORTANT_RE.search(value))
                bare = _IMPORTANT_RE.sub("", value).strip()
                for earlier in declarations[:index]:
                    if earlier.group("prop").lower() not in covered:
                        continue
                    total += 1
                    earlier_important = bool(
                        _IMPORTANT_RE.search(earlier.group("value").strip())
                    )
                    if earlier_important and not shorthand_important:
                        kept += 1
                        continue
                    if not _css1_shorthand_safe(shorthand, bare):
                        kept += 1
                        continue
                    cuts.append((body_start - 1 + earlier.start(),
                                 body_start - 1 + earlier.end()))
        if not total:
            return css_text
        if not ctx.policy.sweep_style_blocks:
            self.note(ctx, Level.INFO, "css.shorthand-overrides-found",
                      values={"count": total}, location=resource.path)
            return css_text
        if not cuts:
            self.note(ctx, Level.PRESERVED, "css.shorthand-overrides-kept",
                      values={"count": kept}, location=resource.path)
            return css_text
        pieces: list = []
        cursor = 0
        for start, end in sorted(set(cuts)):
            pieces.append(css_text[cursor:start])
            cursor = end
        pieces.append(css_text[cursor:])
        cleaned = "".join(pieces)
        if not _structurally_sound(cleaned) or (
            len(stylesheet.top_level_rules(cleaned))
            != len(stylesheet.top_level_rules(css_text))
        ):
            self.note(ctx, Level.WARN, "css.shorthand-overrides-unverified",
                      values={"count": len(cuts)}, location=resource.path)
            return css_text
        self.note(ctx, Level.FIX, "css.shorthand-overrides-removed",
                  values={"count": len(set(cuts))}, location=resource.path)
        if kept:
            self.note(ctx, Level.PRESERVED, "css.shorthand-overrides-kept",
                      values={"count": kept}, location=resource.path)
        self.changed(
            ctx, Action.REMOVED, resource.path,
            before=f"{len(set(cuts))} longhand declaration(s) a later shorthand was resetting",
            after="removed; the shorthand already reset that slot in every parser",
            risk=Risk.NONE, reversible=False,
            rule="css.shorthand-overrides-removed",
        )
        return cleaned

    def _duplicate_properties(self, ctx: Context, css_text: str, resource) -> str:
        """Cut in-block duplicates of a property that provably never win.

        Pillar A of the 0.4 plan, fourth slice — 1 288
        `declaration-block-no-duplicate-properties` findings on the shelf,
        87% of them one Word artifact: `margin-bottom: 0cm` followed by
        `margin-bottom: .0001pt` with another line between. Within one
        block importance beats order and order beats nothing else, so a
        duplicate is dead under exactly two proofs:

        * **Same value everywhere:** every parser picks *some* occurrence
          and they all say the same thing. The winner stays — the last
          important one when importance is in play, the last occurrence
          otherwise — so the inter-rule cascade keeps its importance too.
        * **Different values, and the last one no validator since CSS1
          rejects:** the fallback idiom (`display: block; display: flex`)
          works only because an old reader can *reject* the later value
          and fall back to the earlier. A plain CSS1 length has no reader
          to reject it, so the earlier line never wins anywhere.
          `_css1_safe` is the whole of that argument, kept deliberately
          small.

        A group that mixes values with `!important`, and a group whose
        last value some validator may reject, is somebody's fallback until
        proved otherwise: kept and counted. Blocks inside at-rules are
        treated too — whatever condition turns a block on turns all of it
        on, so the in-block winner is the same under any condition.
        Behind the sweep's opt-out, like the rest of the family.
        """
        cuts, kept, total, askable = _duplicate_declarations(css_text)
        if not total:
            return css_text
        if not ctx.policy.sweep_style_blocks:
            self.note(ctx, Level.INFO, "css.duplicate-properties-found",
                      values={"count": total}, location=resource.path)
            return css_text
        resolved, kept_on_request = self._ask_about_mixed_importance(ctx, resource, askable, cuts)
        kept += kept_on_request
        if not cuts:
            self.note(ctx, Level.PRESERVED, "css.duplicate-properties-kept",
                      values={"count": kept}, location=resource.path)
            return css_text
        cleaned = _without_spans(css_text, cuts)
        if not _structurally_sound(cleaned) or (
            len(stylesheet.top_level_rules(cleaned))
            != len(stylesheet.top_level_rules(css_text))
        ):
            self.note(ctx, Level.WARN, "css.duplicate-properties-unverified",
                      values={"count": len(cuts)}, location=resource.path)
            return css_text
        self._note_duplicates_cut(ctx, resource, provable=len(cuts) - resolved,
                                  resolved=resolved, kept=kept)
        return cleaned

    def _ask_about_mixed_importance(self, ctx: Context, resource, askable: list, cuts: list) -> tuple[int, int]:
        """D-037: each group of different values with mixed `!important` is a
        question; "resolve" adds the losers to `cuts`. Returns how many
        declarations were resolved and how many kept on a person's word."""
        resolved = 0
        kept = 0
        for prop, parsed, body_start in askable:
            winner = [entry for entry in parsed if entry[2]][-1]
            shown = " | ".join(
                value + (" !important" if important else "")
                for _, value, important in parsed
            )
            question = Question(
                kind=STYLE,
                where=resource.path,
                summary=say("style.important.summary", prop=prop),
                detail=say("style.important.detail", where=resource.path,
                           prop=prop, values=shown, winner=winner[1]),
                options=(
                    Option(KEEP, say("style.important.keep"),
                           say("style.important.keep.why")),
                    Option("resolve", say("style.important.resolve"),
                           say("style.important.resolve.why", winner=winner[1])),
                ),
                recommended="resolve",
                reversible=False,
                risk=Risk.APPEARANCE,
                group="style:important",
                subject=prop,
            )
            if ctx.decide(question).option == "resolve":
                for match, _, _ in (e for e in parsed if e is not winner):
                    cuts.append((body_start - 1 + match.start(),
                                 body_start - 1 + match.end()))
                resolved += len(parsed) - 1
            else:
                kept += len(parsed) - 1
        return resolved, kept

    def _note_duplicates_cut(self, ctx: Context, resource, *, provable: int, resolved: int, kept: int) -> None:
        if provable:
            self.note(ctx, Level.FIX, "css.duplicate-properties-removed",
                      values={"count": provable}, location=resource.path)
            self.changed(
                ctx, Action.REMOVED, resource.path,
                before=f"{provable} in-block duplicate declaration(s) that could never win",
                after="removed; each property's winning declaration stays where it stood",
                risk=Risk.NONE, reversible=False,
                rule="css.duplicate-properties-removed",
            )
        if resolved:
            self.note(ctx, Level.FIX, "css.duplicate-properties-resolved",
                      values={"count": resolved}, location=resource.path)
            self.changed(
                ctx, Action.REMOVED, resource.path,
                before=f"{resolved} duplicate declaration(s) with mixed !important over different values",
                after="the modern cascade's winner stands alone, on a person's word",
                automation=Automation.ASKED,
                risk=Risk.APPEARANCE, reversible=False,
                rule="css.duplicate-properties-resolved",
            )
        if kept:
            self.note(ctx, Level.PRESERVED, "css.duplicate-properties-kept",
                      values={"count": kept}, location=resource.path)

    def _ascending_specificity(self, ctx: Context, css_text: str, resource) -> str:
        """Move a rule above the more specific selectors it shares a key with.

        Pillar A of the 0.4 plan, fifth slice — 586 `no-descending-
        specificity` findings on the shelf, two publisher templates
        carrying most of them. The gate's own reading of the rule was
        probed and calibrated to the finding (586 of 586 reproduced,
        zero books divergent): selectors are compared per *key* — the
        last compound with its pseudo-classes stripped, exact string —
        within one top-level context, per occurrence, and only strict
        descents count.

        The move itself is where the proof lives. The flagged pair is
        never the risk: its two selectors *differ* in specificity, so
        their mutual order decides no winner. The risk is everything the
        mover crosses — jumped top-level rules, and the rules **inside**
        any at-rule on the road, read but never cut: whatever the
        condition says, it turns both sides of a tie on together. An
        exact specificity **tie** with a branch of the mover is decided
        by order, and the move would flip it — unless one of three
        disproofs lands:

        * **no shared property** — order picks winners only where two
          rules fight over the same slot, shorthands included
          (`_properties_conflict` owns that reading); this is what lets
          a `margin` rule sail past a `color` tie, and past a whole
          `@media` of colors;
        * **different concrete element types** in the last compounds —
          one element cannot be both `p` and `div`;
        * **this book's documents say so** — both branches read in the
          simple descendant language (`type.class` chains), and no
          element in any document matches both. The shelf measured this
          on one template: all 310 ties dissolved, because page-type
          container classes never share an ancestry path. The same
          philosophy the unreachable sweep already uses: ask the book,
          not the grammar.

        A branch beyond the simple language blocks its tie (nothing to
        disprove with), and a refused pair stays refused — counted, not
        retried. Renaming changes no specificity and the
        post-translation merge only deletes rules, so this pass does not
        run again after translation. Behind the sweep's opt-out.
        """
        cache: dict = {}

        def infos_of(text, spans):
            return [
                (span, [(b, _nds_key(b), _selector_specificity(b))
                        for b in span.selectors])
                for span in spans
            ]

        def descending_count(infos) -> int:
            count = 0
            seen: dict = {}
            for _, branches in infos:
                for _, key, spec in branches:
                    count += sum(1 for other in seen.get(key, ()) if other > spec)
                    seen.setdefault(key, []).append(spec)
            return count

        def body_of(text, span) -> str:
            brace = text.index("{", span.start)
            return text[brace + 1:span.end - 1]

        def contested(some: dict, other: dict) -> str:
            names = sorted(
                name for name in set(some) & set(other)
                if some[name] != other[name]
            )
            if names:
                name = names[0]
                return f"{name}: {some[name]} / {other[name]}"
            return "wspólna rodzina skrótów"

        def move_blocker(text, infos, i, j):
            """None when the move is safe, else `(blocking selector,
            contested property)` — the sentence a question needs.
            Every rule the mover crosses is a potential tie partner —
            the jumped top-level rules, and the rules *inside* any
            at-rule standing on the road. Reading an at-rule is not
            cutting one: whatever its condition, it turns both sides
            of a tie on together or off together."""
            mover_branches = infos[j][1]
            mover_props = _declared_values(body_of(text, infos[j][0]))
            partners = [
                (infos[t][1], _declared_values(body_of(text, infos[t][0])),
                 infos[t][0].selector)
                for t in range(i, j)
            ]
            crossed = text[infos[i][0].start:infos[j][0].start]
            partners.extend(
                ([(b, _nds_key(b), _selector_specificity(b))
                  for b in [part.strip() for part in selector.split(",") if part.strip()]],
                 _declared_values(body), f"@… {selector}")
                for selector, body in stylesheet.conditional_rules(crossed)
            )
            for partner_branches, partner_props, partner_name in partners:
                # A tie is decided by order only where the two rules fight
                # over a property with different values — disjoint or
                # agreeing declarations have no winner for order to flip.
                if not _properties_conflict(partner_props, mover_props):
                    continue
                for branch_t, _, spec_t in partner_branches:
                    for branch_r, _, spec_r in mover_branches:
                        if spec_t != spec_r:
                            continue
                        type_t, type_r = _last_type(branch_t), _last_type(branch_r)
                        if type_t and type_r and type_t != type_r:
                            continue
                        chain_t = _simple_chain(branch_t)
                        chain_r = _simple_chain(branch_r)
                        if chain_t is None or chain_r is None:
                            return (partner_name,
                                    contested(mover_props, partner_props))
                        if self._element_hits(ctx, branch_t, chain_t, cache) \
                                & self._element_hits(ctx, branch_r, chain_r, cache):
                            return (partner_name,
                                    contested(mover_props, partner_props))
            return None

        spans = stylesheet.top_level_rules(css_text)
        infos = infos_of(css_text, spans)
        found = descending_count(infos)
        if not found:
            return css_text
        if not ctx.policy.sweep_style_blocks:
            self.note(ctx, Level.INFO, "css.specificity-found",
                      values={"count": found}, location=resource.path)
            return css_text

        original = css_text
        refused: set = set()
        approved_ties: set = set()
        resolved_moves = 0
        moves = 0
        current = found
        cap = 2 * len(spans) + 10
        progress = True
        while progress and moves < cap:
            progress = False
            spans = stylesheet.top_level_rules(css_text)
            infos = infos_of(css_text, spans)
            for j, (mover, mover_branches) in enumerate(infos):
                offenders = [
                    i for i in range(j)
                    if any(key_i == key_j and spec_i > spec_j
                           for _, key_i, spec_i in infos[i][1]
                           for _, key_j, spec_j in mover_branches)
                ]
                if not offenders:
                    continue
                # The topmost offender, and only that: landing above it
                # is an insertion sort's insertion. A "better than
                # nothing" landing below a blocking tie was tried and
                # measured — it mints new inversions against everything
                # lower-specificity it flies over, and the probe book
                # came out *worse* (83 findings kept became 108, at 332
                # moves against 10).
                top = offenders[0]
                target = infos[top][0]
                signature = (css_text[mover.start:mover.end],
                             css_text[target.start:target.end])
                if signature in refused:
                    continue
                blocker = move_blocker(css_text, infos, top, j)
                if blocker is not None:
                    # D-037: a tie the prover cannot dissolve becomes a
                    # person's question. The monotone guard below still
                    # gates an approved move — the option text promises
                    # exactly that.
                    question = Question(
                        kind=STYLE,
                        where=resource.path,
                        summary=say("style.tie.summary",
                                    selector=mover.selector),
                        detail=say("style.tie.detail", where=resource.path,
                                   selector=mover.selector,
                                   target=target.selector,
                                   blocker=blocker[0], contest=blocker[1]),
                        options=(
                            Option(KEEP, say("style.tie.keep"),
                                   say("style.tie.keep.why")),
                            Option("move", say("style.tie.move"),
                                   say("style.tie.move.why",
                                       blocker=blocker[0])),
                        ),
                        recommended=KEEP,
                        reversible=False,
                        risk=Risk.APPEARANCE,
                        group="style:tie",
                        subject=mover.selector,
                    )
                    if ctx.decide(question).option != "move":
                        refused.add(signature)
                        continue
                    approved_ties.add(signature)
                moved_text = css_text[mover.start:mover.end]
                remainder = (
                    css_text[target.start:mover.start] + css_text[mover.end:]
                )
                candidate = (
                    css_text[:target.start]
                    + moved_text.rstrip() + "\n"
                    + remainder.lstrip("\n")
                )
                # A move earns its keep by the gate's own count: accepted
                # only when the sheet's descending pairs strictly drop.
                # Convergence used to rest on the insertion argument alone,
                # and the shelf broke it the day the value-aware conflicts
                # allowed more moves — a lawful move fixed its pair and
                # minted refused ones, 83 findings became 95. Monotone
                # descent cannot regress by construction.
                candidate_count = descending_count(
                    infos_of(candidate, stylesheet.top_level_rules(candidate))
                )
                if candidate_count >= current:
                    refused.add(signature)
                    continue
                css_text = candidate
                current = candidate_count
                moves += 1
                if signature in approved_ties:
                    resolved_moves += 1
                progress = True
                break
        if not moves:
            self.note(ctx, Level.PRESERVED, "css.specificity-kept",
                      values={"count": found}, location=resource.path)
            return original
        # The reorder's own invariant: the same rules, to the byte, just
        # elsewhere. A move that loses, grows or rewrites a rule is not a
        # move, whatever else it is.
        final_spans = stylesheet.top_level_rules(css_text)
        original_spans = stylesheet.top_level_rules(original)
        if not _structurally_sound(css_text) or sorted(
            css_text[s.start:s.end].strip() for s in final_spans
        ) != sorted(original[s.start:s.end].strip() for s in original_spans):
            self.note(ctx, Level.WARN, "css.specificity-unverified",
                      values={"count": moves}, location=resource.path)
            return original
        if moves - resolved_moves:
            self.note(ctx, Level.FIX, "css.specificity-reordered",
                      values={"count": moves - resolved_moves},
                      location=resource.path)
        if resolved_moves:
            self.note(ctx, Level.FIX, "css.specificity-resolved",
                      values={"count": resolved_moves}, location=resource.path)
            self.changed(
                ctx, Action.MOVED, resource.path,
                before=f"{resolved_moves} rule(s) held below their place by a tie the book confirms",
                after="moved past the contested road, on a person's word; the gate's count strictly fell",
                automation=Automation.ASKED,
                risk=Risk.APPEARANCE, reversible=False,
                rule="css.specificity-resolved",
            )
        remaining = descending_count(infos_of(css_text, final_spans))
        if remaining:
            self.note(ctx, Level.PRESERVED, "css.specificity-kept",
                      values={"count": remaining}, location=resource.path)
        self.changed(
            ctx, Action.MOVED, resource.path,
            before=f"{moves} rule(s) standing below a more specific selector sharing their key",
            after="moved above it; every order-decided winner was proved unchanged, by type or by this book's documents",
            risk=Risk.NONE, reversible=False,
            rule="css.specificity-reordered",
        )
        return css_text

    def _element_hits(self, ctx: Context, branch: str, chain, cache) -> frozenset:
        """Which elements of this book the simple branch *chain* matches.

        Identity is `(document path, XPath)` and not `id()`, and that is a
        lesson, not a style choice: lxml hands out **proxy objects** made
        fresh on every access, so two walks over one tree never produce
        the same `id()` twice — an intersection of ids is empty by
        construction, and a guard built on it approves every move it was
        meant to block. Caught by the tie-confirming test the day it was
        written.
        """
        hits = cache.get(branch)
        if hits is not None:
            return hits
        found = set()
        for resource in ctx.book.content_docs():
            root = ctx.parsed(resource).root
            tree = root.getroottree()
            for element in root.iter():
                if not isinstance(element.tag, str):
                    continue
                if not _compound_matches(element, chain[-1]):
                    continue
                needed = list(chain[:-1])
                node = element.getparent()
                while needed and node is not None:
                    if _compound_matches(node, needed[-1]):
                        needed.pop()
                    node = node.getparent()
                if not needed:
                    found.add((resource.path, tree.getpath(element)))
        hits = frozenset(found)
        cache[branch] = hits
        return hits

    def _empty_noise(self, ctx: Context, css_text: str, resource) -> str:
        """Remove what says nothing: empty comments, empty rules, empty at-rules.

        Pillar A of the 0.4 plan, third slice — 1 982 `/**/` and 71 empty
        blocks on the shelf's lint baseline, most of them Word's. An empty
        comment carries no note of the publisher's (a comment with words in
        it is one, and stays); an empty rule declares nothing; an empty
        at-rule selects nothing. Every parser was already ignoring all
        three. Strings pass whole — `content: "/**/"` is content — because
        the walk is the stylesheet module's, not a regex. Behind the
        sweep's opt-out, like the rest of the family.
        """
        stripped, comments, at_rules = stylesheet.strip_empty_noise(css_text)
        spans = stylesheet.top_level_rules(stripped)
        empty_spans = [
            span for span in spans
            if not stripped[stripped.index("{", span.start) + 1:span.end].strip("} \t\r\n")
        ]
        total = comments + at_rules + len(empty_spans)
        if not total:
            return css_text
        if not ctx.policy.sweep_style_blocks:
            self.note(ctx, Level.INFO, "css.empty-noise-found",
                      values={"count": total}, location=resource.path)
            return css_text
        cleaned = stylesheet.without(stripped, empty_spans) if empty_spans else stripped
        if not _structurally_sound(cleaned) or (
            len(stylesheet.top_level_rules(cleaned)) != len(spans) - len(empty_spans)
        ):
            self.note(ctx, Level.WARN, "css.empty-noise-unverified",
                      values={"count": total}, location=resource.path)
            return css_text
        self.note(ctx, Level.FIX, "css.empty-noise-removed",
                  values={"count": total, "comments": comments,
                          "rules": len(empty_spans) + at_rules},
                  location=resource.path)
        self.changed(
            ctx, Action.REMOVED, resource.path,
            before=f"{total} empty comment(s), rule(s) and at-rule(s)",
            after="removed; they said nothing and every parser ignored them",
            risk=Risk.NONE, reversible=False,
            rule="css.empty-noise-removed",
        )
        return cleaned

    def _faces_that_load_nothing(self, ctx: Context, css_text: str, resource) -> str:
        """Remove `@font-face` rules with no `src` — they declare no font.

        **`src` is required.** A face without one names a family and gives no
        way to fetch it, so every parser drops the rule on the floor. The
        program already says this out loud one method along, where neutralising
        a dead url can empty a face: *a face that can load nothing is not a
        face*. This is the same sentence about a face that never had a source
        to begin with.

        **Measured, and the number is why this exists.** The shelf's largest
        remaining block of lint warnings — 48 963 of them, more than every other
        rule put together — was one obsolete descriptor, `panose-1`, and it sits
        inside exactly this kind of rule. Ten books, all of them exported from a
        word processor that writes its font table into every document:

            /* Font Definitions */
            @font-face {font-family:Helvetica; panose-1:2 11 6 4 2 2 2 2 2 4;}

        **49 177 such rules, 3.93 MB of CSS, and not one with a `src`.** In one
        book that is 68% of the file, in another 82%, and in a third the
        uncompressed rules outweigh the whole compressed book. None of it can
        render anything.

        Removing it cannot change a pixel, which is the D-029/D-030 test for
        this basket and the same argument D-039 used for a declaration written
        as an HTML attribute: no reading system has ever applied it. So it goes
        in both modes, with a line in the report, behind the sweep's own opt-out
        like the rest of the family.

        **What is deliberately not touched:** a face *with* a `src`, however
        strange — that is a font somebody meant to load. And the comment above
        the block stays; `/* Font Definitions */` is a note somebody wrote, and
        removing the rules is not a reason to remove the note.
        """
        faces = stylesheet.at_rules(css_text, "font-face")
        if not faces:
            return css_text
        empty = [
            face for face in faces
            if not _DECLARES_SRC.search(stylesheet.body_of(css_text, face))
        ]
        if not empty:
            return css_text
        if not ctx.policy.sweep_style_blocks:
            self.note(ctx, Level.INFO, "css.faces-without-src-found",
                      values={"count": len(empty)}, location=resource.path)
            return css_text
        cleaned = stylesheet.without(css_text, empty)
        # The same guard the rest of the family uses, and it earns its keep
        # here: these rules come in their thousands, and a walk that miscounted
        # one brace would take a stylesheet apart.
        if not _structurally_sound(cleaned) or len(
            stylesheet.at_rules(cleaned, "font-face")
        ) != len(faces) - len(empty):
            self.note(ctx, Level.WARN, "css.faces-without-src-unverified",
                      values={"count": len(empty)}, location=resource.path)
            return css_text
        self.note(ctx, Level.FIX, "css.faces-without-src-removed",
                  values={"count": len(empty)}, location=resource.path)
        self.changed(
            ctx, Action.REMOVED, resource.path,
            before=f"{len(empty)} @font-face rule(s) with no src",
            after="removed; a face that names no file cannot load one",
            risk=Risk.NONE, reversible=False,
            rule="css.faces-without-src-removed",
        )
        return cleaned

    def _page_plumbing(self, ctx: Context, css_text: str, resource) -> str:
        """Remove Word's `page: SectionN` declarations — print plumbing, not style.

        Pillar 2 of the 0.3 plan; the owner's decision in the D-031
        conversation was one word: eliminate.
        The `page` property selects a named `@page` box for paged media; in
        reflowing text every reading system ignores it, so removing it cannot
        change a pixel — which the render gate still verifies per book, as it
        does for everything. A rule left empty by the removal goes whole.

        Three deliberate boundaries: a **pre-paginated** publication keeps it
        (there the property is in its element); the same opt-out as the sweep
        (`--keep-style-junk`, the window's tick) keeps it and only counts; and
        `@page` *definitions* are not entered — at-rules stay untouched here
        as everywhere in this stage, orphaned or not. No scripted-book guard,
        on purpose: the sweep's guard exists because a script can add a class
        and change what is *dead*, but no script can make `page:` mean
        something in reflow.
        """
        found = list(_PAGE_PLUMBING_RE.finditer(css_text))
        if not found:
            return css_text
        if ctx.book.rendition.get("layout") == "pre-paginated":
            return css_text
        if not ctx.policy.sweep_style_blocks:
            self.note(ctx, Level.INFO, "css.page-plumbing-found",
                      values={"count": len(found)}, location=resource.path)
            return css_text
        cleaned = _PAGE_PLUMBING_RE.sub(lambda m: m.group("lead"), css_text)
        rules_before = len(stylesheet.top_level_rules(css_text))
        emptied = [
            span for span in stylesheet.top_level_rules(cleaned)
            if not cleaned[cleaned.index("{", span.start) + 1:span.end].strip("} \t\r\n")
        ]
        if emptied:
            cleaned = stylesheet.without(cleaned, emptied)
        if not _structurally_sound(cleaned) or (
            len(stylesheet.top_level_rules(cleaned)) != rules_before - len(emptied)
        ):
            self.note(ctx, Level.WARN, "css.page-plumbing-unverified",
                      values={"count": len(found)}, location=resource.path)
            return css_text
        self.note(ctx, Level.FIX, "css.page-plumbing-removed",
                  values={"count": len(found), "rules": len(emptied)},
                  location=resource.path)
        self.changed(
            ctx, Action.REMOVED, resource.path,
            before=f"{len(found)} print-plumbing declaration(s) `page: …`",
            after="removed; no reading system applies them to reflowing text",
            risk=Risk.NONE, reversible=False,
            rule="css.page-plumbing-removed",
        )
        return cleaned

    def _add_watermark_rule(self, ctx: Context) -> None:
        """Define, once, the class the content stage put on watermark markers."""
        for path in sorted(ctx.watermark_stylesheets):
            sheet = ctx.book.get(path)
            if sheet is None or watermark.MARKER_CLASS in sheet.text():
                continue
            sheet.data = sheet.data + watermark.MARKER_RULE.encode("utf-8")

    def _rewrite_urls(self, ctx: Context, css_text: str, source_path: str, current_path: str) -> tuple[str, int]:
        unresolved = 0

        def replace(match: re.Match) -> str:
            nonlocal unresolved
            raw = match.group(2).strip()
            if not raw or paths.is_remote(raw) or raw.startswith("#"):
                return match.group(0)
            target = paths.resolve(source_path, raw)
            new_target = ctx.path_map.get(target) if target else None
            if new_target is None:
                unresolved += 1
                return match.group(0)
            return f'url("{paths.relative(current_path, new_target)}")'

        rewritten = re.sub(r"url\(\s*(['\"]?)(.*?)\1\s*\)", replace, css_text, flags=re.IGNORECASE)

        def replace_import(match: re.Match) -> str:
            nonlocal unresolved
            raw = match.group(2)
            target = paths.resolve(source_path, raw)
            new_target = ctx.path_map.get(target) if target else None
            if new_target is None:
                unresolved += 1
                return match.group(0)
            return f'@import "{paths.relative(current_path, new_target)}"'

        rewritten = re.sub(r'@import\s+(["\'])(.*?)\1', replace_import, rewritten, flags=re.IGNORECASE)
        return rewritten, unresolved

    #: Properties whose value is a comma-separated list where a `url()` is one
    #: candidate among several. A dead entry is dropped *from the list*; the
    #: keyword `none` would not be valid in either of them.
    _URL_LISTS = frozenset({"src", "cursor"})

    def _neutralise_dead_urls(
        self, ctx: Context, css_text: str, source_path: str, current_path: str, resource
    ) -> tuple[str, int]:
        """Strict mode: make a stylesheet's references to absent files stop
        being errors, the way the content stage already does for documents.

        **F-017.** Strict neutralises a dead `href` in a document and left a
        dead `url()` in a stylesheet exactly as it found it — so a book whose
        `@font-face` names a font the archive does not contain could not be made
        conformant, and after 0.2.23 put a publication gate in front of strict,
        could not be published either. Two of the twelve public corpus books.

        What "neutralise" means depends on the property, and the difference is
        not cosmetic:

        * `src` and `cursor` take a **list** of candidates. The dead one is
          dropped and the rest are kept, which is the whole point of a fallback
          list; `none` is not a value either property accepts. A declaration
          left with an empty list goes, and an `@font-face` left with no `src`
          goes with it — a face that can load nothing is not a face.
        * everywhere else the value is a single image, and `none` is exactly
          what "there is no image here" is spelled. `background-image: none`
          renders what a broken url rendered, and says so.

        The rewrite is checked by re-parsing: a sheet this cannot re-parse is
        put back untouched, the same guard the dead-rule removal uses. A repair
        that breaks the stylesheet is worse than the error it repaired.
        """
        before = css_text
        neutralised = 0

        def dead(raw: str) -> bool:
            """Whether this reference reaches nothing, asked of *both* layouts.

            `_rewrite_urls` has already run, so a live reference in this text is
            relative to where the stylesheet has moved *to*, and a dead one is
            still the publisher's original relative to where it came *from*.
            Asking only the second question — which the first version of this
            did — reports every successfully repointed url as dead, and takes a
            whole `@font-face` away because its surviving source now looks
            unreachable. Caught by the fallback-list fixture, which is why that
            fixture exists.
            """
            raw = raw.strip()
            if not raw or paths.is_remote(raw) or raw.startswith(("#", "data:")):
                return False
            repointed = paths.resolve(current_path, raw)
            if repointed and repointed in ctx.book.resources:
                return False
            original = paths.resolve(source_path, raw)
            return not original or original not in ctx.path_map

        def declaration_bounds(text: str, at: int) -> tuple[int, int]:
            start = max(text.rfind(";", 0, at), text.rfind("{", 0, at)) + 1
            end = min(
                (position for position in (text.find(";", at), text.find("}", at)) if position != -1),
                default=len(text),
            )
            return start, end

        while True:
            found = None
            for match in re.finditer(r"url\(\s*(['\"]?)(.*?)\1\s*\)", css_text, flags=re.IGNORECASE):
                if dead(match.group(2)):
                    found = match
                    break
            if found is None:
                break

            start, end = declaration_bounds(css_text, found.start())
            declaration = css_text[start:end]
            prop = declaration.split(":", 1)[0].strip().lower()

            if prop in self._URL_LISTS:
                # Drop this candidate, keep the others.
                _, _, value = declaration.partition(":")
                survivors = [
                    part.strip()
                    for part in _split_top_level(value)
                    if not (
                        (inner := re.search(r"url\(\s*(['\"]?)(.*?)\1\s*\)", part, re.IGNORECASE))
                        and dead(inner.group(2))
                    )
                ]
                if survivors:
                    replacement = f"{prop}: {', '.join(survivors)}"
                    css_text = css_text[:start] + replacement + css_text[end:]
                else:
                    css_text = _drop_declaration(css_text, start, end, prop)
            else:
                css_text = (
                    css_text[: found.start()] + "none" + css_text[found.end() :]
                )
            neutralised += 1

        if not neutralised:
            return before, 0

        # The guard, and the reason this is safe to do with a scanner rather
        # than a full parse: whatever came out has to still be a stylesheet.
        if not _structurally_sound(css_text):
            self.note(
                ctx,
                Level.PRESERVED,
                "css.dead-url-kept",
                values={"count": neutralised},
                location=resource.path,
            )
            return before, 0

        self.note(
            ctx,
            Level.FIX,
            "css.dead-url-neutralised",
            values={"count": neutralised},
            location=resource.path,
        )
        self.changed(
            ctx,
            Action.REPLACED,
            resource.path,
            before=f"{neutralised} url() pointing at files not in the book",
            after="none, or dropped from the fallback list",
            risk=Risk.APPEARANCE,
            reversible=False,
            rule="css.dead-url-neutralised",
        )
        return css_text, neutralised

    def _strip_vendor_hacks(self, ctx: Context, css_text: str, resource) -> str:
        """Remove reader-specific at-rules that no EPUB 3 renderer honours."""
        hacks = re.findall(r"@(-\w+-|media\s+amzn-\w+)", css_text)
        if not hacks:
            return css_text
        if not ctx.policy.strict:
            self.note(
                ctx,
                Level.PRESERVED,
                "css.vendor-at-rule-kept",
                values={"count": len(hacks)},
                location=resource.path,
            )
            return css_text
        cleaned = re.sub(
            r"@media\s+amzn-(?:mobi|kf8)\b[^{]*\{(?:[^{}]|\{[^{}]*\})*\}",
            "",
            css_text,
            flags=re.IGNORECASE,
        )
        self.note(ctx, Level.FIX, "css.kindle-media-removed", location=resource.path)
        return cleaned

    def _repair(self, ctx: Context, css_text: str, resource) -> str:
        """Correct declarations that are simply wrong, not merely unfashionable.

        These are publisher mistakes rather than stylistic choices: the browser
        already discards them, so repairing them restores the intended layout
        instead of overriding it.
        """
        repaired = self._repair_invalid_emphasis(ctx, css_text, resource)
        repaired = self._repair_positioning(ctx, repaired, resource)
        repaired = self._repair_direction(ctx, repaired, resource)
        return repaired

    def _malformed_declarations(
        self, ctx: Context, css_text: str, resource, *, boilerplate: bool = False
    ) -> str:
        """A declaration written `property="value"`: machine junk goes the old
        way, a human-possible one becomes a question (pillar 4 of the 0.3 plan).

        From the owner's shelf, in a `<style>` block a converter wrote:
        `p.sgc-1 {text-align="center"}`. EPUBCheck answers `Token "=" not
        allowed here, expecting :` and strict will not publish the book, which
        is one of nine refusals measured on 160 books (EF-059).

        The split is the anti-flood exception the owner approved: a line in a
        **generator-signed rule** or a **stamped block** is converter output
        and takes the measured path — strict drops it (nothing any reader ever
        applied), preserve keeps it and the report says so. A line no
        generator signed *could* be a publisher's slip of the finger, and the
        owner's call was explicit: ask — enable it (the `=` becomes a `:`,
        and formatting nobody has ever seen starts applying, on a person's
        word), remove it, or leave it. Without an answer nothing changes,
        in either mode.
        """
        matches = list(_MALFORMED_DECL_RE.finditer(css_text))
        if not matches:
            return css_text
        spans = stylesheet.top_level_rules(css_text)

        def machine_made(match: "re.Match[str]") -> bool:
            if boilerplate:
                return True
            for span in spans:
                if span.start <= match.start() < span.end:
                    return any(
                        _GENERATOR_NAME.match(name)
                        for name in set(_SEL_NAME.findall(span.selector))
                    )
            return False

        machine_positions = {m.start() for m in matches if machine_made(m)}
        human = [m for m in matches if m.start() not in machine_positions]

        human_action = "keep"
        if human:
            shown = "\n".join(
                f'{m.group("prop")}="{m.group("value")}"' for m in human[:3]
            )
            question = Question(
                kind=STYLE,
                where=resource.path,
                summary=say("style.equals.summary", count=len(human)),
                detail=say("style.equals.detail", where=resource.path,
                           count=len(human), shown=shown),
                options=(
                    Option(KEEP, say("style.equals.keep"), say("style.equals.keep.why")),
                    Option("drop", say("style.equals.drop"), say("style.equals.drop.why")),
                    Option("enable", say("style.equals.enable"),
                           say("style.equals.enable.why", count=len(human))),
                ),
                recommended=KEEP,
                reversible=False,
                risk=Risk.APPEARANCE,
                group="style:equals",
                subject=f"{len(human)} declarations",
            )
            human_action = ctx.decide(question).option

        # One pass, one action per match: the human subset does what the
        # person said, the machine subset does what the mode says — and an
        # "enable" answer never switches on a generator's junk beside it.
        enabled: list[str] = []
        dropped: list[str] = []

        def repl(match: "re.Match[str]") -> str:
            if match.start() in machine_positions:
                # D-029/D-030, applied to the one case they had left behind
                # (owner, 2026-08-22: "czy po Sigilu też nie powinniśmy
                # sprzątać"). This used to hang on `remove_dead`, which is the
                # gate that divides preserve from strict over deviations **a
                # reader can see** — and a declaration written the way an HTML
                # attribute is written draws nothing anywhere, in any reader,
                # because CSS wants a colon where this has an `=`. So it is
                # not that kind of deviation: it belongs to the generator
                # basket, removed in both modes, reported, and behind the very
                # tick the rest of that sweep is behind.
                action = "drop" if ctx.policy.sweep_style_blocks else "keep"
            else:
                action = human_action
            token = f'{match.group("prop")}="{match.group("value")}"'
            if action == "enable":
                enabled.append(token)
                return f'{match.group("lead")}{match.group("prop")}: {match.group("value")};'
            if action == "drop":
                dropped.append(token)
                return match.group("lead")
            return match.group(0)

        rewritten = _MALFORMED_DECL_RE.sub(repl, css_text)
        if not enabled and not dropped:
            if human and human_action == "keep":
                self.note(ctx, Level.PRESERVED, "css.malformed-declaration-left",
                          values={"count": len(human)}, location=resource.path)
            if machine_positions:
                # Measured on the shelf, 2026-08-22: one such declaration in
                # 160 books, kept by this mode and reported nowhere at all —
                # a defect the output carries and the report did not name,
                # which is the one thing this program may never do. Whether
                # a converter's slip should also become a question is the
                # owner's call; that it must be *said* is not.
                self.note(ctx, Level.PRESERVED, "css.malformed-declaration-converter-kept",
                          values={"count": len(machine_positions)},
                          location=resource.path)
            return css_text
        # The same guard the other removals use: a repair that leaves behind
        # something which is no longer a stylesheet is worse than the error it
        # was repairing.
        if not _structurally_sound(rewritten):
            self.note(ctx, Level.PRESERVED, "css.malformed-declaration-kept",
                      values={"count": len(enabled) + len(dropped)},
                      location=resource.path)
            return css_text
        if enabled:
            self.note(ctx, Level.FIX, "css.malformed-declaration-enabled",
                      values={"count": len(enabled),
                              "names": ", ".join(sorted(set(enabled))[:3])},
                      location=resource.path)
            self.changed(
                ctx, Action.REPLACED, resource.path,
                before=", ".join(sorted(set(enabled))[:3]),
                after="the = became a :, at a person's word — the rule starts applying",
                risk=Risk.APPEARANCE, reversible=False,
                rule="css.malformed-declaration-enabled",
            )
        if dropped:
            self.note(
                ctx,
                Level.FIX,
                "css.malformed-declaration-dropped",
                values={"count": len(dropped), "names": ", ".join(sorted(set(dropped))[:3])},
                location=resource.path,
            )
            self.changed(
                ctx,
                Action.REMOVED,
                resource.path,
                before=", ".join(sorted(set(dropped))[:3]),
                after="nothing — no reader ever applied it",
                risk=Risk.NONE,
                reversible=False,
                rule="css.malformed-declaration-dropped",
            )
        if human and human_action == "keep":
            self.note(ctx, Level.PRESERVED, "css.malformed-declaration-left",
                      values={"count": len(human)}, location=resource.path)
        return rewritten

    def _repair_invalid_emphasis(self, ctx: Context, css_text: str, resource) -> str:
        """`font-style: regular` → `normal`, but only where that is the same page.

        EF-033, and the finding is subtler than the fix it corrects. `regular`
        is not a value of either property, so every parser throws the whole
        declaration away and the element **inherits**. Writing `normal` in its
        place does not restore the publisher's intent — it *overrides*, and
        override and inherit are the same thing only while the inherited value
        is already normal.

            .list { font-style: italic; }
            .list .name { font-style: regular; }   /* dropped: stays italic */

        Correct that and the names come out upright on a page that has been
        italic since the book was published. The publisher probably meant
        upright; this program does not rebuild books to what the publisher
        probably meant, it rebuilds them to what they look like (S-03).

        So the question is whether anything in this sheet could put a non-normal
        emphasis above the declaration. Nothing can: no italic, no bold, no
        shorthand carrying either — then `normal` and the inherited value agree
        for every element the selector can reach, the correction is provably
        invisible, and it is made. Something can: the sheet is left exactly as
        it is, invalid declaration and all, and the report says why. Leaving it
        costs nothing, because it was already being ignored.

        Deliberately a property of the *sheet* and not of the selector. Working
        out which elements a selector reaches means resolving the cascade across
        every document, and the answer would still be wrong the moment a second
        sheet or a `style` attribute joined in. A sheet with no emphasis in it
        anywhere cannot produce the bad case whatever the cascade does, which is
        a weaker question with an answer this program can actually stand behind.
        """
        found = len(_REGULAR_VALUE_RE.findall(css_text))
        if not found:
            return css_text
        if _INHERITABLE_EMPHASIS_RE.search(css_text):
            self.note(
                ctx,
                Level.PRESERVED,
                "css.invalid-value-inherited",
                values={"count": found},
                location=resource.path,
            )
            return css_text
        self.note(
            ctx,
            Level.FIX,
            "css.invalid-value-corrected",
            values={"count": found},
            location=resource.path,
        )
        return _REGULAR_VALUE_RE.sub(r"\1normal", css_text)

    def _absolute_font_sizes(self, ctx: Context, css_text: str, resource) -> str:
        """Report font sizes the reader's own setting cannot move, and — if asked
        — make them movable without moving them today.

        EF-029. `absolute_font_sizes` has been counted in the inventory since
        the survey existed and has never reached a report or a repair, so the
        most common piece of print-era formatting on the shelf was measured and
        never mentioned. The count is now said per file, in both modes, whether
        or not anything is going to be done about it.

        The conversion, when `--relative-units` asks for it, is to **`rem` and
        not `em`**, and that is the whole of why this is safe:

            body { font-size: 20px }      p { font-size: 16px }

        `em` resolves against the *parent*, so `16px → 1em` inside that body
        computes to 20px and the paragraph grows by a quarter. Every nesting in
        the book compounds differently, and no amount of care with the arithmetic
        fixes it, because the regex cannot see which rule ends up inside which.
        `rem` resolves against the root, does not compound, and is therefore
        exactly `size / 16` wherever it lands — identical to the pixel value at
        the default reader setting, on every rule, without knowing the cascade.

        The one case that breaks it is a sheet that pins the root itself in
        pixels: then `rem` is pinned too and the conversion buys nothing while
        still rewriting somebody's stylesheet. Those sheets are reported and
        left alone.

        Measured on Chromium 141, one page, three viewports, rather than argued:

            rem, against the render before conversion      0.000000% of pixels
            em, the same arithmetic and the other unit     0.242292% of pixels

        And the promise itself, with the reader's control moved from 16 to 24 —
        which is the reason the feature exists, so it is worth a number too:

            before conversion, reader 16 → 24             0.0000% of pixels
            after conversion,  reader 16 → 24             0.1998% of pixels

        A book that ignores the person's font setting entirely, and the same
        book following it. That second figure is not a defect: away from the
        default the page deliberately stops being identical, which is why this
        is a switch rather than a repair. The proportions the publisher chose
        survive it — every size moves by one factor.
        """
        sizes = _ABSOLUTE_FONT_SIZE_RE.findall(css_text)
        if not sizes:
            return css_text
        if not ctx.policy.relative_units:
            self.note(
                ctx,
                Level.INFO,
                "css.absolute-units",
                values={"count": len(sizes)},
                location=resource.path,
            )
            return css_text
        if _ROOT_FONT_SIZE_RE.search(css_text):
            self.note(
                ctx,
                Level.PRESERVED,
                "css.absolute-units-rooted",
                values={"count": len(sizes)},
                location=resource.path,
            )
            return css_text

        def to_rem(match: "re.Match[str]") -> str:
            size = float(match.group(1))
            if match.group(2).lower() == "pt":
                size *= _PX_PER_PT
            # Four places, and the number is not arbitrary: 16 is a power of
            # two, so every whole pixel value divides into at most four decimal
            # places and comes out **exact** — 11px is 0.6875rem and not a
            # rounding of it. Points are the only ones that can round (a point
            # is 1/12 of the base, which recurs), and there four places put the
            # error below a ten-thousandth of a character height.
            value = f"{size / _INITIAL_FONT_SIZE_PX:.4f}".rstrip("0").rstrip(".")
            return f"font-size: {value or '0'}rem"

        converted, count = _ABSOLUTE_FONT_SIZE_RE.subn(to_rem, css_text)
        self.note(
            ctx,
            Level.FIX,
            "css.absolute-units-relativised",
            values={"count": count},
            location=resource.path,
        )
        return converted

    def _repair_direction(self, ctx: Context, css_text: str, resource) -> str:
        """Drop `direction` and `unicode-bidi` where they say nothing; keep them where they do.

        `CSS-001: The "direction" property must not be included in an EPUB Style
        Sheet` — EPUB 3 bars both properties outright, because a reading system
        has to know which way the text runs before it has resolved any CSS. The
        markup says it instead: `dir` on the element, `page-progression-direction`
        on the spine.

        That makes the rule easy to satisfy and easy to satisfy wrongly. A sheet
        saying `direction: ltr` says nothing — it is the default, Word and Sigil
        write it into every book they touch, and taking it out cannot move a
        letter. A sheet saying `direction: rtl` is holding an Arabic or Hebrew
        book the right way round, and taking that out mirrors the page. Same
        rule, same message from the validator, opposite consequences.

        So the default value goes and anything else stays, reported as the
        deviation it is. Conformance does not outrank the page: a book that
        validates and reads backwards is not the better outcome.
        """
        dropped = 0
        kept: list[str] = []

        def decide(match: re.Match) -> str:
            nonlocal dropped
            space, name, value = match.group(1), match.group(2).lower(), match.group(3).strip()
            if value.lower() == _DIRECTION_DEFAULT[name]:
                dropped += 1
                # The whitespace that opened the declaration is put back and its
                # terminating `;` is not: the separator before it belongs to the
                # declaration in front, which still needs one.
                return space
            kept.append(f"{name}: {value}")
            return match.group(0)

        repaired = _DIRECTION_RE.sub(decide, css_text)
        if dropped:
            self.note(
                ctx,
                Level.FIX,
                "css.direction-default-removed",
                values={"count": dropped},
                location=resource.path,
            )
        if kept:
            self.note(
                ctx,
                Level.PRESERVED,
                "css.direction-kept",
                values={"count": len(kept), "declarations": "; ".join(sorted(set(kept))[:3])},
                location=resource.path,
            )
        return repaired

    def _unreachable_rules(self, ctx: Context, css_text: str, resource) -> str:
        """Rules for markup this book does not contain — the other half of [4].

        Polish e-book shops ship one house stylesheet into every title they
        sell, and most of it is for things the particular book has not got.
        Measured over thirty-two commercial books: **3 995 rules, 64% of all CSS
        bytes**, naming a class or id that appears in no document of the book
        they were shipped in. `td.proc4`, `td.proc5`, `td.proc10` … in a novel
        with no tables; `hr.dotted_line`, `hr.blue`, `hr.pointa` in one with no
        horizontal rules.

        None of it changes a pixel, which is exactly why removing it needs the
        care it gets here rather than the care it looks like it needs.
        `strict` removes everything dead, as it always has. `preserve` used to
        only report — D-029's recorded asymmetry — and since D-030 it runs
        **the same broom the `<style>` blocks get**: dead rules with a
        converter's name (`_GENERATOR_NAME`) go, with a report line; every
        other dead rule is kept and counted, exactly as before. The owner's
        line settles it the same way in both places: preserve keeps the book's
        layout, not the converter's litter. (The stamp bucket has no meaning
        for a sheet — a sheet is one file, not a block pasted into chapters —
        so here the broom has one bucket fewer, not a different rule.)

        Four things narrow it, and each one is a case that would otherwise be
        got wrong:

        * a selector list dies only when **every** branch does;
        * a branch naming no class and no id — a bare `p` — is never dead,
          because deciding that from a parse would put a book's whole
          running-text styling one bug away from deletion;
        * an attribute selector, a pseudo-class or a `*` is never dead, because
          what it reaches cannot be settled by name;
        * a book that carries a script is left alone entirely — a script can
          add a class, and then "matches nothing" is a statement about the file
          rather than about the reading.

        At-rules are never entered. `@media` and `@supports` say "under this
        condition", and a condition this cannot evaluate is a reason to leave
        the contents alone. That is not a formality: rebuilding these sheets
        through a CSS serialiser instead of cutting the text was measured too,
        and it dropped `@media` blocks outright in 21 of 72 stylesheets.

        Finally the cut is checked rather than trusted. The sheet is re-parsed
        and the surviving rules compared against the originals minus the ones
        marked dead; a sheet that does not match is put back untouched. On the
        shelf this was measured against, 72 of 72 matched.
        """
        spans = stylesheet.top_level_rules(css_text)
        dead = [
            span
            for span in spans
            if stylesheet.names_nothing_here(
                span.selector, ctx.used_classes, ctx.used_ids
            )
        ]
        if not dead:
            return css_text

        share = round(100 * sum(s.end - s.start for s in dead) / max(len(css_text), 1))
        if ctx.scripted:
            self.note(
                ctx,
                Level.INFO,
                "css.unreachable-rules-scripted",
                values={"count": len(dead)},
                location=resource.path,
            )
            return css_text
        if not ctx.policy.remove_dead:
            # D-030, the owner's alignment of the two brooms: in preserve the
            # sheet gets the generator-name bucket of the block sweep, behind
            # the same opt-out. Everything else dead stays counted, as always.
            used = ctx.used_classes | ctx.used_ids
            original_length = max(len(css_text), 1)
            junk = []
            if ctx.policy.sweep_style_blocks:
                junk = [
                    span for span in dead
                    if any(
                        _GENERATOR_NAME.match(n)
                        for n in set(_SEL_NAME.findall(span.selector))
                        if n not in used
                    )
                ]
            if junk:
                trimmed = stylesheet.without(css_text, junk)
                if not self._same_but_for(css_text, trimmed, junk):
                    self.note(
                        ctx,
                        Level.WARN,
                        "css.unreachable-rules-unverified",
                        values={"count": len(junk)},
                        location=resource.path,
                    )
                    junk = []
                else:
                    junk_share = round(
                        100 * sum(s.end - s.start for s in junk) / original_length
                    )
                    self.note(
                        ctx,
                        Level.FIX,
                        "css.sheet-junk-removed",
                        values={"count": len(junk), "share": junk_share, "total": len(spans)},
                        location=resource.path,
                    )
                    self.changed(
                        ctx, Action.REMOVED, resource.path,
                        before=f"{len(junk)} converter-leftover rule(s) matching nothing",
                        after="removed from the stylesheet",
                        risk=Risk.NONE, reversible=False,
                        rule="css.sheet-junk-removed",
                    )
                    css_text = trimmed
            kept = [span for span in dead if span not in junk]
            if kept:
                kept_share = round(
                    100 * sum(s.end - s.start for s in kept) / original_length
                )
                self.note(
                    ctx,
                    Level.INFO,
                    "css.unreachable-rules-found",
                    values={"count": len(kept), "share": kept_share, "total": len(spans)},
                    location=resource.path,
                )
            return css_text

        trimmed = stylesheet.without(css_text, dead)
        if not self._same_but_for(css_text, trimmed, dead):
            self.note(
                ctx,
                Level.WARN,
                "css.unreachable-rules-unverified",
                values={"count": len(dead)},
                location=resource.path,
            )
            return css_text
        self.note(
            ctx,
            Level.FIX,
            "css.unreachable-rules-removed",
            values={"count": len(dead), "share": share, "total": len(spans)},
            location=resource.path,
        )
        return trimmed

    @staticmethod
    def _same_but_for(before: str, after: str, removed: list) -> bool:
        """Did the cut take the rules it meant to, and nothing else?

        Asked of a CSS parser rather than of the code that did the cutting,
        because a scanner that is wrong about where a rule ends is wrong about
        that in both directions at once and would confirm itself happily.
        """
        marked = {_normal_selector(span.selector) for span in removed}
        try:
            was = _rule_model(before)
            now = _rule_model(after)
        except Exception:  # noqa: BLE001 — unparseable means unverifiable
            return False
        expected = Counter(
            {key: count for key, count in was.items() if key[0] not in marked}
        )
        return now == expected

    def _repair_positioning(self, ctx: Context, css_text: str, resource) -> str:
        """Report what became of out-of-flow positioning; delete it only under strict.

        The declaration itself is not the problem and never was — the problem is
        a page the reader cannot see. Where the content stage found a page whose
        whole content was pinned to the foot, it has already written an in-flow
        equivalent into that document, and this declaration is superseded: it
        loses the cascade, changes nothing, and deleting it from a shared
        stylesheet would only risk the documents nobody looked at.

        What is left is the cases no faithful translation exists for — pinned
        between top and bottom, centred, offset into a page of siblings. Those
        stay outside strict, because the alternative is deleting a layout on the
        chance that it is broken, and guessing at somebody's page is how a tool
        that means well ruins a book. They are reported so the choice is visible
        rather than silent.
        """
        matches = _OUT_OF_FLOW_RE.findall(css_text)
        if not matches:
            return css_text

        if ctx.book.rendition.get("layout") == "pre-paginated":
            self.note(
                ctx,
                Level.PRESERVED,
                "css.position-kept",
                values={"count": len(matches)},
                location=resource.path,
            )
            return css_text

        if ctx.positioning_translated:
            self.note(
                ctx,
                Level.INFO,
                "css.position-superseded",
                values={"count": len(ctx.positioning_translated)},
                location=resource.path,
            )
            return css_text

        if ctx.positioning_contained:
            # Whole-stylesheet rather than per-rule, and on purpose: the sheet is
            # shared between documents, the excision is textual, and a rule that
            # holds a caption over a picture in one chapter is the same rule
            # everywhere else. Matching selectors to elements precisely enough to
            # remove *some* of them would be a second cascade engine written to
            # justify a deletion nobody needs.
            self.note(
                ctx,
                Level.PRESERVED,
                "css.position-contained",
                values={
                    "count": len(matches),
                    "documents": len(ctx.positioning_contained),
                },
                location=resource.path,
            )
            return css_text

        if not ctx.policy.strict:
            self.note(
                ctx,
                Level.PRESERVED,
                "css.position-kept-reflowable",
                values={"count": len(matches)},
                location=resource.path,
            )
            return css_text

        repaired = _OUT_OF_FLOW_RE.sub(lambda match: match.group(1), css_text)
        self.note(
            ctx,
            Level.FIX,
            "css.position-removed",
            values={"count": len(matches)},
            location=resource.path,
        )
        return repaired

    def _vendor_properties(self, ctx: Context, css_text: str, resource) -> str:
        """Drop properties no conforming reader knows — unless a compat
        profile speaks for the readers that do.

        Only reader-specific inventions like Adobe's ``adobe-hyphenate`` are
        touched. Real vendor prefixes (``-webkit-``, ``-epub-``) are honoured
        by shipping readers and are never removed.

        D-036 replaced the old mode split (strict dropped, preserve kept
        unconditionally) with the compat module's judgement: the ``legacy``
        profile *is* the program's word for "this book is meant for RMSDK
        readers" — PocketBook among them — so protection belongs there, not
        in a mode. With the profile on, the properties stay and the report
        says for whom; without it, every conforming reader was ignoring
        them anyway, and the owner's call was one word: czystość.
        """
        found = _ADOBE_PROPERTY_RE.findall(css_text)
        if not found:
            return css_text
        names = sorted({name.lower() for _, name in found})
        if "legacy" in ctx.policy.compat_profiles:
            self.note(
                ctx,
                Level.PRESERVED,
                "css.reader-property-kept",
                values={"count": len(found), "names": ", ".join(names)},
                location=resource.path,
            )
            return css_text
        cleaned = _ADOBE_PROPERTY_RE.sub(lambda match: match.group(1), css_text)
        self.note(
            ctx,
            Level.FIX,
            "css.reader-property-removed",
            values={"count": len(found)},
            location=resource.path,
            detail=", ".join(names),
        )
        return cleaned

    def _font_stacks(self, ctx: Context, css_text: str, resource) -> str:
        """Give a font stack the generic family the font declares about itself
        — and, for faces the book does not carry, offer common knowledge
        through a question.

        A stack ending in a named font and nothing else is a real weakness:
        when the named font fails to load — and on an e-reader it often does —
        the reader falls back to whatever it likes. Calibre calls it an error
        and it is right. Three answers, in order of authority:

        * **The embedded font's own numbers.** Where the book embeds the face,
          PANOSE says what it is (:mod:`epubforge.fonts_meta`) — or, where
          the designer left PANOSE blank, the fixed-pitch flag does — and
          appending that generic is reading a declaration, not making one.
          Deterministic, no question. The whole book's `@font-face` blocks
          answer, not just this sheet's — a converter that keeps its faces in
          one sheet and its styles in another embeds them all the same.
        * **The embedded font's own name, on a person's word.** A face whose
          numbers are blank but whose own name says *Sans* or *Serif*
          (`fonts_meta.named`) has said something — in a word, which is for a
          person to confirm, not for a program to apply. The owner's rule
          (2026-09-02): everything uncertain goes through a person, this
          included. So it is a question, recommended, in the shape below.
        * **Common knowledge, on a person's word.** `"Times New Roman"` with
          nothing embedded — 41 913 of the shelf's 50 173 findings — is not in
          any table this program can read, but it is not a guess either. The
          owner delegated the design; the shape is pillar A's question rule:
          one question per generic family per file, grouped so one answer can
          stand for all of them, recommended but **never applied on its own**
          (S-05: no answer, no change). Appending is visible only on a reader
          that lacks the face, and there it moves the look toward the
          publisher's intent. An embedded face that says nothing about itself
          anywhere — TeX Gyre Heros is one — takes this road too, on its
          name: the book carries it, but what kind of face it is the book
          does not state.
        * **Nothing.** A symbol face (Wingdings) gets no question — no generic
          family draws pictures — and an unknown name stays a guess. Both are
          left alone and counted, exactly as before.
        """
        # Blank out @font-face bodies while keeping offsets stable.
        outside = _FONT_FACE_RE.sub(lambda match: " " * len(match.group()), css_text)
        embedded = self._embedded_families(ctx, css_text, resource)
        named = self._embedded_families(ctx, css_text, resource, fonts_meta.named)
        offenders: list[str] = []
        completed: list[str] = []
        edits: list[tuple[int, int, str]] = []
        # Two question queues with one shape: what the embedded font's own
        # name says, and what common knowledge says about a name.
        self_named: dict[str, list] = {}
        askable: dict[str, list] = {}

        for match in _FONT_FAMILY_RE.finditer(outside):
            families = [part.strip().strip("\"'") for part in match.group(1).split(",")]
            families = [family for family in families if family]
            if not families or families[-1].lower() in GENERIC_FAMILIES:
                continue
            verdict, generic = _stack_verdict(families, embedded, named)
            if verdict == "embedded":
                edits.append((match.end(1), match.end(1), f", {generic}"))
                completed.append(f"{families[-1]} → {generic}")
            elif verdict == "self-named":
                self_named.setdefault(generic, []).append((match, families[-1]))
            elif verdict == "well-known":
                askable.setdefault(generic, []).append((match, families[-1]))
            else:
                offenders.append(families[-1])

        approved = self._ask_about_generics(ctx, resource, self_named, askable, edits, offenders)

        for start, end, insertion in sorted(edits, reverse=True):
            css_text = css_text[:start] + insertion + css_text[end:]

        self._note_font_stacks(ctx, resource, completed, approved, offenders)
        return css_text

    def _ask_about_generics(self, ctx: Context, resource, self_named: dict, askable: dict,
                            edits: list, offenders: list) -> dict[str, int]:
        """One question per generic family per file, for both queues; an
        answer of "append" adds the edits, anything else leaves the stacks
        as they are and counts them. Returns how many were approved, by
        generic."""
        approved: dict[str, int] = {}
        queues = (
            ("style.generic.named.summary", "style.generic.named.detail", self_named),
            ("style.generic.summary", "style.generic.detail", askable),
        )
        for summary_key, detail_key, queue in queues:
            for generic in sorted(queue):
                entries = queue[generic]
                names = sorted({name for _, name in entries})
                question = Question(
                    kind=STYLE,
                    where=resource.path,
                    summary=say(summary_key, count=len(entries), generic=generic),
                    detail=say(detail_key, where=resource.path,
                               count=len(entries), generic=generic,
                               examples=", ".join(names[:4])),
                    options=(
                        Option(KEEP, say("style.generic.keep"),
                               say("style.generic.keep.why")),
                        Option("append", say("style.generic.append", generic=generic),
                               say("style.generic.append.why", generic=generic)),
                    ),
                    recommended="append",
                    reversible=True,
                    risk=Risk.APPEARANCE,
                    group=f"style:generic-{generic}",
                    subject=f"{len(entries)} declarations",
                )
                if ctx.decide(question).option == "append":
                    for match, _ in entries:
                        edits.append((match.end(1), match.end(1), f", {generic}"))
                    approved[generic] = approved.get(generic, 0) + len(entries)
                else:
                    offenders.extend(name for _, name in entries)
        return approved

    def _note_font_stacks(self, ctx: Context, resource, completed: list, approved: dict, offenders: list) -> None:
        if completed:
            self.note(
                ctx,
                Level.FIX,
                "css.font-stack-generic-added",
                values={
                    "count": len(completed),
                    "examples": ", ".join(sorted(set(completed))[:4]),
                },
                location=resource.path,
            )
        if approved:
            self.note(
                ctx,
                Level.FIX,
                "css.font-stack-generic-approved",
                values={
                    "count": sum(approved.values()),
                    "generics": ", ".join(sorted(approved)),
                },
                location=resource.path,
            )
            self.changed(
                ctx, Action.ADDED, resource.path,
                before=f"{sum(approved.values())} font stack(s) naming faces whose kind the book itself does not state, with no fallback",
                after="the generic family common knowledge assigns, appended on a person's word",
                automation=Automation.ASKED,
                risk=Risk.APPEARANCE, reversible=True,
                rule="css.font-stack-generic-approved",
            )
        if offenders:
            self.note(
                ctx,
                Level.PRESERVED,
                "css.font-stack-generic-missing",
                values={
                    "count": len(offenders),
                    "examples": ", ".join(sorted(set(offenders))[:4]),
                },
                location=resource.path,
            )

    def _embedded_families(
        self, ctx: Context, css_text: str, resource, reader=fonts_meta.classify,
    ) -> dict[str, str]:
        """`{family name: generic}` for every font the **book** embeds and reads.

        *reader* is what is asked of the font file: `fonts_meta.classify` for
        what it declares in numbers, `fonts_meta.named` for what its own name
        says in words. The whole book's stylesheets are consulted, this
        sheet's entries winning: a converter that keeps its `@font-face` in
        one sheet and its text styles in another (or in `<style>` blocks)
        embeds the font all the same, and reading only the local sheet was
        leaving the embedded answer on the table.
        """
        found = self._families_declared(ctx, css_text, resource, reader)
        for sheet in ctx.book.by_type("style"):
            if sheet.path == resource.path:
                continue
            for family, generic in self._families_declared(
                ctx, sheet.text(), sheet, reader
            ).items():
                found.setdefault(family, generic)
        return found

    def _families_declared(
        self, ctx: Context, css_text: str, sheet, reader=fonts_meta.classify,
    ) -> dict[str, str]:
        """`{family name: generic}` for the `@font-face` blocks of one sheet.

        A url is tried against the sheet's current path first, then against
        its original one, remapped — a sheet read *before* its own urls were
        rewritten still points at the old layout, and the mend order of two
        sheets must not decide whether the book's fonts are seen.
        """
        found: dict[str, str] = {}
        for block in _FONT_FACE_RE.finditer(css_text):
            body = block.group()
            name = _FONT_FAMILY_RE.search(body)
            if not name:
                continue
            family = name.group(1).strip().strip("\"'").split(",")[0].strip()
            for url in re.findall(r"url\(\s*(['\"]?)(.*?)\1\s*\)", body):
                target = paths.resolve(sheet.path, url[1])
                font = ctx.book.get(target) if target else None
                if font is None and sheet.original_path:
                    original = paths.resolve(sheet.original_path, url[1])
                    remapped = ctx.remap(original) if original else None
                    font = ctx.book.get(remapped) if remapped else None
                if font is None:
                    continue
                generic = reader(font.data)
                if generic:
                    found[family.lower()] = generic
                    break
        return found

    def _validate(self, ctx: Context, resource) -> None:
        parser = cssutils.CSSParser(raiseExceptions=False, validate=False)
        try:
            sheet = parser.parseString(resource.text(), href=resource.path)
        except Exception as exc:
            self.note(
                ctx,
                Level.WARN,
                "css.unparseable",
                values={"error": type(exc).__name__},
                location=resource.path,
            )
            return
        if not sheet.cssRules:
            self.note(ctx, Level.WARN, "css.no-usable-rules", location=resource.path)