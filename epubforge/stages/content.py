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

from .. import paths, xhtml
from ..report import Level
from .base import Context, Stage

cssutils.log.setLevel(50)  # cssutils logs every minor deviation at WARNING.

XHTML_NS = xhtml.XHTML_NS
EPUB_NS = xhtml.EPUB_NS
XLINK_NS = xhtml.XLINK_NS
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

#: Attributes whose values are references to other packaged resources.
REFERENCE_ATTRS = ("href", "src", "poster", "data", f"{{{XLINK_NS}}}href")

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

_FONT_SIZE_SCALE = {
    "1": "x-small", "2": "small", "3": "medium", "4": "large",
    "5": "x-large", "6": "xx-large", "7": "xxx-large",
}

_NCNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9._\-]*$")
_LENGTH_RE = re.compile(r"^\d+(\.\d+)?$")

#: Anything a font stack may legally end with instead of a concrete font.
GENERIC_FAMILIES = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded", "math", "emoji",
    "fangsong", "inherit", "initial", "unset", "revert", "revert-layer",
}

#: `regular` is not a CSS value for either property; the whole declaration is
#: dropped by every parser, so the publisher's intent never applied at all.
_REGULAR_VALUE_RE = re.compile(r"(font-(?:style|weight)\s*:\s*)regular\b", re.IGNORECASE)

#: Out-of-flow positioning in a reflowable book. Legitimate in fixed-layout,
#: where the viewport is known; in reflowable it detaches content from
#: pagination and readers clip, overlap or lose it.
_OUT_OF_FLOW_RE = re.compile(
    r"([;{]\s*|^\s*)position\s*:\s*(?:absolute|fixed)\s*;?", re.IGNORECASE | re.MULTILINE
)

