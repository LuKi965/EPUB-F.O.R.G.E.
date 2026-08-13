"""Serialises a :class:`~epubforge.model.Book` into a conforming EPUB 3.3 file.

The package document is generated from the model rather than edited from the
source, which is what makes the output independent of however broken the input
was. ZIP layout follows OCF: an uncompressed ``mimetype`` first, then
``META-INF``, then content.
"""

from __future__ import annotations

import os
import posixpath
import re
import tempfile
import zipfile
from xml.sax.saxutils import escape, quoteattr

from . import compat, paths
from .model import Book, CollectionMembership
from .report import Level, Report

#: A metadata refinement has to name a manifest id, and the manifest is written
#: after the metadata. The path goes in between these markers and is swapped for
#: the id once both halves exist — the same trick `__COVER_ID__` uses, with room
#: for a value in the middle.
_OVERLAY_ID = "__OVERLAY_ID__"
_OVERLAY_END = "__END__"

#: Prefixes EPUB 3.3 reserves, which must not be declared again.
_RESERVED_PREFIXES = frozenset({"dcterms", "marc", "media", "onix", "rendition", "schema", "xsd", "a11y", "msv", "prism"})

#: Where each reserved prefix points, so one this writer *uses* can be declared
#: outright instead of left to the reader's own table.
#:
#: EPUB 3 says a reserved prefix needs no declaration and EPUBCheck agrees, so
#: for two releases this writer declared `schema:` and `a11y:` — with the reason
#: written down beside them — and left `rendition:` and the rest to the rule.
#: An InkBOOK Focus proved the rule is not enough: it opened a package with
#: `rendition:` declared and hung on the same package without it, everything
#: else byte for byte identical. Whatever table that reader consults, ours is
#: not in it.
#:
#: A declaration is redundant under 3.3, legal, and about eighty bytes. Leaving
#: it out was worth nothing and cost a reader.
_RESERVED_URIS = {
    "a11y": "http://www.idpf.org/epub/vocab/package/a11y/#",
    "dcterms": "http://purl.org/dc/terms/",
    "marc": "http://id.loc.gov/vocabulary/",
    "media": "http://www.idpf.org/epub/vocab/overlays/#",
    "onix": "http://www.editeur.org/ONIX/book/codelists/current.html#",
    "rendition": "http://www.idpf.org/vocab/rendition/#",
    "schema": "http://schema.org/",
}

#: Properties this writer produces from the model. A carried-through copy of
#: one of these would be a duplicate, and the model's version is the one that
#: has been through the pipeline.
_GENERATED_PROPERTIES = frozenset(
    {
        "dcterms:modified",
        "dcterms:conformsTo",
        "belongs-to-collection",
        "collection-type",
        "group-position",
        "identifier-type",
        "title-type",
        "file-as",
        "alternate-script",
        "role",
        "display-seq",
    }
)

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
    # The mode goes in the high half, and it has to include the file-type bits.
    # `0o644 << 16` alone declares a Unix mode whose type field is zero — not a
    # regular file, not a directory, not anything. `create_system = 3` below
    # says these attributes *are* Unix attributes, so writing an impossible
    # mode is claiming one thing and providing another.
    #
    # Python's own `writestr` does the same, which is why it is common and why
    # nothing on a desktop notices. Both files known to work on the e-reader
    # that started this — one from another tool, one from Calibre — carry
    # `S_IFREG`; every file this program has ever written does not.
    info.external_attr = (0o100644 << 16)
    # `zipfile` stamps every entry with the operating system it ran on — 0 for
    # Windows, 3 for everything else — in both headers. One book built in two
    # places therefore came out with different bytes and an identical
    # rendering, which is precisely the false alarm a corpus signature must not
    # raise: the person recording signatures and the person checking them are
    # rarely on the same system. Pinned to 3, which is what the Unix permission
    # bits set above already assume.
    info.create_system = 3
    return info


