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

#: The HTML-era shield tokens (CDO/CDC). CSS has ignored them at the top
#: level of a stylesheet since 1997; they exist to hide the sheet from
#: browsers older than that. EF-070 is what happens when a scanner forgets:
#: a `-->` in front of `@page` made the at-rule test read the prelude as an
#: ordinary selector, and an at-rule was one `without()` away from being cut
#: as if it were one.
_HTML_SHIELD = re.compile(r"<!--|-->")


def _selector_of(prelude: str) -> tuple[int, str]:
    """Where the selector really starts in *prelude*, and what it says.

    Anything before the last comment belongs to the file, not to this rule.
    Returning the offset rather than the trimmed text is what lets the caller
    cut a rule and leave the comment above it where the publisher put it.
    A shield token is skipped the same way (EF-070): it belongs to the file's
    ancient armour, never to a selector.
    """
    last = None
    for match in _COMMENT.finditer(prelude):
        last = match
    offset = last.end() if last else 0
    while True:
        tail = prelude[offset:]
        bare = tail.lstrip()
        shield = _HTML_SHIELD.match(bare)
        if not shield:
            break
        offset += (len(tail) - len(bare)) + shield.end()
    tail = prelude[offset:]
    return offset + (len(tail) - len(tail.lstrip())), " ".join(tail.split())


def strip_html_shields(text: str) -> "tuple[str, int]":
    """Remove the `<!--`/`-->` shield tokens at the top level of *text*.

    Only at the top level: inside a rule the same characters are somebody's
    content (`content: "-->"`) and are left exactly where they are, which is
    why this walks braces, strings and comments instead of substituting.
    """
    kept: list[str] = []
    cursor = 0
    depth = 0
    removed = 0
    length = len(text)
    while cursor < length:
        character = text[cursor]
        if character in "\"'" or text.startswith("/*", cursor):
            moved = _skip_noise(text, cursor)
            if moved != cursor:
                kept.append(text[cursor:moved])
                cursor = moved
                continue
        if depth == 0 and (
            text.startswith("<!--", cursor) or text.startswith("-->", cursor)
        ):
            cursor += 4 if text.startswith("<!--", cursor) else 3
            removed += 1
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth = max(0, depth - 1)
        kept.append(character)
        cursor += 1
    return "".join(kept), removed


def structurally_sound(text: str) -> bool:
    """Braces balanced, every string and comment closed — nothing else judged.

    The property each text cut in this package must preserve, and the cheap
    half of a two-part guard: a bad cut breaks *structure* (an orphaned
    brace, a string sliced open — the shelf produced both), and structure is
    checkable in one O(n) walk. Whether the text is still *grammatical* CSS
    is the expensive question, asked of cssutils exactly once per mended
    text at the end of the chain — 235 mid-chain cssutils reads were 205 of
    the 304 seconds that pushed a 135-document book over its time budget.
    """
    cursor = 0
    depth = 0
    length = len(text)
    while cursor < length:
        character = text[cursor]
        if text.startswith("/*", cursor):
            closed = text.find("*/", cursor + 2)
            if closed < 0:
                return False
            cursor = closed + 2
            continue
        if character in "\"'":
            quote = character
            cursor += 1
            while cursor < length:
                if text[cursor] == "\\":
                    cursor += 2
                    continue
                if text[cursor] == quote:
                    break
                cursor += 1
            if cursor >= length:
                return False
            cursor += 1
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth < 0:
                return False
        cursor += 1
    return depth == 0


def conditional_rules(text: str) -> "list[tuple[str, str]]":
    """`(selector, body)` of every rule nested inside an at-rule, any depth.

    Read-only, and that is the point: this module still offers no way to
    *cut* inside a condition it cannot evaluate, but a caller weighing a
    reorder needs to know what the crossed `@media` holds — a tie with a
    rule inside it is decided by order whenever the condition is on, and
    the condition being unreadable changes nothing about that. `@font-face`
    and `@page` hold declarations, not rules, and so contribute nothing.
    """
    found: list = []
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
            judged = _COMMENT.sub(" ", _HTML_SHIELD.sub(" ", prelude))
            if judged.lstrip().startswith("@"):
                interior = text[cursor + 1:end - 1]
                for span in top_level_rules(interior):
                    brace = interior.index("{", span.start)
                    found.append((span.selector, interior[brace + 1:span.end - 1]))
                found.extend(conditional_rules(interior))
            cursor = end
            prelude_start = cursor
            continue
        if character == ";":
            prelude_start = cursor + 1
        cursor += 1
    return found


