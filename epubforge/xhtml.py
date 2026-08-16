"""Parsing and serialising XHTML content documents from unreliable sources.

Content documents in shipped books are XML in name only: undefined HTML
entities, unclosed void elements, tag soup from HTML-to-EPUB converters. This
module recovers a tree from all of that and always emits well-formed XHTML 5.
"""

from __future__ import annotations

import re
from html import escape
from html.entities import html5

from typing import NamedTuple

from lxml import etree, html as lxml_html

from . import budget

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
SVG_NS = "http://www.w3.org/2000/svg"
MATHML_NS = "http://www.w3.org/1998/Math/MathML"
XLINK_NS = "http://www.w3.org/1999/xlink"

XML_PARSER = etree.XMLParser(recover=False, resolve_entities=False, huge_tree=True)
RECOVERING_XML_PARSER = etree.XMLParser(recover=True, resolve_entities=False, huge_tree=True)
HTML_PARSER = lxml_html.HTMLParser(recover=True, encoding="utf-8")

#: Predefined in XML, so they must not be rewritten to numeric form.
_XML_BUILTIN = {"lt", "gt", "amp", "quot", "apos"}

#: Serialising these as ``<div/>`` breaks readers that fall back to an HTML parser.
_NEVER_SELF_CLOSE = {
    "a", "abbr", "address", "article", "aside", "audio", "b", "bdi", "bdo", "blockquote",
    "body", "button", "canvas", "caption", "cite", "code", "colgroup", "data", "datalist",
    "dd", "del", "details", "dfn", "dialog", "div", "dl", "dt", "em", "fieldset",
    "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head",
    "header", "hgroup", "html", "i", "iframe", "ins", "kbd", "label", "legend", "li",
    "main", "map", "mark", "menu", "meter", "nav", "noscript", "object", "ol", "optgroup",
    "option", "output", "p", "picture", "pre", "progress", "q", "rp", "rt", "ruby", "s",
    "samp", "script", "section", "select", "small", "span", "strong", "style", "sub",
    "summary", "sup", "table", "tbody", "td", "textarea", "tfoot", "th", "thead", "time",
    "title", "tr", "u", "ul", "var", "video",
}

_SVG_TAGS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text",
    "tspan", "defs", "use", "image", "symbol", "marker", "clippath", "mask", "pattern",
    "lineargradient", "radialgradient", "stop", "filter", "desc", "title", "switch",
    "foreignobject", "animate", "animatetransform", "textpath", "animatemotion",
    "feblend", "fecolormatrix", "fecomponenttransfer", "fecomposite",
    "feconvolvematrix", "fediffuselighting", "fedisplacementmap", "fedistantlight",
    "fedropshadow", "feflood", "fefunca", "fefuncb", "fefuncg", "fefuncr",
    "fegaussianblur", "feimage", "femerge", "femergenode", "femorphology", "feoffset",
    "fepointlight", "fespecularlighting", "fespotlight", "fetile", "feturbulence",
}

#: SVG names that are not all-lowercase, keyed by what an HTML parser turns
#: them into.
#:
#: The audit's F-004, and the reason it is a finding rather than a curiosity:
#: **SVG is case-sensitive and HTML is not.** A document that has to be
#: recovered by the HTML parser comes back with `linearGradient` spelled
#: `lineargradient`, which is not the SVG element of that name — it is nothing,
#: and the shape it filled draws in flat black or not at all. The same for
#: `viewBox`, without which the drawing has no coordinate system to scale into.
#:
#: Restoring the spelling is a deterministic repair: there is exactly one
#: correct capitalisation of each of these names, and it is written down here.
#: Nothing is guessed and nothing outside the table is touched.
_SVG_CAMEL_ELEMENTS = {
    name.lower(): name
    for name in (
        "linearGradient", "radialGradient", "clipPath", "foreignObject", "textPath",
        "animateTransform", "animateMotion", "feBlend", "feColorMatrix",
        "feComponentTransfer", "feComposite", "feConvolveMatrix", "feDiffuseLighting",
        "feDisplacementMap", "feDistantLight", "feDropShadow", "feFlood", "feFuncA",
        "feFuncB", "feFuncG", "feFuncR", "feGaussianBlur", "feImage", "feMerge",
        "feMergeNode", "feMorphology", "feOffset", "fePointLight",
        "feSpecularLighting", "feSpotLight", "feTile", "feTurbulence",
    )
}

