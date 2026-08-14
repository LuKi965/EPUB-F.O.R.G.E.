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
from ..report import Action, Level, Risk
from .base import Context, Stage

#: Deliberately loose — this drives reachability analysis, not rewriting.
#:
#: `textref` is here because a Media Overlay names the document it narrates with
#: it, and nothing else does; without it a SMIL points at a chapter that the
#: graph believes nothing points at.
_REFERENCE_RE = re.compile(
    rb"""(?:
        (?:href|src|poster|data|xlink:href|textref|epub:textref)\s*=\s*["']([^"'>]+)["']
        | url\(\s*["']?([^"')]+?)["']?\s*\)
        | @import\s+["']([^"']+)["']
    )""",
    re.VERBOSE | re.IGNORECASE,
)

#: `srcset`, which is a list and therefore cannot be read by the rule above.
#:
#: `srcset="cover.jpg 1x, cover@2x.jpg 2x"` matches `src=` in nothing and names
#: two real files. It is how a responsive image is written and how `<picture>`
#: offers alternatives, and until this existed every one of those files looked
#: unreferenced — which is a deletion, on the one setting whose whole promise is
#: that it only deletes what nothing uses.
_SRCSET_RE = re.compile(rb"""\bsrcset\s*=\s*["']([^"'>]+)["']""", re.IGNORECASE)

#: `src="…"` and friends, in the shape SMIL uses them. Deliberately narrow: this
#: rewrites bytes it does not otherwise understand, so it touches attributes it
#: can name and nothing else.
_SRC_ATTRIBUTE = re.compile(r"""\b(src|textref|epub:textref)=(["'])([^"']*)\2""")

#: The same job for a standalone SVG. Both spellings, because a file old enough
#: to be in an EPUB 2 book uses `xlink:href` and a new one uses `href`, and
#: plenty of files written by a converter carry both on the same element.
_SVG_ATTRIBUTE = re.compile(r"""\b((?:xlink:)?href)=(["'])([^"']*)\2""")

#: `url(...)`, which is how an SVG's own `<style>` block reaches a picture.
_CSS_URL = re.compile(r"""url\(\s*(["']?)([^"')]+?)\1\s*\)""")

#: File types carried through as opaque bytes whose internal references still
#: have to follow the files they point at, and the attributes each uses.
#:
#: Media Overlays were the whole of this list, and the audit found the gap the
#: hard way: a standalone `diagram.svg` referring to `../assets/pic.png` was
#: moved to `images/` along with the picture, and came out still saying
#: `../assets/pic.png` — which now resolves to nothing. An `<image>` that does
#: not load, in a file EPUBCheck has no reason to look inside.
#:
#: A standalone SVG is a *document*, not a picture, and this is the difference:
#: it is the one image type that can hold a link.
CARRIED_XML = {
    "application/smil+xml": _SRC_ATTRIBUTE,
    "image/svg+xml": _SVG_ATTRIBUTE,
}

#: Media types this program either models properly or knows how to repoint.
#: Anything else that turns out to hold a relative reference is a file we would
#: be moving blind — see `_unmovable`.
UNDERSTOOD = frozenset({
    "application/xhtml+xml",
    "text/html",
    "text/css",
    "application/oebps-package+xml",
    "application/x-dtbncx+xml",
    *CARRIED_XML,
})

JUNK_PATHS = re.compile(
    r"(^|/)(\.DS_Store|Thumbs\.db|__MACOSX/.*|\._.*|.*\.bak|iTunesMetadata\.plist|calibre_bookmarks\.txt)$",
    re.IGNORECASE,
)


