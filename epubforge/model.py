"""In-memory representation of a book, decoupled from any on-disk EPUB layout.

The reader lowers any EPUB 2 or 3 (or near-miss) file into these structures, the
stages transform them, and the writer raises them back into a conforming
EPUB 3.3 container. Nothing here knows about ZIP files or OPF syntax.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

MEDIA_TYPES = {
    "xhtml": "application/xhtml+xml",
    "html": "application/xhtml+xml",
    "htm": "application/xhtml+xml",
    "xht": "application/xhtml+xml",
    "css": "text/css",
    "js": "text/javascript",
    "ncx": "application/x-dtbncx+xml",
    "opf": "application/oebps-package+xml",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "jpe": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "ttf": "font/ttf",
    "otf": "font/otf",
    "ttc": "font/collection",
    "woff": "font/woff",
    "woff2": "font/woff2",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "mp4": "video/mp4",
    "smil": "application/smil+xml",
    "pls": "application/pls+xml",
    "xml": "application/xml",
    "json": "application/json",
    "txt": "text/plain",
    "vtt": "text/vtt",
}

#: Folder each media category is filed under when the layout is normalised.
MEDIA_FOLDERS = (
    ("application/xhtml+xml", "text"),
    ("text/css", "styles"),
    ("image/", "images"),
    ("font/", "fonts"),
    ("audio/", "audio"),
    ("video/", "video"),
    ("text/javascript", "scripts"),
)


#: Declared types that are wrong often enough for the extension to win, and the
#: only ones. Every entry is a generator's habit rather than a guess:
#: `text/html` for XHTML is what Calibre and Sigil write, and
#: `application/octet-stream` is what a tool writes when it has not looked.
#:
#: The list exists because the rule used to be *the extension always wins*, and
#: that is a different and worse rule. Reproduced on 0.2.21: a stylesheet
#: correctly declared `text/css` and named `styl.xhtml` came out of the rebuild
#: as `application/xhtml+xml` — a file the pipeline then tries to parse as a
#: document, on the strength of the part of its name a person typed by mistake.
#: A declaration that is *plausible for the bytes* is evidence; a filename is a
#: convention.
OVERRIDABLE_DECLARATIONS = frozenset({
    "",
    "text/html",
    "application/octet-stream",
    "application/xml",
    "text/xml",
    "unknown/unknown",
    "application/x-dtbook+xml",
})


def guess_media_type(path: str, declared: str | None = None) -> str:
    """What this file is, weighing what it says against what it is called.

    A declared type is believed unless it is one the generators of this world
    write when they have not looked — see `OVERRIDABLE_DECLARATIONS`. With no
    declaration at all, the extension is all there is.
    """
    stated = (declared or "").strip()
    ext = path.rpartition(".")[2].lower()
    guessed = MEDIA_TYPES.get(ext)
    if stated and stated.lower() not in OVERRIDABLE_DECLARATIONS:
        return stated
    if guessed:
        return guessed
    if stated:
        return stated
    return "application/octet-stream"


def folder_for(media_type: str) -> str:
    for prefix, folder in MEDIA_FOLDERS:
        if media_type == prefix or (prefix.endswith("/") and media_type.startswith(prefix)):
            return folder
    return "misc"


@dataclass
class RemoteResource:
    """A manifest item that lives somewhere else.

    A book may declare a resource by URL — a trailer, a font served from a
    foundry. The reader used to warn and drop it, which meant the output no
    longer declared something the source did, and nothing downstream could tell.
    Nothing here fetches it; it is a declaration, and declarations are carried.
    """

    href: str
    media_type: str
    properties: set[str] = field(default_factory=set)
    #: Container path of the local item to show instead, when there is one.
    fallback: str | None = None


@dataclass
class CollectionLink:
    """One `<link>` inside a `<collection>`."""

    #: Container path when the target is inside the book; None when it is not.
    path: str | None = None
    #: The href exactly as written, kept for remote targets and for anything
    #: that could not be resolved.
    href: str = ""
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class Collection:
    """An `<collection>`: a grouping the publication makes about itself.

    Indexes, manifests of preview content, dictionaries — EPUB 3 leaves the
    vocabulary open, which is precisely why this cannot be modelled field by
    field. Everything the element said is carried: its role, its other
    attributes, its links, its nested collections, and any `<metadata>` it
    holds, the last of those verbatim because its contents are open too.
    """

    role: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    links: list[CollectionLink] = field(default_factory=list)
    children: list["Collection"] = field(default_factory=list)
    #: Serialised `<metadata>` children, carried through untouched.
    raw_metadata: list[str] = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class CollectionMembership:
    """One `belongs-to-collection`: the set or series this book is part of.

    A book can be in several at once — the seventh Chronicle, published inside
    a boxed set as part one — and the model used to hold exactly one, so the
    other disappeared along with its type and position.
    """

    name: str
    collection_type: str = "series"
    position: str | None = None


@dataclass
class Resource:
    """A single file inside the container."""

    path: str
    media_type: str
    data: bytes
    properties: set[str] = field(default_factory=set)
    #: Set when the source declared this file in its manifest.
    manifested: bool = True
    #: Populated by the structure stage so other stages can report old names.
    original_path: str | None = None
    #: Fallback chain target for non-core media types, as a container path.
    fallback: str | None = None
    #: The Media Overlay that narrates this document, as a container path. The
    #: attribute is what makes a book with narration a book with narration; the
    #: SMIL file alone is not enough, and EPUBCheck rejects the pair.
    media_overlay: str | None = None

    @property
    def is_content_doc(self) -> bool:
        return self.media_type == "application/xhtml+xml"

    @property
    def is_style(self) -> bool:
        return self.media_type == "text/css"

    @property
    def is_font(self) -> bool:
        return self.media_type.startswith("font/") or "opentype" in self.media_type or "font-sfnt" in self.media_type

    @property
    def is_image(self) -> bool:
        return self.media_type.startswith("image/")

    @property
    def basename(self) -> str:
        return posixpath.basename(self.path)

    def text(self, encoding: str = "utf-8") -> str:
        """This resource's bytes as text, without quietly inventing characters.

        It was one line — `decode("utf-8", errors="replace")` — and that line
        is a K1 breach with a friendly face. Measured: a chapter carrying one
        `0x92` (an apostrophe in the Windows-1250 an older Polish shop wrote)
        came out with `�` in the text, the rebuild reported **nothing**,
        and the output was valid UTF-8 for ever after. A character of the book
        was gone and the file looked repaired.

        So the declared encoding is asked first, in the order a reading system
        would: a byte-order mark, then the XML declaration, then `meta charset`,
        then UTF-8, and only then the legacy encodings that actually turn up in
        books this old. A round trip has to reproduce the bytes — an encoding
        that decodes without error but re-encodes differently has not read the
        file, it has guessed at it.

        Replacement is still possible for a genuinely damaged file, and
        `decoded()` is how a caller finds out that it happened. This method
        keeps its shape so nothing that only wants a string has to care.
        """
        return self.decoded(encoding)[0]

    #: Tried in order, after whatever the document declares about itself. Both
    #: appear in Polish and Central European books old enough to predate the
    #: shops standardising on UTF-8; `latin-1` is last because it decodes every
    #: byte sequence ever written and so must never win by default.
    _FALLBACK_ENCODINGS = ("cp1250", "cp1252", "latin-1")

    def decoded(self, encoding: str = "utf-8") -> "tuple[str, str, int]":
        """Return ``(text, encoding_used, characters_replaced)``."""
        import re as _re

        data = self.data
        candidates: list[str] = []
        if data.startswith(b"\xef\xbb\xbf"):
            candidates.append("utf-8-sig")
        for pattern in (
            rb'<\?xml[^>]*encoding=["\']([A-Za-z0-9_.\-]+)["\']',
            rb'<meta[^>]*charset=["\']?([A-Za-z0-9_.\-]+)',
            rb'charset=([A-Za-z0-9_.\-]+)',
        ):
            found = _re.search(pattern, data[:2048], _re.IGNORECASE)
            if found:
                candidates.append(found.group(1).decode("ascii", "ignore"))
        candidates.append(encoding)
        candidates.extend(self._FALLBACK_ENCODINGS)

        for candidate in candidates:
            try:
                text = data.decode(candidate)
            except (UnicodeDecodeError, LookupError):
                continue
            # The round trip is the whole test. `latin-1` decodes anything, so
            # "it did not raise" proves nothing; "it comes back the same bytes"
            # proves the file was read rather than guessed at.
            try:
                if text.encode(candidate) == data:
                    return text, candidate, 0
            except (UnicodeEncodeError, LookupError):
                continue

        text = data.decode(encoding, errors="replace")
        return text, encoding, text.count("�")


@dataclass
class NavPoint:
    """One entry in the table of contents; children make it a tree."""

    label: str
    #: Container path plus optional ``#fragment``; ``None`` for heading-only nodes.
    target: str | None = None
    children: list["NavPoint"] = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    @property
    def target_path(self) -> str | None:
        return self.target.split("#", 1)[0] if self.target else None


@dataclass
class Landmark:
    epub_type: str
    label: str
    target: str


@dataclass
class PageTarget:
    label: str
    target: str


@dataclass
class NavSection:
    """A navigation list that is neither the contents, the landmarks nor the pages.

    EPUB 3 puts no limit on what a navigation document may contain: `lot` for a
    list of tables, `loi` for illustrations, `lov` for video, and anything at all
    under a vendor's own `epub:type`. They are ordinary `nav` elements with an
    `ol` inside, and each entry has a label a person wrote.

    The audit's F-018. Until this existed the reader parsed three kinds of `nav`
    and the regenerator wrote three kinds of `nav`, so a book with a list of
    illustrations came out without one — the entries were not moved, not
    reported, and not recoverable from the output. For a tool whose first rule
    is that no character of the book's text is lost, "we did not model that
    section" is not a reason for its contents to disappear.
    """

    #: The `epub:type` exactly as the source wrote it — the whole point.
    epub_type: str
    #: The section's own heading, when it had one. Publishers write these in
    #: their own language and this program has no business inventing them.
    heading: str = ""
    entries: list[NavPoint] = field(default_factory=list)
    #: Whether the source kept it out of the rendered page.
    hidden: bool = False
    #: The section's `aria-label`, which is what a screen reader announces and
    #: often the only name a section has — Project Gutenberg labels its page
    #: list that way and gives it no heading at all.
    aria_label: str = ""


@dataclass
class Creator:
    name: str
    #: MARC relator code, e.g. ``aut``, ``trl``, ``ill``.
    role: str = "aut"
    file_as: str | None = None
    #: Script and direction of the name as written, when the source said so.
    language: str | None = None
    direction: str | None = None
    #: ``(xml:lang, value)`` transliterations — the romanised form a library
    #: catalogue indexes by. Dropping these loses the only machine-readable
    #: link between 夏目漱石 and "Natsume Sōseki".
    alternate_scripts: list[tuple[str, str]] = field(default_factory=list)
    #: The `id` this creator carried in the source, when it had one. Only used
    #: to re-point carried refinements — see `Metadata.extra_refinements`.
    #:
    #: Last in the list on purpose: every construction of this class in the
    #: reader is positional, so a field inserted after `name` would silently
    #: become the role. Caught while writing it; worth a line so the next
    #: addition goes at the end too.
    source_id: str | None = None
    #: Whether the source stated the role itself, or the reader supplied a
    #: default. Both come out of `role`; only the first is the book's own claim.
    #:
    #: EF-035: without this the writer had no way to tell them apart, so a
    #: `role` this program invented was indistinguishable in the output from
    #: one the publisher wrote. Same for `file_as`. Appended at the end for the
    #: reason two fields up.
    role_declared: bool = False
    file_as_declared: bool = False


@dataclass
class Identifier:
    value: str
    scheme: str | None = None
    #: Exactly one identifier is the package's ``unique-identifier``.
    primary: bool = False
    #: The ``id`` this identifier carried in the source package, so a
    #: refinement this model has no field for can be carried and still point at
    #: the right node.
    #:
    #: EF-025: this field did not exist, and the writer asked for it with
    #: ``getattr(identifier, "source_id", None)`` — which answers `None`
    #: forever and reads as careful. So no identifier's refinements could ever
    #: be re-pointed: `<meta refines="#sklep" property="display-seq">` on a
    #: vendor identifier was reported as *referring to a node that did not
    #: survive* and dropped, on every book that had one.
    source_id: str | None = None


@dataclass
class Metadata:
    titles: list[str] = field(default_factory=list)
    subtitle: str | None = None
    sort_title: str | None = None
    creators: list[Creator] = field(default_factory=list)
    identifiers: list[Identifier] = field(default_factory=list)
    language: str | None = None
    languages_extra: list[str] = field(default_factory=list)
    publisher: str | None = None
    published: str | None = None
    modified: str | None = None
    description: str | None = None
    subjects: list[str] = field(default_factory=list)
    rights: str | None = None
    source: str | None = None
    series: str | None = None
    series_index: str | None = None
    #: Vendor metadata worth carrying over, as ``(name, content)`` pairs. This
    #: is the EPUB 2 spelling — ``<meta name= content=>``.
    extra_meta: list[tuple[str, str]] = field(default_factory=list)
    #: The EPUB 3 spelling — ``<meta property="…">value</meta>`` — for every
    #: property this model has no field of its own for, with whatever else the
    #: element said. Apple's `ibooks:specified-fonts` is the one that exposed
    #: the gap: it appeared on eleven of thirty-two real books and vanished
    #: from all of them, because only the EPUB 2 spelling was being carried.
    extra_properties: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)
    #: Refinements this model has no field for, as
    #: ``(source id refined, property, value, other attributes)``.
    #:
    #: The audit's F-011, last two lines of it. A `<meta refines="#t2"
    #: property="display-seq">2</meta>` says which title comes second, and it
    #: was dropped on the floor: the reader consumed the refinements it knew and
    #: `continue`d past the rest. Carried rather than understood — the same
    #: answer as the navigation sections nobody here models — and re-pointed at
    #: the id the writer gives that node, because a refinement whose target does
    #: not exist is not a preserved statement, it is an invalid one.
    extra_refinements: list[tuple[str, str, str, dict[str, str]]] = field(default_factory=list)

    #: `<link>` elements inside `<metadata>`, as attribute maps. A record in a
    #: library catalogue, an ONIX file, a rights statement: the publication
    #: pointing at something about itself. Never read here, and there is nothing
    #: to read — it is a pointer, and a pointer is carried or it is lost.
    links: list[dict[str, str]] = field(default_factory=list)

    #: Source ids of the titles, in the order the titles are held, so a carried
    #: refinement can be re-pointed at whichever title the writer emits.
    title_ids: list[str] = field(default_factory=list)

    #: `package/@prefix` from the source, as prefix → URI. Kept so a carried
    #: property can bring its declaration with it; without one it is not a
    #: property but an error.
    prefixes: dict[str, str] = field(default_factory=dict)
    #: Comments found inside ``<metadata>``. Kept because at least one shop
    #: writes its order number there — a watermark by any other name, and this
    #: tool does not remove watermarks.
    metadata_comments: list[str] = field(default_factory=list)
    #: Dublin Core elements with no dedicated field, as ``(element, value)``.
    #: Carried through verbatim: they are the publisher's statements about the
    #: work, and having no slot in this model is not a reason to discard them.
    dublin_core_extra: list[tuple[str, str]] = field(default_factory=list)

    #: Base text direction for the package (``ltr`` / ``rtl`` / ``auto``).
    direction: str | None = None
    #: Script and direction of the title as written.
    title_language: str | None = None
    title_direction: str | None = None
    #: ``(xml:lang, value)`` transliterations of the title.
    title_alternate_scripts: list[tuple[str, str]] = field(default_factory=list)

    #: EPUB Accessibility 1.1 discovery metadata, as schema.org property names
    #: mapped to their values. Derived from what the book demonstrably contains
    #: — never asserted on faith, because under the European Accessibility Act
    #: these are claims a publisher is answerable for.
    accessibility: dict[str, list[str]] = field(default_factory=dict)
    accessibility_summary: str | None = None
    #: Set only when the caller explicitly asserts conformance.
    conforms_to: str | None = None

    #: Media Overlay declarations. The key is the container path of the SMIL
    #: file the duration refines, or ``None`` for the whole publication. Not
    #: optional decoration: EPUBCheck rejects a book that declares an overlay
    #: without both, so dropping these while keeping the overlay produced an
    #: invalid book rather than a poorer one.
    media_durations: dict[str | None, str] = field(default_factory=dict)
    #: ``media:active-class`` and ``media:playback-active-class`` — the classes
    #: a reading system applies to the phrase being read.
    media_classes: dict[str, str] = field(default_factory=dict)

    #: Every collection this book says it belongs to. `series` and
    #: `series_index` below are the first *series*-typed one, kept because most
    #: of the program only wants that; this list is what actually gets written.
    collection_memberships: list["CollectionMembership"] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.titles[0] if self.titles else "Untitled"

    @property
    def primary_identifier(self) -> Identifier | None:
        for identifier in self.identifiers:
            if identifier.primary:
                return identifier
        return self.identifiers[0] if self.identifiers else None


@dataclass
class SpineItem:
    path: str
    linear: bool = True
    properties: set[str] = field(default_factory=set)


@dataclass
class Book:
    metadata: Metadata = field(default_factory=Metadata)
    resources: dict[str, Resource] = field(default_factory=dict)
    spine: list[SpineItem] = field(default_factory=list)
    toc: list[NavPoint] = field(default_factory=list)
    landmarks: list[Landmark] = field(default_factory=list)
    page_list: list[PageTarget] = field(default_factory=list)
    #: Navigation sections this program does not model by name — see
    #: :class:`NavSection`. Carried rather than understood, which is the honest
    #: position: their entries are labels and targets like any other, and their
    #: `epub:type` is the publisher's word for what they are.
    extra_navs: list[NavSection] = field(default_factory=list)
    cover_path: str | None = None
    nav_path: str | None = None
    ncx_path: str | None = None

    #: Every package document the container offered, as
    #: :class:`epubforge.reader.Rendition`. One entry for an ordinary book; more
    #: when the container lists several `rootfile` elements, each of which is a
    #: complete publication. `source_opf_path` says which of them this `Book` is.
    renditions: list = field(default_factory=list)

    #: Diagnostics carried over from the reader.
    source_version: str = "unknown"
    source_opf_path: str | None = None
    #: The package document exactly as it arrived. Kept because half of what
    #: identifies a generator is written there — `calibre:series`, InDesign's
    #: identifiers — and it is normalised away by the time anything else can
    #: look. Diagnostic only; the writer never reads it.
    source_package: bytes | None = None
    #: Container paths that were encrypted, mapped to their algorithm URI.
    encrypted: dict[str, str] = field(default_factory=dict)
    #: True when the source declares DRM we must not attempt to strip.
    has_drm: bool = False
    #: Fixed-layout and other rendering hints from the source OPF.
    rendition: dict[str, str] = field(default_factory=dict)

    #: Which way the pages turn: ``ltr``, ``rtl`` or ``default``. A structural
    #: attribute rather than a ``<meta>``, which is exactly why it used to be
    #: lost — everything expressed as metadata survived the rebuild and
    #: everything expressed as an attribute did not. A Hebrew, Arabic or manga
    #: edition that loses this opens backwards.
    page_progression_direction: str | None = None

    #: Reader-family concessions applied to this book, as measure keys from
    #: :mod:`epubforge.compat`. The writer consults these; nothing else does.
    compat: set[str] = field(default_factory=set)
    #: Files placed in the container outside the content directory, by
    #: container-absolute path. Reader-specific META-INF entries live here.
    container_files: dict[str, bytes] = field(default_factory=dict)

    #: `<collection>` elements, in document order.
    collections: list["Collection"] = field(default_factory=list)
    #: Manifest items declared by URL. Not fetched, not validated — declared.
    remote_resources: list["RemoteResource"] = field(default_factory=list)

    def add(self, resource: Resource) -> Resource:
        self.resources[resource.path] = resource
        return resource

    def get(self, path: str) -> Resource | None:
        return self.resources.get(path)

    def remove(self, path: str) -> None:
        self.resources.pop(path, None)
        self.spine = [item for item in self.spine if item.path != path]

    def content_docs(self) -> list[Resource]:
        """Content documents in spine order, then any unspined leftovers."""
        seen: set[str] = set()
        ordered: list[Resource] = []
        for item in self.spine:
            resource = self.resources.get(item.path)
            if resource and resource.is_content_doc:
                ordered.append(resource)
                seen.add(resource.path)
        for path, resource in self.resources.items():
            if resource.is_content_doc and path not in seen:
                ordered.append(resource)
        return ordered

    def by_type(self, predicate: str) -> list[Resource]:
        attr = f"is_{predicate}"
        return [r for r in self.resources.values() if getattr(r, attr, False)]

    def rename(self, old_path: str, new_path: str) -> None:
        """Move a resource, keeping spine, nav and cover pointers consistent."""
        if old_path == new_path:
            return
        resource = self.resources.pop(old_path)
        resource.original_path = resource.original_path or old_path
        resource.path = new_path
        self.resources[new_path] = resource

        for item in self.spine:
            if item.path == old_path:
                item.path = new_path
        if self.cover_path == old_path:
            self.cover_path = new_path
        if self.nav_path == old_path:
            self.nav_path = new_path
        if self.ncx_path == old_path:
            self.ncx_path = new_path

        def retarget(target: str | None) -> str | None:
            if not target:
                return target
            path, _, fragment = target.partition("#")
            if path != old_path:
                return target
            return f"{new_path}#{fragment}" if fragment else new_path

        if old_path in self.metadata.media_durations:
            self.metadata.media_durations[new_path] = self.metadata.media_durations.pop(old_path)

        # The register of what is still encrypted is keyed by path like
        # everything else here, and was the one map a move did not carry. It
        # did not show while the register was always emptied — a stale key in a
        # dictionary nothing reads is invisible. It shows the moment the
        # register survives a rebuild, which is what F-007 makes it do.
        if old_path in self.encrypted:
            self.encrypted[new_path] = self.encrypted.pop(old_path)

        # Both are stored as paths precisely so that a move keeps them valid.
        for other in self.resources.values():
            if other.fallback == old_path:
                other.fallback = new_path
            if other.media_overlay == old_path:
                other.media_overlay = new_path
        for remote in self.remote_resources:
            if remote.fallback == old_path:
                remote.fallback = new_path
        for collection in self.collections:
            for node in collection.walk():
                for link in node.links:
                    if link.path == old_path:
                        link.path = new_path

        for root in self.toc:
            for node in root.walk():
                node.target = retarget(node.target)
        for landmark in self.landmarks:
            landmark.target = retarget(landmark.target) or landmark.target
        for page in self.page_list:
            page.target = retarget(page.target) or page.target
        # The sections carried rather than modelled — a list of illustrations,
        # a list of tables. This is the third time a new pointer has had to be
        # added to this method after being forgotten once (media durations, then
        # the encryption register), and the failure is always the same shape: a
        # collection of paths that a move does not carry looks fine until
        # something downstream asks whether the path exists, and then the entries
        # are silently dropped rather than reported wrong.
        for section in self.extra_navs:
            for root in section.entries:
                for node in root.walk():
                    node.target = retarget(node.target)
