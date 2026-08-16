"""XHTML and CSS normalisation.

The guiding rule: a construct that is invalid in EPUB 3 but carries visual
meaning is translated into the conforming equivalent that renders the same way,
never simply deleted. ``<center>`` becomes a centred ``<div>``; ``bgcolor``
becomes ``background-color``. Only genuinely inert markup is dropped.
"""

from __future__ import annotations

import posixpath
import re

import cssutils
from lxml import etree

from .. import covers, cascade as css_cascade
from .. import paths, references, typography, watermark, xhtml
from ..report import Action, Level, Risk
from .accessibility import is_placeholder_alt
from .base import Context, Stage

cssutils.log.setLevel(50)  # cssutils logs every minor deviation at WARNING.

XHTML_NS = xhtml.XHTML_NS
EPUB_NS = xhtml.EPUB_NS
XLINK_NS = xhtml.XLINK_NS
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

#: Attributes whose values are references to other packaged resources.
REFERENCE_ATTRS = ("href", "src", "poster", "data", f"{{{XLINK_NS}}}href")

#: Attributes holding a *list* of references, which the rule above cannot read.
#:
#: `srcset="a.png 1x, a2x.png 2x"` matches none of `REFERENCE_ATTRS`, so the
#: reference rewriting never touched it: the relayout moved the files, `src` was
#: repointed at the new path and `srcset` was left naming the old one. Every
#: high-resolution image in every book with a `srcset` came out of this program
#: pointing at nothing — silently, in all three modes, and reported as a clean
#: rebuild. Found while asking why strict could not publish the gallery fixture
#: after misdirected references stopped being treated as dead ones: the two
#: errors it had left were both `srcset`, and neither was new.
REFERENCE_LISTS = ("srcset",)

#: Elements removed outright — they carry no content and no EPUB 3 equivalent.
DEAD_ELEMENTS = {"basefont", "applet", "blink", "marquee", "nobr", "spacer", "layer", "bgsound"}

#: Invalid elements replaced by a styled inline/block box that renders the same.
STYLED_REPLACEMENTS = {
    "center": ("div", "text-align: center;"),
    "tt": ("span", "font-family: monospace;"),
    "big": ("span", "font-size: larger;"),
    "strike": ("span", "text-decoration: line-through;"),
    "acronym": ("abbr", ""),
    "dir": ("ul", ""),
    "menu": ("ul", ""),
}


#: Attributes XHTML5 allows on any element. Anything outside this set, and
#: outside :data:`_ELEMENT_ATTRIBUTES` for the element carrying it, is not read
#: by any rendering engine — which is what makes removing it safe, and what
#: makes leaving it a plain `RSC-005` in the output.

def _translate_stray(tag: str, name: str, value: str) -> str:
    """The CSS a stray attribute meant, where it meant anything.

    Short and deliberately so. Two entries, both from the owner's shelf, both
    attributes that a rendering engine of the day honoured: `clear` anywhere
    other than `<br>` (which is handled above, on its own terms) and `size` on
    `<hr>`, where it set the rule's thickness. Everything else this sweep meets
    was never drawn by anything, so there is nothing to translate and dropping
    it changes no pixel.
    """
    if not value:
        return ""
    if name == "clear":
        keyword = value.lower()
        if keyword in {"left", "right", "none"}:
            return f"clear: {keyword};"
        if keyword == "all":
            return "clear: both;"
        return ""
    if name == "size" and tag == "hr":
        length = _css_length(value)
        return f"height: {length}; border: 0;" if length else ""
    return ""


_GLOBAL_ATTRIBUTES = frozenset({
    "accesskey", "autocapitalize", "autofocus", "class", "contenteditable",
    "dir", "draggable", "enterkeyhint", "hidden", "id", "inert", "inputmode",
    "is", "itemid", "itemprop", "itemref", "itemscope", "itemtype", "lang",
    "nonce", "popover", "role", "slot", "spellcheck", "style", "tabindex",
    "title", "translate",
})

#: What each element allows beyond the globals. Only the elements a book
#: actually contains; anything not named here is judged on the globals alone,
#: which is the conservative direction — an unknown element keeps everything
#: except what we can prove is junk.
_ELEMENT_ATTRIBUTES = {
    "a": {"href", "download", "hreflang", "ping", "referrerpolicy", "rel", "target", "type"},
    "area": {"alt", "coords", "download", "href", "ping", "referrerpolicy", "rel", "shape", "target"},
    "audio": {"autoplay", "controls", "crossorigin", "loop", "muted", "preload", "src"},
    "base": {"href", "target"},
    "blockquote": {"cite"},
    "button": {"disabled", "form", "formaction", "name", "type", "value"},
    "canvas": {"height", "width"},
    "col": {"span"},
    "colgroup": {"span"},
    "data": {"value"},
    "del": {"cite", "datetime"},
    "details": {"open"},
    "embed": {"height", "src", "type", "width"},
    "form": {"accept-charset", "action", "autocomplete", "enctype", "method", "name", "novalidate", "target"},
    "iframe": {"allow", "height", "loading", "name", "referrerpolicy", "sandbox", "src", "srcdoc", "width"},
    "img": {"alt", "crossorigin", "decoding", "height", "ismap", "loading", "longdesc",
            "referrerpolicy", "sizes", "src", "srcset", "usemap", "width"},
    "input": {"accept", "alt", "checked", "disabled", "form", "list", "max", "maxlength",
              "min", "name", "pattern", "placeholder", "readonly", "required", "size",
              "src", "step", "type", "value"},
    "ins": {"cite", "datetime"},
    "label": {"for"},
    "li": {"value"},
    "link": {"as", "color", "crossorigin", "href", "hreflang", "media", "referrerpolicy",
             "rel", "sizes", "type"},
    "map": {"name"},
    "meta": {"charset", "content", "http-equiv", "name", "property", "scheme"},
    "object": {"data", "form", "height", "name", "type", "usemap", "width"},
    "ol": {"reversed", "start", "type"},
    "optgroup": {"disabled", "label"},
    "option": {"disabled", "label", "selected", "value"},
    "output": {"for", "form", "name"},
    "param": {"name", "value"},
    "q": {"cite"},
    "script": {"async", "crossorigin", "defer", "integrity", "nomodule",
               "referrerpolicy", "src", "type"},
    "select": {"disabled", "form", "multiple", "name", "required", "size"},
    "source": {"height", "media", "sizes", "src", "srcset", "type", "width"},
    "style": {"media", "type"},
    "td": {"colspan", "headers", "rowspan"},
    "textarea": {"cols", "disabled", "form", "maxlength", "name", "placeholder",
                 "readonly", "required", "rows", "wrap"},
    "th": {"abbr", "colspan", "headers", "rowspan", "scope"},
    "time": {"datetime"},
    "track": {"default", "kind", "label", "src", "srclang"},
    "video": {"autoplay", "controls", "crossorigin", "height", "loop", "muted",
              "playsinline", "poster", "preload", "src", "width"},
}

#: Prefixes that carry their own vocabulary and are never this sweep's business:
#: author data, accessibility, the EPUB namespace, XML's own attributes, RDFa,
#: and scripting. Whatever a `data-` attribute means, it means it to somebody.
_KEPT_PREFIXES = ("data-", "aria-", "xml:", "epub:", "on")

#: Exact names kept on any element for the same reason as the prefixes above:
#: RDFa, which EPUB 3 allows in content documents and which a book uses to say
#: what its parts *are*. Held as exact names rather than prefixes so that
#: `relative` and `contents` are not kept by accident.
_KEPT_ANYWHERE = frozenset({
    "about", "content", "datatype", "prefix", "property", "rel", "resource",
    "rev", "typeof", "vocab",
})

#: Attributes with a CSS equivalent that survives the sweep as a declaration
#: rather than being dropped, whichever element they turn up on. A converter
#: that copies `clear` onto a `<p>` copied something that still means
#: something; losing it is losing a piece of the page.
_CARRIES_APPEARANCE = {
    "clear": lambda value: f"clear: {'both' if value == 'all' else value};",
    "size": None,  # element-specific; handled where the element is known
}

_FONT_SIZE_SCALE = {
    "1": "x-small", "2": "small", "3": "medium", "4": "large",
    "5": "x-large", "6": "xx-large", "7": "xxx-large",
}

_NCNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9._\-]*$")
_LENGTH_RE = re.compile(r"^\d+(\.\d+)?$")

#: An `@import` in either spelling — `url(…)` or a bare string — with whatever
#: media query trails it, up to the semicolon.
_IMPORT_RULE = re.compile(
    r"""@import\s+(?:url\(\s*(['"]?)(?P<url>[^'")]*)\1\s*\)|(['"])(?P<quoted>[^'"]*)\3)[^;}]*;?""",
    re.IGNORECASE,
)


def strip_remote_imports(css_text: str) -> tuple[str, int]:
    """Drop `@import` rules that fetch a stylesheet over the network.

    EPUB 3 permits exactly one kind of remote resource — a font, declared on
    its manifest item — and a stylesheet is not one. Google Docs exports every
    document with `@import url(https://themes.googleusercontent.com/…)` at the
    head of its stylesheet, and EPUBCheck rejects the publication for it.

    Nothing is lost by removing it. The sheet keeps its `font-family`
    declarations, so the reader falls back exactly as it would have: no e-reader
    is going to fetch a font from Google mid-page, and one that tried would be
    reporting the owner's reading to a third party.
    """
    dropped = 0

    def replace(match: re.Match) -> str:
        nonlocal dropped
        url = (match.group("url") or match.group("quoted") or "").strip()
        if not paths.is_remote(url):
            return match.group(0)
        dropped += 1
        return ""

    return _IMPORT_RULE.sub(replace, css_text), dropped


#: Characters of a document's own text below which a language rate is
#: arithmetic rather than evidence. The same floor `MetadataStage` uses for the
#: same question one level up, and for the same reason: a page of prose is about
#: two thousand characters, and a nav entry is eight.
ENOUGH_TEXT = 500


def _contradicted_by_text(declared: str, root) -> bool:
    """Whether this document's own text plainly refutes the language it claims.

    Only Polish, and that asymmetry is honest rather than provisional: the test
    is the frequency of letters that exist in one alphabet and not the other,
    measured at 69 per 1 000 in Polish prose against 4.4 in an English novel
    carrying one Polish quotation. There is no equivalent test for French
    against English, so a document claiming `fr` is believed — which is the
    right outcome anyway, because a wrong `fr` costs a reader far less than a
    wrong `en` on Polish text costs a listener.
    """
    if declared.split("-")[0].lower() == "pl":
        return False
    text = " ".join(root.itertext())
    return len(text) >= ENOUGH_TEXT and typography.looks_polish(text)


def _css_length(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    if value.endswith("%") and _LENGTH_RE.match(value[:-1]):
        return value
    if _LENGTH_RE.match(value):
        return f"{value}px"
    if re.match(r"^\d+(\.\d+)?(px|em|rem|pt|cm|mm|in|ex|ch|vw|vh)$", value):
        return value
    return None


def _ancestry(element) -> list[tuple[str, frozenset[str], str | None]]:
    """The element and its ancestors, as the cascade wants to see them.

    Nearest first, because that is the order inheritance resolves in: the
    closest declaration wins.
    """
    chain: list[tuple[str, frozenset[str], str | None]] = []
    current = element
    while current is not None and isinstance(current.tag, str):
        chain.append(
            (
                xhtml.local_name(current).lower(),
                frozenset((current.get("class") or "").split()),
                current.get("id"),
            )
        )
        current = current.getparent()
    return chain


#: Every class name a selector mentions. Crude by design: `.a .b > .c` yields
#: all three, and a rule that names a class anywhere is a rule about that class,
#: which is the only question asked here.
_SELECTOR_CLASS_RE = re.compile(r"\.([A-Za-z_][\w-]*)")


def _walk_style_rules(container):
    """Every style rule in a sheet, including the ones inside `@media`.

    `cascade.Cascade` skips media rules, correctly for its purpose — it resolves
    what applies now, and a media query may not. This one is asked a different
    question: *does the publisher have a rule for this class anywhere*, and a
    rule inside `@media print` is still one.
    """
    for rule in container:
        if rule.type == rule.STYLE_RULE:
            yield rule
        elif rule.type == rule.MEDIA_RULE:
            yield from _walk_style_rules(rule)


def _selector_classes(css_text: str) -> frozenset[str]:
    """Which classes this stylesheet has any rule for."""
    if not css_text or not css_text.strip():
        return frozenset()
    try:
        sheet = cssutils.parseString(css_text, validate=False)
    except Exception:  # noqa: BLE001 — an unreadable sheet defines nothing
        return frozenset()
    found: set[str] = set()
    for rule in _walk_style_rules(sheet):
        found.update(_SELECTOR_CLASS_RE.findall(rule.selectorText))
    return frozenset(found)


def _rules_naming(css_text: str, classes: set[str]) -> list[str]:
    """The rules that mention any of *classes*, as the publisher wrote them.

    Verbatim, selector list and all. A rule reading `.dropcap, .initial { … }`
    comes over whole rather than split: the text is the publisher's, and this
    repair copies it, it does not rewrite it.

    Rules inside `@media` are left where they are. Lifting one out of its query
    would apply it unconditionally, which is the opposite of what it says, and
    no book measured needed it.
    """
    if not css_text or not css_text.strip():
        return []
    try:
        sheet = cssutils.parseString(css_text, validate=False)
    except Exception:  # noqa: BLE001
        return []
    found: list[str] = []
    for rule in sheet:
        if rule.type != rule.STYLE_RULE:
            continue
        if not set(_SELECTOR_CLASS_RE.findall(rule.selectorText)) & classes:
            continue
        text = " ".join(rule.cssText.split())
        # A reference inside the rule is relative to the sheet it lived in, and
        # this text is about to live somewhere else. Rebasing it is possible and
        # is a way to turn a missing drop cap into a missing picture; on the
        # shelf this was measured against, not one case needed it.
        if "url(" in text.lower():
            continue
        found.append(text)
    return found


def _one_candidate_named(ctx, wanted: str) -> str | None:
    """The rebuilt path of the only resource whose file name matches *wanted*.

    `None` when there is none and when there are several, and those two answers
    are the same for a reason: this exists to turn a misdirected reference into
    a derivation, and a derivation with two answers is a guess. A book with
    `images/logo.png` and `chapters/logo.png` gets no repair from here.

    Compared case-insensitively, because the converters that produce this defect
    are the same ones that change a file's case on the way. The comparison is
    only ever used to *find* a candidate; the path written back is the real one.
    """
    import posixpath

    base = posixpath.basename(wanted).lower()
    if not base:
        return None
    matches = {
        new
        for old, new in ctx.path_map.items()
        if posixpath.basename(old).lower() == base
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _split_srcset(value: str) -> list[tuple[str, str]]:
    """Split a `srcset` into its `(url, descriptor)` candidates.

    Follows HTML's own algorithm rather than `split(",")`, because a URL is
    allowed to contain a comma and the naive split cuts one reference in half:
    `a,b.png 2x` is one candidate. HTML resolves the ambiguity by position — a
    comma ends a candidate only after the URL has ended, and a URL ends at the
    first space — so this reads the same way: take the run of non-space as the
    URL, then whatever runs to the next comma as the descriptor.
    """
    items: list[tuple[str, str]] = []
    index, end = 0, len(value)
    while index < end:
        while index < end and (value[index].isspace() or value[index] == ","):
            index += 1
        if index >= end:
            break
        start = index
        while index < end and not value[index].isspace():
            index += 1
        url = value[start:index]
        if url.endswith(","):
            # A comma glued to the URL ends the candidate and leaves no
            # descriptor. `a.png,b.png 2x` is two candidates, the first bare.
            items.append((url.rstrip(","), ""))
            continue
        descriptor_start = index
        while index < end and value[index] != ",":
            index += 1
        items.append((url, value[descriptor_start:index].strip()))
        index += 1
    return items


def _join_srcset(items: list[tuple[str, str]]) -> str:
    return ", ".join(url if not descriptor else f"{url} {descriptor}" for url, descriptor in items)


#: `#rgb`, `#rrggbb`, `rgb(r, g, b)` and the two names that matter. Anything
#: else returns None, which every caller reads as "cannot say" and leaves alone.
_HEX6 = re.compile(r"#([0-9a-f]{6})")
_HEX3 = re.compile(r"#([0-9a-f]{3})")
_RGB = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")


def _colour(value: str) -> "tuple[int, int, int] | None":
    said = (value or "").strip().lower()
    match = _HEX6.fullmatch(said)
    if match:
        digits = match.group(1)
        return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))
    match = _HEX3.fullmatch(said)
    if match:
        return tuple(int(c * 2, 16) for c in match.group(1))
    match = _RGB.fullmatch(said)
    if match:
        return tuple(int(part) for part in match.groups())
    return {"black": (0, 0, 0), "white": (255, 255, 255)}.get(said)


