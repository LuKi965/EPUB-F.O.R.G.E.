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
from ..report import Action, Level, Risk
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

#: A declaration written the way an HTML attribute is written: `text-align=
#: "center"` where CSS wants a colon. The lead is `{` or `;` on purpose — it is
#: what keeps this away from an attribute selector (`a[href="x"]`), from a
#: media query, and from an `=` inside a `url()` string, none of which can be
#: preceded by the start of a declaration.
_MALFORMED_DECL_RE = re.compile(
    r"(?P<lead>[{;]\s*)(?P<prop>-?[A-Za-z][A-Za-z0-9-]*)\s*=\s*"
    r"(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)\s*;?"
)

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

def _parses_as_css(css_text: str) -> bool:
    """Whether cssutils can still read this. The guard on any text surgery."""
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

    def _mend(
        self,
        ctx: Context,
        css_text: str,
        source_path: str,
        resource,
        unresolved: int,
        *,
        sweep_unreachable: bool = True,
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
        if unresolved and ctx.policy.remove_dead:
            css_text, neutralised = self._neutralise_dead_urls(
                ctx, css_text, source_path, resource.path, resource
            )
            unresolved -= neutralised
        css_text = self._strip_vendor_hacks(ctx, css_text, resource)
        css_text = self._repair(ctx, css_text, resource)
        css_text = self._malformed_declarations(ctx, css_text, resource)
        css_text = self._absolute_font_sizes(ctx, css_text, resource)
        css_text = self._vendor_properties(ctx, css_text, resource)
        if sweep_unreachable:
            css_text = self._unreachable_rules(ctx, css_text, resource)
        css_text = self._font_stacks(ctx, css_text, resource)
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
                    stamped[b" ".join(found.group(1).split())] += 1

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
                )
                if ctx.policy.sweep_style_blocks:
                    key = b" ".join(before.encode("utf-8", "replace").split())
                    after = self._sweep_style_block(
                        ctx, after, resource, boilerplate=stamped.get(key, 0) >= 3
                    )
                if after != before:
                    element.text = after
                    touched = True
            if touched:
                resource.data = xhtml.serialize(root)

    @staticmethod
    def _one_edit_away(dead: str, used: "set[str]") -> "tuple[str, int] | None":
        """The used name closest to *dead*, if any is close enough to be a typo.

        Distance 1, or 2 for names of eight characters and more — tight on
        purpose. A looser cap would call Google Docs' `lst-kix_list_1-3` a typo
        of `lst-kix_list_1-0`, which it is not; those never reach this check
        anyway (generator-named), but the cap should not depend on that.
        """
        best = None
        for candidate in used:
            cap = 1 if min(len(dead), len(candidate)) < 8 else 2
            if abs(len(dead) - len(candidate)) > cap:
                continue
            previous = list(range(len(candidate) + 1))
            for row, a in enumerate(dead, 1):
                current = [row]
                for col, b in enumerate(candidate, 1):
                    current.append(min(previous[col] + 1, current[-1] + 1,
                                       previous[col - 1] + (a != b)))
                previous = current
            distance = previous[-1]
            if 0 < distance <= cap and (best is None or distance < best[1]):
                best = (candidate, distance)
        return best

    def _sweep_style_block(
        self, ctx: Context, css_text: str, resource, *, boilerplate: bool
    ) -> str:
        """The unreachable-rule sweep, for one `<style>` block, three buckets.

        D-028. The sheet sweep removes every rule that names nothing in the
        book; this one is narrower on purpose, because the owner's rule about
        removal draws the line at *significant* changes versus code errors
        (D-026), and a `<style>` block is where the two meet. So:

        * a rule whose dead name is a **converter's** (`_GENERATOR_NAME`), or
          whose whole block is boilerplate pasted into three or more documents
          of this book, is a code error and goes — with a report line;
        * a rule whose dead name is one edit away from a name the book **uses**
          may be a human's typo, and only a human can tell — it becomes a
          question (keep / drop / correct to the used name), and nothing
          happens without an answer;
        * anything else dead is kept and counted, because a list of generator
          prefixes is safe only while matching none of them means keeping.

        The same guards as the sheet sweep, in the same order: a scripted book
        is left alone entirely, `preserve` reports instead of removing, and the
        cut is verified by re-parsing before it is kept.
        """
        from ..decisions import KEEP, STYLE, Option, Question
        from ..question_texts import say

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
        if not ctx.policy.remove_dead:
            self.note(ctx, Level.INFO, "css.unreachable-rules-found",
                      values={"count": len(dead), "share": share, "total": len(spans)},
                      location=resource.path)
            return css_text

        used = ctx.used_classes | ctx.used_ids
        #: `(span, action, replacement)`; applied back to front so offsets hold.
        surgery: list = []
        typos: list[str] = []
        unmatched = 0
        for span in dead:
            missing = {n for n in set(_SEL_NAME.findall(span.selector)) if n not in used}
            generator_named = any(_GENERATOR_NAME.match(n) for n in missing)
            near = None
            if not boilerplate and not generator_named:
                for name in sorted(missing):
                    found = self._one_edit_away(name, used)
                    if found:
                        near = (name, *found)
                        break
            if near:
                dead_name, near_name, distance = near
                rule_text = css_text[span.start:span.end].strip()
                question = Question(
                    kind=STYLE,
                    where=resource.path,
                    summary=say("style.typo.summary", dead=dead_name, near=near_name),
                    detail=say("style.typo.detail", where=resource.path,
                               rule=rule_text[:400], dead=dead_name,
                               near=near_name, distance=distance),
                    options=(
                        Option(KEEP, say("style.typo.keep"), say("style.typo.keep.why")),
                        Option("drop", say("style.typo.drop"), say("style.typo.drop.why")),
                        Option("rename", say("style.typo.rename", near=near_name),
                               say("style.typo.rename.why", near=near_name)),
                    ),
                    recommended=KEEP,
                    reversible=False,
                    risk=Risk.APPEARANCE,
                    group="style:typo",
                    subject=f"{dead_name}~{near_name}",
                )
                answer = ctx.decide(question)
                if answer.option == "drop":
                    surgery.append((span, "drop", ""))
                elif answer.option == "rename":
                    surgery.append((span, "rename",
                                    css_text[span.start:span.end].replace(dead_name, near_name)))
                else:
                    typos.append(f".{dead_name} ~ .{near_name}")
            elif boilerplate or generator_named:
                surgery.append((span, "drop", ""))
            else:
                unmatched += 1

        dropped = sum(1 for _, action, _ in surgery if action == "drop")
        renamed = sum(1 for _, action, _ in surgery if action == "rename")
        if surgery:
            result = css_text
            for span, action, replacement in sorted(surgery, key=lambda s: -s[0].start):
                result = result[:span.start] + replacement + result[span.end:]
            # One verification for the whole surgery: the result must still be
            # a stylesheet, and must hold exactly the rules that were not cut.
            # `_same_but_for` cannot serve here — it verifies removals only,
            # and a rename is not a removal.
            if not _parses_as_css(result) or (
                len(stylesheet.top_level_rules(result)) != len(spans) - dropped
            ):
                self.note(ctx, Level.WARN, "css.unreachable-rules-unverified",
                          values={"count": dropped + renamed}, location=resource.path)
            else:
                css_text = result
                if dropped:
                    self.note(ctx, Level.FIX, "css.style-junk-removed",
                              values={"count": dropped, "share": share, "total": len(spans)},
                              location=resource.path)
                    self.changed(
                        ctx, Action.REMOVED, resource.path,
                        before=f"{dropped} converter-leftover rule(s) matching nothing",
                        after="removed from the document's <style> block",
                        risk=Risk.NONE, reversible=False,
                        rule="css.style-junk-removed",
                    )
        if typos:
            self.note(ctx, Level.INFO, "css.style-typo-kept",
                      values={"count": len(typos), "examples": ", ".join(typos[:3])},
                      location=resource.path)
        if unmatched:
            self.note(ctx, Level.INFO, "css.style-unmatched-kept",
                      values={"count": unmatched}, location=resource.path)
        return css_text

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
        if not _parses_as_css(css_text):
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

    def _malformed_declarations(self, ctx: Context, css_text: str, resource) -> str:
        """Drop a declaration written `property="value"` instead of `property: value`.

        From the owner's shelf, in a `<style>` block a converter wrote:
        `p.sgc-1 {text-align="center"}`. EPUBCheck answers `Token "=" not
        allowed here, expecting :` and strict will not publish the book, which
        is one of nine refusals measured on 160 books (EF-059).

        **Dropped rather than corrected, and the choice is the careful one.**
        Every reader already discards this declaration, so removing it changes
        nothing anybody has ever seen; turning the `=` into a `:` would start
        centring text that has never been centred. Which of the two the
        publisher wanted is a question about their intent, not a fact about the
        file — the same shape as D-022, where the answer that changes nothing is
        what happens when nobody is there to ask.

        Gated on `remove_dead` for the same reason `_neutralise_dead_urls` is:
        `preserve` keeps the book as the publisher wrote it and says so in the
        report, `strict` was chosen by somebody who wants a file that conforms.
        """
        if not ctx.policy.remove_dead:
            return css_text
        dropped: list[str] = []

        def cut(match: "re.Match[str]") -> str:
            dropped.append(f'{match.group("prop")}="{match.group("value")}"')
            return match.group("lead")

        rewritten = _MALFORMED_DECL_RE.sub(cut, css_text)
        if not dropped:
            return css_text
        # The same guard the other removals use: a repair that leaves behind
        # something which is no longer a stylesheet is worse than the error it
        # was repairing.
        if not _parses_as_css(rewritten):
            self.note(
                ctx,
                Level.PRESERVED,
                "css.malformed-declaration-kept",
                values={"count": len(dropped)},
                location=resource.path,
            )
            return css_text
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
        `preserve` reports and keeps; `strict` removes. That split was written
        into the roadmap before any of this existed, against a source document
        that wanted the removal in `preserve` too, and the reasoning has not
        aged: a selector that matches nothing *in the documents we parsed* is
        not the same claim as a selector that matches nothing.

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
            self.note(
                ctx,
                Level.INFO,
                "css.unreachable-rules-found",
                values={"count": len(dead), "share": share, "total": len(spans)},
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
        """Report — and under strict, drop — properties no EPUB 3 reader knows.

        Only reader-specific inventions like Adobe's ``adobe-hyphenate`` are
        touched. Real vendor prefixes (``-webkit-``, ``-epub-``) are honoured by
        shipping readers and are never removed.
        """
        found = _ADOBE_PROPERTY_RE.findall(css_text)
        if not found:
            return css_text
        names = sorted({name.lower() for _, name in found})
        if not ctx.policy.strict:
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
        """Give a font stack the generic family the font declares about itself.

        A stack ending in a named font and nothing else is a real weakness: when
        the named font fails to load — and on an e-reader it often does — the
        reader falls back to whatever it likes. Calibre calls it an error and it
        is right; this tool reported it and left it alone, on the ground that
        choosing between `serif` and `sans-serif` from a font's *name* is
        guesswork.

        The premise was wrong wherever the book embeds the font. Then the answer
        is written in the font's own OS/2 table — PANOSE, ten bytes the designer
        filled in — and appending it is reading a declaration, not making one.
        See :mod:`epubforge.fonts_meta`.

        Where the font is not embedded, or will not say, nothing is added and
        the stack is reported exactly as before. That case really is a guess.
        """
        # Blank out @font-face bodies while keeping offsets stable.
        outside = _FONT_FACE_RE.sub(lambda match: " " * len(match.group()), css_text)
        embedded = self._embedded_families(ctx, css_text, resource)
        offenders: list[str] = []
        completed: list[str] = []
        edits: list[tuple[int, int, str]] = []

        for match in _FONT_FAMILY_RE.finditer(outside):
            families = [part.strip().strip("\"'") for part in match.group(1).split(",")]
            families = [family for family in families if family]
            if not families or families[-1].lower() in GENERIC_FAMILIES:
                continue
            generic = None
            # The whole stack is searched, not only its last entry: a stack is a
            # list of preferences and any one of them being an embedded font
            # settles what kind of type this is meant to be.
            for family in families:
                generic = embedded.get(family.lower())
                if generic:
                    break
            if generic:
                edits.append((match.end(1), match.end(1), f", {generic}"))
                completed.append(f"{families[-1]} → {generic}")
            else:
                offenders.append(families[-1])

        for start, end, insertion in reversed(edits):
            css_text = css_text[:start] + insertion + css_text[end:]

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
        return css_text

    def _embedded_families(self, ctx: Context, css_text: str, resource) -> dict[str, str]:
        """`{family name: generic}` for every font this sheet embeds and reads."""
        found: dict[str, str] = {}
        for block in _FONT_FACE_RE.finditer(css_text):
            body = block.group()
            name = _FONT_FAMILY_RE.search(body)
            if not name:
                continue
            family = name.group(1).strip().strip("\"'").split(",")[0].strip()
            for url in re.findall(r"url\(\s*(['\"]?)(.*?)\1\s*\)", body):
                target = paths.resolve(resource.path, url[1])
                font = ctx.book.get(target) if target else None
                if font is None:
                    continue
                generic = fonts_meta.classify(font.data)
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