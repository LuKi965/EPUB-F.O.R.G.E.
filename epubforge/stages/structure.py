"""Container layout: prune unreachable files and regroup the rest by media type.

Books arrive with everything dumped in one folder, or split across a dozen with
non-ASCII filenames that some readers refuse to open. This stage decides the
final path of every resource; all href rewriting happens later against the map
it produces.
"""

from __future__ import annotations

import posixpath
import re

from .. import paths
from ..model import folder_for
from ..report import Level
from .base import Context, Stage

#: Deliberately loose — this drives reachability analysis, not rewriting.
_REFERENCE_RE = re.compile(
    rb"""(?:
        (?:href|src|poster|data|xlink:href)\s*=\s*["']([^"'>]+)["']
        | url\(\s*["']?([^"')]+?)["']?\s*\)
        | @import\s+["']([^"']+)["']
    )""",
    re.VERBOSE | re.IGNORECASE,
)

#: File types carried through as opaque bytes whose internal references still
#: have to follow the files they point at. Media Overlays are the whole of this
#: list today; anything added here needs a fixture proving the same failure.
CARRIED_XML = {"application/smil+xml"}

#: `src="…"` and friends, in the shape SMIL uses them. Deliberately narrow: this
#: rewrites bytes it does not otherwise understand, so it touches attributes it
#: can name and nothing else.
_SRC_ATTRIBUTE = re.compile(r"""\b(src|textref|epub:textref)=(["'])([^"']*)\2""")

JUNK_PATHS = re.compile(
    r"(^|/)(\.DS_Store|Thumbs\.db|__MACOSX/.*|\._.*|.*\.bak|iTunesMetadata\.plist|calibre_bookmarks\.txt)$",
    re.IGNORECASE,
)


def scan_references(data: bytes) -> list[str]:
    """Every relative reference that looks like a link to another packaged file."""
    found: list[str] = []
    for match in _REFERENCE_RE.finditer(data):
        raw = next((group for group in match.groups() if group), None)
        if not raw:
            continue
        try:
            href = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        href = href.strip()
        if href and not paths.is_remote(href) and not href.startswith("#"):
            found.append(href)
    return found


def _join(directory: str, name: str) -> str:
    """A container path, with no leading slash when the directory is empty.

    The content directory may be empty — the package at the archive root, which
    is the layout Calibre produces. Joining unconditionally produced "/images/…",
    which is not a container path at all.
    """
    return f"{directory}/{name}" if directory else name