def _prefixes_used(metadata) -> set[str]:
    """Prefixes the carried-through properties actually need declared."""
    used = set()
    for prop, _, _ in metadata.extra_properties:
        if prop in _GENERATED_PROPERTIES or prop.startswith(("schema:", "rendition:", "media:")):
            continue
        prefix, separator, _ = prop.partition(":")
        if separator and prefix not in _RESERVED_PREFIXES:
            used.add(prefix)
    return used


def _render_collection(collection, opf_path: str, indent: str) -> list[str]:
    """One `<collection>` and everything under it, back into XML."""
    attributes = dict(collection.attributes)
    if collection.role:
        attributes = {"role": collection.role, **attributes}
    rendered = "".join(f" {key}={quoteattr(value)}" for key, value in attributes.items())
    lines = [f"{indent}<collection{rendered}>"]

    for raw in collection.raw_metadata:
        # Carried verbatim: the contents of a collection's metadata are as open
        # as its role, so re-serialising it from a model would mean inventing
        # one for something nobody here understands.
        lines.append(f"{indent}  {raw}")

    # A collection holds links *or* nested collections, never both, so the
    # order between the two groups cannot matter for a conforming source. A
    # non-conforming one is regrouped rather than reproduced — the alternative
    # is emitting a package document that no reader will accept.
    for child in collection.children:
        lines += _render_collection(child, opf_path, indent + "  ")

    for link in collection.links:
        href = paths.relative(opf_path, link.path) if link.path else link.href
        link_attributes = {"href": href, **link.attributes}
        rendered = "".join(f" {key}={quoteattr(value)}" for key, value in link_attributes.items())
        lines.append(f"{indent}  <link{rendered}/>")

    lines.append(f"{indent}</collection>")
    return lines


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


def _alternate_script(target_id: str, language: str, value: str) -> str:
    """A transliteration of a title or a name, tagged with the script it is in.

    Without the language the refinement says nothing — it is the pair that
    tells a catalogue that this Latin string denotes that Japanese one.
    """
    language_attribute = f" xml:lang={quoteattr(language)}" if language else ""
    return (
        f'    <meta refines="#{target_id}" property="alternate-script"'
        f"{language_attribute}>{escape(value)}</meta>"
    )


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


#: Stands in for the `<package>` line until the rest of the document exists.
_PACKAGE_PLACEHOLDER = "\x00package\x00"


def _declare_prefixes(document: str, metadata) -> str:
    """The `prefix` attribute, derived from the properties actually written.

    Every `property="x:y"` and `scheme="x:y"` in the finished document needs
    `x` to mean something to whoever reads it. Reserved prefixes are supposed
    to need no declaration, and a reader that does not know one is the reason
    this is computed rather than assumed.
    """
    used = {
        match.group(1)
        for match in re.finditer(r'(?:property|scheme)="([A-Za-z][\w.-]*):', document)
    }
    declarations = []
    for prefix in sorted(used):
        uri = _RESERVED_URIS.get(prefix) or metadata.prefixes.get(prefix)
        if uri:
            declarations.append(f"{prefix}: {uri}")
    return f" prefix={quoteattr(' '.join(declarations))}" if declarations else ""


#: ONIX Code List 5 — "Product identifier type", the vocabulary this program
#: declares when it says `scheme="onix:codelist5"`. Its members are two-digit
#: codes, and a two-digit code is what a distributor's importer reads.
#:
#: This wrote the word `ISBN` into that field for as long as the field existed:
#: `scheme="onix:codelist5">ISBN<`, which announces a vocabulary and then says
#: something that is not in it. Valid XML, valid EPUB, and unreadable by the
#: only kind of software that asks the question.
_ONIX_CODELIST_5 = {"ISBN_13": "15", "ISBN_10": "02", "DOI": "06"}