_SVG_CAMEL_ATTRIBUTES = {
    name.lower(): name
    for name in (
        "viewBox", "preserveAspectRatio", "gradientUnits", "gradientTransform",
        "spreadMethod", "patternUnits", "patternContentUnits", "patternTransform",
        "clipPathUnits", "maskUnits", "maskContentUnits", "markerUnits", "markerWidth",
        "markerHeight", "refX", "refY", "textLength", "lengthAdjust", "startOffset",
        "baseFrequency", "numOctaves", "stdDeviation", "kernelMatrix", "pathLength",
        "diffuseConstant", "specularConstant", "specularExponent", "surfaceScale",
        "requiredFeatures", "requiredExtensions", "systemLanguage", "attributeName",
        "attributeType", "repeatCount", "repeatDur", "keyPoints", "keyTimes",
        "keySplines", "calcMode", "xChannelSelector", "yChannelSelector",
        "primitiveUnits", "filterUnits", "edgeMode", "tableValues", "targetX",
        "targetY", "baseProfile", "zoomAndPan",
    )
}


def _restore_svg_case(root) -> int:
    """Put the capitals back on SVG names an HTML parse folded away.

    Only inside an `<svg>` subtree, and only names in the tables above: outside
    SVG, lowercase is correct and "restoring" anything would be inventing it.
    """
    restored = 0
    for svg in root.iter(f"{{{SVG_NS}}}svg"):
        for element in svg.iter():
            if not isinstance(element.tag, str) or not element.tag.startswith(f"{{{SVG_NS}}}"):
                continue
            local = element.tag.rpartition("}")[2]
            correct = _SVG_CAMEL_ELEMENTS.get(local)
            if correct and correct != local:
                element.tag = f"{{{SVG_NS}}}{correct}"
                restored += 1
            for key in list(element.attrib):
                if not isinstance(key, str) or key.startswith("{"):
                    continue
                proper = _SVG_CAMEL_ATTRIBUTES.get(key)
                if proper and proper != key:
                    element.set(proper, element.attrib.pop(key))
                    restored += 1
    return restored