class StructureStage(Stage):
    name = "structure"

    def run(self, ctx: Context) -> None:
        ctx.build_path_map()
        self._drop_junk(ctx)
        if ctx.policy.drop_orphans:
            self._drop_orphans(ctx)
        if ctx.policy.reorganize_files:
            self._relayout(ctx)
        ctx.build_path_map()
        self._repoint_carried_xml(ctx)

    def _repoint_carried_xml(self, ctx: Context) -> None:
        """Fix references inside files this pipeline moves but does not model.

        A Media Overlay is the case that exposed this. The SMIL file is carried
        through as opaque bytes, so nothing rewrote the `src` attributes inside
        it — and moving it to `misc/` left it pointing at a chapter and an audio
        file that are no longer where it says. The result does not merely lose
        the narration: it is an invalid EPUB, and EPUBCheck says so.

        Carrying a file without carrying its references is worse than not
        carrying it, because it turns a silent loss into a broken book.
        """
        book = ctx.book
        for resource in list(book.resources.values()):
            if resource.media_type not in CARRIED_XML:
                continue
            source_path = resource.original_path or resource.path
            try:
                text = resource.data.decode("utf-8")
            except UnicodeDecodeError:
                continue

            rewritten = 0

            def repoint(match: re.Match) -> str:
                nonlocal rewritten
                attribute, quote, value = match.group(1), match.group(2), match.group(3)
                if not value or paths.is_remote(value) or value.startswith("#"):
                    return match.group(0)
                href, _, fragment = value.partition("#")
                target = paths.resolve(source_path, href)
                if target is None:
                    return match.group(0)
                moved = ctx.path_map.get(target, target)
                if moved not in book.resources:
                    return match.group(0)
                new_value = paths.relative(resource.path, moved)
                if fragment:
                    new_value = f"{new_value}#{fragment}"
                if new_value != value:
                    rewritten += 1
                return f"{attribute}={quote}{new_value}{quote}"

            updated = _SRC_ATTRIBUTE.sub(repoint, text)
            if rewritten:
                resource.data = updated.encode("utf-8")
                self.note(
                    ctx,
                    Level.FIX,
                    "structure.carried-xml-repointed",
                    values={"count": rewritten},
                    location=resource.path,
                )

    def _drop_junk(self, ctx: Context) -> None:
        for path in list(ctx.book.resources):
            if JUNK_PATHS.search(path):
                ctx.book.remove(path)
                self.note(ctx, Level.FIX, "structure.junk-removed", location=path)

    def _reachable(self, ctx: Context) -> set[str]:
        """Transitive closure of references starting from the spine and the cover."""
        book = ctx.book
        roots: set[str] = {item.path for item in book.spine}
        if book.cover_path:
            roots.add(book.cover_path)
        if book.nav_path:
            roots.add(book.nav_path)
        for node_root in book.toc:
            for node in node_root.walk():
                if node.target_path:
                    roots.add(node.target_path)
        for landmark in book.landmarks:
            roots.add(landmark.target.split("#")[0])

        reachable: set[str] = set()
        queue = [path for path in roots if path in book.resources]
        while queue:
            current = queue.pop()
            if current in reachable:
                continue
            reachable.add(current)
            resource = book.get(current)
            if resource is None or resource.is_image or resource.is_font:
                continue
            source_path = resource.original_path or resource.path
            for href in scan_references(resource.data):
                target = paths.resolve(source_path, href)
                if target is None:
                    continue
                mapped = ctx.path_map.get(target, target)
                if mapped in book.resources and mapped not in reachable:
                    queue.append(mapped)
        return reachable

    def _drop_orphans(self, ctx: Context) -> None:
        book = ctx.book
        reachable = self._reachable(ctx)
        keep_types = {"application/x-dtbncx+xml"}
        for path in list(book.resources):
            resource = book.resources[path]
            if path in reachable or resource.media_type in keep_types:
                continue
            book.remove(path)
            self.note(
                ctx,
                Level.FIX,
                "structure.orphan-removed",
                values={"bytes": len(resource.data)},
                location=path,
            )

    def _relayout(self, ctx: Context) -> None:
        book = ctx.book
        root = ctx.policy.content_dir.strip("/")
        taken: set[str] = set()
        moves: list[tuple[str, str]] = []

        # Spine order first so chapter files get stable, sortable names.
        ordered = [item.path for item in book.spine if item.path in book.resources]
        ordered += [path for path in book.resources if path not in set(ordered)]

        spine_positions = {item.path: index for index, item in enumerate(book.spine)}

        for path in ordered:
            resource = book.resources[path]
            if resource.media_type == "application/x-dtbncx+xml":
                new_path = _join(root, "toc.ncx")
            else:
                folder = folder_for(resource.media_type)
                basename = paths.ascii_slug(posixpath.basename(path), fallback=folder)
                if resource.is_content_doc:
                    stem = basename.rpartition(".")[0] or basename
                    # Strip a prefix from an earlier run so names cannot accrete.
                    stem = re.sub(r"^\d{4}-", "", stem)
                    prefix = f"{spine_positions[path]:04d}-" if path in spine_positions else ""
                    basename = f"{prefix}{stem or 'section'}.xhtml"
                new_path = _join(root, f"{folder}/{basename}")
            new_path = paths.unique(new_path, taken)
            taken.add(new_path)
            if new_path != path:
                moves.append((path, new_path))

        for old_path, new_path in moves:
            book.rename(old_path, new_path)

        if moves:
            renamed = sum(
                1 for old, new in moves if posixpath.basename(old) != posixpath.basename(new)
            )
            self.note(
                ctx,
                Level.FIX,
                "structure.relaid-out",
                values={"count": len(moves), "directory": root, "renamed": renamed},
            )
