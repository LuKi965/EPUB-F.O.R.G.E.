"""Serialises a :class:`~epubforge.model.Book` into a conforming EPUB 3.3 file.

The package document is generated from the model rather than edited from the
source, which is what makes the output independent of however broken the input
was. ZIP layout follows OCF: an uncompressed ``mimetype`` first, then
``META-INF``, then content.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from xml.sax.saxutils import escape, quoteattr

from . import compat, paths
from .model import Book
from .report import Level, Report

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{opf_path}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

#: Media types that are already compressed; deflating them wastes time and space.
_STORE_TYPES = (
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "font/woff", "font/woff2", "audio/mpeg", "audio/mp4", "video/mp4",
)

_ID_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

#: The earliest timestamp a ZIP entry can carry. Every entry gets it, so two
#: runs on the same input produce the same bytes. `writestr` with a plain string
#: name stamps the wall clock instead, which is how `container.xml` and the
#: package document used to differ between otherwise identical runs.
EPOCH = (1980, 1, 1, 0, 0, 0)


def _entry(path: str, compression: int = zipfile.ZIP_DEFLATED) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=EPOCH)
    info.compress_type = compression
    info.external_attr = 0o644 << 16
    return info


def _make_id(path: str, taken: set[str]) -> str:
    stem = posixpath.basename(path)
    candidate = _ID_UNSAFE.sub("-", stem) or "item"
    if not re.match(r"^[A-Za-z_]", candidate):
        candidate = f"i-{candidate}"
    unique = candidate
    counter = 2
    while unique in taken:
        unique = f"{candidate}-{counter}"
        counter += 1
    taken.add(unique)
    return unique


def _element(tag: str, text: str | None = None, **attributes) -> str:
    parts = [tag]
    for key, value in attributes.items():
        if value is None:
            continue
        parts.append(f"{key.replace('_', '-')}={quoteattr(str(value))}")
    opened = " ".join(parts)
    if text is None:
        return f"<{opened}/>"
    return f"<{opened}>{escape(text)}</{tag}>"


def build_opf(book: Book, opf_path: str, report: Report) -> tuple[str, dict[str, str]]:
    """Render the package document; also returns the path→manifest-id map."""
    metadata = book.metadata
    identifier = metadata.primary_identifier
    lines: list[str] = ['<?xml version="1.0" encoding="utf-8"?>']
    language = metadata.language or "en"
    # "schema" only became a reserved prefix in EPUB 3.3. A reader built to
    # 3.0 or 3.1 sees an undeclared prefix in every accessibility property and
    # may reject the package document outright — which looks to the user like a
    # book that will not open. Declaring it is redundant under 3.3 and legal,
    # so it costs nothing and restores those readers.
    prefixes = []
    if metadata.accessibility or metadata.accessibility_summary:
        prefixes.append("schema: http://schema.org/")
    if metadata.conforms_to:
        prefixes.append("a11y: http://www.idpf.org/epub/vocab/package/a11y/#")
    prefix_attribute = f" prefix={quoteattr(' '.join(prefixes))}" if prefixes else ""

    lines.append(
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        f'unique-identifier="pub-id" xml:lang={quoteattr(language)}{prefix_attribute}>'
    )

    # --- metadata -----------------------------------------------------------
    lines.append('  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">')
    if identifier:
        lines.append(f"    {_element('dc:identifier', identifier.value, id='pub-id')}")
        if identifier.scheme:
            lines.append(
                f'    <meta refines="#pub-id" property="identifier-type" '
                f'scheme="onix:codelist5">{escape(identifier.scheme)}</meta>'
            )
    for index, extra in enumerate(i for i in metadata.identifiers if not i.primary):
        lines.append(f"    {_element('dc:identifier', extra.value, id=f'id-{index}')}")

    lines.append(f"    {_element('dc:title', metadata.title, id='title')}")
    lines.append('    <meta refines="#title" property="title-type">main</meta>')
    if metadata.sort_title:
        lines.append(
            f'    <meta refines="#title" property="file-as">{escape(metadata.sort_title)}</meta>'
        )
    if metadata.subtitle:
        lines.append(f"    {_element('dc:title', metadata.subtitle, id='subtitle')}")
        lines.append('    <meta refines="#subtitle" property="title-type">subtitle</meta>')

    lines.append(f"    {_element('dc:language', language)}")
    for extra_language in metadata.languages_extra:
        lines.append(f"    {_element('dc:language', extra_language)}")

    for index, creator in enumerate(metadata.creators):
        tag = "dc:creator" if creator.role == "aut" else "dc:contributor"
        creator_id = f"creator-{index}"
        lines.append(f"    {_element(tag, creator.name, id=creator_id)}")
        lines.append(
            f'    <meta refines="#{creator_id}" property="role" '
            f'scheme="marc:relators">{escape(creator.role)}</meta>'
        )
        if creator.file_as:
            lines.append(
                f'    <meta refines="#{creator_id}" property="file-as">{escape(creator.file_as)}</meta>'
            )

    if metadata.publisher:
        lines.append(f"    {_element('dc:publisher', metadata.publisher)}")
    if metadata.published:
        lines.append(f"    {_element('dc:date', metadata.published)}")
    if metadata.description:
        lines.append(f"    {_element('dc:description', metadata.description)}")
    for subject in dict.fromkeys(metadata.subjects):
        lines.append(f"    {_element('dc:subject', subject)}")
    if metadata.rights:
        lines.append(f"    {_element('dc:rights', metadata.rights)}")
    if metadata.source:
        lines.append(f"    {_element('dc:source', metadata.source)}")

    if metadata.series:
        lines.append(
            f'    <meta property="belongs-to-collection" id="series">{escape(metadata.series)}</meta>'
        )
        lines.append('    <meta refines="#series" property="collection-type">series</meta>')
        if metadata.series_index:
            lines.append(
                f'    <meta refines="#series" property="group-position">'
                f"{escape(metadata.series_index)}</meta>"
            )

    lines.append(f'    <meta property="dcterms:modified">{escape(metadata.modified or "")}</meta>')

    # EPUB Accessibility 1.1. The prefixes are declared on <package> above so
    # that readers predating EPUB 3.3 accept these properties.
    for property_name, values in metadata.accessibility.items():
        for value in values:
            lines.append(f'    <meta property="{property_name}">{escape(value)}</meta>')
    if metadata.accessibility_summary:
        lines.append(
            f'    <meta property="schema:accessibilitySummary">'
            f"{escape(metadata.accessibility_summary)}</meta>"
        )
    if metadata.conforms_to:
        lines.append(
            f'    <link rel="dcterms:conformsTo" href="{escape(metadata.conforms_to)}"/>'
            if metadata.conforms_to.startswith("http")
            else f'    <meta property="dcterms:conformsTo">{escape(metadata.conforms_to)}</meta>'
        )

    for key, value in book.rendition.items():
        lines.append(f'    <meta property="rendition:{escape(key)}">{escape(value)}</meta>')

    for name, content in metadata.extra_meta:
        if name.startswith("calibre:"):
            continue
        lines.append(f'    <meta name={quoteattr(name)} content={quoteattr(content)}/>')

    if book.cover_path:
        # Legacy hint: EPUB 2 readers only recognise the cover this way.
        cover_id_placeholder = "__COVER_ID__"
        lines.append(f'    <meta name="cover" content="{cover_id_placeholder}"/>')
    lines.append("  </metadata>")

    # --- manifest -----------------------------------------------------------
    lines.append("  <manifest>")
    taken_ids: set[str] = {"pub-id", "title", "subtitle", "series"}
    id_by_path: dict[str, str] = {}
    for path in sorted(book.resources):
        resource = book.resources[path]
        item_id = _make_id(path, taken_ids)
        id_by_path[path] = item_id
        href = paths.relative(opf_path, path)
        properties = " ".join(sorted(resource.properties)) or None
        attributes = {
            "id": item_id,
            "href": href,
            "media-type": resource.media_type,
            "properties": properties,
        }
        rendered = " ".join(
            f"{key}={quoteattr(value)}" for key, value in attributes.items() if value is not None
        )
        lines.append(f"    <item {rendered}/>")
    lines.append("  </manifest>")

    # --- spine --------------------------------------------------------------
    ncx_id = id_by_path.get(book.ncx_path) if book.ncx_path else None
    spine_attributes = f' toc={quoteattr(ncx_id)}' if ncx_id else ""
    lines.append(f"  <spine{spine_attributes}>")
    for item in book.spine:
        item_id = id_by_path.get(item.path)
        if item_id is None:
            report.add("writer", Level.ERROR, "spine item vanished before writing", location=item.path)
            continue
        attributes = [f"idref={quoteattr(item_id)}"]
        if not item.linear:
            attributes.append('linear="no"')
        if item.properties:
            attributes.append(f'properties={quoteattr(" ".join(sorted(item.properties)))}')
        lines.append(f"    <itemref {' '.join(attributes)}/>")
    lines.append("  </spine>")

    # --- guide (opt-in) -----------------------------------------------------
    # EPUB 3.3 removed this element. It is emitted only when a compatibility
    # profile asked for it, because Amazon's converter and RMSDK-based readers
    # locate the cover and the start-reading position here and nowhere else.
    if "guide" in book.compat:
        references = compat.guide_references(book)
        if references:
            lines.append("  <guide>")
            for guide_type, title, target in references:
                target_path, _, fragment = target.partition("#")
                href = paths.relative(opf_path, target_path)
                if fragment:
                    href = f"{href}#{fragment}"
                lines.append(
                    f"    <reference type={quoteattr(guide_type)} "
                    f"title={quoteattr(title)} href={quoteattr(href)}/>"
                )
            lines.append("  </guide>")

    lines.append("</package>")

    opf = "\n".join(lines) + "\n"
    if book.cover_path:
        cover_id = id_by_path.get(book.cover_path)
        if cover_id:
            opf = opf.replace("__COVER_ID__", cover_id)
        else:
            opf = re.sub(r'\s*<meta name="cover" content="__COVER_ID__"/>\n', "\n", opf)
    return opf, id_by_path


def write_epub(book: Book, destination: str, report: Report, content_dir: str = "EPUB") -> None:
    opf_path = f"{content_dir.strip('/')}/package.opf"
    opf, _ = build_opf(book, opf_path, report)

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        # OCF requires 'mimetype' to be the first entry and stored uncompressed.
        archive.writestr(_entry("mimetype", zipfile.ZIP_STORED), b"application/epub+zip")

        archive.writestr(
            _entry("META-INF/container.xml"), CONTAINER_XML.format(opf_path=opf_path)
        )
        # Reader-specific container entries, added only by a compatibility
        # profile. Written next to container.xml because that is where the
        # readers that look for them look.
        for extra_path in sorted(book.container_files):
            archive.writestr(_entry(extra_path), book.container_files[extra_path])
        archive.writestr(_entry(opf_path), opf.encode("utf-8"))

        for path in sorted(book.resources):
            resource = book.resources[path]
            compression = (
                zipfile.ZIP_STORED if resource.media_type in _STORE_TYPES else zipfile.ZIP_DEFLATED
            )
            archive.writestr(_entry(path, compression), resource.data)

    # mimetype, container.xml and the package document, plus anything a
    # compatibility profile added beside them.
    report.stats["output_resources"] = len(book.resources) + 3 + len(book.container_files)
    report.stats["output_spine_items"] = len(book.spine)