_ENTITY_RE = re.compile(rb"&([A-Za-z][A-Za-z0-9]{1,31});")
_XML_DECL_RE = re.compile(rb"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
_DOCTYPE_RE = re.compile(rb"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", re.IGNORECASE)
_STYLESHEET_PI_RE = re.compile(rb"<\?xml-stylesheet[^>]*\?>", re.IGNORECASE)
_PI_HREF_RE = re.compile(rb"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def _numeric_entities(data: bytes) -> bytes:
    """Rewrite named HTML entities to numeric ones so an XML parser accepts them."""

    def replace(match: re.Match) -> bytes:
        name = match.group(1).decode("ascii")
        if name in _XML_BUILTIN:
            return match.group(0)
        char = html5.get(name + ";") or html5.get(name)
        if not char:
            return match.group(0)
        return "".join(f"&#{ord(c)};" for c in char).encode("ascii")

    return _ENTITY_RE.sub(replace, data)


def _strip_internal_dtd(data: bytes) -> bytes:
    """Drop the DOCTYPE, including any internal subset declaring custom entities."""
    return _DOCTYPE_RE.sub(b"", data, count=1)


#: Entity declarations in an internal subset, in the only form worth expanding:
#: a name and a quoted literal. `SYSTEM` and `PUBLIC` declarations deliberately
#: do not match — a file does not get to tell this tool to fetch something.
_ENTITY_DECL_RE = re.compile(rb"""<!ENTITY\s+([A-Za-z_][\w.\-]*)\s+(["'])(.*?)\2\s*>""", re.S)
_EXTERNAL_ENTITY_RE = re.compile(rb"<!ENTITY\s+([A-Za-z_][\w.\-]*)\s+(?:SYSTEM|PUBLIC)\b", re.I)
_INTERNAL_SUBSET_RE = re.compile(rb"<!DOCTYPE[^>\[]*\[(.*?)\]", re.S | re.I)

#: An entity may name another entity. Four levels is far past anything a real
#: book uses and far short of anything that could run away.
_MAX_ENTITY_DEPTH = 4
#: A document that expands tenfold is not a document, it is an attack.
_MAX_ENTITY_GROWTH = 10


def expand_internal_entities(data: bytes) -> tuple[bytes, list[str], list[str]]:
    """Resolve entities declared in the internal subset, before it is thrown away.

    Returns the rewritten bytes, the names expanded, and the names refused.

    The subset has to go — it can declare anything, and the EPUB 3 `<!DOCTYPE
    html>` that replaces it declares nothing. But the *references* to those
    entities live in the text, and once the declaration is gone they resolve to
    nothing: the ampersand gets escaped and `&mypauza;` appears on the page as
    six literal characters. The reader sees markup where a dash should be.

    Expanded here rather than by the parser, and that is the whole point.
    Handing this to libxml2 means turning `resolve_entities` back on, which is
    what closes XXE and the billion-laughs expansion in the first place. Doing
    it here keeps both shut: external declarations are never resolved, nesting
    is bounded, and a document that tries to grow tenfold is refused outright.
    """
    subset = _INTERNAL_SUBSET_RE.search(data)
    if not subset:
        return data, [], []

    declarations = subset.group(1)
    refused = [
        name.decode("ascii", "replace")
        for name, in (m.groups()[:1] for m in _EXTERNAL_ENTITY_RE.finditer(declarations))
    ]

    values: dict[bytes, bytes] = {}
    for match in _ENTITY_DECL_RE.finditer(declarations):
        values[match.group(1)] = match.group(3)
    if not values:
        return data, [], refused

    body = data[subset.end():]
    limit = len(data) * _MAX_ENTITY_GROWTH
    used: set[str] = set()

    for _ in range(_MAX_ENTITY_DEPTH):
        replaced = False

        def substitute(match: re.Match) -> bytes:
            nonlocal replaced
            name = match.group(1)
            if name not in values:
                return match.group(0)
            replaced = True
            used.add(name.decode("ascii", "replace"))
            return values[name]

        expanded = _ENTITY_RE.sub(substitute, body)
        if len(expanded) > limit:
            # Refuse the lot rather than half of it: a partially expanded
            # document is harder to reason about than an untouched one.
            return data, [], refused + sorted(used)
        body = expanded
        if not replaced:
            break

    return data[: subset.end()] + body, sorted(used), refused


def _namespacify(element, default_ns: str = XHTML_NS):
    """Rebuild a namespace-less (HTML-parsed) tree into a namespaced XHTML tree."""
    tag = element.tag
    if not isinstance(tag, str):
        copy = etree.Comment(element.text) if tag is etree.Comment else etree.ProcessingInstruction("x", "")
        return copy

    local = tag.rpartition("}")[2].lower()
    ns = default_ns
    if local == "svg":
        ns = SVG_NS
    elif local == "math":
        ns = MATHML_NS
    elif default_ns in (SVG_NS, MATHML_NS):
        ns = default_ns if local in _SVG_TAGS or default_ns == MATHML_NS else default_ns

    new = etree.Element(f"{{{ns}}}{local}")
    for key, value in element.attrib.items():
        if not isinstance(key, str):
            continue
        # The HTML parser has no namespace support, so it hands back xmlns
        # declarations as ordinary attributes; re-setting them would emit a
        # duplicate, conflicting declaration.
        if key == "xmlns" or key.startswith("xmlns:"):
            continue
        if key.startswith("{"):
            new.set(key, value)
        elif ":" in key:
            prefix, _, rest = key.partition(":")
            mapped = {"epub": EPUB_NS, "xlink": XLINK_NS, "xml": "http://www.w3.org/XML/1998/namespace"}.get(prefix)
            new.set(f"{{{mapped}}}{rest}" if mapped else rest, value)
        else:
            new.set(key, value)
    new.text = element.text
    new.tail = element.tail
    for child in element:
        new.append(_namespacify(child, ns))
    return new


class ParseResult(NamedTuple):
    """A parsed document plus what had to be done to it on the way in."""

    root: etree._Element
    #: ``"xml"`` when the source was already well-formed, ``"xml-entities"``
    #: when only entity rewriting was needed, ``"html"`` after a tag-soup
    #: recovery.
    mode: str
    #: Entities declared in the internal subset and resolved before it was
    #: dropped. A content change, so the caller has to report it.
    entities_expanded: list[str] = []
    #: Entity declarations refused — external, or past the expansion limits.
    entities_refused: list[str] = []
    #: The encoding this document turned out to really be in, when that is not
    #: what it said. Empty when the declaration was true.
    encoding_mended: str = ""
    #: Stylesheet hrefs found in `<?xml-stylesheet?>` processing instructions.
    #:
    #: The PI is how an XHTML document written before EPUB 3 links a stylesheet,
    #: and it was being deleted here without a word — one `sub()` at the top of
    #: the parse, so a book styled that way came out unstyled and the report
    #: said nothing. It is a construct that carries visual meaning, which under
    #: this project's own rule is translated rather than removed; the caller
    #: turns each of these into a `<link rel="stylesheet">`.
    stylesheet_links: list[str] = []
    #: SVG names an HTML recovery had folded to lowercase and that were put back.
    svg_case_restored: int = 0



#: How a document says what it is encoded in, in the order a reading system
#: asks. `latin-1` is deliberately absent from the fallbacks tried here even
#: though `Resource.decoded` has it: it decodes every byte sequence ever
#: written, so it can only ever be a last resort, and a last resort that
#: silently succeeds is how a mojibake book gets called repaired.
_DECLARED_ENCODING = re.compile(
    rb'(?:<\?xml[^>]*encoding=["\']([A-Za-z0-9_.\-]+)["\']'
    rb'|<meta[^>]*charset=["\']?([A-Za-z0-9_.\-]+))',
    re.IGNORECASE,
)

_ENCODINGS_BOOKS_ACTUALLY_USE = ("cp1250", "cp1252")


def mend_encoding(data: bytes) -> tuple[bytes, str]:
    """Read a document that lies about its encoding, without inventing anything.

    Measured on 0.2.21: a chapter declaring `encoding="utf-8"` and carrying one
    `0x92` — an apostrophe in the Windows-1250 an older Polish shop wrote — was
    handed to lxml, which recovered by substituting `U+FFFD`. The output was
    valid UTF-8, the report said **nothing**, and a character of the book was
    gone. K1 says no character of the book's text is lost; this was the path
    that lost one and called it a repair.

    **The declaration chooses the method, the bytes fill in the details**, and
    the first version of this got that backwards with an interesting result
    worth keeping written down. It asked only "does some legacy encoding decode
    the whole file and round-trip?" — and for a UTF-8 document with one stray
    byte, `cp1250` answers yes. The file came back with every Polish letter
    reinterpreted: `jaźń` became `jaĹşĹ„`. One `U+FFFD` had been replaced by a
    document of mojibake, which is a worse outcome arrived at by a better
    intention.

    So:

    * a document declaring a legacy encoding is **believed**, and re-encoded to
      UTF-8 whole with its declaration corrected;
    * a document declaring UTF-8, or nothing, that is UTF-8 apart from a few
      bytes is **repaired byte by byte** — each invalid byte is read as
      Windows-1250, which is what it almost always is, and the rest of the
      document is left exactly as it was.

    Returns the bytes to parse, and what was done — empty when the document was
    telling the truth.
    """
    try:
        data.decode("utf-8")
        return data, ""
    except UnicodeDecodeError:
        pass

    found = _DECLARED_ENCODING.search(data[:2048])
    declared = next(
        (group.decode("ascii", "ignore") for group in (found.groups() if found else ()) if group),
        "",
    )
    normalised = declared.lower().replace("_", "-")

    def redeclare(mended: bytes) -> bytes:
        """Point the declaration at what the bytes now are."""
        if not found:
            return mended
        return _DECLARED_ENCODING.sub(
            lambda m: m.group(0).replace((m.group(1) or m.group(2)), b"utf-8"), mended, count=1
        )

    if normalised and normalised not in ("utf-8", "utf8"):
        try:
            text = data.decode(declared)
            if text.encode(declared) == data:
                return redeclare(text.encode("utf-8")), declared
        except (UnicodeDecodeError, LookupError):
            pass

    # Declared UTF-8 and nearly is. Rescue the stray bytes where they stand.
    rescued = bytearray()
    remaining = data
    repaired = 0
    while True:
        try:
            remaining.decode("utf-8")
        except UnicodeDecodeError as bad:
            rescued += remaining[: bad.start]
            rescued += remaining[bad.start : bad.end].decode("cp1250", "replace").encode("utf-8")
            repaired += bad.end - bad.start
            remaining = remaining[bad.end :]
            continue
        rescued += remaining
        break
    if repaired:
        return redeclare(bytes(rescued)), f"utf-8, {repaired} stray byte(s) read as cp1250"
    return data, ""


def parse_document(data: bytes, where: str = "") -> ParseResult:
    """Parse an XHTML document and say what it cost.

    Most callers only want the tree; :func:`parse` is the two-value form for
    them. This is for the one that has to report what changed.
    """
    data, mended = mend_encoding(data)
    # Captured before it is removed. Removing it is right — EPUB 3 documents
    # link stylesheets with `<link>` — but only once what it *said* has been
    # carried over.
    stylesheet_links = [
        href for href in (
            _PI_HREF_RE.search(match.group(0)) for match in _STYLESHEET_PI_RE.finditer(data)
        ) if href
    ]
    stylesheet_links = [
        match.group(1).decode("utf-8", "replace") for match in stylesheet_links
    ]
    prepared = _STYLESHEET_PI_RE.sub(b"", data)

    # Before the DOCTYPE is dropped, because dropping it is what strands the
    # references to anything it declared.
    prepared, expanded, refused = expand_internal_entities(prepared)

    # Entities must be rewritten *before* the strict parse, not as a fallback
    # after it. With resolve_entities=False lxml accepts an undeclared &nbsp;
    # as an entity node and parsing succeeds, so the reference survives into the
    # output — where the EPUB 3 <!DOCTYPE html> does not declare it and readers
    # fail fatally on the file.
    normalized = _numeric_entities(_strip_internal_dtd(prepared))
    mode = "xml" if normalized == prepared else "xml-entities"

    # The content-document half of F-019. Charged here rather than at the
    # callers because this is the one function every content document in the
    # program goes through, and the finding was precisely that a limit reachable
    # only by remembering to call it is a limit nobody calls. Measured on the
    # *normalised* bytes: those are what a parser is about to be handed, and an
    # entity expansion that multiplies the document is the attack this counts.
    budget.bounded(normalized, where)

    try:
        root = etree.fromstring(normalized, XML_PARSER)
    except etree.XMLSyntaxError:
        root = None

    if root is not None and isinstance(root.tag, str):
        # Well-formed but namespace-less documents parse cleanly as XML and
        # would then fail every namespaced lookup downstream.
        tree = root if root.tag.startswith("{") else _namespacify(root)
        return ParseResult(tree, mode, expanded, refused, mended, stylesheet_links)

    html_root = lxml_html.document_fromstring(
        normalized or b"<html><body></body></html>", parser=HTML_PARSER
    )
    tree = _namespacify(html_root)
    # Only on this path. A document the XML parser accepted never lost its
    # capitals, so there is nothing to restore and nothing to report.
    restored = _restore_svg_case(tree)
    return ParseResult(tree, "html", expanded, refused, "", stylesheet_links, restored)


def parse(data: bytes) -> tuple[etree._Element, str]:
    """The tree and the recovery mode, for callers that need nothing else."""
    result = parse_document(data)
    return result.root, result.mode


def strip_doctype(data: bytes) -> bytes:
    """Public form of the DOCTYPE removal, for tools that parse a *source* file.

    `lxml.html` loses its footing on an internal subset — it fails to find
    `<body>` and hands back the stray `]>` as text. Anything comparing a source
    document with a rebuilt one has to remove the subset from the source first,
    or the difference it reports is the DOCTYPE rather than the content.
    """
    return _DOCTYPE_RE.sub(b"", data, count=1)


#: The only DOCTYPE EPUB 3 accepts. EPUBCheck on anything else: *Irregular
#: DOCTYPE: found "-//W3C//DTD XHTML 1.1//EN", expected "<!DOCTYPE html>"*.
EPUB3_DOCTYPE = b"<!DOCTYPE html>"

#: `&name;`. Numeric references need no declaration and are not matched.
_ENTITY_REFERENCE = re.compile(rb"&([A-Za-z][A-Za-z0-9]*);")

#: The only entities an XML parser knows without being told.
_XML_BUILTIN_ENTITIES = {b"amp", b"lt", b"gt", b"quot", b"apos"}


def modernise_doctype(data: bytes) -> tuple[bytes, bool]:
    """Swap a legacy DOCTYPE for the EPUB 3 one, touching nothing else.

    For the container-only mode, which does not open documents at all. A
    DOCTYPE declares nothing about how a page looks, so replacing it is the one
    change that cannot alter rendering — but it is what stands between a
    container-only rebuild and a valid EPUB 3, and roughly half the older books
    in a real library carry the XHTML 1.1 one.

    A legacy DOCTYPE declares entities two ways — an internal subset, and the
    external DTD it names — and the second is the one that matters in practice:
    every XHTML 1.1 document may write `&nbsp;` because `xhtml11.dtd` declares
    it. Under EPUB 3 no external DTD is fetched, so the reference is stranded
    and EPUBCheck stops at *Fatal Error while parsing file: The entity "nbsp"
    was referenced, but not declared*. Four of thirty-two real books were in
    that state, and the whole of one book's 235 errors traced back to seven
    documents failing to parse for this reason.

    So the named entities go with it, rewritten to numeric references — the
    same character, byte-for-byte identical on screen, and needing no
    declaration at all. What this mode promises is that the book looks the same,
    and bytes were only ever a convenient way of keeping that promise.

    Returns the data unchanged when something in it cannot be resolved: an
    internal subset, whose entities are the book's own, or a name no HTML
    vocabulary knows. Refusing there is the point — a book that will not open is
    worse than a book that is merely invalid.
    """
    match = _DOCTYPE_RE.search(data)
    if match is None or match.group(0) == EPUB3_DOCTYPE:
        return data, False
    if match.group(1):  # an internal subset declares its own — see the docstring
        return data, False
    if unresolvable_entities(data):
        return data, False
    body = _numeric_entities(data[: match.start()] + data[match.end() :])
    return body[: match.start()] + EPUB3_DOCTYPE + body[match.start() :], True


#: `<title></title>`, `<title> </title>`, `<title/>` — with or without attributes.
#: Anchored on the first occurrence only: `<title>` also exists inside SVG, where
#: it is a label on a shape and may legitimately hold nothing.
_EMPTY_TITLE_RE = re.compile(
    rb"<title(\s[^>]*)?\s*(?:/>|>\s*</title\s*>)", re.IGNORECASE
)

#: How far into the document the `<head>` can reasonably be. A `<title>` after
#: this is not the document's own; it belongs to something embedded.
_HEAD_WINDOW = 4096


def fill_empty_title(data: bytes, title: str) -> tuple[bytes, bool]:
    """Give an empty `<title>` some text, touching nothing else.

    The second edit the container-only mode is allowed to make, and it is
    allowed for the same reason as the first: `<title>` is not rendered in the
    body, so what the reader sees cannot change.

    It is here because of a measurement. Fourteen EPUBCheck errors across
    thirteen books in a private corpus were introduced by container-only mode,
    and once the run started recording message identifiers they turned out to
    be one identifier — `RSC-005` — and, on the one book of that shape I could
    reach, one sentence: *Element "title" must not be empty.* EPUB 2 allowed it;
    EPUB 3 does not, and this mode rebuilds the package as EPUB 3 whatever
    happens to the content. So the mode was not carrying a defect the book
    already had — it was creating one, by upgrading the package around markup
    that was legal only under the old rules.

    Only the first `<title>` in the head window, and only when it is empty. An
    SVG `<title>` is a label on a shape and is nobody's business here.
    """
    match = _EMPTY_TITLE_RE.search(data, 0, _HEAD_WINDOW)
    if match is None:
        return data, False
    text = re.sub(r"\s+", " ", title).strip()
    if not text:
        return data, False
    attributes = (match.group(1) or b"").rstrip()
    filled = (
        b"<title" + attributes + b">"
        + escape(text[:200]).encode("utf-8")
        + b"</title>"
    )
    return data[: match.start()] + filled + data[match.end() :], True


def unresolvable_entities(data: bytes) -> set[str]:
    """Named entities in the document that nothing here can turn into characters.

    The five XML built-ins need no declaration; everything else has to be
    rewritten before the declaration that defined it is taken away.
    """
    found = set()
    for raw in _ENTITY_REFERENCE.findall(data):
        name = raw.decode("ascii")
        if raw in _XML_BUILTIN_ENTITIES:
            continue
        if html5.get(name + ";") or html5.get(name):
            continue
        found.add(name)
    return found


def qname(local: str, ns: str = XHTML_NS) -> str:
    return f"{{{ns}}}{local}"


def local_name(element) -> str:
    tag = element.tag
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def iter_elements(root):
    for node in root.iter():
        if isinstance(node.tag, str):
            yield node


def _with_default_namespace(root):
    """Re-root the tree so XHTML is the default namespace.

    An element's prefix is fixed by the nsmap in force when it was created, and
    ``cleanup_namespaces`` cannot change it afterwards. A document recovered by
    the HTML parser therefore serialises as ``<html:p>`` unless the root is
    rebuilt with the right nsmap and the children reparented under it.
    """
    prefixed_xhtml = {p for p, uri in root.nsmap.items() if p and uri == XHTML_NS}
    if root.nsmap.get(None) == XHTML_NS and not prefixed_xhtml:
        return root

    # Any prefix still bound to XHTML would keep winning over the default
    # declaration for elements created under it, so drop those bindings.
    nsmap = {p: uri for p, uri in root.nsmap.items() if p and uri != XHTML_NS}
    nsmap[None] = XHTML_NS
    nsmap.setdefault("epub", EPUB_NS)

    rebuilt = etree.Element(root.tag, nsmap=nsmap)
    for key, value in root.attrib.items():
        if key == "xmlns" or (isinstance(key, str) and key.startswith("xmlns:")):
            continue
        rebuilt.set(key, value)
    rebuilt.text = root.text
    rebuilt.tail = root.tail
    for child in list(root):
        rebuilt.append(child)
    return rebuilt


#: Characters XML 1.0 cannot represent. The same set the package writer uses
#: (`writer._XML_FORBIDDEN`) and here for the same reason, found by the same
#: fuzz run: a document carrying one of these is written and does not parse, so
#: the chapter does not open.
#:
#: This half is the worse of the two. A control character in a title spoils the
#: package; a control character in a chapter spoils the text of the book, and it
#: arrives from the source — a damaged file recovered by the parser keeps it, and
#: the rebuild writes it back out faithfully into a document nothing can read.
_XML_FORBIDDEN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f\ud800-\udfff￾￿]"
)