def _identifier_type(identifier) -> tuple[str, str]:
    """The code and vocabulary for one identifier's `identifier-type`.

    ISBN-13 and ISBN-10 are different codes in the same list, so the digits
    decide rather than the word: everything an EPUB carries in practice is a
    13-digit ISBN, but a book old enough to have a 10-digit one is exactly the
    book somebody is rebuilding.

    A scheme this does not know keeps its own word and loses the ONIX claim,
    because the alternative is asserting membership of a list on a value that
    is not in it — which is the defect this exists to stop making.
    """
    scheme = (identifier.scheme or "").strip()
    # A source that already wrote a code keeps it, whatever it is. The reader
    # fills `scheme` from the source's own refinement when there is one, so this
    # value may well be a code already — the kitchen-sink fixture carries `06` —
    # and rewriting somebody's ONIX code because it is not one of the three
    # spelled out below would be inventing metadata, not repairing it. Two
    # digits in a field declared as this list is a code.
    if len(scheme) == 2 and scheme.isdigit():
        return scheme, "onix:codelist5"
    if scheme.upper() == "ISBN":
        digits = "".join(c for c in identifier.value if c.isdigit() or c in "Xx")
        key = "ISBN_10" if len(digits) == 10 else "ISBN_13"
        return _ONIX_CODELIST_5[key], "onix:codelist5"
    code = _ONIX_CODELIST_5.get(scheme.upper())
    if code:
        return code, "onix:codelist5"
    return scheme, "xsd:string"


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
    # Base text direction for the whole package. A structural attribute, so it
    # has to be carried deliberately: a Hebrew or Arabic edition that loses it
    # renders its metadata the wrong way round.
    direction = f" dir={quoteattr(metadata.direction)}" if metadata.direction else ""
    # The prefix attribute is filled in at the end, from the document that was
    # actually written. Deciding it up front means deciding it twice — once
    # here and once wherever a property is emitted — and the two drifted: the
    # writer declared `schema:` while emitting `rendition:` undeclared, which
    # is exactly the package an InkBOOK Focus hangs on.
    lines.append(_PACKAGE_PLACEHOLDER)

    # --- metadata -----------------------------------------------------------
    lines.append('  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">')
    if identifier:
        lines.append(f"    {_element('dc:identifier', identifier.value, id='pub-id')}")
        if identifier.scheme:
            code, vocabulary = _identifier_type(identifier)
            lines.append(
                f'    <meta refines="#pub-id" property="identifier-type" '
                f'scheme="{vocabulary}">{escape(code)}</meta>'
            )
    for index, extra in enumerate(i for i in metadata.identifiers if not i.primary):
        lines.append(f"    {_element('dc:identifier', extra.value, id=f'id-{index}')}")

    title_attributes = {"id": "title"}
    if metadata.title_language:
        title_attributes["xml:lang"] = metadata.title_language
    if metadata.title_direction:
        title_attributes["dir"] = metadata.title_direction
    lines.append(f"    {_element('dc:title', metadata.title, **title_attributes)}")
    lines.append('    <meta refines="#title" property="title-type">main</meta>')
    if metadata.sort_title:
        lines.append(
            f'    <meta refines="#title" property="file-as">{escape(metadata.sort_title)}</meta>'
        )
    for script_language, script_value in metadata.title_alternate_scripts:
        lines.append(_alternate_script("title", script_language, script_value))
    if metadata.subtitle:
        lines.append(f"    {_element('dc:title', metadata.subtitle, id='subtitle')}")
        lines.append('    <meta refines="#subtitle" property="title-type">subtitle</meta>')
    # Everything past the main title and the subtitle. Written without a
    # `title-type`, because the source did not say what they were and inventing
    # a type is a claim; written at all, because the alternative is what this
    # did until 0.2.20 — a third `dc:title` that simply stopped existing.
    for index, other in enumerate(metadata.titles[1:]):
        lines.append(f"    {_element('dc:title', other, id=f'title-{index}')}")

    lines.append(f"    {_element('dc:language', language)}")
    for extra_language in metadata.languages_extra:
        lines.append(f"    {_element('dc:language', extra_language)}")

    for index, creator in enumerate(metadata.creators):
        tag = "dc:creator" if creator.role == "aut" else "dc:contributor"
        creator_id = f"creator-{index}"
        creator_attributes = {"id": creator_id}
        if creator.language:
            creator_attributes["xml:lang"] = creator.language
        if creator.direction:
            creator_attributes["dir"] = creator.direction
        lines.append(f"    {_element(tag, creator.name, **creator_attributes)}")
        lines.append(
            f'    <meta refines="#{creator_id}" property="role" '
            f'scheme="marc:relators">{escape(creator.role)}</meta>'
        )
        if creator.file_as:
            lines.append(
                f'    <meta refines="#{creator_id}" property="file-as">{escape(creator.file_as)}</meta>'
            )
        for script_language, script_value in creator.alternate_scripts:
            lines.append(_alternate_script(creator_id, script_language, script_value))

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
    for element_name, element_value in metadata.dublin_core_extra:
        lines.append(f"    {_element(f'dc:{element_name}', element_value)}")

    # Every collection the book belongs to, not just the first series-typed
    # one. A book published inside a boxed set *and* as part of a series used
    # to keep whichever the model happened to hold.
    memberships = list(metadata.collection_memberships)
    if not memberships and metadata.series:
        # Nothing was read from a `belongs-to-collection`; the series came from
        # somewhere else, such as calibre's own metadata.
        memberships = [CollectionMembership(metadata.series, "series", metadata.series_index)]
    for index, membership in enumerate(memberships):
        anchor = "series" if index == 0 else f"collection-{index}"
        lines.append(
            f'    <meta property="belongs-to-collection" id="{anchor}">'
            f"{escape(membership.name)}</meta>"
        )
        lines.append(
            f'    <meta refines="#{anchor}" property="collection-type">'
            f"{escape(membership.collection_type)}</meta>"
        )
        if membership.position:
            lines.append(
                f'    <meta refines="#{anchor}" property="group-position">'
                f"{escape(membership.position)}</meta>"
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

    # Media Overlays. Declaring an overlay without its duration is not a
    # smaller book, it is an invalid one — EPUBCheck rejects the pair. The
    # refinement targets a manifest id that does not exist yet, so it goes in
    # as a placeholder and is resolved once the manifest has been written.
    for key, value in sorted(metadata.media_classes.items()):
        lines.append(f'    <meta property="{escape(key)}">{escape(value)}</meta>')
    for target, value in sorted(metadata.media_durations.items(), key=lambda pair: pair[0] or ""):
        if target is None:
            lines.append(f'    <meta property="media:duration">{escape(value)}</meta>')
        elif target in book.resources:
            lines.append(
                f'    <meta refines="#{_OVERLAY_ID}{target}{_OVERLAY_END}" '
                f'property="media:duration">{escape(value)}</meta>'
            )

    for name, content in metadata.extra_meta:
        if name.startswith("calibre:"):
            continue
        lines.append(f'    <meta name={quoteattr(name)} content={quoteattr(content)}/>')

    # Properties with no field of their own, carried through. Anything this
    # writer generates itself is skipped rather than repeated: the model's
    # version is the one that has been through the pipeline.
    for prop, value, attributes in metadata.extra_properties:
        if prop in _GENERATED_PROPERTIES or prop.startswith(("schema:", "rendition:", "media:")):
            continue
        rendered = "".join(
            f" {key}={quoteattr(attribute_value)}"
            for key, attribute_value in sorted(attributes.items())
            if not key.startswith("{")
        )
        lines.append(f'    <meta property={quoteattr(prop)}{rendered}>{escape(value)}</meta>')

    for comment in metadata.metadata_comments:
        # `--` cannot appear inside an XML comment and there is no escape for
        # it, so one that contains a pair is dropped rather than mangled. No
        # watermark seen in the wild has looked like that.
        if "--" in comment or comment.endswith("-"):
            continue
        lines.append(f"    <!--{comment}-->")

    if book.cover_path:
        # Legacy hint: EPUB 2 readers only recognise the cover this way.
        cover_id_placeholder = "__COVER_ID__"
        lines.append(f'    <meta name="cover" content="{cover_id_placeholder}"/>')
    lines.append("  </metadata>")

    # --- manifest -----------------------------------------------------------
    lines.append("  <manifest>")
    taken_ids: set[str] = {"pub-id", "title", "subtitle", "series"}
    id_by_path: dict[str, str] = {}
    # Two passes: an item may point forwards, at a fallback or an overlay that
    # has not been given an id yet.
    for path in sorted(book.resources):
        id_by_path[path] = _make_id(path, taken_ids)

    for path in sorted(book.resources):
        resource = book.resources[path]
        href = paths.relative(opf_path, path)
        properties = " ".join(sorted(resource.properties)) or None
        attributes = {
            "id": id_by_path[path],
            "href": href,
            "media-type": resource.media_type,
            "properties": properties,
            # Dropped silently until 0.2.1. A book whose narration attribute is
            # gone does not merely lose the narration: EPUBCheck rejects a SMIL
            # file whose document does not point back at it.
            "fallback": id_by_path.get(resource.fallback or ""),
            "media-overlay": id_by_path.get(resource.media_overlay or ""),
        }
        rendered = " ".join(
            f"{key}={quoteattr(value)}" for key, value in attributes.items() if value is not None
        )
        lines.append(f"    <item {rendered}/>")

    # Declared, never fetched. An id is minted for these too, so that a local
    # item can name one as its fallback and vice versa.
    for index, remote in enumerate(book.remote_resources):
        remote_id = _make_id(f"remote-{index}-{posixpath.basename(remote.href)}", taken_ids)
        attributes = {
            "id": remote_id,
            "href": remote.href,
            "media-type": remote.media_type,
            "properties": " ".join(sorted(remote.properties)) or None,
            "fallback": id_by_path.get(remote.fallback or ""),
        }
        rendered = " ".join(
            f"{key}={quoteattr(value)}" for key, value in attributes.items() if value is not None
        )
        lines.append(f"    <item {rendered}/>")
    lines.append("  </manifest>")

    # --- spine --------------------------------------------------------------
    ncx_id = id_by_path.get(book.ncx_path) if book.ncx_path else None
    spine_attributes = f' toc={quoteattr(ncx_id)}' if ncx_id else ""
    if book.page_progression_direction:
        spine_attributes += (
            f" page-progression-direction={quoteattr(book.page_progression_direction)}"
        )
    lines.append(f"  <spine{spine_attributes}>")
    for item in book.spine:
        item_id = id_by_path.get(item.path)
        if item_id is None:
            report.add("writer", Level.ERROR, "package.spine-item-vanished", location=item.path)
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

    # `<collection>` comes after the spine and the guide. The vocabulary of
    # `role` is open, so nothing here interprets them — what was read is what
    # is written, with only the hrefs moved to follow their files.
    for collection in book.collections:
        lines += _render_collection(collection, opf_path, indent="  ")

    lines.append("</package>")

    opf = "\n".join(lines) + "\n"

    def resolve_overlay(match: re.Match) -> str:
        item_id = id_by_path.get(match.group(1))
        # An overlay whose file is gone leaves a refinement pointing nowhere,
        # which is worse than no refinement; the loss is already reported by the
        # stage that removed the file.
        return item_id if item_id else "__MISSING__"

    if _OVERLAY_ID in opf:
        opf = re.sub(
            re.escape(_OVERLAY_ID) + r"(.*?)" + re.escape(_OVERLAY_END), resolve_overlay, opf
        )
        opf = re.sub(r'\s*<meta refines="#__MISSING__"[^>]*>[^<]*</meta>', "", opf)

    if book.cover_path:
        cover_id = id_by_path.get(book.cover_path)
        if cover_id:
            opf = opf.replace("__COVER_ID__", cover_id)
        else:
            opf = re.sub(r'\s*<meta name="cover" content="__COVER_ID__"/>\n', "\n", opf)

    # Last, so it describes the finished document rather than a prediction of it.
    opf = opf.replace(
        _PACKAGE_PLACEHOLDER,
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        f'unique-identifier="pub-id" xml:lang={quoteattr(language)}'
        f"{direction}{_declare_prefixes(opf, metadata)}>",
    )
    return opf, id_by_path


class ArchiveVerificationError(OSError):
    """The file this program just wrote is not the file it meant to write.

    A distinct type because it means something categorically different from the
    `OSError`s around it. A full disk or a read-only folder is the world saying
    no, and a batch should record that book as failed and carry on. *This* is
    the archive failing its own read-back — a defect in this program, or a disk
    corrupting what it was handed — and swallowing it into a tidy result would
    hide the one failure nobody else can see.

    Introduced when catching `OSError` in `rebuild` for batch isolation (F-026)
    turned out to catch this too, and the failure-injection suite said so within
    the hour: six tests that pin "a container reading back wrong is not
    promoted" stopped seeing anything raised at all.
    """



def _encryption_xml(book: Book) -> str:
    """Declare the resources this rebuild could not turn back into plain files.

    Until 0.2.22 there was nothing to write here, because the font stage cleared
    its whole register the moment *any* font was recovered. A book with two
    fonts and one bad key came out with the second still scrambled, its
    declaration gone with the first's, and `font/ttf` on the label — a font that
    loads and draws nothing, in a container that says everything is fine.

    Nothing is re-encrypted here and nothing could be. This says what is true of
    the bytes as they stand.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"',
        '            xmlns:enc="http://www.w3.org/2001/04/xmlenc#">',
    ]
    for path in sorted(book.encrypted):
        lines += [
            "  <enc:EncryptedData>",
            f'    <enc:EncryptionMethod Algorithm={quoteattr(book.encrypted[path])}/>',
            "    <enc:CipherData>",
            f"      <enc:CipherReference URI={quoteattr(path)}/>",
            "    </enc:CipherData>",
            "  </enc:EncryptedData>",
        ]
    lines.append("</encryption>")
    return "\n".join(lines) + "\n"


def _verify_container(path: str) -> None:
    """Read back what was just written and check it is an EPUB at all.

    Cheap, and it runs while the file is still under a temporary name — so a
    truncated write, a corrupted entry or a mimetype that ended up in the wrong
    place stops here instead of replacing a good book with a bad one.

    This is not validation. EPUBCheck answers a different and larger question;
    this one asks only whether the container survived the trip to disk.
    """
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not names or names[0] != "mimetype":
            raise ArchiveVerificationError("the written archive does not start with 'mimetype'")
        if archive.read("mimetype") != b"application/epub+zip":
            raise ArchiveVerificationError("the written archive has the wrong mimetype")
        if archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            raise ArchiveVerificationError("the written mimetype entry is compressed")
        if "META-INF/container.xml" not in names:
            raise ArchiveVerificationError("the written archive has no META-INF/container.xml")
        # Parsed, not merely present. "Has a container.xml" was the whole check,
        # and a container whose `full-path` carried an unescaped `&` passed it
        # while lxml refused to read the file — an archive nothing could open,
        # pronounced good by the thing whose job is to say so. The rootfile it
        # names has to be in the archive too: a container pointing at a package
        # document that was never written is the same failure one step later.
        from lxml import etree

        try:
            container = etree.fromstring(archive.read("META-INF/container.xml"))
        except etree.XMLSyntaxError as exc:
            raise ArchiveVerificationError(f"the written container.xml is not well-formed XML: {exc}") from exc
        rootfiles = container.findall(
            ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
        )
        if not rootfiles:
            raise ArchiveVerificationError("the written container.xml names no rootfile")
        for rootfile in rootfiles:
            target = rootfile.get("full-path")
            if not target or target not in names:
                raise ArchiveVerificationError(f"the written container.xml points at a missing rootfile: {target!r}")
        broken = archive.testzip()
        if broken is not None:
            raise ArchiveVerificationError(f"the written archive has a corrupt entry: {broken}")


def write_epub(
    book: Book,
    destination: str,
    report: Report,
    content_dir: str = "EPUB",
    package_name: str = "package.opf",
) -> None:
    """Write *book* to *destination*, or leave whatever is there untouched.

    The write goes to a temporary file beside the destination and only replaces
    it once the archive has been closed and read back. Opening the destination
    directly — which is what this did until 0.1.7 — meant that a disk filling up
    halfway left a truncated file where a good book had been. Measured, not
    imagined: an injected failure took a 2338-byte output down to 1196 bytes,
    and that file was still called by the name the user knew.

    ``os.replace`` is atomic within a filesystem, which is why the temporary
    file is created in the destination's own directory rather than in /tmp.
    """
    # Checked here as well as in `Policy`, because a dataclass field assigned
    # after construction never sees `__post_init__` — and that is not a corner
    # case, it is the ordinary way a caller adjusts one setting. The measured
    # result of trusting the constructor: four archive members beginning `../`
    # written from `policy.content_dir = '../evil&dir'` set on a policy that
    # had already validated itself. This function is the last place the values
    # are still just values; after it they are names in an archive.
    from .policy import _check_ocf_segment

    _check_ocf_segment("content_dir", content_dir, allow_empty=True)
    _check_ocf_segment("package_name", package_name, allow_empty=False)

    # An empty content directory means the package sits at the archive root,
    # which is what Calibre produces and what some readers were built against.
    # Joining unconditionally gave "/content.opf" — a leading slash, and an
    # invalid container path.
    directory = content_dir.strip("/")
    opf_path = f"{directory}/{package_name}" if directory else package_name
    opf, _ = build_opf(book, opf_path, report)

    directory = os.path.dirname(os.path.abspath(destination))
    handle, staging = tempfile.mkstemp(
        dir=directory, prefix=f".{os.path.basename(destination)}.", suffix=".part"
    )
    os.close(handle)

    try:
        _write_archive(book, staging, opf_path, opf)
        _verify_container(staging)
        os.replace(staging, destination)
    except BaseException:
        # Including KeyboardInterrupt: a half-written book must not survive a
        # user pressing Ctrl-C either.
        try:
            os.unlink(staging)
        except OSError:
            pass
        raise

    # mimetype, container.xml and the package document, plus anything a
    # compatibility profile added beside them.
    report.stats["output_resources"] = len(book.resources) + 3 + len(book.container_files)
    report.stats["output_spine_items"] = len(book.spine)


def _write_archive(book: Book, destination: str, opf_path: str, opf: str) -> None:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        # OCF requires 'mimetype' to be the first entry and stored uncompressed.
        archive.writestr(_entry("mimetype", zipfile.ZIP_STORED), b"application/epub+zip")

        archive.writestr(
            # Escaped, because `opf_path` reaches here from two directions: a
            # `Policy` a library caller built, and the layout of the source
            # archive, which is somebody else's file. Both are checked before
            # they get this far; this is the line that does not depend on that
            # being true. An unescaped `&` in a directory name is enough to make
            # `container.xml` unparsable, and the archive verifier — which reads
            # entry order, mimetype and CRC — pronounced such a book good.
            _entry("META-INF/container.xml"),
            CONTAINER_XML.format(opf_path=escape(opf_path, {'"': "&quot;"})),
        )
        # Whatever is still obfuscated has to be declared, or the book lies
        # about itself: bytes that no reading system can use, wearing the media
        # type of a font that works. Written from the model rather than carried,
        # because the paths in it have been through a relayout.
        if book.encrypted:
            archive.writestr(
                _entry("META-INF/encryption.xml"), _encryption_xml(book).encode("utf-8")
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