_FONT_FACE_RE = re.compile(r"@font-face\s*\{[^}]*\}", re.IGNORECASE)
_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}]+)", re.IGNORECASE)
#: Adobe Digital Editions inventions; unprefixed, so validators call them unknown.
_ADOBE_PROPERTY_RE = re.compile(
    r"([;{]\s*|^\s*)(adobe-[a-z-]+)\s*:\s*[^;}]*;?", re.IGNORECASE | re.MULTILINE
)


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

    def run(self, ctx: Context) -> None:
        documents: list[tuple[object, object, dict[str, str]]] = []

        for resource in ctx.book.content_docs():
            try:
                root, mode = xhtml.parse(resource.data)
            except Exception as exc:
                self.note(
                    ctx,
                    Level.ERROR,
                    f"content document could not be parsed at all: {type(exc).__name__}",
                    location=resource.path,
                )
                continue
            if mode == "html":
                self.note(
                    ctx,
                    Level.FIX,
                    "document was not well-formed XML; recovered with an HTML parser",
                    location=resource.path,
                )
            elif mode == "xml-entities":
                self.note(
                    ctx,
                    Level.FIX,
                    "rewrote undefined HTML entities to numeric character references",
                    location=resource.path,
                )

            id_map = self._fix_identifiers(ctx, root, resource.path)
            documents.append((resource, root, id_map))

        # Fragment targets can point across documents, so every id rename must be
        # known before any href is rewritten.
        global_ids = {
            resource.path: id_map for resource, _, id_map in documents if id_map
        }
        ctx.id_map = global_ids

        for resource, root, _ in documents:
            self._skeleton(ctx, root, resource)
            self._rewrite_references(ctx, root, resource, global_ids)
            self._modernise(ctx, root, resource)
            self._accessibility(ctx, root, resource)
            self._scripting(ctx, root, resource)
            self._properties(ctx, root, resource)
            resource.data = xhtml.serialize(root)

    def _fix_identifiers(self, ctx: Context, root, path: str) -> dict[str, str]:
        """Make every ``id`` a valid XML NCName, remembering what changed."""
        renamed: dict[str, str] = {}
        taken = {
            element.get("id")
            for element in xhtml.iter_elements(root)
            if element.get("id")
        }
        for element in xhtml.iter_elements(root):
            current = element.get("id")
            if current is None or _NCNAME_RE.match(current):
                continue
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
            renamed[current] = unique
        if renamed:
            self.note(
                ctx,
                Level.FIX,
                f"renamed {len(renamed)} id attribute(s) that were not valid XML names",
                location=path,
            )
        return renamed

    def _skeleton(self, ctx: Context, root, resource) -> None:
        """Guarantee html/head/title/body with the right namespace and language."""
        language = ctx.book.metadata.language or ctx.policy.default_language
        root.set("lang", language)
        root.set(XML_LANG, language)

        head = root.find(xhtml.qname("head"))
        if head is None:
            head = etree.Element(xhtml.qname("head"))
            root.insert(0, head)
            self.note(ctx, Level.FIX, "added a missing <head>", location=resource.path)

        body = root.find(xhtml.qname("body"))
        if body is None:
            body = etree.SubElement(root, xhtml.qname("body"))
            self.note(ctx, Level.FIX, "added a missing <body>", location=resource.path)

        for meta in head.findall(xhtml.qname("meta")):
            if meta.get("http-equiv") or meta.get("charset"):
                head.remove(meta)
        charset = etree.Element(xhtml.qname("meta"))
        charset.set("charset", "utf-8")
        head.insert(0, charset)

        title = head.find(xhtml.qname("title"))
        if title is None:
            title = etree.SubElement(head, xhtml.qname("title"))
        if not (title.text or "").strip():
            title.text = self._derive_title(root, resource)

    def _derive_title(self, root, resource) -> str:
        for level in ("h1", "h2", "h3", "h4", "title"):
            for element in root.iter(xhtml.qname(level)):
                text = re.sub(r"\s+", " ", "".join(element.itertext())).strip()
                if text:
                    return text[:200]
        stem = posixpath.basename(resource.path).rpartition(".")[0]
        return re.sub(r"^\d+-", "", stem).replace("-", " ").replace("_", " ").strip() or "Section"

    def _rewrite_references(self, ctx: Context, root, resource, global_ids: dict) -> None:
        """Repoint every href/src at the resource's new location."""
        source_path = resource.original_path or resource.path
        broken = 0
        dangling: list[tuple[object, str]] = []

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
                        element.set(attribute, f"#{local_map[fragment]}")
                    continue

                target = paths.resolve(source_path, value)
                if target is None:
                    continue
                new_target = ctx.path_map.get(target)
                if new_target is None:
                    broken += 1
                    dangling.append((element, attribute))
                    continue
                fragment = value.partition("#")[2]
                if fragment:
                    remapped = global_ids.get(new_target, {}).get(fragment)
                    fragment = remapped or fragment
                href = paths.relative(resource.path, new_target)
                element.set(attribute, f"{href}#{fragment}" if fragment else href)

            style = element.get("style")
            if style and "url(" in style:
                element.set("style", self._rewrite_css_urls(ctx, style, source_path, resource.path))

        for style_element in root.iter(xhtml.qname("style")):
            if style_element.text and "url(" in style_element.text:
                style_element.text = self._rewrite_css_urls(
                    ctx, style_element.text, source_path, resource.path
                )

        if not broken:
            return
        if not ctx.policy.strict:
            self.note(
                ctx,
                Level.PRESERVED,
                f"{broken} reference(s) point at files not present in the book; left unchanged",
                location=resource.path,
                detail="These are source defects and remain conformance errors. Use --strict to neutralise them.",
            )
            return
        self._neutralise(ctx, dangling, resource)

    def _neutralise(self, ctx: Context, dangling: list, resource) -> None:
        """Strict mode: make references to absent files stop being errors."""
        unlinked = removed = 0
        for element, attribute in dangling:
            tag = xhtml.local_name(element).lower()
            if tag == "a" and attribute == "href":
                # Dropping href keeps the text and any styling; the link is inert.
                element.attrib.pop(attribute, None)
                unlinked += 1
            else:
                parent = element.getparent()
                if parent is not None:
                    self._unwrap(element, keep_children=False)
                    removed += 1
        self.note(
            ctx,
            Level.FIX,
            f"neutralised {unlinked + removed} reference(s) to files absent from the book",
            location=resource.path,
            detail=f"{unlinked} link(s) unlinked, {removed} element(s) removed",
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

            self._presentational_attributes(element, tag, changed)

        if changed:
            self.note(
                ctx,
                Level.FIX,
                "converted legacy presentational markup to CSS",
                location=resource.path,
                detail=", ".join(sorted(changed)),
            )

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

        if tag == "br" and element.get("clear"):
            clear = element.get("clear").strip().lower()
            declarations.append(f"clear: {'both' if clear == 'all' else clear};")
            element.attrib.pop("clear", None)
            changed.add("br[clear]")

        # width/height stay as attributes on replaced elements, where HTML 5
        # still defines them; elsewhere they only exist as CSS.
        if tag not in {"img", "canvas", "video", "iframe", "embed", "object", "svg"}:
            for attribute in ("width", "height"):
                value = element.get(attribute)
                if value:
                    length = _css_length(value)
                    if length:
                        declarations.append(f"{attribute}: {length};")
                    element.attrib.pop(attribute, None)
                    changed.add(attribute)

        for obsolete in ("nowrap", "compact", "noshade", "frameborder", "scrolling", "language"):
            if element.get(obsolete) is not None:
                element.attrib.pop(obsolete, None)
                changed.add(obsolete)

        _append_style(element, " ".join(declarations))

    def _unwrap(self, element, keep_children: bool) -> None:
        """Replace an element with its children (or remove it entirely)."""
        parent = element.getparent()
        if parent is None:
            return
        index = list(parent).index(element)
        tail = element.tail or ""
        if keep_children:
            previous_text = element.text or ""
            if previous_text:
                if index == 0:
                    parent.text = (parent.text or "") + previous_text
                else:
                    sibling = parent[index - 1]
                    sibling.tail = (sibling.tail or "") + previous_text
            for offset, child in enumerate(list(element)):
                parent.insert(index + offset, child)
        if tail:
            if len(parent) and index > 0:
                parent[index - 1].tail = (parent[index - 1].tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
        parent.remove(element)

    def _accessibility(self, ctx: Context, root, resource) -> None:
        missing_alt = 0
        for image in root.iter(xhtml.qname("img")):
            if image.get("alt") is None:
                image.set("alt", "")
                missing_alt += 1
        if missing_alt:
            self.note(
                ctx,
                Level.FIX,
                f"added an empty alt attribute to {missing_alt} image(s)",
                location=resource.path,
                detail="Required by EPUB 3; empty marks them decorative.",
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
                f"kept {len(scripts)} script element(s); document marked scripted",
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
            f"removed {len(scripts)} script element(s) and {len(handlers)} inline handler(s)",
            location=resource.path,
        )

    def _properties(self, ctx: Context, root, resource) -> None:
        """Derive the manifest properties EPUB 3 requires to be declared."""
        properties = {p for p in resource.properties if p in {"nav", "cover-image"}}

        if any(root.iter(xhtml.qname("script"))) or any(
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

        for element in xhtml.iter_elements(root):
            for attribute in REFERENCE_ATTRS:
                value = element.get(attribute)
                if value and paths.is_remote(value) and not value.lower().startswith(("mailto:", "tel:")):
                    properties.add("remote-resources")
                    break

        resource.properties = properties


class StyleStage(Stage):
    """Repoints stylesheet URLs and reports rules that will not survive."""

    name = "css"

    def run(self, ctx: Context) -> None:
        for resource in ctx.book.by_type("style"):
            source_path = resource.original_path or resource.path
            text = resource.text()
            rewritten, unresolved = self._rewrite_urls(ctx, text, source_path, resource.path)
            rewritten = self._strip_vendor_hacks(ctx, rewritten, resource)
            rewritten = self._repair(ctx, rewritten, resource)
            rewritten = self._vendor_properties(ctx, rewritten, resource)
            self._font_stacks(ctx, rewritten, resource)
            resource.data = rewritten.encode("utf-8")

            if unresolved:
                self.note(
                    ctx,
                    Level.WARN,
                    f"{unresolved} url() reference(s) could not be resolved; left unchanged",
                    location=resource.path,
                )
            self._validate(ctx, resource)

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

    def _strip_vendor_hacks(self, ctx: Context, css_text: str, resource) -> str:
        """Remove reader-specific at-rules that no EPUB 3 renderer honours."""
        hacks = re.findall(r"@(-\w+-|media\s+amzn-\w+)", css_text)
        if not hacks:
            return css_text
        if not ctx.policy.strict:
            self.note(
                ctx,
                Level.PRESERVED,
                f"kept {len(hacks)} vendor-specific at-rule(s) that target particular readers",
                location=resource.path,
                detail="Use --strict to remove them.",
            )
            return css_text
        cleaned = re.sub(
            r"@media\s+amzn-(?:mobi|kf8)\b[^{]*\{(?:[^{}]|\{[^{}]*\})*\}",
            "",
            css_text,
            flags=re.IGNORECASE,
        )
        self.note(
            ctx,
            Level.FIX,
            "removed Kindle-specific @media blocks",
            location=resource.path,
        )
        return cleaned

    def _repair(self, ctx: Context, css_text: str, resource) -> str:
        """Correct declarations that are simply wrong, not merely unfashionable.

        These are publisher mistakes rather than stylistic choices: the browser
        already discards them, so repairing them restores the intended layout
        instead of overriding it.
        """
        repaired, invalid_values = _REGULAR_VALUE_RE.subn(r"\1normal", css_text)
        if invalid_values:
            self.note(
                ctx,
                Level.FIX,
                f"corrected {invalid_values} declaration(s) using the invalid value 'regular'",
                location=resource.path,
                detail=(
                    "font-style/font-weight have no 'regular' keyword, so parsers dropped these "
                    "rules entirely. Replaced with 'normal', which is what was meant."
                ),
            )

        repaired = self._repair_positioning(ctx, repaired, resource)
        return repaired

    def _repair_positioning(self, ctx: Context, css_text: str, resource) -> str:
        matches = _OUT_OF_FLOW_RE.findall(css_text)
        if not matches:
            return css_text

        if ctx.book.rendition.get("layout") == "pre-paginated":
            self.note(
                ctx,
                Level.PRESERVED,
                f"kept {len(matches)} absolute/fixed position rule(s)",
                location=resource.path,
                detail="This is a fixed-layout book, where out-of-flow positioning is legitimate.",
            )
            return css_text

        repaired = _OUT_OF_FLOW_RE.sub(lambda match: match.group(1), css_text)
        self.note(
            ctx,
            Level.FIX,
            f"removed {len(matches)} absolute/fixed position rule(s) from a reflowable book",
            location=resource.path,
            detail=(
                "Out-of-flow content cannot paginate: readers clip it, overlap it, or drop it, "
                "and text-align inside it stops being visible. The affected blocks now flow "
                "normally and their own alignment applies again."
            ),
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
                f"kept {len(found)} reader-specific CSS propert(ies) inherited from the source",
                location=resource.path,
                detail=f"{', '.join(names)} — validators flag these as unknown. Use --strict to remove them.",
            )
            return css_text
        cleaned = _ADOBE_PROPERTY_RE.sub(lambda match: match.group(1), css_text)
        self.note(
            ctx,
            Level.FIX,
            f"removed {len(found)} reader-specific CSS propert(ies)",
            location=resource.path,
            detail=", ".join(names),
        )
        return cleaned

    def _font_stacks(self, ctx: Context, css_text: str, resource) -> None:
        """Flag font stacks with no generic family to fall back on.

        Not a conformance error, but if the embedded font fails to load the
        reader is left guessing. Declarations inside @font-face name a font
        rather than build a stack, so they are excluded.
        """
        # Blank out @font-face bodies while keeping offsets stable.
        outside = _FONT_FACE_RE.sub(lambda match: " " * len(match.group()), css_text)
        offenders: list[str] = []
        for match in _FONT_FAMILY_RE.finditer(outside):
            families = [part.strip().strip("\"'") for part in match.group(1).split(",")]
            families = [family for family in families if family]
            if families and families[-1].lower() not in GENERIC_FAMILIES:
                offenders.append(families[-1])
        if not offenders:
            return
        self.note(
            ctx,
            Level.PRESERVED,
            f"{len(offenders)} font stack(s) end without a generic family",
            location=resource.path,
            detail=(
                f"e.g. {', '.join(sorted(set(offenders))[:4])} — inherited from the source and left "
                "as-is, since guessing serif vs sans-serif could change how the book looks."
            ),
        )

    def _validate(self, ctx: Context, resource) -> None:
        parser = cssutils.CSSParser(raiseExceptions=False, validate=False)
        try:
            sheet = parser.parseString(resource.text(), href=resource.path)
        except Exception as exc:
            self.note(
                ctx,
                Level.WARN,
                f"stylesheet could not be parsed for validation: {type(exc).__name__}",
                location=resource.path,
            )
            return
        if not sheet.cssRules:
            self.note(ctx, Level.WARN, "stylesheet contains no usable rules", location=resource.path)
