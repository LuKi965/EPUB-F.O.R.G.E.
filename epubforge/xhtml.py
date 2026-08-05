"""Parsing and serialising XHTML content documents from unreliable sources.

Content documents in shipped books are XML in name only: undefined HTML
entities, unclosed void elements, tag soup from HTML-to-EPUB converters. This
module recovers a tree from all of that and always emits well-formed XHTML 5.
"""

from __future__ import annotations

import re
from html.entities import html5

from typing import NamedTuple

from lxml import etree, html as lxml_html

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
    "foreignobject", "animate", "animatetransform",
}

_ENTITY_RE = re.compile(rb"&([A-Za-z][A-Za-z0-9]{1,31});")
_XML_DECL_RE = re.compile(rb"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
_DOCTYPE_RE = re.compile(rb"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", re.IGNORECASE)
_STYLESHEET_PI_RE = re.compile(rb"<\?xml-stylesheet[^>]*\?>", re.IGNORECASE)


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


def parse_document(data: bytes) -> ParseResult:
    """Parse an XHTML document and say what it cost.

    Most callers only want the tree; :func:`parse` is the two-value form for
    them. This is for the one that has to report what changed.
    """
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

    try:
        root = etree.fromstring(normalized, XML_PARSER)
    except etree.XMLSyntaxError:
        root = None

    if root is not None and isinstance(root.tag, str):
        # Well-formed but namespace-less documents parse cleanly as XML and
        # would then fail every namespaced lookup downstream.
        tree = root if root.tag.startswith("{") else _namespacify(root)
        return ParseResult(tree, mode, expanded, refused)

    html_root = lxml_html.document_fromstring(
        normalized or b"<html><body></body></html>", parser=HTML_PARSER
    )
    return ParseResult(_namespacify(html_root), "html", expanded, refused)


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

    Returns the data unchanged whenever the document references an entity that
    `<!DOCTYPE html>` does not define. A legacy DOCTYPE declares entities two
    ways — an internal subset, and the external DTD it names — and the second
    is the one that matters in practice: every XHTML 1.1 document may write
    `&nbsp;` because `xhtml11.dtd` declares it. Swapping the declaration
    strands the reference, and EPUBCheck stops at *Fatal Error while parsing
    file: The entity "nbsp" was referenced, but not declared*. That turns a book
    that is merely invalid into one that will not open, which is worse than
    doing nothing.

    Only the five XML built-ins survive without a declaration.
    """
    match = _DOCTYPE_RE.search(data)
    if match is None or match.group(0) == EPUB3_DOCTYPE:
        return data, False
    if match.group(1):  # an internal subset declares its own — leave it alone
        return data, False
    body = data[: match.start()] + data[match.end() :]
    if set(_ENTITY_REFERENCE.findall(body)) - _XML_BUILTIN_ENTITIES:
        return data, False
    return data[: match.start()] + EPUB3_DOCTYPE + data[match.end() :], True


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


def serialize(root) -> bytes:
    """Emit well-formed XHTML 5 with a stable namespace declaration set."""
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