def _has_flow_text(root) -> bool:
    """Whether this document has running text — anything to lay out besides art.

    The question the cover page template has to be asked before it is used
    (EF-041). A cover page is one image; a document with a sentence in it is
    somebody's chapter, and centring it in a flex box the height of the screen
    is not a repair.

    Whitespace does not count, and neither does the `<title>` in the head: a
    cover page has a title like every other document. What counts is text a
    reader would see on the page.
    """
    body = root.find(xhtml.qname("body"))
    if body is None:
        return False
    return bool("".join(body.itertext()).strip())


def _append_style(element, declarations: str) -> None:
    if not declarations:
        return
    existing = (element.get("style") or "").strip()
    if existing and not existing.endswith(";"):
        existing += ";"
    element.set("style", f"{existing} {declarations}".strip())


class ContentStage(Stage):
    """Rebuilds every content document and rewrites its outgoing references."""

    name = "xhtml"

    def __init__(self) -> None:
        self._sheet_cache: dict[str, str] = {}
        # Which classes each sheet has a rule for. Asked once per sheet per
        # book rather than once per document: parsing a 27 kB stylesheet
        # forty-nine times to answer the same question is how a repair that
        # touches seven books in thirty-two ends up costing every book.
        self._class_cache: dict[str, frozenset[str]] = {}
        # A watermark repeats across every document, so its findings are summed
        # and reported once rather than thirty-four times.
        self._cascade_cache: dict[tuple, css_cascade.Cascade] = {}
        self._watermarks_consolidated = 0
        self._watermarks_relocated = 0
        self._watermarks_removed = 0
        self._watermark_documents = 0
        self._watermark_tokens: set[str] = set()
        self._watermark_notices: list[str] = []
        # WP-17. Kept as the sentences themselves rather than as a count: this
        # is the one switch that deletes readable text, and the report has to
        # let somebody check it rather than trust it.
        self._shop_notices_removed: list[str] = []
        self._shop_notice_documents: set[str] = set()
        # Aggregated for the same reason as the watermarks: a book whose every
        # document arrived with an empty <title> would otherwise report the
        # same sentence forty times.
        self._titles_filled = 0

    def run(self, ctx: Context) -> None:
        if not ctx.policy.rewrite_content:
            # Container-only rebuild. Parsing and reserialising a document
            # changes its bytes even when nothing about it is wrong, so the way
            # to keep that promise is not to open them at all.
            # Two exceptions, and they are the same exception twice: a legacy
            # DOCTYPE and an empty <title> each make the output an invalid
            # EPUB 3 — "Irregular DOCTYPE", "Element title must not be empty" —
            # and neither says anything about how a page looks, so neither edit
            # can change what the reader sees. Half the older books in a real
            # library carry the XHTML 1.1 DOCTYPE, and thirteen books in the
            # private corpus were failing on nothing but the title.
            #
            # Both were legal in EPUB 2. This mode does not touch content, but
            # it does rebuild the package as EPUB 3, so markup that was only
            # ever legal under the old rules stops being legal around it —
            # which makes those errors ours, not the source's.
            modernised = 0
            titled = 0
            stranded: set[str] = set()
            refused: dict[str, set[str]] = {}
            for resource in ctx.book.content_docs():
                data, changed = xhtml.modernise_doctype(resource.data)
                if changed:
                    resource.data = data
                    modernised += 1
                else:
                    unresolvable = xhtml.unresolvable_entities(resource.data)
                    if unresolvable and b"<!DOCTYPE html>" not in resource.data[:400]:
                        refused[resource.path] = unresolvable

                # Reading the ids costs a parse and changes nothing, and
                # without them the navigation stage cannot tell a live anchor
                # from a dead one — so in this mode it assumed every anchor was
                # live and left `nav.xhtml` pointing at fragments that do not
                # exist. EPUBCheck: "Fragment identifier is not defined".
                try:
                    root, _ = xhtml.parse(resource.data)
                except Exception:  # noqa: BLE001 — a document we cannot read has no ids
                    continue
                ctx.document_ids[resource.path] = {
                    element.get("id")
                    for element in xhtml.iter_elements(root)
                    if element.get("id")
                }
                # The same parse also decides the manifest properties, and this
                # mode needs them as much as any other: the package is rebuilt
                # as EPUB 3 whatever happens to the content, and EPUB 3 requires
                # a document containing SVG to say so. Calibre wraps its cover
                # in `<svg>` and writes an EPUB 2 package, where no such
                # declaration exists — so nineteen books came out of this mode
                # with "The property svg should be declared in the OPF file",
                # having gone in valid. The one mode that promises to break
                # nothing was breaking something.
                #
                # It costs nothing here: reading properties writes no bytes, and
                # the document has already been parsed a line above.
                self._properties(ctx, root, resource)

                # And the second edit this mode is allowed, for the same reason
                # as the DOCTYPE: `<title>` is not rendered in the body, so
                # filling it cannot change what the reader sees. EPUB 2 let it
                # be empty and EPUB 3 does not — so the mode was not carrying a
                # defect the book had, it was making one by rebuilding the
                # package as EPUB 3 around markup that was legal only under the
                # old rules. Decided by the parse, applied to the bytes.
                data, filled = xhtml.fill_empty_title(
                    resource.data, self._derive_title(root, resource)
                )
                if filled:
                    resource.data = data
                    titled += 1

                stranded.update(self._only_legal_in_epub2(root))
            if modernised:
                self.note(
                    ctx,
                    Level.FIX,
                    "xhtml.doctype-modernised",
                    values={"count": modernised},
                )
            if refused:
                names = sorted({name for names in refused.values() for name in names})
                self.note(
                    ctx,
                    Level.WARN,
                    "xhtml.doctype-kept",
                    values={"count": len(refused), "documents": ", ".join(names[:5])},
                    location=sorted(refused)[0],
                )
            if titled:
                self.note(
                    ctx,
                    Level.FIX,
                    "xhtml.title-filled",
                    values={"count": titled},
                )
            if stranded:
                # Not an apology and not a defect to chase: a statement of what
                # this mode cannot reach. The alternative is a reader running
                # EPUBCheck, getting `RSC-005`, and having no way to learn that
                # the answer is "use another mode".
                self.note(
                    ctx,
                    Level.WARN,
                    "xhtml.epub2-only-markup",
                    values={"what": ", ".join(sorted(stranded)[:4])},
                )
            if modernised or titled:
                self.note(ctx, Level.INFO, "xhtml.untouched-except-doctype")
            else:
                self.note(ctx, Level.INFO, "xhtml.untouched")
            return

        documents: list[tuple[object, object, dict[str, str]]] = []

        expanded_entities: dict[str, list[str]] = {}
        refused_entities: dict[str, list[str]] = {}

        for resource in ctx.book.content_docs():
            try:
                # `take`, not `parsed`: this stage edits the tree and writes it
                # back, so it must own the one it gets — see `Context.take`.
                parsed = ctx.take(resource)
                root, mode = parsed.root, parsed.mode
                if parsed.entities_expanded:
                    expanded_entities[resource.path] = parsed.entities_expanded
                if parsed.entities_refused:
                    refused_entities[resource.path] = parsed.entities_refused
            except Exception as exc:
                self.note(
                    ctx,
                    Level.ERROR,
                    "xhtml.unparseable",
                    values={"error": type(exc).__name__},
                    location=resource.path,
                )
                continue
            if parsed.encoding_mended:
                # Said out loud, because a silent repair is only a little better
                # than a silent loss: both leave a person unable to tell what
                # the file they have is.
                self.note(
                    ctx,
                    Level.FIX,
                    "xhtml.encoding-mended",
                    values={"encoding": parsed.encoding_mended},
                    location=resource.path,
                )
            if parsed.stylesheet_links:
                added = self._carry_stylesheet_pis(root, parsed.stylesheet_links)
                if added:
                    # A construct that carries visual meaning is translated, not
                    # removed — the project's own rule, and this was the one
                    # place quietly breaking it.
                    self.note(
                        ctx,
                        Level.FIX,
                        "xhtml.stylesheet-pi-converted",
                        values={"count": added, "names": ", ".join(parsed.stylesheet_links[:3])},
                        location=resource.path,
                    )
            if parsed.svg_case_restored:
                self.note(
                    ctx,
                    Level.FIX,
                    "xhtml.svg-case-restored",
                    values={"count": parsed.svg_case_restored},
                    location=resource.path,
                )
            if mode == "html":
                # Two documents can end up here and they are not the same event.
                #
                # An EPUB 2 book may legitimately carry `text/html`, and an HTML
                # parser is then simply *the right parser* — nothing was
                # recovered from anything, and calling that a warning would put
                # one on almost every legacy book this tool exists to rebuild.
                #
                # A document that claims to be XHTML and does not parse as XML
                # is the audit's F-004: what comes back is a reconstruction, not
                # a repair with a known result, and this program cannot show
                # that it means what the publisher wrote. WARN, and the status
                # of the whole rebuild follows — a book with one of these does
                # not come back reading a flat "succeeded".
                if self._declared_html(resource):
                    self.note(
                        ctx,
                        Level.FIX,
                        "xhtml.html-source-parsed",
                        location=resource.path,
                    )
                else:
                    ctx.recovered.append(resource.path)
                    self.note(
                        ctx,
                        Level.WARN,
                        "xhtml.recovered-with-html-parser",
                        location=resource.path,
                    )
            elif mode == "xml-entities":
                self.note(ctx, Level.FIX, "xhtml.entities-rewritten", location=resource.path)

            id_map = self._fix_identifiers(ctx, root, resource.path)
            documents.append((resource, root, id_map))

        # Fragment targets can point across documents, so every id rename must be
        # known before any href is rewritten.
        global_ids = {
            resource.path: id_map for resource, _, id_map in documents if id_map
        }
        ctx.id_map = global_ids
        # And which ids each document actually *has*, for the same reason: a
        # link to `chapter.xhtml#238` where nothing is called `238` is an error
        # EPUBCheck reports, and the only way to know is to have read every
        # document first. `global_ids` cannot answer it — it holds renames.
        present_ids = {
            resource.path: {
                element.get("id")
                for element in xhtml.iter_elements(root)
                if element.get("id")
            }
            for resource, root, _ in documents
        }

        for resource, root, _ in documents:
            self._skeleton(ctx, root, resource)
            self._rewrite_references(ctx, root, resource, global_ids, present_ids)
            self._modernise(ctx, root, resource)
            # Before anything that reads the cascade: a rule restored here
            # is a rule those must see. The cover repair below is the one
            # that matters — four of the seven books this found are covers,
            # and adding page-fitting limits on top of the publisher's own
            # restored sizing would be a second opinion nobody asked for.
            self._orphaned_styling(ctx, root, resource)
            self._image_paragraphs(ctx, root, resource)
            self._cover_fits_the_page(ctx, root, resource)
            self._page_bottom_kept(ctx, root, resource)
            self._positioning_contained(ctx, root, resource)
            self._block_in_inline(ctx, root, resource)
            self._empty_spans(ctx, root, resource)
            self._watermarks(ctx, root, resource)
            self._accessibility(ctx, root, resource)
            self._scripting(ctx, root, resource)
            self._properties(ctx, root, resource)
            self._census(ctx, root)
            ctx.document_ids[resource.path] = {
                element.get("id")
                for element in xhtml.iter_elements(root)
                if element.get("id")
            }
            # Counted before serialising, because serialising is what removes
            # them. Never silent: this is the book's own text, and a character
            # leaving it is the reader's information rather than their surprise.
            impossible = xhtml.forbidden_characters(root)
            if impossible:
                self.note(
                    ctx,
                    Level.FIX,
                    "xhtml.forbidden-characters-removed",
                    values={"count": impossible},
                    location=resource.path,
                )
            resource.data = xhtml.serialize(root)

        self._report_entities(ctx, expanded_entities, refused_entities)
        if self._titles_filled:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.title-filled",
                values={"count": self._titles_filled},
            )
        self._report_watermarks(ctx)

    def _report_entities(
        self,
        ctx: Context,
        expanded: dict[str, list[str]],
        refused: dict[str, list[str]],
    ) -> None:
        """Custom entities are a content change, so K6 requires saying so."""
        if expanded:
            names = sorted({name for names in expanded.values() for name in names})
            self.note(
                ctx,
                Level.FIX,
                "xhtml.dtd-entities-resolved",
                values={"count": len(names), "names": ", ".join(names[:8])},
                location=next(iter(expanded)) if len(expanded) == 1 else f"{len(expanded)} documents",
            )
        if refused:
            names = sorted({name for names in refused.values() for name in names})
            self.note(
                ctx,
                Level.WARN,
                "xhtml.dtd-entities-refused",
                values={"count": len(names), "names": ", ".join(names[:8])},
                location=next(iter(refused)) if len(refused) == 1 else f"{len(refused)} documents",
            )

    def _report_watermarks(self, ctx: Context) -> None:
        if self._watermarks_consolidated:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.watermark-consolidated",
                values={
                    "count": self._watermarks_consolidated,
                    "documents": self._watermark_documents,
                    "tokens": len(self._watermark_tokens),
                },
            )
        if self._watermarks_relocated:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.watermark-relocated",
                values={
                    "count": self._watermarks_relocated,
                    "documents": self._watermark_documents,
                    "tokens": len(self._watermark_tokens),
                    "name": watermark.META_NAME,
                },
            )
        if self._watermarks_removed:
            # A warning rather than a fix, and deliberately so: this is the one
            # place the tool destroys something a publisher put in the file. It
            # only happens because somebody asked, and the report should say it
            # loudly enough that they remember asking.
            self.note(
                ctx,
                Level.WARN,
                "xhtml.watermark-removed",
                values={
                    "count": self._watermarks_removed,
                    "documents": self._watermark_documents,
                    "tokens": len(self._watermark_tokens),
                },
            )
        if self._shop_notices_removed:
            # Verbatim, and every one of them. The acceptance for WP-17 said the
            # report has to name what went "tekstem, nie liczbą", and it is the
            # right condition: this is the only switch in the program that
            # deletes readable text, so the report is the thing that lets
            # somebody see it took the shop's sentence and not their book's.
            self.note(
                ctx,
                Level.FIX,
                "xhtml.shop-notice-removed",
                values={
                    "count": len(self._shop_notices_removed),
                    "documents": len(self._shop_notice_documents),
                    "removed": " | ".join(self._shop_notices_removed),
                },
            )
        if self._watermark_notices:
            emails = watermark.personal_data(" ".join(self._watermark_notices))
            kept = len(self._watermark_notices)
            message = f"kept {kept} visible watermark notice(s)"
            # Two findings, not one behind a conditional: a notice carrying
            # somebody's e-mail address is a different thing to report than one
            # that does not, and an id chosen by an expression is an id nothing
            # can see was raised.
            if emails:
                data = ", ".join(sorted(set(emails)))
                self.note(
                    ctx,
                    Level.PRESERVED,
                    "xhtml.watermark-kept-personal-data",
                    values={"count": kept, "data": data},
                )
            else:
                self.note(ctx, Level.PRESERVED, "xhtml.watermark-kept", values={"count": kept})

    def _fix_identifiers(self, ctx: Context, root, path: str) -> dict[str, str]:
        """Make every ``id`` a valid XML NCName **and unique**, and say what moved.

        Two defects, one pass, because they are the same bookkeeping: an id that
        is not a name, and an id that is not the only one of its name. The
        second was not handled at all until the mixed shelf produced eight
        `RSC-005: Duplicate ID` across two books — `bookmark63` … `bookmark86`,
        which is Word's naming, and `heading_id_3`/`heading_id_5`, which is a
        converter's. Both are older than us and neither is reachable: a document
        with the same id twice is invalid in XHTML 1.1 exactly as it is in
        HTML 5, so this is not something the upgrade introduced.

        **The first one keeps its name.** Every reference into the document
        already resolved to it — that is what every parser does with a
        duplicate — so renaming the later ones changes nothing anybody could
        link to, and renaming the first would change where existing links land.
        For that reason the later ones are deliberately *not* returned in the
        rename map: the map exists to repoint references, and a reference to a
        duplicate was never pointing at the copy.
        """
        renamed: dict[str, str] = {}
        duplicated: list[str] = []
        carrying = [
            element for element in xhtml.iter_elements(root) if element.get("id") is not None
        ]
        taken = {element.get("id") for element in carrying}
        seen: set[str] = set()
        for element in carrying:
            current = element.get("id")
            repeat = current in seen
            seen.add(current)
            valid = _NCNAME_RE.match(current) is not None
            if valid and not repeat:
                continue
            candidate = current
            if not valid:
                candidate = re.sub(r"[^A-Za-z0-9._\-]", "-", current)
                if not candidate or not re.match(r"^[A-Za-z_]", candidate):
                    candidate = f"id-{candidate}".rstrip("-")
            unique = candidate
            counter = 2
            while unique in taken:
                unique = f"{candidate}-{counter}"
                counter += 1
            taken.add(unique)
            element.set("id", unique)
            if repeat:
                duplicated.append(current)
            else:
                # One entry per distinct name, taken from its first appearance:
                # the map is read to rewrite `#name`, and a second entry for the
                # same key would send every reference to whichever came last.
                renamed[current] = unique
        if renamed:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.ids-renamed",
                values={"count": len(renamed)},
                location=path,
            )
        if duplicated:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.duplicate-ids-renamed",
                values={"count": len(duplicated), "names": ", ".join(sorted(set(duplicated))[:5])},
                location=path,
            )
        return renamed

    def _skeleton(self, ctx: Context, root, resource) -> None:
        """Guarantee html/head/title/body with the right namespace and language."""
        # The publication's language is a *default*, not an instruction to make
        # every document agree with it. A document that states its own is
        # stating a fact about itself: measured, a chapter declaring `lang="fr"`
        # in a book whose package says `en` came out saying `en`, and with it
        # went the hyphenation, the speech synthesiser's accent and the
        # dictionary. A bilingual edition is not an error to be tidied.
        #
        # This is K11 read the other way round. The source's declaration is not
        # a fact — but the argument for correcting one is evidence about the
        # text, which is what `metadata` weighs for the package as a whole. Here
        # there is no evidence at all, only a difference, and a difference
        # between a document and its book is the ordinary shape of a book with
        # two languages in it.
        language = ctx.book.metadata.language or ctx.policy.default_language
        stated = (root.get("lang") or root.get(XML_LANG) or "").strip()
        # Both spellings, and they must agree: EPUB 3 requires it, and a
        # document saying `lang="fr" xml:lang="en"` is one a reading system
        # resolves by picking, differently in each one.
        settled = stated or language
        if not stated:
            pass
        elif _contradicted_by_text(stated, root):
            # And this is why "believe the document" is not the rule either.
            # The public corpus answered it within the hour: three Polish
            # Project Gutenberg books wrap Polish text in `<html lang="en">`,
            # because the boilerplate says `en` and nobody edits it. Believing
            # that hands the text-to-speech engine an English voice for
            # *Pan Tadeusz*.
            #
            # So the rule is the one this program already applies to the
            # package's own declaration, applied a level down: the text decides.
            # K11 — the source's declaration is not a fact — and its converse,
            # that a difference is not a defect either. Narrow in exactly the
            # same way: only a language whose letters are their own proof, only
            # over enough of them to be evidence.
            settled = "pl"
            self.note(
                ctx,
                Level.FIX,
                "xhtml.document-language-corrected",
                values={"was": stated, "now": settled},
                location=resource.path,
            )
        elif stated != language:
            self.note(
                ctx,
                Level.PRESERVED,
                "xhtml.document-language-kept",
                values={"document": stated, "publication": language},
                location=resource.path,
            )
        root.set("lang", settled)
        root.set(XML_LANG, settled)

        head = root.find(xhtml.qname("head"))
        if head is None:
            head = etree.Element(xhtml.qname("head"))
            root.insert(0, head)
            self.note(ctx, Level.FIX, "xhtml.head-added", location=resource.path)

        body = root.find(xhtml.qname("body"))
        if body is None:
            body = etree.SubElement(root, xhtml.qname("body"))
            self.note(ctx, Level.FIX, "xhtml.body-added", location=resource.path)

        for meta in head.findall(xhtml.qname("meta")):
            if meta.get("http-equiv") or meta.get("charset"):
                head.remove(meta)
            elif meta.get("name") is not None and meta.get("content") is None:
                # `<meta name="…">` with nothing to say. HTML requires the pair
                # and EPUBCheck refuses the document without it — sixteen books
                # out of sixty-seven, all of them out of Sigil or Word, which
                # write the name and leave the value for later.
                #
                # Completed rather than removed, and the difference matters:
                # the publisher named something, and an empty value is the
                # honest reading of "named it and said nothing". Dropping the
                # element would throw away the name as well.
                meta.set("content", "")
        charset = etree.Element(xhtml.qname("meta"))
        charset.set("charset", "utf-8")
        head.insert(0, charset)

        title = head.find(xhtml.qname("title"))
        if title is None:
            title = etree.SubElement(head, xhtml.qname("title"))
        if not (title.text or "").strip():
            title.text = self._derive_title(root, resource)
            # Counted, not silent. This has always happened here and never had
            # a name, so a book whose every document gained a title said so
            # nowhere — and when the same repair turned out to be what stood
            # between container-only mode and a conformant EPUB 3, there was no
            # record that it was already being done three feet away.
            self._titles_filled += 1

    @staticmethod
    def _declared_html(resource) -> bool:
        """Did the source say this document was HTML rather than XHTML?

        EPUB 2 allowed `text/html`, and half the books this tool is pointed at
        are EPUB 2. For those an HTML parse is the correct reading of the file,
        not a rescue from a broken one.
        """
        path = (resource.original_path or resource.path).lower()
        return resource.media_type == "text/html" or path.endswith((".html", ".htm"))

    def _carry_stylesheet_pis(self, root, hrefs: list[str]) -> int:
        """Turn `<?xml-stylesheet href="…"?>` into `<link rel="stylesheet">`.

        The PI is how an XHTML document written before EPUB 3 links a
        stylesheet. EPUB 3 does not allow it, so it goes — and it was going
        without anything taking its place, which means the book came out
        unstyled and the report said nothing. The `<link>` says the same thing
        in the form this specification uses, and the href is rewritten with
        every other reference in the document afterwards.
        """
        head = root.find(xhtml.qname("head"))
        if head is None:
            return 0
        existing = {
            (element.get("href") or "").strip()
            for element in head.iter(xhtml.qname("link"))
        }
        added = 0
        for href in hrefs:
            if not href or href in existing or paths.is_remote(href):
                continue
            link = etree.SubElement(head, xhtml.qname("link"))
            link.set("rel", "stylesheet")
            link.set("type", "text/css")
            link.set("href", href)
            existing.add(href)
            added += 1
        return added

    def _derive_title(self, root, resource) -> str:
        for level in ("h1", "h2", "h3", "h4", "title"):
            for element in root.iter(xhtml.qname(level)):
                text = re.sub(r"\s+", " ", "".join(element.itertext())).strip()
                if text:
                    return text[:200]
        stem = posixpath.basename(resource.path).rpartition(".")[0]
        return re.sub(r"^\d+-", "", stem).replace("-", " ").replace("_", " ").strip() or "Section"

    def _rewrite_references(
        self, ctx: Context, root, resource, global_ids: dict, present_ids: dict
    ) -> None:
        """Repoint every href/src at the resource's new location."""
        source_path = resource.original_path or resource.path
        broken = 0
        misdirected = 0
        unresolved = 0
        repointed = 0
        sent_to_document = 0
        #: `(element, attribute, dead)`. `dead` is empty for a scalar attribute,
        #: where the whole value is the dead reference; for a list attribute it
        #: names the candidates that are dead, since the rest of the list may be
        #: perfectly good and must survive.
        dangling: list[tuple[object, str, tuple[str, ...]]] = []
        examples: list[str] = []

        def resolves(path: str, fragment: str) -> bool:
            """Is there anything in `path` carrying that id?

            Only answerable for documents this stage parsed. A fragment into a
            resource nobody here has read — an SVG, say — is left alone: an
            unanswered question is not the same as a "no", and dropping the
            fragment on a guess would break a link that works.
            """
            known = present_ids.get(path)
            return known is None or fragment in known

        def unresolvable(element, target_path: str, fragment: str) -> references.Decision:
            """Record one reference nothing here can resolve, and ask about it.

            The question carries what a person needs to answer it: the link's
            own text — for a footnote that is the number the reader sees — and
            the anchors the target document does have. Nobody to ask is the
            normal case and answers `keep`.
            """
            nonlocal unresolved
            question = references.Unresolved(
                document=resource.path,
                target=target_path,
                fragment=fragment,
                text=re.sub(r"\s+", " ", "".join(element.itertext())).strip()[:80],
                candidates=tuple(sorted(present_ids.get(target_path) or ())),
            )
            answer = ctx.ask(question)
            if answer.action == references.KEEP:
                # Recorded only when it stays unresolved. `strict` reads this
                # list to decide whether the book may be published at all, and
                # a reference a person has just answered is answered.
                ctx.unresolved.append(question)
                unresolved += 1
                if len(examples) < 3:
                    examples.append(str(question))
            return answer

        for element in xhtml.iter_elements(root):
            for attribute in REFERENCE_ATTRS:
                value = element.get(attribute)
                if not value:
                    continue
                value = value.strip()
                if paths.is_remote(value):
                    continue
                if value.startswith("#"):
                    fragment = value[1:]
                    local_map = global_ids.get(resource.path, {})
                    if fragment in local_map:
                        # REPAIRED: this rebuild renamed that id and holds the
                        # map that says what to.
                        element.set(attribute, f"#{local_map[fragment]}")
                    elif fragment and not resolves(resource.path, fragment):
                        # Nothing in this document answers to that name.
                        #
                        # This used to remove the attribute — the link became
                        # inert text and the validator stopped complaining. That
                        # is the same false repair as the cross-document case
                        # below, one step further along: a link the publisher
                        # wrote is *gone*, and the report called it a fix. The
                        # reference stays now, and a person may decide otherwise.
                        answer = unresolvable(element, resource.path, fragment)
                        if answer.action == references.REPOINT:
                            element.set(attribute, f"#{answer.fragment}")
                            repointed += 1
                        elif answer.action == references.POINT_AT_DOCUMENT:
                            # There is no such thing as a same-document
                            # reference to no place: `href="#"` is not one. A
                            # person asking for this is asking for the link to
                            # stop being a link, which is what removing the
                            # attribute does — the text stays put.
                            element.attrib.pop(attribute, None)
                            sent_to_document += 1
                    continue

                target = paths.resolve(source_path, value)
                if target is None:
                    continue
                new_target = ctx.path_map.get(target)
                if new_target is None:
                    # Before this counts as dead: is the thing it names actually
                    # in the book, under another path?
                    #
                    # The owner asked how this program knows a reference is dead
                    # rather than merely misdirected, "and the content is
                    # physically in the document". It did not know. It asked one
                    # question — does this path resolve to a resource — and a
                    # path miss is not evidence that the target is absent. A
                    # link written `images/a.png` from a document in `text/`,
                    # where the picture sits at `images/a.png` from the *root*,
                    # is one missing `../` and a picture the reader can see.
                    #
                    # Measured before writing this, over twenty books of both
                    # corpora and the owner's shelf: three dangling references
                    # in total, and **all three** had a file of that name
                    # elsewhere in the same book. Strict was unlinking pictures
                    # that were right there.
                    #
                    # Repointed only where there is exactly one candidate, which
                    # makes it a derivation rather than a guess. Two candidates
                    # is a question, and a question this cannot answer is left
                    # as it was — the same rule F-010 settled for fragments.
                    relocated = _one_candidate_named(ctx, target)
                    if relocated is not None:
                        element.set(attribute, paths.relative(resource.path, relocated))
                        misdirected += 1
                        continue
                    broken += 1
                    dangling.append((element, attribute, ()))
                    continue
                fragment = value.partition("#")[2]
                if fragment:
                    remapped = global_ids.get(new_target, {}).get(fragment)
                    fragment = remapped or fragment
                    if not resolves(new_target, fragment):
                        # The file is there and the anchor is not — what a PDF
                        # conversion leaves behind when it writes a page-number
                        # strip and only half the pages get an id.
                        #
                        # Dropping the fragment was the answer here for a long
                        # time, on the reasoning that the right file beats
                        # nowhere at all. For a footnote it is not: measured, a
                        # `noteref` to `przypisy.xhtml#fn-17` came out pointing
                        # at `przypisy.xhtml`, so tapping footnote seventeen
                        # lands on footnote one. That is not a broken link a
                        # reader can see; it is a working link to the wrong
                        # place, which is worse, and this tool called it a
                        # repair.
                        #
                        # The first answer to the audit's F-010 split the modes:
                        # `preserve` kept it, `strict` still dropped it. That was
                        # half an answer, and it never shipped. Strict is
                        # not a licence to invent a meaning — it is a promise
                        # that the output conforms, and a fragment removed to
                        # buy a validator's silence keeps the promise by
                        # breaking the book. So neither mode touches it now:
                        # the reference is UNRESOLVED, it stays exactly as the
                        # publisher wrote it, and what the modes disagree about
                        # is whether the result may be published at all —
                        # decided at the commit gate, not here.
                        answer = unresolvable(element, new_target, fragment)
                        if answer.action == references.REPOINT:
                            fragment = answer.fragment
                            repointed += 1
                        elif answer.action == references.POINT_AT_DOCUMENT:
                            fragment = ""
                            sent_to_document += 1
                href = paths.relative(resource.path, new_target)
                element.set(attribute, f"{href}#{fragment}" if fragment else href)

            for attribute in REFERENCE_LISTS:
                value = element.get(attribute)
                if not value or not value.strip():
                    continue
                rewritten: list[tuple[str, str]] = []
                dead: list[str] = []
                for candidate, descriptor in _split_srcset(value):
                    if paths.is_remote(candidate) or candidate.startswith("#"):
                        rewritten.append((candidate, descriptor))
                        continue
                    target = paths.resolve(source_path, candidate)
                    if target is None:
                        rewritten.append((candidate, descriptor))
                        continue
                    new_target = ctx.path_map.get(target)
                    if new_target is None:
                        relocated = _one_candidate_named(ctx, target)
                        if relocated is None:
                            # Kept in the list for now. Whether it survives is
                            # the mode's decision, taken below with every other
                            # dead reference, not this loop's.
                            rewritten.append((candidate, descriptor))
                            dead.append(candidate)
                            continue
                        new_target = relocated
                        misdirected += 1
                    rewritten.append((paths.relative(resource.path, new_target), descriptor))
                new_value = _join_srcset(rewritten)
                if new_value != value:
                    element.set(attribute, new_value)
                if dead:
                    broken += len(dead)
                    dangling.append((element, attribute, tuple(dead)))

            style = element.get("style")
            if style and "url(" in style:
                element.set("style", self._rewrite_css_urls(ctx, style, source_path, resource.path))

        remote_imports = 0
        for style_element in root.iter(xhtml.qname("style")):
            if not style_element.text:
                continue
            text, dropped = strip_remote_imports(style_element.text)
            remote_imports += dropped
            if "url(" in text:
                text = self._rewrite_css_urls(ctx, text, source_path, resource.path)
            style_element.text = text

        if unresolved:
            # WARN, not PRESERVED, and the level is the finding. `PRESERVED`
            # means *this program decided to keep a deviation because removing
            # it would change how the book looks* — a decision with a reason
            # behind it. This is the opposite: a defect the book arrived with,
            # which the rebuild could not resolve and did not pretend to. The
            # status of the whole rebuild follows the same distinction, so a
            # book carrying these never comes back reading `succeeded` flat.
            self.note(
                ctx,
                Level.WARN,
                "xhtml.fragment-unresolved",
                values={"count": unresolved, "examples": "; ".join(examples)},
                location=resource.path,
            )
        if repointed:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.fragment-repointed",
                values={"count": repointed},
                location=resource.path,
            )
        if sent_to_document:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.dead-fragment-dropped",
                values={"count": sent_to_document},
                location=resource.path,
            )
        if remote_imports:
            # `xhtml.` rather than `css.`: the prefix on a rule id names the
            # stage that reports it, and this is the content stage finding an
            # import inside a `<style>` element. The stylesheet stage has its
            # own id for the same repair in a linked sheet — which is not
            # duplication, because they are different places to go and look.
            self.note(
                ctx,
                Level.FIX,
                "xhtml.remote-import-removed",
                values={"count": remote_imports},
                location=resource.path,
            )

        if misdirected:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.reference-relocated",
                values={"count": misdirected},
                location=resource.path,
            )
            self.changed(
                ctx,
                Action.REPLACED,
                resource.path,
                before=f"{misdirected} reference(s) whose path named nothing",
                after="the one resource of that name the book does contain",
                risk=Risk.NONE,
                reversible=True,
                rule="xhtml.reference-relocated",
            )

        if not broken:
            return
        if not ctx.policy.strict:
            self.note(
                ctx,
                Level.PRESERVED,
                "xhtml.dead-reference-kept",
                values={"count": broken},
                location=resource.path,
            )
            return
        self._neutralise(ctx, dangling, resource)

    def _neutralise(self, ctx: Context, dangling: list, resource) -> None:
        """Strict mode: make references to absent files stop being errors."""
        unlinked = removed = 0
        for element, attribute, dead in dangling:
            tag = xhtml.local_name(element).lower()
            if dead:
                # A list attribute, and only some of the list is dead. A srcset
                # candidate is the same picture at another resolution, so what
                # goes here is a duplicate of something the reader still gets
                # from `src` — dropping it costs the book nothing, where taking
                # the whole `<img>` away would cost it the illustration.
                kept = [
                    (url, descriptor)
                    for url, descriptor in _split_srcset(element.get(attribute) or "")
                    if url not in dead
                ]
                if kept:
                    element.set(attribute, _join_srcset(kept))
                    unlinked += len(dead)
                    continue
                element.attrib.pop(attribute, None)
                unlinked += len(dead)
                if tag == "source":
                    # `<source>` exists only to carry the list. Emptied, it is a
                    # `<source>` with no `srcset`, which is invalid — and the
                    # `<img>` beside it in the `<picture>` is what displays.
                    parent = element.getparent()
                    if parent is not None:
                        self._unwrap(element, keep_children=False)
                continue
            if tag == "a" and attribute == "href":
                # Dropping href keeps the text and any styling; the link is inert.
                element.attrib.pop(attribute, None)
                unlinked += 1
            else:
                parent = element.getparent()
                if parent is not None:
                    # A `<picture>` is required to contain an `<img>`, and the
                    # `<img>` is the only part of it a reader ever displays; the
                    # `<source>` elements are alternatives to it. Removing the
                    # dead `<img>` and leaving the wrapper produced a `<picture>`
                    # with no `<img>` — invalid, and displaying nothing either
                    # way, so the wrapper goes with it.
                    #
                    # Found by the publication gate on the corpus the hour it
                    # was switched on: strict mode was the only mode that
                    # introduced an EPUBCheck error anywhere, and this was it.
                    if (
                        xhtml.local_name(element).lower() == "img"
                        and xhtml.local_name(parent).lower() == "picture"
                    ):
                        element = parent
                    self._unwrap(element, keep_children=False)
                    removed += 1
        self.note(
            ctx,
            Level.FIX,
            "xhtml.dead-reference-neutralised",
            values={
                "count": unlinked + removed,
                "unlinked": unlinked,
                "removed": removed,
            },
            location=resource.path,
        )
        # Strict mode taking markup out of somebody's page. `unlinked` keeps the
        # text and drops the href; `removed` takes the element away, and the
        # output has nothing left to say what it was — which is exactly the
        # distinction a balance sheet has to make and a count of 5 cannot.
        if unlinked:
            self.changed(
                ctx,
                Action.REPLACED,
                resource.path,
                before=f"{unlinked} link(s) to files not in the book",
                after="the same text, no longer a link",
                risk=Risk.APPEARANCE,
                reversible=False,
                rule="xhtml.dead-reference-neutralised",
            )
        if removed:
            self.changed(
                ctx,
                Action.REMOVED,
                resource.path,
                before=f"{removed} element(s) pointing at files not in the book",
                risk=Risk.CONTENT,
                reversible=False,
                rule="xhtml.dead-reference-neutralised",
            )

    def _rewrite_css_urls(self, ctx: Context, css_text: str, source_path: str, current_path: str) -> str:
        def replace(match: re.Match) -> str:
            raw = match.group(2).strip()
            if paths.is_remote(raw) or raw.startswith("#"):
                return match.group(0)
            target = paths.resolve(source_path, raw)
            if target is None:
                return match.group(0)
            new_target = ctx.path_map.get(target)
            if new_target is None:
                return match.group(0)
            return f"url({paths.relative(current_path, new_target)})"

        return re.sub(r"url\(\s*(['\"]?)(.*?)\1\s*\)", replace, css_text, flags=re.IGNORECASE)

    def _modernise(self, ctx: Context, root, resource) -> None:
        """Translate legacy presentational markup into equivalent CSS."""
        changed: set[str] = set()

        for element in list(root.iter()):
            if not isinstance(element.tag, str):
                continue
            tag = xhtml.local_name(element).lower()

            if tag in DEAD_ELEMENTS:
                parent = element.getparent()
                if parent is not None:
                    self._unwrap(element, keep_children=tag not in {"applet", "bgsound", "spacer"})
                    changed.add(tag)
                continue

            if tag == "font":
                declarations = []
                if element.get("color"):
                    declarations.append(f"color: {element.get('color').strip()};")
                if element.get("face"):
                    declarations.append(f"font-family: {element.get('face').strip()};")
                size = (element.get("size") or "").strip()
                if size in _FONT_SIZE_SCALE:
                    declarations.append(f"font-size: {_FONT_SIZE_SCALE[size]};")
                elif size.startswith(("+", "-")):
                    declarations.append("font-size: larger;" if size[0] == "+" else "font-size: smaller;")
                for attribute in ("color", "face", "size"):
                    element.attrib.pop(attribute, None)
                element.tag = xhtml.qname("span")
                _append_style(element, " ".join(declarations))
                changed.add("font")
                continue

            if tag in STYLED_REPLACEMENTS:
                replacement, declarations = STYLED_REPLACEMENTS[tag]
                element.tag = xhtml.qname(replacement)
                _append_style(element, declarations)
                changed.add(tag)

            if tag == "a" and element.get("name") and not element.get("id"):
                name = element.get("name")
                if _NCNAME_RE.match(name):
                    element.set("id", name)
                element.attrib.pop("name", None)
                changed.add("a[name]")

            if tag == "col" and self._wrap_a_stray_col(element):
                changed.add("col")

            if self._foster_out_of_a_table(element, tag):
                changed.add(f"table>{tag}")

            if self._move_flow_out_of_the_head(element, tag, root):
                changed.add(f"head>{tag}")

            self._presentational_attributes(element, tag, changed)

        if changed:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.presentational-markup-converted",
                location=resource.path,
                detail=", ".join(sorted(changed)),
            )


    #: What a table is allowed to contain directly. Anything else sitting under
    #: `<table>` is content a converter dropped in the wrong place.
    _TABLE_CONTENT = frozenset({
        "caption", "colgroup", "col", "thead", "tbody", "tfoot", "tr", "script",
        "template",
    })

    #: What a `<head>` is allowed to contain. Anything else there is flow
    #: content, and a browser has been quietly moving it into the body for
    #: twenty years.
    _HEAD_CONTENT = frozenset({
        "base", "link", "meta", "noscript", "script", "style", "title",
        "template",
    })

    @classmethod
    def _foster_out_of_a_table(cls, element, tag: str) -> bool:
        """Lift content that is inside `<table>` but not inside a cell.

        `<a>` straight under `<table>`, from the owner's second shelf. XHTML 1.1
        let it through and XHTML5 does not, so a book that arrived valid left
        this program invalid — which is the one thing `preserve` may never do.

        Moved **in front of** the table rather than into the first cell, and
        that is not a preference. It is what every HTML parser already does with
        this markup: content in a table but not in a cell is *foster parented*
        out to just before the table, and that is where a reader has always seen
        it. So the fix puts the element where it was already being drawn, which
        is why the page does not move.
        """
        parent = element.getparent()
        if parent is None:
            return False
        if xhtml.local_name(parent).lower() != "table":
            return False
        if tag in cls._TABLE_CONTENT:
            return False
        grandparent = parent.getparent()
        if grandparent is None:
            return False
        grandparent.insert(list(grandparent).index(parent), element)
        return True

    @classmethod
    def _move_flow_out_of_the_head(cls, element, tag: str, root) -> bool:
        """Move flow content out of `<head>` and to the top of `<body>`.

        A `<p>` inside `<head>`, from the same shelf. A browser starts the body
        at the first thing that does not belong in the head, so the paragraph
        was already the first thing on the page — moving it to the top of
        `<body>` writes down where it was already being shown.
        """
        parent = element.getparent()
        if parent is None or xhtml.local_name(parent).lower() != "head":
            return False
        if tag in cls._HEAD_CONTENT:
            return False
        body = next(
            (child for child in root if xhtml.local_name(child).lower() == "body"),
            None,
        )
        if body is None:
            return False
        body.insert(0, element)
        return True

    @staticmethod
    def _wrap_a_stray_col(element) -> bool:
        """Put a `<col>` that sits straight under `<table>` into a `<colgroup>`.

        XHTML 1.1 allows `col` as a child of `table`; XHTML5, which is what an
        EPUB 3 content document is, requires it inside a `colgroup`. So a book
        that validated as EPUB 2 comes out of the version upgrade with
        `RSC-005: element "col" not allowed here` — and that error is *ours*,
        because the markup was conforming where it started and the rebuild is
        what moved it.

        Found on the owner's 67-book collection: of six error shapes his run
        attributed to `preserve`, this is the one that reproduced as genuinely
        introduced — source clean, output not. Four of the others are carried
        from markup that was already invalid, and one (`<a name="1…">`) this
        program already repairs.

        The repair is the smallest one that is true: consecutive `col` elements
        move together into one `colgroup`, which is what they meant, and column
        widths keep applying exactly as before. Nothing is deleted and nothing
        is styled differently.
        """
        parent = element.getparent()
        if parent is None or xhtml.local_name(parent).lower() != "table":
            return False
        position = list(parent).index(element)
        group = parent.makeelement(xhtml.qname("colgroup"), {})
        parent.insert(position, group)
        # Every `col` from here on, so a table declaring four columns gets one
        # group of four rather than four groups of one.
        for sibling in list(parent)[position + 1:]:
            if not isinstance(sibling.tag, str):
                continue
            if xhtml.local_name(sibling).lower() != "col":
                break
            parent.remove(sibling)
            group.append(sibling)
        group.tail = element.tail
        element.tail = None
        return True

    def _document_cascade(self, ctx: Context, root, resource) -> css_cascade.Cascade:
        """Collect the CSS that actually applies to one document.

        The parsed result is cached on the sources it was built from, and that
        cache is not a micro-optimisation. Six passes over each document ask
        for the cascade, and every one of them was re-parsing the same
        stylesheet through cssutils: on a twenty-chapter book sharing one sheet
        that is forty parses of the same bytes, **eleven of the fifteen seconds
        a rebuild took**. Books share a stylesheet almost by definition, so one
        parse serves the whole book.

        Keyed on the sources rather than on the document, because two documents
        with the same links and the same inline `<style>` have the same cascade
        and a third with an extra `<style>` does not.
        """
        sources: list[str] = []
        for link in root.iter(xhtml.qname("link")):
            if "stylesheet" not in (link.get("rel") or "").lower():
                continue
            href = link.get("href")
            target = paths.resolve(resource.path, href) if href else None
            sheet = ctx.book.get(target) if target else None
            if sheet is not None and sheet.is_style:
                cached = self._sheet_cache.get(sheet.path)
                if cached is None:
                    cached = sheet.text()
                    self._sheet_cache[sheet.path] = cached
                sources.append(cached)
        for style in root.iter(xhtml.qname("style")):
            if style.text:
                sources.append(style.text)
        key = tuple(sources)
        cached = self._cascade_cache.get(key)
        if cached is None:
            cached = css_cascade.Cascade.parse(sources)
            self._cascade_cache[key] = cached
        return cached

    #: How many rules may be lifted into one document to restore its styling.
    #:
    #: Measured, not chosen: across thirty-two commercial books, every single
    #: case needed **one** rule. The cap exists so that a book built some way
    #: nobody here has seen cannot turn this into "paste a stylesheet into every
    #: chapter" — at which point the repair would be doing more than restoring
    #: what the publisher wrote, and would need a different justification.
    RESTORED_RULE_LIMIT = 8

    def _orphaned_styling(self, ctx: Context, root, resource) -> None:
        """A rule the publisher wrote, in a sheet this document never links.

        Roadmap point [4], from the end the owner of the corpus named: not
        unused classes — which cost nothing and are the small half of it — but a
        stylesheet that is **correct** and reaches no document. Calibre does
        this by the shelf-load, and so do the repackaging pipelines the shops
        run: the archive still holds the rule, the page no longer sees it, and
        the book renders as raw HTML in the middle of a typeset one.

        "This document uses a class no rule reaches" is not the test. It fires
        on almost every book ever made — thirty-four documents in one, a hundred
        and thirty-four in another — because converters leave class names behind
        like `EPubfirstparagraph` that nothing ever styled. Those are dead
        markup, not dead CSS, and they cost the reader nothing.

        The test is narrower, and it names the fix as it finds it:

        * the document uses a class,
        * nothing it links — no sheet, no `<style>` — defines that class,
        * **exactly one** stylesheet in the book does, and this document does
          not link it.

        Then there is no guessing left: the rule exists, it was written for this
        class, and only one candidate can have meant it. What that turns up on a
        real shelf is small and it is not noise — 52 documents across 7 of 32
        books, and every one of them a single rule:

        ===================================  ==================================
        `Book 1`     `.dropcap` — 37 chapters open with
                                              `<span class="dropcap">` and the
                                              linked sheet defines only
                                              `.dropcap_small`
        `Book 4`               `.coverimage2 { height: 100vh }`
        `Book 5`              `.cover { margin: 0 }`
        three jednego wydawcy titles                   `.cover { height: 97% }`, on a
                                              cover page linking no sheet at all
        `Book 6`                         `.photo`
        ===================================  ==================================

        Four of the seven are covers, which is the owner's correction arriving
        as a measurement: *a cover needs CSS — how else would it scale to the
        reader?* These are exactly the rules that make one fill the screen, and
        they were reaching nothing.

        The rule is copied into the document rather than the sheet linked. A
        sheet is 20 kB of somebody else's decisions and linking it would import
        all of them into a page it was not written for; the rule for the class
        the page actually uses is the part that was lost. Rules that fetch
        something with `url()` are left alone — their references are relative to
        the sheet, and rebasing a background image into a document three
        directories away is a way to turn a missing drop cap into a missing
        picture. On the shelf this was measured against, no case needed one.
        """
        used: set[str] = set()
        for element in xhtml.iter_elements(root):
            used.update((element.get("class") or "").split())
        if not used:
            return

        linked = set(self._linked_stylesheets(ctx, root, resource))
        reachable: set[str] = set()
        for path in linked:
            reachable |= self._classes_defined(ctx, path)
        for style in root.iter(xhtml.qname("style")):
            reachable |= _selector_classes(style.text or "")
        orphaned = used - reachable
        if not orphaned:
            return

        # Which sheet in the book owns each orphaned class. One owner is
        # evidence; two is a choice, and choosing between two publishers'
        # intentions on a page neither was written for is guessing.
        donors: dict[str, str] = {}
        for name in sorted(orphaned):
            holders = [
                sheet.path
                for sheet in ctx.book.by_type("style")
                if name in self._classes_defined(ctx, sheet.path)
            ]
            if len(holders) == 1 and holders[0] not in linked:
                donors[name] = holders[0]
        if not donors:
            return

        restored: list[str] = []
        names: list[str] = []
        for path in sorted(set(donors.values())):
            wanted = {name for name, sheet in donors.items() if sheet == path}
            found = _rules_naming(self._sheet_text(ctx, path), wanted)
            if found:
                restored.extend(found)
                names.extend(sorted(wanted))
        if not restored or len(restored) > self.RESTORED_RULE_LIMIT:
            return

        head = root.find(xhtml.qname("head"))
        if head is None:
            return
        style = etree.SubElement(head, xhtml.qname("style"))
        style.text = (
            "\n      /* EPUB-Forge: the publisher's own rule(s) for "
            + ", ".join(f".{name}" for name in names)
            + ", which this document uses and no stylesheet it links defines. "
            "Copied verbatim from the sheet that holds them. */\n      "
            + "\n      ".join(restored)
            + "\n    "
        )
        self.note(
            ctx,
            Level.FIX,
            "xhtml.orphaned-styling-restored",
            values={"count": len(names), "classes": ", ".join(names[:5])},
            location=resource.path,
        )

    def _only_legal_in_epub2(self, root) -> "set[str]":
        """Markup that XHTML 1.1 allowed and EPUB 3 does not, named as found.

        Container-only mode makes two edits and both live in the `<head>`,
        because the head is not rendered. Everything else in a document is left
        alone — which is the promise, and which means a construct that was legal
        under the old rules and is not under the new ones **stays**, and the
        output is an invalid EPUB 3 through no fault of the content.

        The corpus found eleven books in that state, all reporting `RSC-005`,
        and on the shelf reachable from here the sentence behind it was always
        the same: *value of attribute "width" is invalid; must be an integer* —
        `<img width="50%">`, which XHTML 1.1 allowed and HTML5 does not. The
        modes that open documents move it into CSS and come out clean.

        So this says so, out loud, instead of leaving somebody to run EPUBCheck
        and find a message that does not mention which mode would fix it. It
        names what it found rather than claiming to know the whole class:
        anything not listed here will still show up in a validator, and that is
        the honest limit of a check written from six examples.
        """
        found: set[str] = set()
        for element in xhtml.iter_elements(root):
            tag = xhtml.local_name(element).lower()
            if tag in ("img", "table", "td", "th", "object", "iframe"):
                for name in ("width", "height"):
                    value = (element.get(name) or "").strip()
                    # HTML5 wants a plain pixel count. XHTML 1.1 took a
                    # percentage, and shops used it constantly.
                    if value and not value.isdigit():
                        found.add(f"{tag}[{name}]")
            if element.get("valign"):
                # Never valid in HTML5; `vertical-align` in CSS is the
                # equivalent, and that is what the other modes write.
                found.add(f"{tag}[valign]")
            if tag == "li" and element.get("value"):
                parent = element.getparent()
                if parent is None or xhtml.local_name(parent).lower() != "ol":
                    # `value` on a list item is legal inside an ordered list and
                    # nowhere else.
                    found.add("li[value]")
        return found

    def _census(self, ctx: Context, root) -> None:
        """Note every class and id this document carries, for the CSS stage.

        Taken last, after every repair that might have added one — the drop cap
        restored above puts no class on anything, but a future one might, and a
        census taken before the repairs would call its own work dead.

        The scan is of the finished tree, which includes inline SVG and MathML:
        those carry classes too, and a rule for one of them is not dead because
        the element it styles happens to be drawn rather than written.
        """
        for element in xhtml.iter_elements(root):
            classes = element.get("class")
            if classes:
                ctx.used_classes.update(classes.split())
            identifier = element.get("id")
            if identifier:
                ctx.used_ids.add(identifier)
            if xhtml.local_name(element).lower() == "script":
                ctx.scripted = True

    def _sheet_text(self, ctx: Context, path: str) -> str:
        sheet = ctx.book.get(path)
        if sheet is None:
            return ""
        cached = self._sheet_cache.get(path)
        if cached is None:
            cached = sheet.text()
            self._sheet_cache[path] = cached
        return cached

    def _classes_defined(self, ctx: Context, path: str) -> frozenset[str]:
        cached = self._class_cache.get(path)
        if cached is None:
            cached = _selector_classes(self._sheet_text(ctx, path))
            self._class_cache[path] = cached
        return cached

    def _image_paragraphs(self, ctx: Context, root, resource) -> None:
        """Stop body-text rules from indenting a paragraph that is just an image.

        Cover and title pages are almost always ``<p><img/></p>``. When the
        stylesheet gives ``p`` an indent and justification — which it does for
        running text — that indent shifts the artwork off-centre.

        The correction only applies where the layout is an accident of
        inheritance. If the publisher aimed a rule at this paragraph — by class,
        by id, or inline — that is a decision about the image, and it is left
        exactly as written even when it is not centred.
        """
        candidates = []
        for element in xhtml.iter_elements(root):
            if xhtml.local_name(element).lower() not in {"p", "div"}:
                continue
            children = [child for child in element if isinstance(child.tag, str)]
            if len(children) != 1:
                continue
            if xhtml.local_name(children[0]).lower() not in {"img", "svg", "image"}:
                continue
            if (element.text or "").strip() or (children[0].tail or "").strip():
                continue
            candidates.append(element)

        if not candidates:
            return

        cascade = self._document_cascade(ctx, root, resource)
        adjusted = 0
        respected = 0
        unindented = 0
        unstyled = 0

        for element in candidates:
            tag = xhtml.local_name(element).lower()
            classes = frozenset((element.get("class") or "").split())
            element_id = element.get("id")
            inline = (element.get("style") or "").lower()

            if "text-align" in inline or "text-indent" in inline:
                respected += 1
                continue
            # A rule naming this paragraph's class or id is about this image.
            if cascade.declares_targeted("text-align", tag, classes, element_id) or (
                cascade.declares_targeted("text-indent", tag, classes, element_id)
            ):
                respected += 1
                continue

            # Both properties are inherited, so the answer may be several
            # elements up. `body.cover { text-align: center }` around a bare
            # <div><img/></div> is a centred cover page; reading the <div>
            # alone sees nothing and "fixes" what was never broken.
            chain = _ancestry(element)
            align, align_targeted, _ = cascade.resolve("text-align", chain)
            indent, indent_targeted, indent_distance = cascade.resolve("text-indent", chain)
            centred = (align or "").strip().lower() in {"center", "-webkit-center"}
            if centred and css_cascade.is_zero_length(indent):
                # Already centred, wherever that was decided. Restating it would
                # add noise to the markup and claim a fix that changed nothing.
                continue

            # An ancestor the publisher aimed at — `div.right`, `body.cover` —
            # is still a statement about where this image sits, and moving it
            # to the middle would overrule a decision.
            if align_targeted and not centred:
                if indent_targeted or css_cascade.is_zero_length(indent):
                    respected += 1
                    continue
                # The alignment was chosen, but a running-text indent still
                # leaks in from a generic rule. Take the indent, leave the
                # alignment: only one of the two was decided.
                _append_style(element, "text-indent: 0;")
                unindented += 1
                continue

            # Nothing decided this paragraph's alignment. Either running-text
            # rules leak onto it, or — as on title pages that link no stylesheet
            # at all — the reader's default left-aligns the artwork. Both leave
            # the image off-centre for want of an instruction, not by choice.
            #
            # The two are counted apart, because the sentence that describes
            # them is not the same sentence. EF-034: one message said "their
            # text indent was removed" for pages that had no indent to remove
            # — nothing false about the *change*, and untrue about the *book*,
            # which is the kind of report line that teaches somebody to stop
            # reading them. The code knew the difference all along; the
            # catalogue had one entry for both.
            _append_style(element, "text-indent: 0; text-align: center;")
            adjusted += 1
            if not self._linked_stylesheets(ctx, root, resource):
                unstyled += 1

        if unstyled:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.image-paragraph-centred-unstyled",
                location=resource.path,
                values={"count": unstyled},
            )
        if adjusted - unstyled:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.image-paragraph-centred",
                values={"count": adjusted - unstyled},
                location=resource.path,
            )
        if unindented:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.image-paragraph-unindented",
                values={"count": unindented},
                location=resource.path,
            )
        if respected:
            self.note(
                ctx,
                Level.PRESERVED,
                "xhtml.image-paragraph-kept",
                values={"count": respected},
                location=resource.path,
            )

    def _cover_fits_the_page(self, ctx: Context, root, resource) -> None:
        """Keep a cover from being shown at its pixel size for want of a rule.

        A cover page normally carries ``img { max-width: 100%; max-height: 100% }``
        and an ancestor with a height. When that goes missing — a stylesheet
        link the publisher's tooling broke, a page that links no stylesheet at
        all — the reader falls back to the image's own dimensions, and a 1600px
        cover on a six-inch screen is cropped or shrunk to a stamp depending on
        the device.

        **Two things were wrong here and both are EF-024 and EF-026.**

        It asked *is this the cover* by resolving `src` against the document's
        original path — at a point where `src` has already been rewritten to its
        new one. The result named nothing, `path_map` answered `None` for both
        sides of the comparison, and `None != None` is false: the guard let
        everything through. Every unsized image in the book got the cover's
        rule, twice over on the fixture used by the suite. The question is now
        asked of the **manifest**, through `covers.is_the_cover`, and a manifest
        does not move when files do.

        And what it added was two inline declarations, one of which could not
        work. `max-height: 100%` is a percentage; a percentage height resolves
        against the containing block, and with no height on `html` and `body`
        there is nothing to resolve against. So the rule that keeps a tall cover
        on one page was inert exactly where it was needed. What goes in now is
        the same block a generated cover page is born with, scoped to this
        document, from `covers.COVER_STYLE_ADDED`.

        Both properties can still only ever make an image *smaller* than its
        natural size, so the worst case of being wrong remains that a reader
        ignores them.
        """
        if not covers.cover_identities(ctx.book):
            return

        wanted = []
        pixel_sized = []
        for element in root.iter(xhtml.qname("img")):
            source = (element.get("src") or "").strip()
            if not source:
                continue
            # Resolved against the path this resource has **now**, because that
            # is what `src` is relative to after the relayout.
            target = paths.resolve(resource.path, source)
            if not covers.is_the_cover(ctx.book, target):
                continue
            if element.get("width") or element.get("height"):
                # The publisher pinned the cover in pixels, which is the defect
                # named in D2 and not something to overwrite silently.
                pixel_sized.append(source)
                continue
            inline = (element.get("style") or "").lower()
            if any(prop in inline for prop in ("width", "height")):
                continue
            wanted.append(element)

        if pixel_sized:
            self.note(
                ctx,
                Level.WARN,
                "xhtml.cover-sized-in-pixels",
                location=resource.path,
                values={"count": len(pixel_sized)},
            )

        if not wanted:
            return

        cascade = self._document_cascade(ctx, root, resource)
        still_wanted = []
        for element in wanted:
            chain = _ancestry(element)
            if any(
                cascade.resolve(prop, chain[:1])[0] is not None
                for prop in ("width", "height", "max-width", "max-height")
            ):
                continue
            still_wanted.append(element)

        if not still_wanted:
            return

        head = root.find(xhtml.qname("head"))
        # The page-level template lays out the **whole document**: `height: 100%`
        # on html and body, and a centring flex box. That is right for a cover
        # page, which is one image and nothing else, and destroys any document
        # with text in it — the running text gets centred and clipped to the
        # height of the screen, and whatever does not fit simply is not drawn.
        #
        # EF-041, measured. A legacy `<guide>` may point `type="cover"` at a
        # document that is also chapter one, and books do: the suite's own
        # legacy fixture is one. Before this condition existed, that chapter got
        # the cover template and came out with **3.3% → 2.9%** of the page inked
        # at 600×800 — the render gate caught it and refused to publish, which
        # is the gate working exactly as intended.
        #
        # So the template needs a page with nothing to lay out, and everything
        # else gets the per-image rule instead: `max-width`/`max-height` can only
        # ever make an image smaller than it already is, so it is safe on any
        # document, and it is what this code did before WP-8.
        if head is None or _has_flow_text(root):
            for element in still_wanted:
                _append_style(element, "max-width: 100%; max-height: 100%;")
        else:
            style = etree.SubElement(head, xhtml.qname("style"))
            style.text = covers.COVER_STYLE_ADDED

        self.note(ctx, Level.FIX, "xhtml.cover-fitted", location=resource.path)

    #: What replaces `position: absolute; bottom: 0` on a one-block page.
    #:
    #: Scoped into the document that needs it rather than added to the shared
    #: stylesheet, and that is the whole reason this is safe. Making every
    #: `<body>` in a book a flex column would stop adjacent margins collapsing
    #: on every page of it — two 1em margins becoming 2em instead of 1em — which
    #: is a change to the look of the entire book in service of one page.
    #:
    #: `min-height` rather than `height`: a page taller than the screen must
    #: still be allowed to grow. The same idiom as the generated cover page,
    #: which is the one piece of evidence available that it works on the
    #: owner's reader.
    PAGE_BOTTOM_STYLE = (
        "\n      /* EPUB-Forge: the publisher pinned this page's content to the "
        "foot of the page with out-of-flow positioning, which loses it on a "
        "paginating reader. Same result, in the flow. */\n"
        "      html { height: 100%; }\n"
        "      body { display: flex; flex-direction: column; min-height: 100%; }\n    "
    )

    def _page_bottom_kept(self, ctx: Context, root, resource) -> None:
        """Keep a page pinned to the foot of the screen without taking it out of flow.

        `div.dol { position: absolute; bottom: 0; width: 100% }` — a real rule
        from a real book, `.dol` being Polish for "bottom". The publisher meant
        the dedication to sit at the foot of the page, and on the owner's reader
        that page came out **blank**: the block left the flow and pagination
        went round it.

        The first repair here deleted the declaration. That made the page
        appear and put the dedication at the top, which is not what anybody
        asked for — the owner's words: *what matters to me is not the rule, it
        is that the page keeps looking the way the publisher wanted it.* He is
        right, and this file says so in its first paragraph: a construct that is
        invalid or unsupported but carries visual meaning is **translated into
        the conforming equivalent that renders the same way, never simply
        deleted**. Deleting it was the tool breaking its own rule.

        So it is translated. `margin-top: auto` inside a flex column puts a
        block at the bottom of its container exactly as `bottom: 0` was meant
        to, and it stays in the flow, so pagination cannot lose it.

        Narrow on purpose, and only where the translation is provably faithful:

        * reflowable only — in fixed layout the viewport is declared, nothing
          paginates, and out-of-flow positioning is how the format works;
        * the positioned element must be the **only** element child of `<body>`,
          which is what "this page is that block" means. With siblings, making
          the body a flex column would stop their margins collapsing, and a
          repair that changes the spacing of a page it was not called for is
          worse than the defect;
        * `bottom` set and `top` unset — a block pinned to the foot. Anything
          else (stretched between both, centred, offset from the top) is left
          alone and reported, because guessing at an equivalent is how a tool
          that means well ruins a layout.
        """
        if ctx.book.rendition.get("layout") == "pre-paginated":
            return
        body = root.find(xhtml.qname("body"))
        if body is None:
            return
        children = [child for child in body if isinstance(child.tag, str)]
        if len(children) != 1:
            return

        element = children[0]
        tag = xhtml.local_name(element).lower()
        classes = frozenset((element.get("class") or "").split())
        identifier = element.get("id")
        cascade = self._document_cascade(ctx, root, resource)

        position, _ = cascade.lookup("position", tag, classes, identifier)
        if (position or "").strip().lower() not in ("absolute", "fixed"):
            return
        bottom, _ = cascade.lookup("bottom", tag, classes, identifier)
        top, _ = cascade.lookup("top", tag, classes, identifier)
        if bottom is None or top is not None:
            return

        head = root.find(xhtml.qname("head"))
        if head is None:
            return
        style = etree.SubElement(head, xhtml.qname("style"))
        style.text = self.PAGE_BOTTOM_STYLE

        # Inline, so it beats the publisher's own rule wherever that sits in the
        # cascade. The offset carries over as a margin when it is not zero: a
        # block two ems clear of the foot was two ems clear on purpose.
        declarations = "position: static; margin-top: auto;"
        if not css_cascade.is_zero_length(bottom):
            declarations += f" margin-bottom: {bottom.strip()};"
        _append_style(element, declarations)

        ctx.positioning_translated.add(resource.path)
        self.note(ctx, Level.FIX, "xhtml.position-pinned-in-flow", location=resource.path)

    #: Values of `position` that make an element a containing block for the
    #: absolutely positioned descendants beneath it. `fixed` is deliberately in
    #: the list as a *positioned ancestor* and deliberately not treated as
    #: *contained* itself: a fixed element is laid out against the viewport and
    #: an ordinary positioned ancestor does not hold it.
    POSITIONED = ("relative", "absolute", "fixed", "sticky")

    _INLINE_POSITION_RE = re.compile(r"(?:^|;)\s*position\s*:\s*([a-z-]+)", re.IGNORECASE)

    def _position_of(self, cascade, element) -> str:
        """The `position` in force on one element: inline first, then the sheet."""
        inline = self._INLINE_POSITION_RE.search(element.get("style") or "")
        if inline:
            return inline.group(1).lower()
        value, _ = cascade.lookup(
            "position",
            xhtml.local_name(element).lower(),
            frozenset((element.get("class") or "").split()),
            element.get("id"),
        )
        return (value or "static").strip().lower()

    def _positioning_contained(self, ctx: Context, root, resource) -> None:
        """Note absolute positioning that is held inside a positioned ancestor.

        `position: absolute` is not an error and EPUBCheck has never said it
        was. The argument for touching it is a rendering argument: a block taken
        out of the flow is not paginated with the text, so a reader can clip it,
        overlap it or lose the page it was on — which is exactly what happened
        to a real dedication page, and why `_page_bottom_kept` exists.

        That argument has a precondition nobody wrote down: it only holds when
        the element's containing block is the page. Put the same declaration
        inside an ancestor the publisher positioned — `.cover { position:
        relative }` around `.caption { position: absolute; bottom: 8px }` — and
        the caption cannot go anywhere. It is laid out against a box that is
        itself in the flow, it travels with it, and it is the ordinary way to
        put words over a picture in CSS. Removing it does not repair anything:
        it drops the caption below the image on every reader, including the ones
        where it was fine.

        Under `--strict` that is what the tool did, on a book where nothing was
        broken. So the case is recognised here and the style stage is told.
        """
        if ctx.book.rendition.get("layout") == "pre-paginated":
            return
        cascade = self._document_cascade(ctx, root, resource)
        for element in xhtml.iter_elements(root):
            # Only `absolute`: a `fixed` element resolves against the viewport,
            # so a positioned ancestor is not its containing block and cannot
            # promise to keep it.
            if self._position_of(cascade, element) != "absolute":
                continue
            ancestor = element.getparent()
            while ancestor is not None and isinstance(ancestor.tag, str):
                if self._position_of(cascade, ancestor) in self.POSITIONED:
                    ctx.positioning_contained.add(resource.path)
                    return
                ancestor = ancestor.getparent()

    #: Attributes that make a `<span>` mean something regardless of styling.
    #: `id` is a link target, `lang` decides hyphenation and speech, `epub:type`
    #: is semantics a reading system acts on, `role` and `aria-*` are what a
    #: blind reader gets, `dir` is direction, `title` is a tooltip, `style` is a
    #: rule of its own.
    SPAN_MEANS_SOMETHING = (
        "id", "lang", "{http://www.w3.org/XML/1998/namespace}lang",
        "{http://www.idpf.org/2007/ops}type", "role", "dir", "title", "style",
    )

    #: Declarations that are the default for an inline box, so a rule saying
    #: only these is a rule saying nothing. Values are matched literally after
    #: lowercasing; a shorthand of all-zero lengths counts for the box ones.
    INERT_VALUES = {
        "background": ("transparent", "none"),
        "background-color": ("transparent", "none"),
        "font-size": ("100%", "1em", "inherit", "medium"),
        "font-weight": ("normal", "400", "inherit"),
        "font-style": ("normal", "inherit"),
        "font-variant": ("normal", "inherit"),
        "text-transform": ("none", "inherit"),
        "text-decoration": ("none", "inherit"),
        "line-height": ("inherit", "normal"),
        "vertical-align": ("baseline", "inherit"),
    }

    #: How far a colour may sit from the one it would inherit and still count as
    #: no change, per channel out of 255.
    #:
    #: Two, and it is not a taste. PDF converters copy the exact colour out of
    #: the source, and black in a PDF is rarely `#000000`: the corpus has
    #: `.black { color: #010000 }` and `.dark-gray { color: #000100 }` — black
    #: nudged by one part in 255 on a single channel, on 1 135 spans in one
    #: book. No screen shows that and no eye sees it. Wider than this and the
    #: threshold would start deciding that somebody's dark grey is black.
    COLOUR_TOLERANCE = 2

    def _empty_spans(self, ctx: Context, root, resource) -> None:
        """Unwrap a `<span>` whose every rule says nothing — roadmap point [5].

        **Unwrap, not delete.** The text inside stays exactly where it was; only
        the wrapper goes. Nothing this rule does can lose a character, which is
        the difference between tidying a conversion artefact and editing a book.

        Measured over 12 475 spans in thirty-two commercial books before any of
        it was written, and the measurement moved the point:

        ========================================  ======  ==========================
        do something                              12 108  `span.Italic` × 1906 alone
        carry an attribute that means something       21
        **a rule reaches them and says nothing**    **90**  the only real targets
        nothing reaches them at all                  256  **not this rule's business**
        ========================================  ======  ==========================

        That last row is why the measurement had to come first. Its largest
        class is `dropcap` — **219 of them**, the drop caps whose stylesheet
        point [4] had just reconnected. A rule keyed on "nothing styles it"
        would have deleted 219 drop caps the moment after they were repaired.
        `antique`, `hagrid`, `sans` are the same shape: a class nobody defines
        is a record of what the publisher meant, not rubbish. `hagrid` on a span
        says how a character should sound.

        So the condition is **a rule exists and everything it says is inert** —
        which is a statement about the stylesheet, not about our ignorance of
        it. The 90 that qualify are all one thing: conversion from PDF.
        `.reset { margin: 0; padding: 0 }` on an inline box, where those are the
        defaults, and `.black { color: #010000 }`, which is black moved by one
        part in 255 because the converter copied the exact ink out of the PDF.
        """
        if not ctx.policy.rewrite_content:
            return
        spans = [
            span
            for span in root.iter(xhtml.qname("span"))
            if not any(span.get(name) for name in self.SPAN_MEANS_SOMETHING)
        ]
        if not spans:
            return

        cascade = self._document_cascade(ctx, root, resource)
        inherited = self._text_colour(cascade)
        candidates = []
        for span in spans:
            classes = frozenset((span.get("class") or "").split())
            declarations: dict[str, str] = {}
            for rule in cascade.rules:
                if rule.matches("span", classes, None):
                    declarations.update(rule.declarations)
            if not declarations:
                # Nothing reaches it. That is point [4]'s question, not this
                # one's, and the answer there was never "delete the markup".
                continue
            if any(
                not self._inert(prop, value, inherited)
                for prop, value in declarations.items()
            ):
                continue
            candidates.append(span)

        if not candidates:
            return
        if not ctx.policy.remove_dead:
            self.note(
                ctx,
                Level.INFO,
                "xhtml.empty-span-found",
                values={"count": len(candidates)},
                location=resource.path,
            )
            return
        for span in candidates:
            self._unwrap(span, keep_children=True)
        self.note(
            ctx,
            Level.FIX,
            "xhtml.empty-span-unwrapped",
            values={"count": len(candidates)},
            location=resource.path,
        )

    @staticmethod
    def _text_colour(cascade) -> "tuple[int, int, int]":
        """The colour a span would inherit if nothing gave it one."""
        for rule in cascade.rules:
            if rule.tag == "body" and "color" in rule.declarations:
                parsed = _colour(rule.declarations["color"])
                if parsed is not None:
                    return parsed
        return (0, 0, 0)

    def _inert(self, prop: str, value: str, inherited: "tuple[int, int, int]") -> bool:
        name, said = prop.lower(), (value or "").strip().lower()
        if name.startswith(("margin", "padding")):
            # Horizontal margins do apply to an inline box; zero is the default,
            # so zero is what makes them inert, not the fact of being inline.
            return all(css_cascade.is_zero_length(part) for part in said.split())
        if name == "color":
            here = _colour(said)
            return here is not None and all(
                abs(a - b) <= self.COLOUR_TOLERANCE for a, b in zip(here, inherited)
            )
        return said in self.INERT_VALUES.get(name, ())

    def _block_in_inline(self, ctx: Context, root, resource) -> None:
        """Repair a block-level box nested directly inside an inline one.

        Seen in the wild as a chapter heading built like::

            <h1><a href="toc.xhtml"><span class="numer">III</span>…</a></h1>

        where the stylesheet gives that span ``display: block``. A block inside
        an inline box forces the browser to split the inline into anonymous
        boxes; margins and centring on the heading then behave unpredictably.
        Promoting the inline wrapper to ``inline-block`` makes it a legal
        container without changing where it sits in the line.
        """
        cascade = self._document_cascade(ctx, root, resource)
        promoted = 0

        for element in xhtml.iter_elements(root):
            tag = xhtml.local_name(element).lower()
            if tag in {"html", "head", "body"}:
                continue
            display = css_cascade.effective_display(
                cascade,
                tag,
                frozenset((element.get("class") or "").split()),
                element.get("id"),
                element.get("style") or "",
            )
            if display != "inline":
                continue
            # Only direct children: a deeper block is the intermediate
            # element's problem, and it will be visited in its own right.
            has_block_child = any(
                css_cascade.is_block_level(
                    css_cascade.effective_display(
                        cascade,
                        xhtml.local_name(child).lower(),
                        frozenset((child.get("class") or "").split()),
                        child.get("id"),
                        child.get("style") or "",
                    )
                )
                for child in element
                if isinstance(child.tag, str)
            )
            if not has_block_child:
                continue
            _append_style(element, "display: inline-block;")
            promoted += 1

        if promoted:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.inline-promoted",
                values={"count": promoted},
                location=resource.path,
            )

    def _strip_shop_notice(self, element, resource) -> bool:
        """Take the shop's sentences out of *element*, and nothing else.

        WP-17. Sentence by sentence rather than element by element, and that is
        the whole safety of it: in Book 1 the stamp sits in the running text
        immediately in front of the novel's first sentence, so removing the
        element that contains it would remove the opening of the book.

        Three things this deliberately does not do:

        * **it does not remove a page.** The owner corrected me on exactly this:
          the job is the shop's leavings in the text, not documents. A document
          that ends up empty stays, empty, and the balance reports it — a
          rebuild that silently drops a spine item is a different program;
        * **it does not touch an element whose text is not the shop's.** A
          publisher's colophon carries an address, a telephone number, an e-mail
          and an ISBN, and names the publisher rather than the sale, so
          `is_shop_notice` says no to all of it;
        * **it does not count.** Every removed sentence is recorded verbatim for
          the report, because this is the one switch in the program that deletes
          text a person can read, and "3 fragments removed" is not something
          anybody can check.
        """
        text = element.text or ""
        kept, removed = watermark.without_shop_notices(text)
        if not removed:
            return False
        element.text = kept
        self._shop_notices_removed.extend(removed)
        self._shop_notice_documents.add(resource.path)
        return True

    def _watermarks(self, ctx: Context, root, resource) -> None:
        """Deal with a publisher's per-purchase marker, as the caller asked.

        A visible notice is never touched under any mode: it is a sentence the
        buyer is meant to read. What this handles is the opaque token, and what
        happens to it is :attr:`Policy.watermarks` — see
        :mod:`epubforge.watermark` for why the default moves it rather than
        merely hiding it.
        """
        mode = ctx.policy.watermarks
        if mode == "keep":
            return

        consolidated = 0
        notices: list[str] = []
        # Collected rather than acted on in the loop: `iter_elements` walks the
        # tree it is being asked about, and removing from underneath it is how
        # the second marker in a document gets skipped.
        displaced: list = []
        tokens: list[str] = []

        for element in xhtml.iter_elements(root):
            if len(element) or xhtml.local_name(element).lower() in {"html", "head", "body"}:
                continue
            text = (element.text or "").strip()
            if not text:
                continue

            if watermark.is_visible_notice(text):
                # Meant to be read; the buyer's own copy notice. Never restyled,
                # and removed only where somebody has asked for that (WP-17).
                # Recorded as kept only if it survived. A notice that has just
                # been taken out must not also be reported as preserved — two
                # findings contradicting each other in one report is worse than
                # either of them being absent.
                if ctx.policy.remove_shop_notices and self._strip_shop_notice(
                    element, resource
                ):
                    continue
                notices.append(text[:120])
                continue

            style = element.get("style") or ""
            if not watermark.is_token(text) or not watermark.is_negligibly_styled(style):
                continue
            self._watermark_tokens.add(text)

            if mode == "consolidate":
                element.attrib.pop("style", None)
                classes = (element.get("class") or "").split()
                if watermark.MARKER_CLASS not in classes:
                    classes.append(watermark.MARKER_CLASS)
                element.set("class", " ".join(classes))
                # Hides it from the accessibility tree. Not from a reader's own
                # text-to-speech, which is why this is no longer the default.
                element.set("aria-hidden", "true")
                consolidated += 1
            else:
                displaced.append(element)
                if text not in tokens:
                    tokens.append(text)

        if consolidated:
            for sheet in self._linked_stylesheets(ctx, root, resource):
                ctx.watermark_stylesheets.add(sheet)
            self._watermarks_consolidated += consolidated
            self._watermark_documents += 1

        if displaced:
            if mode == "gather":
                self._gather_tokens(root, tokens)
                self._watermarks_relocated += len(displaced)
            else:
                self._watermarks_removed += len(displaced)
            for element in displaced:
                # Not `parent.remove`: the marker sits at the end of a chapter
                # and whatever whitespace or text trailed it belongs to the
                # chapter, not to the marker.
                self._unwrap(element, keep_children=False)
            self._watermark_documents += 1

        self._watermark_notices.extend(notices)

    def _gather_tokens(self, root, tokens: list[str]) -> None:
        """Park the tokens in the document's own ``<head>``.

        One ``<meta>`` per distinct token, in the document the token came from,
        so a shop tracing a leak finds it exactly where it put it. The skeleton
        pass guarantees a ``<head>`` exists by the time this runs.
        """
        head = root.find(xhtml.qname("head"))
        if head is None:
            return
        already = {
            meta.get("content")
            for meta in head.iter(xhtml.qname("meta"))
            if meta.get("name") == watermark.META_NAME
        }
        for token in tokens:
            if token in already:
                continue
            meta = etree.SubElement(head, xhtml.qname("meta"))
            meta.set("name", watermark.META_NAME)
            meta.set("content", token)

    def _linked_stylesheets(self, ctx: Context, root, resource) -> list[str]:
        found = []
        for link in root.iter(xhtml.qname("link")):
            if "stylesheet" not in (link.get("rel") or "").lower():
                continue
            href = link.get("href")
            target = paths.resolve(resource.path, href) if href else None
            sheet = ctx.book.get(target) if target else None
            if sheet is not None and sheet.is_style:
                found.append(sheet.path)
        return found

    def _presentational_attributes(self, element, tag: str, changed: set[str]) -> None:
        declarations: list[str] = []

        align = (element.get("align") or "").strip().lower()
        if align:
            if tag == "img" and align in {"left", "right"}:
                declarations.append(f"float: {align};")
            elif tag == "table" and align == "center":
                declarations.append("margin-left: auto; margin-right: auto;")
            elif align in {"left", "right", "center", "justify"}:
                declarations.append(f"text-align: {align};")
            element.attrib.pop("align", None)
            changed.add("align")

        valign = (element.get("valign") or "").strip().lower()
        if valign:
            declarations.append(f"vertical-align: {valign};")
            element.attrib.pop("valign", None)
            changed.add("valign")

        for attribute, property_name in (("bgcolor", "background-color"), ("color", "color")):
            value = element.get(attribute)
            if value and tag != "font":
                declarations.append(f"{property_name}: {value.strip()};")
                element.attrib.pop(attribute, None)
                changed.add(attribute)

        # The rest of the HTML 3.2 `<body>` palette. `bgcolor` was handled from
        # the start and these four were not, which is how a Dutch and English
        # shelf of 67 books produced forty-two EPUBCheck errors in one run —
        # `text`, `link`, `vlink` and `bordercolor`, all of them written by
        # Word and Sigil and all of them still meaning something on the page.
        #
        # `text` is the body's colour and translates exactly. The link colours
        # do not have a plain equivalent, because CSS says them with pseudo
        # classes and an inline style cannot hold one; they are dropped and
        # counted rather than guessed at, since inventing `a:link { }` in a
        # shared stylesheet would reach documents nobody looked at.
        if tag == "body":
            text_colour = element.get("text")
            if text_colour:
                declarations.append(f"color: {text_colour.strip()};")
                element.attrib.pop("text", None)
                changed.add("text")
            for attribute in ("link", "vlink", "alink"):
                if element.get(attribute) is not None:
                    element.attrib.pop(attribute, None)
                    changed.add(attribute)

        # Table borders in colour, from the same era and the same generators.
        if element.get("bordercolor") is not None:
            colour = element.get("bordercolor").strip()
            if colour:
                declarations.append(f"border-color: {colour};")
            element.attrib.pop("bordercolor", None)
            changed.add("bordercolor")

        # `target` tells a browser which window to open a link in. An EPUB has
        # no windows, EPUB 3 does not allow the attribute, and removing it
        # changes nothing anybody can see.
        #
        # Not only on `<a>`, which is where this looked for it and where it never
        # actually was. Two books on the mixed shelf kept an `RSC-005` about
        # `target` through `preserve` and lost it in `strict` — which is not the
        # attribute being handled but the element carrying it being unwrapped by
        # a strict-only cleanup, and the tell that it was sitting somewhere else
        # entirely. A converter copies attributes wholesale; `target` on a
        # `<span>` renders exactly as `target` on an `<a>` does, which is not at
        # all.
        if element.get("target") is not None:
            element.attrib.pop("target", None)
            changed.add("target")

        # `value` numbers an item in an ordered list and means nothing anywhere
        # else. The `<li>` case is handled below, on its own terms; this is the
        # attribute turning up on elements that never had a use for it, which
        # is what a converter does when it copies attributes wholesale.
        if tag not in ("li", "option", "param", "input", "button", "data", "meter", "progress"):
            if element.get("value") is not None:
                element.attrib.pop("value", None)
                changed.add("value")

        if tag == "table":
            border = element.get("border")
            if border is not None:
                width = _css_length(border) or "1px"
                declarations.append(
                    "border-style: solid; border-width: %s;" % ("0" if border.strip() == "0" else width)
                )
                element.attrib.pop("border", None)
                changed.add("border")
            spacing = element.get("cellspacing")
            if spacing is not None:
                length = _css_length(spacing)
                if length:
                    declarations.append(f"border-spacing: {length};")
                element.attrib.pop("cellspacing", None)
                changed.add("cellspacing")
            element.attrib.pop("cellpadding", None)
            element.attrib.pop("summary", None)

        for attribute, properties in (("hspace", ("margin-left", "margin-right")), ("vspace", ("margin-top", "margin-bottom"))):
            value = element.get(attribute)
            if value:
                length = _css_length(value)
                if length:
                    declarations.extend(f"{prop}: {length};" for prop in properties)
                element.attrib.pop(attribute, None)
                changed.add(attribute)

        # HTML 5 allows `value` on a list item only inside an ordered list,
        # where it sets the number. Inside `<ul>` it numbers nothing and no
        # renderer has ever drawn it — but it makes the document invalid, and
        # a MOBI back-conversion carries one on every bullet it ever had.
        if tag == "li" and element.get("value") is not None:
            parent = element.getparent()
            if parent is None or xhtml.local_name(parent).lower() != "ol":
                element.attrib.pop("value", None)
                changed.add("li[value]")

        if tag == "br" and element.get("clear"):
            clear = element.get("clear").strip().lower()
            declarations.append(f"clear: {'both' if clear == 'all' else clear};")
            element.attrib.pop("clear", None)
            changed.add("br[clear]")

        # HTML 5 keeps width/height on replaced elements, but only as bare
        # integers. XHTML 1.1 allowed percentages, so EPUB 2 books carry values
        # like width="10%" that make an EPUB 3 parser reject the document.
        replaced = tag in {"img", "canvas", "video", "iframe", "embed", "object", "svg"}
        for attribute in ("width", "height"):
            value = (element.get(attribute) or "").strip()
            if not value:
                continue
            if replaced and re.fullmatch(r"\d+", value):
                continue
            length = _css_length(value)
            if length:
                declarations.append(f"{attribute}: {length};")
            element.attrib.pop(attribute, None)
            changed.add(attribute)

        for obsolete in ("nowrap", "compact", "noshade", "frameborder", "scrolling", "language"):
            if element.get(obsolete) is not None:
                element.attrib.pop(obsolete, None)
                changed.add(obsolete)

        declarations.extend(self._sweep_unknown_attributes(element, tag, changed))

        _append_style(element, " ".join(declarations))

    @staticmethod
    def _sweep_unknown_attributes(element, tag: str, changed: set[str]) -> "list[str]":
        """Whatever is left that XHTML5 does not allow on this element.

        Everything above this names an attribute and says what it means. That
        answers the attributes somebody thought of; it does not answer the ones
        a converter invents. The owner's second shelf produced `font17` and `p`
        — not misspellings of anything, just an exporter writing its own state
        into the markup — alongside `clear` and `size` sitting on elements that
        never took them. Each is an `RSC-005` in a book this program rebuilt,
        and each was reached by a route no list of known names would cover.

        So the rule runs the other way: an attribute this element is not
        allowed to carry is one **no engine reads**, and that is exactly what
        makes removing it safe. Where it is a legacy attribute that still means
        something to a page — `clear`, `<hr size>` — the meaning is translated
        into CSS first and the appearance survives the removal. Anything under a
        prefix that carries its own vocabulary is not touched at all.

        The direction matters: an element this table has never heard of is
        judged on the global attributes alone, so an unknown element keeps
        everything the globals permit rather than being stripped on a guess.
        """
        # SVG and MathML are whole other vocabularies inside an XHTML document,
        # with their own attribute names on their own elements — `viewBox`, `d`,
        # `fill`, `display`. Judging them by the HTML tables would strip a
        # drawing of its coordinate system, which the suite caught within a
        # minute of this being written and is the reason the exemption is by
        # **namespace** rather than by a list of element names: an SVG document
        # can contain elements this program has never heard of.
        if isinstance(element.tag, str) and element.tag.startswith("{"):
            namespace = element.tag[1:].split("}", 1)[0]
            if namespace != xhtml.XHTML_NS:
                return []

        allowed = _GLOBAL_ATTRIBUTES | _ELEMENT_ATTRIBUTES.get(tag, frozenset())
        declarations: list[str] = []
        for name in list(element.attrib):
            if name.startswith("{"):
                continue  # namespaced: xml:lang, epub:type, and anybody else's
            plain = name.lower()
            if plain in allowed or plain in _KEPT_ANYWHERE:
                continue
            if plain.startswith(_KEPT_PREFIXES):
                continue
            value = (element.get(name) or "").strip()
            translated = _translate_stray(tag, plain, value)
            if translated:
                declarations.append(translated)
            element.attrib.pop(name, None)
            changed.add(f"{tag}[{plain}]")
        return declarations

    def _unwrap(self, element, keep_children: bool) -> None:
        """Replace an element with its children (or remove it entirely)."""
        parent = element.getparent()
        if parent is None:
            return
        index = list(parent).index(element)
        tail = element.tail or ""
        moved = []
        if keep_children:
            previous_text = element.text or ""
            if previous_text:
                if index == 0:
                    parent.text = (parent.text or "") + previous_text
                else:
                    sibling = parent[index - 1]
                    sibling.tail = (sibling.tail or "") + previous_text
            moved = list(element)
            for offset, child in enumerate(moved):
                parent.insert(index + offset, child)
        if tail:
            # After the last thing that came out of the element, not before it.
            # This used to attach the tail to the element *preceding* the one
            # being unwrapped, which for `<p>x<span>b<i>i</i>t</span>c</p>` put
            # the "c" in front of the `<i>` — every character still present and
            # two of them in the wrong order. K1 compares a stream in order, so
            # it would have read as text lost rather than text moved.
            if moved:
                last = moved[-1]
                last.tail = (last.tail or "") + tail
            elif index > 0:
                sibling = parent[index - 1]
                sibling.tail = (sibling.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
        parent.remove(element)

    def _accessibility(self, ctx: Context, root, resource) -> None:
        """Give every image an alt, and describe the cover rather than hiding it.

        An empty alt is not a neutral placeholder — it tells assistive software
        the image carries no information. That is the right answer for a rule or
        a flourish and the wrong one for cover art, which is why the cover is
        named. Everything else is counted here and reported by the accessibility
        stage, because inventing descriptions is not this tool's job.
        """
        cover_path = ctx.book.cover_path
        missing_alt = 0
        described = 0

        for image in root.iter(xhtml.qname("img")):
            alt = image.get("alt")
            source = image.get("src")
            target = paths.resolve(resource.path, source) if source else None
            is_cover = bool(cover_path) and target == cover_path

            if is_cover and (alt is None or is_placeholder_alt(alt, source)):
                # The cover depicts the book, so its title is a true description
                # — unlike "cover", which names the slot rather than the picture.
                image.set("alt", ctx.book.metadata.title)
                described += 1
            elif alt is None:
                image.set("alt", "")
                missing_alt += 1

        if described:
            self.note(ctx, Level.FIX, "xhtml.cover-described", location=resource.path)
        if missing_alt:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.empty-alt-added",
                values={"count": missing_alt},
                location=resource.path,
            )

    def _scripting(self, ctx: Context, root, resource) -> None:
        scripts = list(root.iter(xhtml.qname("script")))
        handlers = [
            (element, key)
            for element in xhtml.iter_elements(root)
            for key in list(element.attrib)
            if isinstance(key, str) and key.lower().startswith("on")
        ]
        if not scripts and not handlers:
            return
        if not ctx.policy.strip_scripts:
            self.note(
                ctx,
                Level.PRESERVED,
                "xhtml.scripts-kept",
                values={"count": len(scripts)},
                location=resource.path,
            )
            return
        for script in scripts:
            parent = script.getparent()
            if parent is not None:
                parent.remove(script)
        for element, key in handlers:
            element.attrib.pop(key, None)
        self.note(
            ctx,
            Level.FIX,
            "xhtml.scripts-removed",
            values={"count": len(scripts), "handlers": len(handlers)},
            location=resource.path,
        )

    def _properties(self, ctx: Context, root, resource) -> None:
        """Derive the manifest properties EPUB 3 requires to be declared."""
        properties = {p for p in resource.properties if p in {"nav", "cover-image"}}

        # `any(root.iter(...))` truth-tests the elements themselves, and an
        # lxml element with no children is falsy — so a document whose only
        # script was `<script>void 0;</script>` came out undeclared, and lxml
        # had been warning about exactly this in a FutureWarning nobody read.
        # The svg and mathml checks below were already written the right way.
        if any(True for _ in root.iter(xhtml.qname("script"))) or any(
            key.lower().startswith("on")
            for element in xhtml.iter_elements(root)
            for key in element.attrib
            if isinstance(key, str)
        ):
            properties.add("scripted")
        if any(True for _ in root.iter(f"{{{xhtml.SVG_NS}}}svg")):
            properties.add("svg")
        if any(True for _ in root.iter(f"{{{xhtml.MATHML_NS}}}math")):
            properties.add("mathml")

        # "remote-resources" is about resources the document *embeds*, not about
        # where its hyperlinks point; declaring it for an ordinary <a href> to a
        # website is a conformance error in its own right.
        for element in xhtml.iter_elements(root):
            tag = xhtml.local_name(element).lower()
            if tag == "a":
                continue
            for attribute in ("src", "poster", "data", f"{{{XLINK_NS}}}href") + (
                ("href",) if tag in {"link", "image", "use"} else ()
            ):
                value = element.get(attribute)
                if value and paths.is_remote(value) and not value.lower().startswith(
                    ("mailto:", "tel:", "data:")
                ):
                    properties.add("remote-resources")
                    break

        withdrawn = sorted(resource.properties - properties)
        if withdrawn:
            # Silent until 0.2.3. A manifest property is a claim about the
            # document — that it scripts, that it holds MathML — and a reading
            # system acts on it. Withdrawing one because the document does not
            # bear it out is right, and doing it without saying so is not: the
            # publisher gets a package that differs from theirs with nothing in
            # the report to explain why.
            self.note(
                ctx,
                Level.FIX,
                "xhtml.property-withdrawn",
                values={"properties": ", ".join(withdrawn)},
                location=resource.path,
            )
        resource.properties = properties


