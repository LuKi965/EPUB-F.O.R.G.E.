"""Parsing and serialising XHTML content documents from unreliable sources.

Content documents in shipped books are XML in name only: undefined HTML
entities, unclosed void elements, tag soup from HTML-to-EPUB converters. This
module recovers a tree from all of that and always emits well-formed XHTML 5.
"""

from __future__ import annotations

import re
from html.entities import html5

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


def parse(data: bytes) -> tuple[etree._Element, str]:
    """Parse an XHTML document.

    Returns the root element and the recovery mode used: ``"xml"`` when the
    source was already well-formed, ``"xml-entities"`` when only entity
    rewriting was needed, or ``"html"`` when a full tag-soup recovery ran.
    """
    prepared = _STYLESHEET_PI_RE.sub(b"", data)
    for mode, candidate in (
        ("xml", prepared),
        ("xml-entities", _numeric_entities(_strip_internal_dtd(prepared))),
    ):
        try:
            root = etree.fromstring(candidate, XML_PARSER)
        except etree.XMLSyntaxError:
            continue
        if root is not None and isinstance(root.tag, str):
            # Well-formed but namespace-less documents parse cleanly as XML and
            # would then fail every namespaced lookup downstream.
            if not root.tag.startswith("{"):
                return _namespacify(root), mode
            return root, mode

    html_root = lxml_html.document_fromstring(
        _numeric_entities(_strip_internal_dtd(prepared)) or b"<html><body></body></html>",
        parser=HTML_PARSER,
    )
    return _namespacify(html_root), "html"


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