def readable(text: str) -> str:
    """*text* rewritten one declaration per line, four-space indent per depth.

    A pure whitespace transform: strings and comments pass through
    verbatim (the walker skips them the way every walker here does), and
    everything else keeps its characters — only the space between them
    changes. Meant for sheets that arrive as one line, where there is no
    publisher formatting to respect; the caller decides when that is.
    """
    out: list[str] = []
    cursor = 0
    depth = 0
    length = len(text)

    def skip_space(position: int) -> int:
        while position < length and text[position] in " \t\r\n":
            position += 1
        return position

    def trim_tail() -> None:
        while out:
            stripped = out[-1].rstrip(" \t\r\n")
            if stripped:
                out[-1] = stripped
                return
            out.pop()

    cursor = skip_space(cursor)
    while cursor < length:
        character = text[cursor]
        if character in "\"'" or text.startswith("/*", cursor):
            moved = _skip_noise(text, cursor)
            if moved != cursor:
                out.append(text[cursor:moved])
                cursor = moved
                continue
        if character == "{":
            depth += 1
            trim_tail()
            out.append(" {\n" + "    " * depth)
            cursor = skip_space(cursor + 1)
            continue
        if character == ";":
            trim_tail()
            out.append(";\n" + "    " * depth)
            cursor = skip_space(cursor + 1)
            continue
        if character == "}":
            depth = max(0, depth - 1)
            trim_tail()
            out.append("\n" + "    " * depth + "}\n\n" + "    " * depth)
            cursor = skip_space(cursor + 1)
            continue
        if character in " \t\r\n":
            out.append(" ")
            cursor = skip_space(cursor)
            continue
        out.append(character)
        cursor += 1
    trim_tail()
    return "".join(out).rstrip() + "\n"


def declaration_blocks(text: str) -> "list[tuple[int, int]]":
    """Every innermost `{…}` body in *text*, at any depth, as offsets.

    `text[start:end]` is what stands between the braces, braces excluded.
    Innermost is the point: a block holding other blocks (`@media`) is a
    container, and declarations live in the leaves. Depth deliberately
    does not matter — the caller's question, which declaration wins
    *within* one block, has the same answer under any at-rule condition,
    because whatever turns the block on turns all of it on.
    """
    found: list[tuple[int, int]] = []
    stack: list[list] = []
    cursor = 0
    length = len(text)
    while cursor < length:
        character = text[cursor]
        if character in "\"'" or text.startswith("/*", cursor):
            moved = _skip_noise(text, cursor)
            if moved != cursor:
                cursor = moved
                continue
        if character == "{":
            if stack:
                stack[-1][1] = True
            stack.append([cursor + 1, False])
        elif character == "}":
            if stack:
                start, has_children = stack.pop()
                if not has_children:
                    found.append((start, cursor))
        cursor += 1
    return found


_EMPTY_AT_RULE = re.compile(r"@[A-Za-z-][^{};\"']*\{\s*\}")


def strip_empty_noise(text: str) -> "tuple[str, int, int]":
    """Remove empty comments and empty at-rules; strings pass untouched.

    `/**/` says nothing and `@media print {}` selects nothing — every parser
    was already ignoring both. Walked rather than substituted, for the same
    reason as `strip_html_shields`: `content: "/**/"` is somebody's content,
    and a blind regex would eat it. Returns the text, the comment count and
    the at-rule count; empty *ordinary* rules are the caller's business —
    they need the rule-count guard the caller already holds.
    """
    kept: list[str] = []
    cursor = 0
    comments = 0
    at_rules = 0
    length = len(text)
    while cursor < length:
        character = text[cursor]
        if character in "\"'":
            moved = _skip_noise(text, cursor)
            if moved != cursor:
                kept.append(text[cursor:moved])
                cursor = moved
                continue
        if text.startswith("/*", cursor):
            end = text.find("*/", cursor + 2)
            end = length if end < 0 else end + 2
            if text[cursor + 2:end - 2].strip():
                kept.append(text[cursor:end])
            else:
                comments += 1
            cursor = end
            continue
        if character == "@":
            matched = _EMPTY_AT_RULE.match(text, cursor)
            if matched:
                at_rules += 1
                cursor = matched.end()
                continue
        kept.append(character)
        cursor += 1
    return "".join(kept), comments, at_rules


