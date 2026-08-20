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
#: catalogue can enumerate) never even reaches the judgement below.
_DECLARATION_RE = re.compile(
    r"(?<=[{;])\s*(?P<prop>[A-Za-z][A-Za-z0-9-]*)\s*:\s*(?P<value>[^;}]*?)\s*(?:;|(?=\}))"
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
        self._translate_class_names(ctx)

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
        if unresolved and ctx.policy.remove_dead:
            css_text, neutralised = self._neutralise_dead_urls(
                ctx, css_text, source_path, resource.path, resource
            )
            unresolved -= neutralised
        css_text = self._comment_shield(ctx, css_text, resource)
        css_text = self._strip_vendor_hacks(ctx, css_text, resource)
        css_text = self._repair(ctx, css_text, resource)
        css_text = self._malformed_declarations(ctx, css_text, resource, boilerplate=boilerplate)
        css_text = self._unknown_properties(ctx, css_text, resource)
        css_text = self._page_plumbing(ctx, css_text, resource)
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
            if not _parses_as_css(result) or (
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
        css_texts: list[str] = [sheet.text() for sheet in sheets]
        for document in documents:
            css_texts += [
                found.group(1).decode("utf-8", "replace")
                for found in _STYLE_TEXT.finditer(document.data)
            ]
        if any("[class" in text for text in css_texts):
            self.note(ctx, Level.INFO, "css.class-translation-attr-selector", values={})
            return

        # The census: which tags carry each class, and the order classes first
        # appear in reading order. Serialized bytes, double-quoted attributes —
        # which is what this program's own writer produces by this point.
        tags_of: dict[str, set] = {}
        first_use: list[str] = []
        for document in documents:
            for found in self._TAG_CLASS_RE.finditer(document.data):
                tag = found.group(1).decode("ascii", "replace").lower()
                for name in found.group(2).decode("utf-8", "replace").split():
                    tags_of.setdefault(name, set()).add(tag)
                    if name not in first_use and _GENERATOR_NAME.match(name):
                        first_use.append(name)
        if not first_use:
            return

        # Each class's declarations, read off every rule that names it.
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

        # Always English (D-034), whatever the window speaks: identifiers in
        # source code are international, and one spelling per book forever is
        # also one less thing a reproducible build has to pin.
        language = "en"
        used = set(tags_of) | set(ctx.used_classes)
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
        if not renames:
            return

        # Build every rewritten text first, verify, and only then commit —
        # a half-renamed book is worse than an untouched one.
        def rename_css(text: str) -> str:
            for old, new in renames.items():
                text = re.sub(r"\." + re.escape(old) + r"(?![\w-])", "." + new, text)
            return text

        new_sheets = [rename_css(text) for text in [sheet.text() for sheet in sheets]]
        for before, after in zip([sheet.text() for sheet in sheets], new_sheets):
            if len(stylesheet.top_level_rules(before)) != len(
                stylesheet.top_level_rules(after)
            ) or not _parses_as_css(after):
                self.note(ctx, Level.WARN, "css.class-translation-unverified", values={})
                return

        def rename_document(data: bytes) -> bytes:
            def attribute(match: "re.Match") -> bytes:
                tokens = match.group(1).decode("utf-8", "replace").split()
                return (
                    'class="' + " ".join(renames.get(t, t) for t in tokens) + '"'
                ).encode("utf-8")

            def tag(match: "re.Match") -> bytes:
                return self._CLASS_ATTR_RE.sub(attribute, match.group(0))

            data = self._TAG_RE.sub(tag, data)

            def block(match: "re.Match") -> bytes:
                renamed = rename_css(
                    match.group(1).decode("utf-8", "replace")
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

        for sheet, text in zip(sheets, new_sheets):
            sheet.data = text.encode("utf-8")
        for document in documents:
            document.data = rename_document(document.data)

        listed = "\n".join(f"{old} → {new}" for old, new in renames.items())
        self.note(
            ctx, Level.FIX, "css.classes-renamed",
            values={"count": len(renames), "language": language},
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

    def _comment_shield(self, ctx: Context, css_text: str, resource) -> str:
        """Strip the `<!-- … -->` wrapper an HTML-era converter left in the CSS.

        Pillar A of the 0.4 plan, first slice. The wrapper hid CSS from
        browsers that predate 1997; every CSS parser since ignores the
        `<!--`/`-->` tokens at the top level of a stylesheet, so removing
        them cannot change a parse — and leaving them is what 312 of the 314
        parse errors in the Calibre-lint baseline were. Only the leading and
        trailing shield is taken, which is the one shape the shelf measured;
        a `-->` in the middle of a sheet is somebody's content and stays.
        """
        stripped = re.sub(r"^\s*<!--", "", css_text)
        stripped = re.sub(r"-->\s*$", "", stripped)
        if stripped == css_text:
            return css_text
        if not _parses_as_css(stripped) or len(
            stylesheet.top_level_rules(stripped)
        ) != len(stylesheet.top_level_rules(css_text)):
            return css_text
        self.note(ctx, Level.FIX, "css.comment-shield-removed", location=resource.path)
        return stripped

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
        if not _parses_as_css(cleaned) or (
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
        if not _parses_as_css(cleaned) or (
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
                action = "drop" if ctx.policy.remove_dead else "keep"
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
            return css_text
        # The same guard the other removals use: a repair that leaves behind
        # something which is no longer a stylesheet is worse than the error it
        # was repairing.
        if not _parses_as_css(rewritten):
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