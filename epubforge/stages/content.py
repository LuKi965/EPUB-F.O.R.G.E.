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

from .. import cascade as css_cascade
from .. import paths, watermark, xhtml
from ..report import Level
from .accessibility import is_placeholder_alt
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
        # A watermark repeats across every document, so its findings are summed
        # and reported once rather than thirty-four times.
        self._watermarks_consolidated = 0
        self._watermark_documents = 0
        self._watermark_tokens: set[str] = set()
        self._watermark_notices: list[str] = []

    def run(self, ctx: Context) -> None:
        if not ctx.policy.rewrite_content:
            # Container-only rebuild. Parsing and reserialising a document
            # changes its bytes even when nothing about it is wrong, so the way
            # to keep that promise is not to open them at all.
            # One exception, and it is exactly one. A legacy DOCTYPE makes the
            # output an invalid EPUB 3 — EPUBCheck: "Irregular DOCTYPE" — and a
            # DOCTYPE declares nothing about how a page looks, so replacing it
            # is the only edit that cannot change what the reader sees. Half
            # the older books in a real library carry the XHTML 1.1 one.
            modernised = 0
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
            if modernised:
                self.note(ctx, Level.INFO, "xhtml.untouched-except-doctype")
            else:
                self.note(ctx, Level.INFO, "xhtml.untouched")
            return

        documents: list[tuple[object, object, dict[str, str]]] = []

        expanded_entities: dict[str, list[str]] = {}
        refused_entities: dict[str, list[str]] = {}

        for resource in ctx.book.content_docs():
            try:
                parsed = xhtml.parse_document(resource.data)
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
            if mode == "html":
                self.note(
                    ctx,
                    Level.FIX,
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

        for resource, root, _ in documents:
            self._skeleton(ctx, root, resource)
            self._rewrite_references(ctx, root, resource, global_ids)
            self._modernise(ctx, root, resource)
            self._image_paragraphs(ctx, root, resource)
            self._cover_fits_the_page(ctx, root, resource)
            self._block_in_inline(ctx, root, resource)
            self._watermarks(ctx, root, resource)
            self._accessibility(ctx, root, resource)
            self._scripting(ctx, root, resource)
            self._properties(ctx, root, resource)
            ctx.document_ids[resource.path] = {
                element.get("id")
                for element in xhtml.iter_elements(root)
                if element.get("id")
            }
            resource.data = xhtml.serialize(root)

        self._report_entities(ctx, expanded_entities, refused_entities)
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
                "xhtml.ids-renamed",
                values={"count": len(renamed)},
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
            self.note(ctx, Level.FIX, "xhtml.head-added", location=resource.path)

        body = root.find(xhtml.qname("body"))
        if body is None:
            body = etree.SubElement(root, xhtml.qname("body"))
            self.note(ctx, Level.FIX, "xhtml.body-added", location=resource.path)

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
                "xhtml.dead-reference-kept",
                values={"count": broken},
                location=resource.path,
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
            "xhtml.dead-reference-neutralised",
            values={
                "count": unlinked + removed,
                "unlinked": unlinked,
                "removed": removed,
            },
            location=resource.path,
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
                "xhtml.presentational-markup-converted",
                location=resource.path,
                detail=", ".join(sorted(changed)),
            )

    def _document_cascade(self, ctx: Context, root, resource) -> css_cascade.Cascade:
        """Collect the CSS that actually applies to one document."""
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
        return css_cascade.Cascade.parse(sources)

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
            _append_style(element, "text-indent: 0; text-align: center;")
            adjusted += 1

        if adjusted:
            self.note(
                ctx,
                Level.FIX,
                "xhtml.image-paragraph-centred",
                values={"count": adjusted},
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
        and nothing else. When that rule goes missing — a stylesheet link the
        publisher's tooling broke, a page that links no stylesheet at all — the
        reader falls back to the image's own dimensions, and a 1600px cover on a
        six-inch screen is cropped or shrunk to a stamp depending on the device.

        Only applied when **nothing** sizes the image: no inline style, no rule
        of any kind reaching it for width, height or their maxima. Both
        properties can only ever make an image smaller than its natural size, so
        the worst case is that a reader ignores them.
        """
        cover = ctx.book.cover_path
        if not cover:
            return

        source_path = resource.original_path or resource.path
        cascade = None
        adjusted = 0

        for element in root.iter(xhtml.qname("img")):
            source = (element.get("src") or "").strip()
            if not source:
                continue
            target = paths.resolve(source_path, source)
            if target != cover and ctx.path_map.get(target) != ctx.path_map.get(cover):
                continue
            inline = (element.get("style") or "").lower()
            if any(prop in inline for prop in ("width", "height")):
                continue
            if element.get("width") or element.get("height"):
                continue

            if cascade is None:
                cascade = self._document_cascade(ctx, root, resource)
            chain = _ancestry(element)
            if any(
                cascade.resolve(prop, chain[:1])[0] is not None
                for prop in ("width", "height", "max-width", "max-height")
            ):
                continue

            _append_style(element, "max-width: 100%; max-height: 100%;")
            adjusted += 1

        if adjusted:
            self.note(ctx, Level.FIX, "xhtml.cover-fitted", location=resource.path)

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

    def _watermarks(self, ctx: Context, root, resource) -> None:
        """Consolidate a publisher's per-purchase marker without touching it.

        The token text is left exactly as found — it is the publisher's
        traceability mark and removing it would defeat its purpose. What goes is
        the collateral damage: the ``!important`` inline style repeated in every
        document, and the token's presence in the reading order, where a screen
        reader announces it character by character at the end of each chapter.
        """
        if not ctx.policy.normalize_watermarks:
            return

        consolidated = 0
        notices: list[str] = []

        for element in xhtml.iter_elements(root):
            if len(element) or xhtml.local_name(element).lower() in {"html", "head", "body"}:
                continue
            text = (element.text or "").strip()
            if not text:
                continue

            if watermark.is_visible_notice(text):
                # Meant to be read; the buyer's own copy notice. Never restyled.
                notices.append(text[:120])
                continue

            style = element.get("style") or ""
            if not watermark.is_token(text) or not watermark.is_negligibly_styled(style):
                continue
            self._watermark_tokens.add(text)

            element.attrib.pop("style", None)
            classes = (element.get("class") or "").split()
            if watermark.MARKER_CLASS not in classes:
                classes.append(watermark.MARKER_CLASS)
            element.set("class", " ".join(classes))
            # Keeps the token in the file and out of the spoken reading order.
            element.set("aria-hidden", "true")
            consolidated += 1

        if consolidated:
            for sheet in self._linked_stylesheets(ctx, root, resource):
                ctx.watermark_stylesheets.add(sheet)
            self._watermarks_consolidated += consolidated
            self._watermark_documents += 1
        self._watermark_notices.extend(notices)

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
                    "css.url-unresolved",
                    values={"count": unresolved},
                    location=resource.path,
                )
            self._validate(ctx, resource)

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
        repaired, invalid_values = _REGULAR_VALUE_RE.subn(r"\1normal", css_text)
        if invalid_values:
            self.note(
                ctx,
                Level.FIX,
                "css.invalid-value-corrected",
                values={"count": invalid_values},
                location=resource.path,
            )

        repaired = self._repair_positioning(ctx, repaired, resource)
        return repaired

    def _repair_positioning(self, ctx: Context, css_text: str, resource) -> str:
        """Absolute positioning is a compatibility risk, not a defect.

        Publishers use it deliberately — a rule named ``.dol`` ("bottom") pins a
        dedication to the foot of the page, and that is intent, not a mistake.
        Readium-based readers honour it; older ones ignore it. Since removing it
        destroys a layout the publisher chose, it is reported and kept unless
        conformance has been asked to win.
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
            "css.font-stack-generic-missing",
            values={
                "count": len(offenders),
                "examples": ", ".join(sorted(set(offenders))[:4]),
            },
            location=resource.path,
        )

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