def top_level_rules(text: str) -> list[RuleSpan]:
    """Every style rule at the top level of *text*, in source order.

    Rules nested inside an at-rule are not returned, and neither is the at-rule
    itself: this module offers no way to remove something whose condition it
    cannot read. :func:`at_rules` is how a caller asks for one it *can* read.
    """
    return [span for kind, span in _walk(text) if kind is None]


def at_rules(text: str, name: str) -> list[RuleSpan]:
    """Every top-level at-rule called *name*, with its span and its body.

    Separate from :func:`top_level_rules`, and the reason is the sentence
    above: an at-rule is a condition, and removing something whose condition
    this module cannot read would be removing on a guess. Asking for one **by
    name** is a caller saying it knows what that condition means — `@font-face`
    is not a condition at all, it is a declaration block with a required
    descriptor, and a caller can judge it.

    `span.selector` is the at-rule's prelude as written, so `@font-face` and
    `@media print` are told apart by the caller rather than here.
    """
    wanted = "@" + name.lower().lstrip("@")
    return [
        span
        for kind, span in _walk(text)
        if kind is not None and kind.lower() == wanted
    ]


def body_of(text: str, span: RuleSpan) -> str:
    """What sits between the braces of *span*, without them."""
    opening = text.index("{", span.start)
    return text[opening + 1:text.rindex("}", opening, span.end)]


def _at_sign(prelude: str) -> int:
    """Where the at-rule's `@` actually starts, past any comment in front.

    The same courtesy the selector walk pays: `/* Font Definitions */` heading
    a block of `@font-face` rules is a note somebody wrote, and removing the
    rules is not a reason to remove the note. Without this the span swallowed
    the comment and the header vanished with the first face under it.
    """
    cursor = 0
    while cursor < len(prelude):
        if prelude[cursor] in "\"'" or prelude.startswith("/*", cursor):
            moved = _skip_noise(prelude, cursor)
            if moved != cursor:
                cursor = moved
                continue
        if prelude[cursor] == "@":
            return cursor
        cursor += 1
    return len(prelude) - len(prelude.lstrip())


def _walk(text: str):
    """Every brace-delimited block at the top level, in source order.

    Yields `(at_rule_name_or_None, RuleSpan)`. One walk rather than two: the
    rules for what counts as a prelude are subtle — Word writes `--> @page …`
    and `/* Font Definitions */ @font-face …`, and both have already been
    misread once (EF-070, both of its faces) — so there is one place that can
    be got wrong and one place to fix.
    """
    spans: list = []
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
            # Comments and shield tokens are stripped before the at-rule test
            # (EF-070, both of its faces): Word writes `--> @page …` *and*
            # `/* Page Definitions */ @page …`, and a prelude that starts
            # with either is still an at-rule's, not a selector. The first
            # fix handled only the shield; the shelf then showed `@font-face`
            # behind `/* Font Definitions */` misread the same way — the test
            # must see the prelude the way a CSS parser does, noise removed.
            judged = _COMMENT.sub(" ", _HTML_SHIELD.sub(" ", prelude))
            if judged.lstrip().startswith("@"):
                # An at-rule, contents and all. Handed over whole, named by
                # its keyword so that a caller who understands that keyword can
                # act and one who does not is not tempted to.
                offset = _at_sign(prelude)
                keyword = judged.split(None, 1)[0] if judged.split() else "@"
                spans.append((
                    keyword,
                    RuleSpan(" ".join(judged.split()), prelude_start + offset, end),
                ))
                cursor = end
            else:
                # A comment sitting in front of a rule is not part of its
                # selector, and it is not necessarily about that rule either —
                # `/* Wiersze i listy */` heads a section. So it is cut out of
                # the selector and left out of the span: the rule goes, the
                # publisher's note about the section stays.
                offset, selector = _selector_of(prelude)
                if selector:
                    spans.append((None, RuleSpan(selector, prelude_start + offset, end)))
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
