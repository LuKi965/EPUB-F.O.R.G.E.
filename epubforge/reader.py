"""Tolerant loader: lowers any EPUB-ish archive into the :mod:`~epubforge.model`.

Nothing in here rejects a file for being malformed. Real-world books declare the
wrong namespaces, omit ``container.xml``, point the spine at missing files, and
nest an NCX inside the manifest while calling themselves EPUB 3. Every such case
is recovered from and recorded, because the rebuild downstream regenerates the
container from scratch anyway.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass

from lxml import etree

from . import paths
from .model import (
    Book,
    Creator,
    Identifier,
    Landmark,
    Metadata,
    NavPoint,
    PageTarget,
    Resource,
    SpineItem,
    guess_media_type,
)
from .report import Level, Report

DC_NS = "http://purl.org/dc/elements/1.1/"
OPF_NS = "http://www.idpf.org/2007/opf"
EPUB_NS = "http://www.idpf.org/2007/ops"
XHTML_NS = "http://www.w3.org/1999/xhtml"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
ENC_NS = "http://www.w3.org/2001/04/xmlenc#"

IDPF_OBFUSCATION = "http://www.idpf.org/2008/embedding"
ADOBE_OBFUSCATION = "http://ns.adobe.com/pdf/enc#RC"
OBFUSCATION_ALGORITHMS = {IDPF_OBFUSCATION, ADOBE_OBFUSCATION}

_XML_PARSER = etree.XMLParser(recover=True, resolve_entities=False, huge_tree=True)


class EpubReadError(Exception):
    """Raised only when the archive cannot be opened at all."""


def lname(element) -> str:
    """Local tag name, namespace-agnostic — broken files omit namespaces."""
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    return tag.rpartition("}")[2]


def children(element, *names: str):
    wanted = {n.lower() for n in names}
    return [child for child in element if lname(child).lower() in wanted]


def descendants(element, *names: str):
    wanted = {n.lower() for n in names}
    return [node for node in element.iter() if lname(node).lower() in wanted]


def attr(element, name: str, *namespaces: str) -> str | None:
    """Read an attribute whether or not it carries a namespace prefix."""
    value = element.get(name)
    if value is not None:
        return value
    for ns in namespaces:
        value = element.get(f"{{{ns}}}{name}")
        if value is not None:
            return value
    for key, val in element.attrib.items():
        if isinstance(key, str) and key.rpartition("}")[2] == name:
            return val
    return None


def text_of(element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def _read_collection(node, refines: dict[str, dict[str, str]], metadata) -> None:
    """Resolve series name and number from the *same* collection.

    A book may belong to several collections at once — the seventh Chronicle,
    published inside a boxed set as part one. Both carry a `group-position`, and
    reading them independently produced "Chronicles, volume 1": the name came
    from the series, the number from whichever refinement the document happened
    to list first.

    So the collections are gathered whole, with their refinements attached, and
    the number is taken from the collection the name came from. Untyped
    collections count as series, which is what EPUB 3 says they default to.
    """
    collections: list[tuple[str, str]] = [
        (meta.get("id") or "", text_of(meta))
        for meta in descendants(node, "meta")
        if (meta.get("property") or "").strip() == "belongs-to-collection"
        and not meta.get("refines")
        and text_of(meta)
    ]
    for collection_id, name in collections:
        attached = refines.get(collection_id, {})
        if attached.get("collection-type", "series") != "series":
            continue
        metadata.series = metadata.series or name
        position = attached.get("group-position")
        if position:
            metadata.series_index = metadata.series_index or position
        break


@dataclass
class _RawArchive:
    entries: dict[str, bytes]
    mimetype_ok: bool


#: Ceilings on what a single archive may expand to. The whole book is held in
#: memory by design, and files arrive by drag-and-drop from wherever the user
#: found them, so a malicious or merely broken archive must not be able to ask
#: for unbounded allocation. Both limits sit far above any real book: the
#: largest illustrated EPUBs run to a few hundred megabytes, and legitimate
#: content (already-compressed images, fonts, XHTML) does not deflate anywhere
#: near two hundred to one.
MAX_TOTAL_BYTES = 2 * 1024**3
MAX_ENTRY_BYTES = 512 * 1024**2
MAX_COMPRESSION_RATIO = 200
#: Below this, a high ratio means nothing — a few hundred bytes of repeated
#: whitespace compresses spectacularly and harmlessly.
_RATIO_FLOOR = 64 * 1024
#: Read granularity. Small enough that overshooting the limit costs at most this
#: much, large enough that ordinary books are read in a handful of calls.
_CHUNK = 1024 * 1024


def _human(size: int) -> str:
    return f"{size / 1024**3:.0f} GiB" if size >= 1024**3 else f"{size / 1024**2:.0f} MiB"


def _implausible_header(info: zipfile.ZipInfo) -> str | None:
    """Why this entry is refused on the strength of its header alone.

    A cheap first pass: an archive that admits to holding a 300 MiB entry can be
    turned away without decompressing a byte. It is *only* a first pass — the
    header is what the author of the file chose to write there, and a hostile
    one simply says something else. The real limit is enforced on the stream by
    :func:`_read_bounded`.
    """
    if info.file_size > MAX_ENTRY_BYTES:
        return f"entry declares {info.file_size / 1024**2:.0f} MiB"
    if (
        info.file_size > _RATIO_FLOOR
        and info.compress_size
        and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
    ):
        return (
            f"entry declares a {info.file_size / info.compress_size:.0f}× expansion "
            f"({info.compress_size} → {info.file_size} bytes)"
        )
    return None


def _read_bounded(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes | None:
    """The entry's contents, or ``None`` when it alone exceeds the entry limit.

    Measured while decompressing rather than asked of the header, because the
    header is a claim and this is the one place where the claim is exactly what
    an attacker controls. Reading in chunks and stopping at the ceiling means a
    ten-gigabyte entry costs a megabyte to refuse.

    Only the per-entry limit is enforced here. The whole-archive budget is a
    different question with a different answer — see :func:`_read_archive`.
    """
    buffer = bytearray()
    with archive.open(info) as stream:
        while True:
            chunk = stream.read(_CHUNK)
            if not chunk:
                break
            buffer.extend(chunk)
            if len(buffer) > MAX_ENTRY_BYTES:
                return None
    return bytes(buffer)


def _read_archive(source: str, report: Report) -> _RawArchive:
    try:
        archive = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise EpubReadError(f"not a readable ZIP archive: {exc}") from exc

    entries: dict[str, bytes] = {}
    mimetype_ok = False
    total = 0

    def refuse(name: str, reason: str) -> None:
        report.add(
            "reader",
            Level.ERROR,
            f"refused an implausibly large archive entry: {reason}",
            location=name,
            detail="No real book contains this; the archive is broken or hostile.",
        )

    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/").lstrip("/")

            declared = _implausible_header(info)
            if declared:
                refuse(name, declared)
                continue

            try:
                data = _read_bounded(archive, info)
            except (RuntimeError, zipfile.BadZipFile, NotImplementedError, EOFError) as exc:
                # Encrypted or unsupported-compression member; keep going.
                report.add("reader", Level.ERROR, f"unreadable archive entry: {exc}", location=name)
                continue
            if data is None:
                refuse(
                    name,
                    f"entry passed {_human(MAX_ENTRY_BYTES)} while being read",
                )
                continue

            # The two limits are different questions and deserve different
            # answers. One monstrous entry is skipped and the rest of the book
            # is still worth reading; running out of budget for the archive as a
            # whole means this book cannot be read in full — and for a tool
            # whose first rule is that no character is lost, half a book is a
            # worse outcome than a refusal. Merging the two, as an earlier
            # version did, silently produced books missing four of six images
            # and blamed the fifth one for "expanding past the limit".
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise EpubReadError(
                    f"archive expands past {_human(MAX_TOTAL_BYTES)}; "
                    f"refusing to read it partially"
                )

            if name == "mimetype":
                mimetype_ok = data.strip() == b"application/epub+zip"
                continue
            entries[name] = data

    if not entries:
        raise EpubReadError("archive contains no readable files")
    return _RawArchive(entries, mimetype_ok)


def _locate_opf(entries: dict[str, bytes], report: Report) -> str:
    container = entries.get("META-INF/container.xml")
    if container:
        root = etree.fromstring(container, _XML_PARSER)
        if root is not None:
            for rootfile in descendants(root, "rootfile"):
                full_path = rootfile.get("full-path")
                if full_path:
                    candidate = full_path.replace("\\", "/").lstrip("/")
                    if candidate in entries:
                        return candidate
                    report.add(
                        "reader",
                        Level.WARN,
                        "container.xml points at a missing rootfile",
                        location=candidate,
                    )
    else:
        report.add("reader", Level.WARN, "META-INF/container.xml is missing; locating the OPF by scan")

    opf_candidates = sorted(
        (name for name in entries if name.lower().endswith(".opf")),
        key=lambda name: (name.count("/"), len(name)),
    )
    if opf_candidates:
        report.add("reader", Level.FIX, "recovered the package document by scanning", location=opf_candidates[0])
        return opf_candidates[0]
    raise EpubReadError("no package document (.opf) found in the archive")


def _parse_metadata(package, report: Report) -> Metadata:
    metadata = Metadata()
    meta_nodes = children(package, "metadata")
    if not meta_nodes:
        report.add("reader", Level.WARN, "package has no <metadata> element")
        return metadata
    node = meta_nodes[0]

    # EPUB 3 refinements are keyed by the id of the element they describe.
    refines: dict[str, dict[str, str]] = {}
    #: The same refinements as elements, because some of them carry attributes
    #: that matter — `alternate-script` is meaningless without its `xml:lang`.
    refine_nodes: dict[str, list] = {}
    for meta in descendants(node, "meta"):
        target = meta.get("refines")
        prop = meta.get("property")
        if target and prop:
            key = target.lstrip("#")
            refines.setdefault(key, {})[prop.strip()] = text_of(meta)
            refine_nodes.setdefault(key, []).append(meta)

    metadata.direction = (package.get("dir") or "").strip().lower() or None

    def alternate_scripts(element) -> list[tuple[str, str]]:
        """Transliterations attached to *element*, as ``(xml:lang, value)``.

        A romanised title or author name is how a library catalogue finds a book
        written in a script its index does not hold. It lives in a refinement,
        and once `_read_collection` became the only reader of refinements these
        went out with the bathwater.
        """
        element_id = element.get("id")
        found: list[tuple[str, str]] = []
        for meta in refine_nodes.get(element_id or "", []):
            if (meta.get("property") or "").strip() != "alternate-script":
                continue
            language = attr(meta, "lang", "http://www.w3.org/XML/1998/namespace") or ""
            value = text_of(meta)
            if value:
                found.append((language, value))
        return found

    def language_of(element) -> str | None:
        return attr(element, "lang", "http://www.w3.org/XML/1998/namespace")

    def refinement(element, prop: str) -> str | None:
        element_id = element.get("id")
        if element_id and element_id in refines:
            return refines[element_id].get(prop)
        return None

    _read_collection(node, refines, metadata)

    for child in node:
        tag = lname(child).lower()
        value = text_of(child)
        if tag == "title" and value:
            title_type = refinement(child, "title-type")
            if title_type == "subtitle":
                metadata.subtitle = value
            elif title_type == "collection":
                metadata.series = metadata.series or value
            else:
                if not metadata.titles:
                    metadata.title_language = language_of(child)
                    metadata.title_direction = (child.get("dir") or "").strip().lower() or None
                    metadata.title_alternate_scripts = alternate_scripts(child)
                metadata.titles.append(value)
                sort_as = refinement(child, "file-as")
                if sort_as:
                    metadata.sort_title = sort_as
        elif tag in ("creator", "contributor") and value:
            default_role = "aut" if tag == "creator" else "ctb"
            role = refinement(child, "role") or attr(child, "role", OPF_NS) or default_role
            file_as = refinement(child, "file-as") or attr(child, "file-as", OPF_NS)
            metadata.creators.append(
                Creator(
                    value,
                    role.strip().lower()[:3] or default_role,
                    file_as,
                    language=language_of(child),
                    direction=(child.get("dir") or "").strip().lower() or None,
                    alternate_scripts=alternate_scripts(child),
                )
            )
        elif tag == "identifier" and value:
            scheme = refines.get(child.get("id", ""), {}).get("identifier-type") or attr(child, "scheme", OPF_NS)
            metadata.identifiers.append(Identifier(value, scheme, primary=False))
        elif tag == "language" and value:
            if metadata.language is None:
                metadata.language = value
            else:
                metadata.languages_extra.append(value)
        elif tag == "publisher" and value:
            metadata.publisher = metadata.publisher or value
        elif tag == "date" and value:
            event = attr(child, "event", OPF_NS)
            if event == "modification":
                metadata.modified = metadata.modified or value
            else:
                metadata.published = metadata.published or value
        elif tag == "description" and value:
            metadata.description = metadata.description or value
        elif tag == "subject" and value:
            metadata.subjects.append(value)
        elif tag == "rights" and value:
            metadata.rights = metadata.rights or value
        elif tag == "source" and value:
            metadata.source = metadata.source or value
        elif tag in ("type", "coverage", "relation") and value:
            metadata.dublin_core_extra.append((tag, value))
        elif tag == "meta":
            name = child.get("name")
            content = child.get("content")
            prop = child.get("property")
            if child.get("refines"):
                # Collections and their refinements are resolved together by
                # _read_collection, above; nothing else here reads a refinement.
                continue
            if prop == "dcterms:modified" and value:
                metadata.modified = value
            elif name and content:
                if name == "calibre:series":
                    metadata.series = metadata.series or content
                elif name == "calibre:series_index":
                    metadata.series_index = metadata.series_index or content
                elif name != "cover":
                    metadata.extra_meta.append((name, content))

    unique_id = package.get("unique-identifier")
    if unique_id:
        for child in descendants(node, "identifier"):
            if child.get("id") == unique_id:
                target_value = text_of(child)
                for identifier in metadata.identifiers:
                    if identifier.value == target_value:
                        identifier.primary = True
                        break
                break
    if metadata.identifiers and not any(i.primary for i in metadata.identifiers):
        metadata.identifiers[0].primary = True
    return metadata


def _parse_manifest(package, opf_dir: str, entries: dict[str, bytes], report: Report):
    """Return ``(resources_by_id, id_by_path)`` for everything the manifest lists."""
    resources: dict[str, Resource] = {}
    id_by_path: dict[str, str] = {}
    manifest_nodes = children(package, "manifest")
    if not manifest_nodes:
        report.add("reader", Level.WARN, "package has no <manifest>; falling back to archive contents")
        return resources, id_by_path

    for item in children(manifest_nodes[0], "item"):
        item_id = item.get("id")
        href = item.get("href")
        if not href:
            continue
        if paths.is_remote(href):
            report.add("reader", Level.WARN, "manifest lists a remote resource", location=href)
            continue
        path = paths.resolve(posixpath.join(opf_dir, "_"), href) if opf_dir else paths.resolve("_", href)
        if path is None:
            continue
        if path not in entries:
            resolved = _find_case_insensitive(path, entries)
            if resolved is None:
                report.add(
                    "reader",
                    Level.WARN,
                    "manifest listed a file that is not in the archive; the entry was dropped",
                    location=path,
                )
                continue
            report.add("reader", Level.FIX, "matched a manifest entry by case-insensitive path", location=path)
            path = resolved
        declared = (item.get("media-type") or "").strip()
        media_type = guess_media_type(path, declared)
        if declared and declared != media_type:
            report.add(
                "reader",
                Level.FIX,
                f"manifest declared {declared!r}, which is not the type this file actually is; "
                f"corrected to {media_type!r}",
                location=path,
            )
        properties = set((item.get("properties") or "").split())
        resource = Resource(path=path, media_type=media_type, data=entries[path], properties=properties)
        if item_id:
            resources[item_id] = resource
            id_by_path[path] = item_id
        else:
            resources[f"__anon_{len(resources)}"] = resource
    return resources, id_by_path


def _find_case_insensitive(path: str, entries: dict[str, bytes]) -> str | None:
    lowered = path.lower()
    for name in entries:
        if name.lower() == lowered:
            return name
    return None


def _parse_spine(
    package, by_id: dict[str, Resource], report: Report
) -> tuple[list[SpineItem], str | None, str | None]:
    spine_nodes = children(package, "spine")
    if not spine_nodes:
        report.add("reader", Level.WARN, "package has no <spine>")
        return [], None, None
    spine_node = spine_nodes[0]
    items: list[SpineItem] = []
    for itemref in children(spine_node, "itemref"):
        idref = itemref.get("idref")
        resource = by_id.get(idref) if idref else None
        if resource is None:
            report.add(
                "reader",
                Level.WARN,
                "spine referenced an unknown manifest id; the entry was dropped",
                location=idref or "?",
            )
            continue
        linear = (itemref.get("linear") or "yes").strip().lower() != "no"
        properties = {
            # `page-spread-center` belongs to the rendition vocabulary and needs
            # its prefix; the other two live in the package vocabulary and do
            # not. EPUB 3.0 accepted the bare spelling, EPUB 3.3 calls it an
            # undefined property — so a book written to the older spec produces
            # an invalid package unless this is translated.
            "rendition:page-spread-center" if name == "page-spread-center" else name
            for name in (itemref.get("properties") or "").split()
        }
        items.append(SpineItem(resource.path, linear, properties))
    toc_id = spine_node.get("toc")
    ncx_path = by_id[toc_id].path if toc_id and toc_id in by_id else None
    # Which way the pages turn. An attribute, not a <meta> — and that is the
    # whole reason it used to be dropped: everything the model reads from
    # metadata survived a rebuild, and everything expressed structurally did not.
    direction = (spine_node.get("page-progression-direction") or "").strip().lower() or None
    return items, ncx_path, direction


def _parse_ncx(data: bytes, ncx_path: str, report: Report) -> tuple[list[NavPoint], list[PageTarget]]:
    root = etree.fromstring(data, _XML_PARSER)
    if root is None:
        report.add("reader", Level.WARN, "NCX could not be parsed", location=ncx_path)
        return [], []

    def build(nav_point) -> NavPoint | None:
        labels = descendants(nav_point, "navLabel")
        label = text_of(labels[0]) if labels else ""
        content = children(nav_point, "content")
        src = content[0].get("src") if content else None
        target = paths.resolve(ncx_path, src) if src else None
        if target and src and "#" in src:
            target = f"{target}#{src.split('#', 1)[1]}"
        kids = [build(child) for child in children(nav_point, "navPoint")]
        node = NavPoint(label=label or "—", target=target, children=[k for k in kids if k])
        return node if (node.label or node.target or node.children) else None

    toc: list[NavPoint] = []
    nav_maps = descendants(root, "navMap")
    if nav_maps:
        for nav_point in children(nav_maps[0], "navPoint"):
            built = build(nav_point)
            if built:
                toc.append(built)

    page_list: list[PageTarget] = []
    page_lists = descendants(root, "pageList")
    if page_lists:
        for page_target in children(page_lists[0], "pageTarget"):
            labels = descendants(page_target, "navLabel")
            content = children(page_target, "content")
            src = content[0].get("src") if content else None
            if not src:
                continue
            resolved = paths.resolve(ncx_path, src)
            if resolved and "#" in src:
                resolved = f"{resolved}#{src.split('#', 1)[1]}"
            if resolved:
                page_list.append(PageTarget(text_of(labels[0]) if labels else "", resolved))
    return toc, page_list


def _parse_nav_doc(data: bytes, nav_path: str, report: Report):
    """Extract toc / landmarks / page-list from an EPUB 3 navigation document."""
    root = etree.fromstring(data, _XML_PARSER)
    if root is None:
        report.add("reader", Level.WARN, "navigation document could not be parsed", location=nav_path)
        return [], [], []

    def parse_list(ol) -> list[NavPoint]:
        result: list[NavPoint] = []
        for li in children(ol, "li"):
            anchors = [c for c in li if lname(c).lower() in {"a", "span"}]
            label, target = "", None
            if anchors:
                label = text_of(anchors[0])
                href = anchors[0].get("href")
                if href:
                    resolved = paths.resolve(nav_path, href)
                    if resolved:
                        fragment = href.partition("#")[2]
                        target = f"{resolved}#{fragment}" if fragment else resolved
            nested = children(li, "ol")
            kids = parse_list(nested[0]) if nested else []
            if label or target or kids:
                result.append(NavPoint(label or "—", target, kids))
        return result

    toc: list[NavPoint] = []
    landmarks: list[Landmark] = []
    page_list: list[PageTarget] = []
    for nav in descendants(root, "nav"):
        nav_type = (attr(nav, "type", EPUB_NS) or "").strip().lower()
        lists = children(nav, "ol")
        if not lists:
            continue
        if nav_type == "landmarks":
            for li in children(lists[0], "li"):
                anchors = children(li, "a")
                if not anchors:
                    continue
                href = anchors[0].get("href")
                resolved = paths.resolve(nav_path, href) if href else None
                if not resolved:
                    continue
                fragment = (href or "").partition("#")[2]
                target = f"{resolved}#{fragment}" if fragment else resolved
                landmarks.append(
                    Landmark(
                        (attr(anchors[0], "type", EPUB_NS) or "bodymatter").strip(),
                        text_of(anchors[0]),
                        target,
                    )
                )
        elif nav_type == "page-list":
            for node in parse_list(lists[0]):
                if node.target:
                    page_list.append(PageTarget(node.label, node.target))
        elif nav_type == "toc" or not toc:
            parsed = parse_list(lists[0])
            if nav_type == "toc":
                toc = parsed
            elif not toc:
                toc = parsed
    return toc, landmarks, page_list


def _parse_guide(package, opf_path: str) -> list[Landmark]:
    """EPUB 2 ``<guide>`` maps onto EPUB 3 landmark semantics."""
    mapping = {
        "cover": "cover",
        "title-page": "titlepage",
        "titlepage": "titlepage",
        "toc": "toc",
        "text": "bodymatter",
        "copyright-page": "copyright-page",
        "acknowledgements": "acknowledgments",
        "bibliography": "bibliography",
        "colophon": "colophon",
        "dedication": "dedication",
        "epigraph": "epigraph",
        "foreword": "foreword",
        "glossary": "glossary",
        "index": "index",
        "loi": "loi",
        "lot": "lot",
        "notes": "endnotes",
        "preface": "preface",
    }
    landmarks: list[Landmark] = []
    for guide in children(package, "guide"):
        for reference in children(guide, "reference"):
            href = reference.get("href")
            if not href:
                continue
            resolved = paths.resolve(opf_path, href)
            if not resolved:
                continue
            fragment = href.partition("#")[2]
            target = f"{resolved}#{fragment}" if fragment else resolved
            guide_type = (reference.get("type") or "").strip().lower()
            landmarks.append(
                Landmark(mapping.get(guide_type, "bodymatter"), reference.get("title") or guide_type or "", target)
            )
    return landmarks


def _parse_encryption(entries: dict[str, bytes], book: Book, report: Report) -> None:
    data = entries.get("META-INF/encryption.xml")
    if not data:
        return
    root = etree.fromstring(data, _XML_PARSER)
    if root is None:
        report.add("reader", Level.WARN, "META-INF/encryption.xml could not be parsed")
        return
    for encrypted_data in descendants(root, "EncryptedData"):
        methods = descendants(encrypted_data, "EncryptionMethod")
        algorithm = methods[0].get("Algorithm", "") if methods else ""
        for reference in descendants(encrypted_data, "CipherReference"):
            uri = reference.get("URI")
            if not uri:
                continue
            target = paths.resolve("_", uri)
            if not target:
                continue
            book.encrypted[target] = algorithm
            if algorithm not in OBFUSCATION_ALGORITHMS:
                book.has_drm = True
    if book.has_drm:
        report.add(
            "reader",
            Level.ERROR,
            "archive declares real encryption (DRM), not just font obfuscation",
            detail="EPUB-Forge will not attempt to decrypt DRM-protected content.",
        )


def _detect_cover(package, by_id: dict[str, Resource], book: Book) -> str | None:
    for resource in by_id.values():
        if "cover-image" in resource.properties:
            return resource.path
    for metadata_node in children(package, "metadata"):
        for meta in descendants(metadata_node, "meta"):
            if (meta.get("name") or "").lower() == "cover":
                content = meta.get("content")
                if content and content in by_id and by_id[content].is_image:
                    return by_id[content].path
    for landmark in book.landmarks:
        if landmark.epub_type == "cover":
            candidate = landmark.target.split("#")[0]
            resource = book.resources.get(candidate)
            if resource and resource.is_image:
                return candidate
    for path, resource in book.resources.items():
        if resource.is_image and "cover" in posixpath.basename(path).lower():
            return path
    return None


def read_epub(source: str, report: Report) -> Book:
    """Load *source* into a :class:`Book`, recovering from structural damage."""
    archive = _read_archive(source, report)
    entries = archive.entries
    if not archive.mimetype_ok:
        report.add("reader", Level.FIX, "missing or incorrect 'mimetype' entry; will be regenerated")

    opf_path = _locate_opf(entries, report)
    opf_dir = posixpath.dirname(opf_path)
    package = etree.fromstring(entries[opf_path], _XML_PARSER)
    if package is None:
        raise EpubReadError(f"package document at {opf_path} is unparseable")

    book = Book()
    book.source_opf_path = opf_path
    book.source_version = (package.get("version") or "unknown").strip()
    book.metadata = _parse_metadata(package, report)

    by_id, _ = _parse_manifest(package, opf_dir, entries, report)
    for resource in by_id.values():
        book.add(resource)

    book.source_package = entries.get(opf_path)
    book.spine, book.ncx_path, book.page_progression_direction = _parse_spine(
        package, by_id, report
    )
    if book.page_progression_direction in ("rtl", "ltr"):
        report.add(
            "reader",
            Level.INFO,
            f"page progression is {book.page_progression_direction}; carried through",
        )

    for prefix in ("rendition:layout", "rendition:orientation", "rendition:spread", "rendition:flow"):
        for metadata_node in children(package, "metadata"):
            for meta in descendants(metadata_node, "meta"):
                if (meta.get("property") or "").strip() == prefix and not meta.get("refines"):
                    book.rendition[prefix.split(":", 1)[1]] = text_of(meta)

    book.landmarks = _parse_guide(package, opf_path)

    for resource in list(book.resources.values()):
        if "nav" in resource.properties and resource.is_content_doc:
            book.nav_path = resource.path
            break

    if book.nav_path:
        toc, landmarks, page_list = _parse_nav_doc(book.resources[book.nav_path].data, book.nav_path, report)
        book.toc = toc
        if landmarks:
            book.landmarks = landmarks
        book.page_list = page_list

    if not book.toc and book.ncx_path and book.ncx_path in book.resources:
        toc, page_list = _parse_ncx(book.resources[book.ncx_path].data, book.ncx_path, report)
        book.toc = toc
        book.page_list = book.page_list or page_list
        report.add("reader", Level.INFO, "table of contents recovered from the legacy NCX")

    if not book.toc:
        ncx_candidates = [r for r in book.resources.values() if r.path.lower().endswith(".ncx")]
        if ncx_candidates:
            toc, page_list = _parse_ncx(ncx_candidates[0].data, ncx_candidates[0].path, report)
            book.toc = toc
            book.page_list = book.page_list or page_list
            book.ncx_path = ncx_candidates[0].path
            report.add("reader", Level.FIX, "found an unreferenced NCX and used it for the toc")

    book.cover_path = _detect_cover(package, by_id, book)
    _parse_encryption(entries, book, report)

    manifested = set(book.resources)
    skipped_prefixes = ("META-INF/",)
    for name, data in entries.items():
        if name in manifested or name == opf_path or name.startswith(skipped_prefixes):
            continue
        media_type = guess_media_type(name)
        book.add(Resource(path=name, media_type=media_type, data=data, manifested=False))
        report.add(
            "reader", Level.INFO, "file present in the archive but absent from the manifest", location=name
        )

    if not book.spine:
        recovered = sorted(r.path for r in book.resources.values() if r.is_content_doc)
        book.spine = [SpineItem(path) for path in recovered]
        if recovered:
            report.add(
                "reader",
                Level.FIX,
                f"spine was empty; rebuilt it from {len(recovered)} content documents in filename order",
            )

    report.stats["source_version"] = book.source_version
    report.stats["source_resources"] = len(book.resources)
    report.stats["source_spine_items"] = len(book.spine)
    return book
