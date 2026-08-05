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


def guess_media_type(path: str, declared: str | None = None) -> str:
    """Trust the extension over a declared type.

    Broken generators routinely declare ``text/html`` for XHTML or
    ``application/octet-stream`` for fonts; the extension is the better signal.
    """
    ext = path.rpartition(".")[2].lower()
    guessed = MEDIA_TYPES.get(ext)
    if guessed:
        return guessed
    if declared:
        return declared.strip()
    return "application/octet-stream"


def folder_for(media_type: str) -> str:
    for prefix, folder in MEDIA_FOLDERS:
        if media_type == prefix or (prefix.endswith("/") and media_type.startswith(prefix)):
            return folder
    return "misc"


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
        return self.data.decode(encoding, errors="replace")


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


@dataclass
class Identifier:
    value: str
    scheme: str | None = None
    #: Exactly one identifier is the package's ``unique-identifier``.
    primary: bool = False


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
    #: Vendor metadata worth carrying over, as ``(name, content)`` pairs.
    extra_meta: list[tuple[str, str]] = field(default_factory=list)
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
    cover_path: str | None = None
    nav_path: str | None = None
    ncx_path: str | None = None

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

        # Both are stored as paths precisely so that a move keeps them valid.
        for other in self.resources.values():
            if other.fallback == old_path:
                other.fallback = new_path
            if other.media_overlay == old_path:
                other.media_overlay = new_path

        for root in self.toc:
            for node in root.walk():
                node.target = retarget(node.target)
        for landmark in self.landmarks:
            landmark.target = retarget(landmark.target) or landmark.target
        for page in self.page_list:
            page.target = retarget(page.target) or page.target