def forbidden_characters(root) -> int:
    """How many characters of *root*'s text XML cannot carry."""
    found = 0
    for element in iter_elements(root):
        for value in (element.text, element.tail):
            if value:
                found += len(_XML_FORBIDDEN.findall(value))
    return found


def _drop_forbidden(root) -> None:
    """Take those characters out, leaving every other character in place."""
    for element in iter_elements(root):
        if element.text and _XML_FORBIDDEN.search(element.text):
            element.text = _XML_FORBIDDEN.sub("", element.text)
        if element.tail and _XML_FORBIDDEN.search(element.tail):
            element.tail = _XML_FORBIDDEN.sub("", element.tail)


def serialize(root) -> bytes:
    """Emit well-formed XHTML 5 with a stable namespace declaration set."""
    # Before anything else, because everything after this assumes the tree can
    # be written. K1 says no character of the book's text is lost, and these are
    # not characters of the text: XML has no way to carry them, so the choice is
    # between a document without them and a document nobody can open.
    _drop_forbidden(root)
    for element in iter_elements(root):
        if (
            local_name(element).lower() in _NEVER_SELF_CLOSE
            and len(element) == 0
            and not element.text
        ):
            element.text = ""

    root = _with_default_namespace(root)
    etree.cleanup_namespaces(root, keep_ns_prefixes=["epub", "xlink"])
    body = etree.tostring(root, encoding="unicode", method="xml")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        f"{body}\n"
    ).encode("utf-8")