def scan_references(data: bytes) -> list[str]:
    """Every relative reference that looks like a link to another packaged file."""
    found: list[str] = []

    def keep(raw: bytes) -> None:
        try:
            href = raw.decode("utf-8")
        except UnicodeDecodeError:
            return
        href = href.strip()
        if href and not paths.is_remote(href) and not href.startswith("#"):
            found.append(href)

    for match in _REFERENCE_RE.finditer(data):
        raw = next((group for group in match.groups() if group), None)
        if raw:
            keep(raw)
    for match in _SRCSET_RE.finditer(data):
        for candidate in match.group(1).split(b","):
            # `url descriptor`, where the descriptor is optional: take the URL
            # and ignore whatever follows it.
            url = candidate.strip().split()[:1]
            if url:
                keep(url[0])
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
            pattern = CARRIED_XML.get(resource.media_type)
            if pattern is None:
                continue
            source_path = resource.original_path or resource.path
            try:
                text = resource.data.decode("utf-8")
            except UnicodeDecodeError:
                continue

            rewritten = 0

            def moved_target(value: str) -> "str | None":
                """Where *value* points now, or None if it must be left alone."""
                if not value or paths.is_remote(value) or value.startswith("#"):
                    return None
                href, _, fragment = value.partition("#")
                target = paths.resolve(source_path, href)
                if target is None:
                    return None
                moved = ctx.path_map.get(target, target)
                if moved not in book.resources:
                    return None
                settled = paths.relative(resource.path, moved)
                return f"{settled}#{fragment}" if fragment else settled

            def repoint(match: re.Match) -> str:
                nonlocal rewritten
                attribute, quote, value = match.group(1), match.group(2), match.group(3)
                new_value = moved_target(value)
                if new_value is None:
                    return match.group(0)
                if new_value != value:
                    rewritten += 1
                return f"{attribute}={quote}{new_value}{quote}"

            def repoint_url(match: re.Match) -> str:
                nonlocal rewritten
                quote, value = match.group(1), match.group(2)
                new_value = moved_target(value)
                if new_value is None:
                    return match.group(0)
                if new_value != value:
                    rewritten += 1
                return f"url({quote}{new_value}{quote})"

            updated = pattern.sub(repoint, text)
            if resource.media_type == "image/svg+xml":
                # An SVG carries its own stylesheet, and a `background-image` in
                # it reaches a file exactly as an `<image href>` does.
                updated = _CSS_URL.sub(repoint_url, updated)
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
        """Remove what the archive picked up on the way, and nothing else.

        The audit's F-016, second half. This used to delete by *name*: anything
        matching `JUNK_PATHS` went, unconditionally and with no switch. Most of
        those names are safe — nobody links to `.DS_Store` — and one is not.
        `.bak` is a name a publisher can give a file the book actually uses, and
        `chapter.bak` in the manifest, referenced from the navigation, was
        deleted on the strength of its extension. Deletion by name is a guess
        about content, and this program is not allowed those.

        So a file is removed only when the book does not reach it, on the same
        graph that decides orphans — plus a wider test, because "reachable from
        the spine" is not the same question as "referenced by anything": a file
        used only by a document that is itself unreachable is still a file
        somebody linked to on purpose, and this is not the pass that decides
        what to do about that.

        And it is a switch, because the owner's standing rule is that whatever
        this program deletes must be optional to untick.
        """
        if not ctx.policy.remove_junk:
            return
        named = [path for path in ctx.book.resources if JUNK_PATHS.search(path)]
        if not named:
            return
        spoken_for = self._reachable(ctx) | self._referenced_anywhere(ctx)
        for path in named:
            if path in spoken_for:
                self.note(ctx, Level.PRESERVED, "structure.junk-kept", location=path)
                continue
            ctx.book.remove(path)
            self.note(ctx, Level.FIX, "structure.junk-removed", location=path)
            # A deletion, and the output carries nothing that would put it back.
            self.changed(
                ctx,
                Action.REMOVED,
                path,
                before="present in the source archive",
                risk=Risk.NONE,
                reversible=False,
                rule="structure.junk-removed",
            )

    def _referenced_anywhere(self, ctx: Context) -> set[str]:
        """Every packaged file that any other packaged file points at.

        Wider than `_reachable` on purpose and used only to *keep* things. The
        two answer different questions — "can a reader get here" and "did
        anybody mean this" — and for deciding whether to delete something, the
        second is the one that matters.
        """
        book = ctx.book
        pointed: set[str] = set()
        for path, resource in book.resources.items():
            if resource.is_font or (resource.is_image and resource.media_type != "image/svg+xml"):
                continue
            source_path = resource.original_path or resource.path
            for href in scan_references(resource.data):
                target = paths.resolve(source_path, href.partition("#")[0])
                if target is None:
                    continue
                mapped = ctx.path_map.get(target, target)
                if mapped in book.resources and mapped != path:
                    pointed.add(mapped)
        return pointed

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
            if resource is None or resource.is_font:
                continue
            if resource.is_image and resource.media_type != "image/svg+xml":
                # An SVG is the one image that can hold a link, and skipping it
                # here is the audit's "references made from inside an SVG are
                # invisible to the graph" — a picture used only by an SVG looked
                # like an orphan and was deleted, leaving the SVG drawing a hole.
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

    def _unmovable(self, ctx: Context) -> set[str]:
        """Files that hold a link and that nothing here knows how to repoint.

        The half of the audit's finding that matters more than the SVG rewriter
        above it. Adding a media type to `CARRIED_XML` fixes the type somebody
        thought of; this fixes the ones nobody has. A JavaScript file naming a
        JSON beside it, a WebVTT naming an image, a vendor XML naming anything —
        all get moved to a typed folder today and all keep saying where they used
        to be.

        The rule is the audit's own and it is the only safe one: a relayout may
        proceed *only* where every reference in a moved file can be followed. A
        file whose references cannot be followed is not moved. It stays where
        the publisher put it, which costs a tidy directory listing and keeps a
        book that works.

        Two tests, because one was not enough. `scan_references` is the loose
        scanner already used for reachability, and it is *markup*-shaped: it
        knows `href`, `src`, `url()` and `@import`. A script saying
        `fetch("../data/quiz.json")` matches none of them, and the first version
        of this function moved that file exactly as before — a rule against
        moving files blind, blind to the commonest case of it.

        So the second test is cruder and catches what the first cannot: does
        this file's own text contain the *name* of another file in the book?
        That over-matches, and over-matching here means leaving one extra file
        where the publisher put it, which is the cheap direction to be wrong in.
        Only files that decode as text are asked — a PNG whose bytes happen to
        spell `pic.png` is not making a reference.
        """
        stuck: set[str] = set()
        basenames = {
            posixpath.basename(other): other
            for other in ctx.book.resources
        }
        for path, resource in ctx.book.resources.items():
            if resource.media_type in UNDERSTOOD or resource.is_content_doc:
                continue
            references: dict[str, str] = {}
            for href in scan_references(resource.data):
                target = paths.resolve(path, href.partition("#")[0])
                if target in ctx.book.resources:
                    references[href] = target
            try:
                text = resource.data.decode("utf-8")
            except UnicodeDecodeError:
                text = ""
            if text:
                mine = posixpath.basename(path)
                for name, other in basenames.items():
                    if other != path and name != mine and name in text:
                        references[name] = other
            if references:
                # Both ends, and the first version pinned only one. Leaving the
                # script where it sits does nothing if the JSON it names is
                # moved to a typed folder — the reference dangles exactly as
                # before, from a file that did not move. What cannot be
                # rewritten has to keep *both* sides of the sentence true.
                stuck.add(path)
                stuck.update(references.values())
                self.note(
                    ctx,
                    Level.PRESERVED,
                    "structure.reference-bearing-kept",
                    values={
                        "media_type": resource.media_type,
                        "count": len(references),
                        "names": ", ".join(sorted(references)[:3]),
                    },
                    location=path,
                )
        return stuck

    def _relayout(self, ctx: Context) -> None:
        book = ctx.book
        root = ctx.policy.content_dir.strip("/")
        taken: set[str] = set()
        moves: list[tuple[str, str]] = []
        stuck = self._unmovable(ctx)
        taken |= stuck

        # Spine order first so chapter files get stable, sortable names.
        ordered = [item.path for item in book.spine if item.path in book.resources]
        ordered += [path for path in book.resources if path not in set(ordered)]

        spine_positions = {item.path: index for index, item in enumerate(book.spine)}

        for path in ordered:
            if path in stuck:
                continue
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
            # Reversible: every move is in the report with both names, which is
            # what F-003/F-016 put there. Entered one by one rather than as a
            # count, because "42 files moved" cannot answer "where did
            # `okładka.jpg` go".
            for old, new in moves:
                self.changed(
                    ctx,
                    Action.MOVED,
                    old,
                    before=old,
                    after=new,
                    risk=Risk.NONE,
                    reversible=True,
                    rule="structure.relaid-out",
                )
