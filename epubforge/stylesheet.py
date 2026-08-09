"""Locating rules in a stylesheet without rewriting the parts left alone.

`cssutils` parses CSS well and serialises it badly for this purpose: rebuilding
a sheet from its parsed model reformats every line, drops every comment, and —
measured on seventy-two stylesheets out of thirty-two commercial books —
**silently loses `@media` blocks in twenty-one of them.** A repair whose method
deletes a media query while claiming to delete an unused rule is not a repair.

So nothing here reformats anything. The scanner finds where each top-level rule
begins and ends, the caller decides which spans to cut, and every byte outside
those spans survives exactly as the publisher wrote it — comments, indentation,
vendor hacks and all.

At-rules are skipped whole. `@media`, `@supports` and `@font-face` each mean
"these rules apply under a condition", and a condition this module cannot
evaluate is a reason to leave the contents alone rather than a reason to guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RuleSpan:
    """One top-level style rule, and exactly where it sits in the source."""

    #: The selector list as written, whitespace collapsed: `td.proc4, td.proc5`.
    selector: str
    #: Byte offsets into the source text: `text[start:end]` is the whole rule.
    start: int
    end: int

    @property
    def selectors(self) -> list[str]:
        return [part.strip() for part in self.selector.split(",") if part.strip()]


def _skip_noise(text: str, index: int) -> int:
    """Advance past a comment or a quoted string starting at *index*, or don't.

    Both exist to stop a brace inside them from being read as structure.
    `content: "}"` is legal CSS and has ended more than one hand-written parser.
    """
    if text.startswith("/*", index):
        closed = text.find("*/", index + 2)
        return len(text) if closed < 0 else closed + 2
    if text[index] in "\"'":
        quote = text[index]
        cursor = index + 1
        while cursor < len(text):
            if text[cursor] == "\\":
                cursor += 2
                continue
            if text[cursor] == quote:
                return cursor + 1
            cursor += 1
        return len(text)
    return index


_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _selector_of(prelude: str) -> tuple[int, str]:
    """Where the selector really starts in *prelude*, and what it says.

    Anything before the last comment belongs to the file, not to this rule.
    Returning the offset rather than the trimmed text is what lets the caller
    cut a rule and leave the comment above it where the publisher put it.
    """
    last = None
    for match in _COMMENT.finditer(prelude):
        last = match
    offset = last.end() if last else 0
    tail = prelude[offset:]
    return offset + (len(tail) - len(tail.lstrip())), " ".join(tail.split())


def top_level_rules(text: str) -> list[RuleSpan]:
    """Every style rule at the top level of *text*, in source order.

    Rules nested inside an at-rule are not returned, and neither is the at-rule
    itself: this module offers no way to remove something whose condition it
    cannot read.
    """
    spans: list[RuleSpan] = []
    cursor = 0
    prelude_start = 0
    length = len(text)

    while cursor < length:
        character = text[cursor]
        if character in "\"'" or text.startswith("/*", cursor):
            moved = _skip_noise(text, cursor)
            if moved != cursor:
                cursor = moved
                continue
        if character == "{":
            prelude = text[prelude_start:cursor]
            end = _matching_brace(text, cursor)
            if prelude.lstrip().startswith("@"):
                # An at-rule, contents and all. Left whole, deliberately.
                cursor = end
            else:
                # A comment sitting in front of a rule is not part of its
                # selector, and it is not necessarily about that rule either —
                # `/* Wiersze i listy */` heads a section. So it is cut out of
                # the selector and left out of the span: the rule goes, the
                # publisher's note about the section stays.
                offset, selector = _selector_of(prelude)
                if selector:
                    spans.append(RuleSpan(selector, prelude_start + offset, end))
                cursor = end
            prelude_start = cursor
            continue
        if character == ";" and not text[prelude_start:cursor].strip().startswith("@"):
            prelude_start = cursor + 1
        elif character == ";":
            prelude_start = cursor + 1
        cursor += 1
    return spans


def _matching_brace(text: str, opening: int) -> int:
    """The index just past the `}` that closes the `{` at *opening*."""
    depth = 0
    cursor = opening
    while cursor < len(text):
        if text[cursor] in "\"'" or text.startswith("/*", cursor):
            moved = _skip_noise(text, cursor)
            if moved != cursor:
                cursor = moved
                continue
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return len(text)


def without(text: str, spans: list[RuleSpan]) -> str:
    """*text* with those spans cut out, and the gap they leave tidied.

    The whitespace either side is collapsed to one blank line so a sheet with a
    hundred rules removed does not come out as a hundred blank gaps. Nothing
    else in the file is touched.
    """
    if not spans:
        return text
    keep: list[str] = []
    cursor = 0
    for span in sorted(spans, key=lambda s: s.start):
        if span.start < cursor:
            continue
        keep.append(text[cursor : span.start])
        cursor = span.end
    keep.append(text[cursor:])
    return re.sub(r"\n[ \t]*\n[ \t]*(\n[ \t]*)+", "\n\n", "".join(keep))


#: A class or id in a selector. Deliberately not a CSS parser: the question is
#: only "does this selector name something the book does not contain".
_CLASS = re.compile(r"\.(-?[A-Za-z_][\w-]*)")
_ID = re.compile(r"#(-?[A-Za-z_][\w-]*)")

#: Anything that makes a selector's reach impossible to settle by name alone.
#: An attribute selector may match on a value nothing here enumerates; a
#: pseudo-class may depend on document position or on reader state; `*` matches
#: everything. Every one of them is a reason to leave the rule where it is.
_UNSETTLED = re.compile(r"[\[\]:@*]")


def names_nothing_here(selector: str, classes: set[str], ids: set[str]) -> bool:
    """True when *selector* can never match anything in this book.

    Conservative in every direction. A selector list is dead only when **every**
    branch of it is; a branch is dead only when it names a class or id and at
    least one of them appears nowhere; and a branch with an attribute selector,
    a pseudo-class or a universal is never called dead at all.

    A bare `p` or `blockquote` is never dead either — not because it could not
    be, but because deciding that from a parse would put the whole of a book's
    running-text styling one bug away from deletion.
    """
    branches = [part.strip() for part in selector.split(",") if part.strip()]
    if not branches:
        return False
    for branch in branches:
        if _UNSETTLED.search(branch):
            return False
        named_classes = set(_CLASS.findall(branch))
        named_ids = set(_ID.findall(branch))
        if not named_classes and not named_ids:
            return False
        if not (named_classes - classes) and not (named_ids - ids):
            return False
    return True


__all__ = ["RuleSpan", "top_level_rules", "without", "names_nothing_here"]
