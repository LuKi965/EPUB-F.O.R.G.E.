"""Navigation: EPUB 3 nav document, legacy NCX, landmarks and the cover page."""

from __future__ import annotations

import html
import re

from .. import paths
from ..model import Landmark, NavPoint, Resource, SpineItem
from ..report import Level
from ..xhtml import EPUB_NS, XHTML_NS
from .base import Context, Stage

#: `href="…"` and `src="…"` as they appear in a content document. Narrow on
#: purpose: this rewrites bytes rather than a parse tree, so it touches the
#: attributes it can name and nothing else.
_HREF_ATTRIBUTE = re.compile(r"""\b(href|src)=(["'])([^"']*)\2""")

COVER_PAGE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="{xhtml}" xmlns:epub="{epub}" lang="{lang}" xml:lang="{lang}">
  <head>
    <meta charset="utf-8"/>
    <title>{title}</title>
    <style>
      html, body {{ margin: 0; padding: 0; height: 100%; }}
      body {{ display: flex; align-items: center; justify-content: center; }}
      img {{ max-width: 100%; max-height: 100%; object-fit: contain; }}
    </style>
  </head>
  <body epub:type="cover">
    <section epub:type="cover">
      <img src="{href}" alt="{alt}"/>
    </section>
  </body>
</html>
"""


def _escape(value: str) -> str:
    return html.escape(value or "", quote=True)


#: What the generated navigation calls its own sections, by language.
#:
#: These are the only words this program puts in front of a reader inside their
#: book, and they were English in every book it produced — "Table of Contents"
#: heading a Polish novel whose own `lang` attribute says `pl`. The report being
#: bilingual made that worse rather than better: the part nobody could change
#: was the part printed in the book itself.
#:
#: A language with no entry falls back to English, which is the same rule the
#: message catalogue uses and for the same reason: a heading in the wrong
#: language is a blemish, and a book that fails to build is not.
NAV_HEADINGS: dict[str, dict[str, str]] = {
    "en": {
        "toc": "Table of Contents",
        "landmarks": "Landmarks",
        "page-list": "Page List",
        "title": "Contents",
    },
    "pl": {
        "toc": "Spis treści",
        "landmarks": "Punkty orientacyjne",
        "page-list": "Numery stron",
        "title": "Spis treści",
    },
}


def heading(language: str, section: str) -> str:
    """One navigation heading, in the book's language where we have it."""
    tag = (language or "en").replace("_", "-").split("-")[0].lower()
    return NAV_HEADINGS.get(tag, NAV_HEADINGS["en"])[section]


class NavigationStage(Stage):
    name = "navigation"

    def run(self, ctx: Context) -> None:
        # EPUB 2 sources have no navigation document at all; generating one is a
        # correction, whereas replacing an existing one is routine.
        self._had_nav = bool(ctx.book.nav_path)
        self._ensure_cover_page(ctx)
        self._prune_toc(ctx)
        self._spine_what_the_navigation_reaches(ctx)
        if not ctx.book.toc:
            self._synthesize_toc(ctx)
        self._ensure_landmarks(ctx)
        self._write_nav(ctx)
        if ctx.policy.write_ncx:
            self._write_ncx(ctx)
        else:
            self._drop_ncx(ctx)

    def _ensure_cover_page(self, ctx: Context) -> None:
        book = ctx.book
        if not book.cover_path or book.cover_path not in book.resources:
            if book.cover_path:
                self.note(ctx, Level.WARN, "nav.cover-image-missing")
                book.cover_path = None
            return

        book.resources[book.cover_path].properties.add("cover-image")

        existing = next(
            (landmark for landmark in book.landmarks if landmark.epub_type == "cover"), None
        )
        cover_page = existing.target.split("#")[0] if existing else None
        if cover_page and cover_page in book.resources and book.resources[cover_page].is_content_doc:
            return

        # Some books reference the image directly from the spine; others have no
        # cover page at all. Either way, synthesise one so readers show it.
        page_path = paths.content_path(ctx.policy, "text/0000-cover.xhtml")
        page_path = paths.unique(page_path, set(book.resources))
        markup = COVER_PAGE_TEMPLATE.format(
            xhtml=XHTML_NS,
            epub=EPUB_NS,
            lang=_escape(book.metadata.language or ctx.policy.default_language),
            title=_escape(book.metadata.title),
            href=paths.relative(page_path, book.cover_path),
            alt=_escape(book.metadata.title),
        )
        book.add(
            Resource(
                path=page_path,
                media_type="application/xhtml+xml",
                data=markup.encode("utf-8"),
            )
        )
        book.spine.insert(0, SpineItem(page_path, linear=True))
        book.landmarks = [l for l in book.landmarks if l.epub_type != "cover"]
        book.landmarks.insert(0, Landmark("cover", "Cover", page_path))
        self.note(ctx, Level.FIX, "nav.cover-page-generated", location=page_path)

    def _prune_toc(self, ctx: Context) -> None:
        book = ctx.book
        removed = 0
        dangling_fragments = 0

        # The content stage may have renamed the very ids these targets point at.
        for root in book.toc:
            for node in root.walk():
                node.target = ctx.remap_fragment(node.target)
        for landmark in book.landmarks:
            landmark.target = ctx.remap_fragment(landmark.target) or landmark.target
        for page in book.page_list:
            page.target = ctx.remap_fragment(page.target) or page.target

        def fragment_exists(target: str | None) -> bool:
            if not target or "#" not in target:
                return True
            path, _, fragment = target.partition("#")
            known = ctx.document_ids.get(path)
            # Unknown document (an image, say): nothing to verify against.
            return fragment in known if known is not None else True

        def prune(nodes: list[NavPoint]) -> list[NavPoint]:
            nonlocal removed
            kept: list[NavPoint] = []
            for node in nodes:
                node.children = prune(node.children)
                target_path = node.target_path
                if target_path and target_path not in book.resources:
                    removed += 1
                    node.target = None
                elif not fragment_exists(node.target):
                    # The document survives, only the anchor is gone; keep the
                    # entry pointing at the file rather than dropping it.
                    nonlocal dangling_fragments
                    dangling_fragments += 1
                    node.target = node.target.split("#", 1)[0]
                if node.target or node.children:
                    kept.append(node)
                else:
                    removed += 1
            return kept

        book.toc = prune(book.toc)

        for landmark in book.landmarks:
            if not fragment_exists(landmark.target):
                landmark.target = landmark.target.split("#", 1)[0]
                dangling_fragments += 1
        for page in book.page_list:
            if not fragment_exists(page.target):
                page.target = page.target.split("#", 1)[0]
                dangling_fragments += 1

        book.page_list = [p for p in book.page_list if p.target.split("#")[0] in book.resources]
        book.landmarks = [l for l in book.landmarks if l.target.split("#")[0] in book.resources]
        if removed:
            self.note(ctx, Level.FIX, "nav.entry-dropped", values={"count": removed})
        if dangling_fragments:
            self.note(
                ctx,
                Level.FIX,
                "nav.fragment-cleared",
                values={"count": dangling_fragments},
            )

    def _spine_what_the_navigation_reaches(self, ctx: Context) -> None:
        """Put a document the navigation points at into the spine, out of the flow.

        `RSC-011: Found a reference to a resource that is not a spine item` — four
        books on the mixed shelf, in all three modes, and absent from every
        source's own verdict because EPUB 2 navigated by NCX and had no such
        rule. EPUB 3 does: what the table of contents leads to has to be part of
        the publication's reading order.

        The publisher's intent is not in doubt. They put the document in the
        manifest and linked it from the navigation, so they meant it to be
        reachable; they left it out of the spine, so they meant page-turning not
        to arrive at it. `linear="no"` is the standard's own word for exactly
        that pair — in the spine, out of the flow — and it is what a cover page,
        a colophon or a rights notice usually wants.

        So the entry is kept and the document is spined, rather than the entry
        being dropped. Dropping it is the shorter patch and it deletes the only
        way to reach a page the book still contains.

        Placed where the navigation implies rather than appended: an entry sits
        before the next entry that *is* in the spine, so a cover listed first
        comes out first. Only content documents — a table of contents pointing
        at an image is a different defect and not one `linear="no"` describes.
        """
        book = ctx.book
        placed = {item.path for item in book.spine}

        # Navigation order, which is the order a reader meets these in.
        wanted: list[str] = []
        ordered: list[str] = []
        for root in book.toc:
            for node in root.walk():
                path = node.target_path
                if not path:
                    continue
                ordered.append(path)
                if path in placed or path in wanted:
                    continue
                resource = book.resources.get(path)
                if resource is not None and resource.is_content_doc:
                    wanted.append(path)
        if not wanted:
            return

        for path in wanted:
            after = ordered.index(path)
            following = next(
                (
                    other
                    for other in ordered[after + 1:]
                    if any(item.path == other for item in book.spine)
                ),
                None,
            )
            where = (
                next(i for i, item in enumerate(book.spine) if item.path == following)
                if following is not None
                else len(book.spine)
            )
            book.spine.insert(where, SpineItem(path, linear=False))

        self.note(
            ctx,
            Level.FIX,
            "nav.unspined-target-added",
            values={"count": len(wanted), "names": ", ".join(sorted(wanted)[:3])},
        )

    def _synthesize_toc(self, ctx: Context) -> None:
        book = ctx.book
        entries: list[NavPoint] = []
        for item in book.spine:
            resource = book.get(item.path)
            if resource is None or not resource.is_content_doc or not item.linear:
                continue
            entries.append(NavPoint(self._document_title(resource), item.path))
        book.toc = entries
        if entries:
            self.note(ctx, Level.FIX, "nav.toc-synthesised", values={"count": len(entries)})

    def _document_title(self, resource: Resource) -> str:
        text = resource.text()
        for pattern in (r"<title[^>]*>(.*?)</title>", r"<h1[^>]*>(.*?)</h1>", r"<h2[^>]*>(.*?)</h2>"):
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                stripped = re.sub(r"<[^>]+>", "", match.group(1))
                cleaned = html.unescape(re.sub(r"\s+", " ", stripped)).strip()
                if cleaned:
                    return cleaned[:200]
        return resource.basename.rpartition(".")[0].replace("-", " ")

    def _ensure_landmarks(self, ctx: Context) -> None:
        book = ctx.book
        by_type = {landmark.epub_type: landmark for landmark in book.landmarks}
        if "bodymatter" not in by_type:
            first_body = next(
                (
                    item.path
                    for item in book.spine
                    if item.linear
                    and book.get(item.path)
                    and book.get(item.path).is_content_doc
                    and item.path != (book.landmarks[0].target.split("#")[0] if book.landmarks else None)
                ),
                None,
            )
            if first_body:
                book.landmarks.append(Landmark("bodymatter", "Start of Content", first_body))

        seen: set[str] = set()
        deduped: list[Landmark] = []
        for landmark in book.landmarks:
            if landmark.epub_type in seen:
                continue
            seen.add(landmark.epub_type)
            deduped.append(landmark)
        book.landmarks = deduped

    def _render_nav_list(self, nodes: list[NavPoint], nav_path: str, indent: str) -> str:
        lines = [f"{indent}<ol>"]
        for node in nodes:
            label = _escape(node.label or "—")
            if node.target:
                target_path, _, fragment = node.target.partition("#")
                href = paths.relative(nav_path, target_path)
                if fragment:
                    href = f"{href}#{fragment}"
                anchor = f'<a href="{href}">{label}</a>'
            else:
                anchor = f"<span>{label}</span>"
            if node.children:
                lines.append(f"{indent}  <li>{anchor}")
                lines.append(self._render_nav_list(node.children, nav_path, indent + "    "))
                lines.append(f"{indent}  </li>")
            else:
                lines.append(f"{indent}  <li>{anchor}</li>")
        lines.append(f"{indent}</ol>")
        return "\n".join(lines)

    def _redirect(self, ctx: Context, old_path: str, new_path: str) -> None:
        """Point everything that referenced `old_path` at `new_path` instead.

        Called just before the source's navigation document is replaced. Three
        kinds of reference have to follow it: the entries of the tables this
        stage is about to render, the landmarks and page list beside them, and
        plain links inside content documents — a book whose foreword says "back
        to contents" is linking to the page that is about to stop existing.

        Retargeted rather than deleted: a link to the table of contents still
        means the table of contents, and the new document is it.
        """
        book = ctx.book
        moved = 0

        def retarget(target: str | None) -> str | None:
            nonlocal moved
            if not target:
                return target
            path, _, fragment = target.partition("#")
            if path != old_path:
                return target
            moved += 1
            # The fragment belonged to the old document and means nothing in
            # the regenerated one.
            return new_path

        for root in book.toc:
            for node in root.walk():
                node.target = retarget(node.target)
        for landmark in book.landmarks:
            landmark.target = retarget(landmark.target) or landmark.target
        for page in book.page_list:
            page.target = retarget(page.target) or page.target

        in_documents = 0
        for resource in book.content_docs():
            if resource.path == old_path:
                continue
            try:
                text = resource.data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            replaced = 0

            def repoint(match: re.Match) -> str:
                nonlocal replaced
                attribute, quote, value = match.group(1), match.group(2), match.group(3)
                if not value or paths.is_remote(value) or value.startswith("#"):
                    return match.group(0)
                href, _, fragment = value.partition("#")
                if paths.resolve(resource.path, href) != old_path:
                    return match.group(0)
                replaced += 1
                return f"{attribute}={quote}{paths.relative(resource.path, new_path)}{quote}"

            updated = _HREF_ATTRIBUTE.sub(repoint, text)
            if replaced:
                resource.data = updated.encode("utf-8")
                in_documents += replaced

        if moved or in_documents:
            self.note(
                ctx,
                Level.FIX,
                "nav.repointed",
                values={
                    "count": moved + in_documents,
                    "in_tables": moved,
                    "in_documents": in_documents,
                },
                location=old_path,
            )

    @staticmethod
    def _free_path(book, wanted: str) -> str:
        """A path near *wanted* that nothing in the book occupies."""
        stem, _, suffix = wanted.rpartition(".")
        for attempt in range(1, 100):
            candidate = f"{stem}-{attempt}.{suffix}" if attempt > 1 else f"{stem}-epub3.{suffix}"
            if book.get(candidate) is None:
                return candidate
        return wanted

    def _write_nav(self, ctx: Context) -> None:
        book = ctx.book
        nav_path = paths.content_path(ctx.policy, "nav.xhtml")

        # A navigation document is allowed to be part of the reading order, and
        # that is how a *visible* table of contents is built — the page the
        # reader can turn to. `Book.remove` drops the resource and its spine
        # entry together, so replacing the old document silently deleted that
        # page from the book. No error, no warning: the source had two spine
        # items and the output had one.
        #
        # What is carried over is the fact of being in the spine, its position
        # and its `linear` flag. Everything else about the document is
        # regenerated, which is the point of the stage.
        old_place = None

        # The guard below used to read `book.nav_path != nav_path`, and that
        # comparison is where a real book lost text. In container-only mode
        # nothing is renamed, so the generated document lands on **the same
        # path** the source's nav already occupies — the two are equal, the
        # protection is skipped, and the publisher's contents page is
        # overwritten in place. Twenty-four megabytes, 9 809 spine items, and
        # 32 characters gone: the book's own word for "contents".
        #
        # Worse, that is the one mode whose promise is that the content files
        # come out byte for byte, and the report said `xhtml.untouched` while
        # it happened — true of the stage that says it, and false of the book.
        #
        # So when the collision is with a nav the reader can turn to, the
        # generated one moves aside instead.
        if (
            book.nav_path
            and book.nav_path == nav_path
            and any(item.path == book.nav_path for item in book.spine)
        ):
            nav_path = self._free_path(book, nav_path)

        if book.nav_path and book.nav_path != nav_path:
            in_spine = next(
                (i for i, item in enumerate(book.spine) if item.path == book.nav_path), None
            )
            if in_spine is not None:
                # A nav document in the reading order is *two* things at once:
                # the machine-readable navigation, and a contents page written
                # by the publisher that the reader can turn to. Regenerating it
                # served the first and destroyed the second — on four of the
                # first thirty-two real books this ran against, the publisher's
                # own wording ("Spis treści", "Punkty orientacyjne", their
                # chapter labels) was replaced by ours. That is text the source
                # had and the output does not, which is K1.
                #
                # So the page stays as an ordinary content document, and the
                # regenerated nav goes in beside it, outside the reading order.
                # One nav document, as EPUB 3 requires; the publisher's page,
                # as the reader expects.
                book.resources[book.nav_path].properties.discard("nav")
                self.note(
                    ctx,
                    Level.PRESERVED,
                    "nav.contents-page-kept",
                    location=book.nav_path,
                )
            else:
                # Not a page anyone can turn to — only the machinery. Replacing
                # it loses nothing, but everything pointing at it has to be told
                # where it went: missing that produced an *invalid* book, with
                # EPUBCheck reporting "Referenced resource ... could not be
                # found" against the regenerated nav.
                self._redirect(ctx, book.nav_path, nav_path)
                book.remove(book.nav_path)
        self._nav_spine_place = old_place
        language = _escape(book.metadata.language or ctx.policy.default_language)

        sections = [
            '    <nav epub:type="toc" id="toc" role="doc-toc">',
            f"      <h1>{_escape(heading(language, 'toc'))}</h1>",
            self._render_nav_list(book.toc, nav_path, "      "),
            "    </nav>",
        ]

        if book.landmarks:
            sections.append('    <nav epub:type="landmarks" id="landmarks" hidden="hidden">')
            sections.append(f"      <h1>{_escape(heading(language, 'landmarks'))}</h1>")
            sections.append("      <ol>")
            for landmark in book.landmarks:
                target_path, _, fragment = landmark.target.partition("#")
                href = paths.relative(nav_path, target_path)
                if fragment:
                    href = f"{href}#{fragment}"
                label = _escape(landmark.label or landmark.epub_type.replace("-", " ").title())
                sections.append(
                    f'        <li><a epub:type="{_escape(landmark.epub_type)}" href="{href}">{label}</a></li>'
                )
            sections.append("      </ol>")
            sections.append("    </nav>")

        if book.page_list:
            sections.append('    <nav epub:type="page-list" id="page-list" hidden="hidden">')
            sections.append(f"      <h1>{_escape(heading(language, 'page-list'))}</h1>")
            sections.append("      <ol>")
            for page in book.page_list:
                target_path, _, fragment = page.target.partition("#")
                href = paths.relative(nav_path, target_path)
                if fragment:
                    href = f"{href}#{fragment}"
                sections.append(f'        <li><a href="{href}">{_escape(page.label)}</a></li>')
            sections.append("      </ol>")
            sections.append("    </nav>")

        body = "\n".join(sections)
        markup = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_NS}" lang="{language}" xml:lang="{language}">
  <head>
    <meta charset="utf-8"/>
    <title>{_escape(book.metadata.title)} — {_escape(heading(language, "title"))}</title>
  </head>
  <body>
{body}
  </body>
</html>
"""
        book.add(
            Resource(
                path=nav_path,
                media_type="application/xhtml+xml",
                data=markup.encode("utf-8"),
                properties={"nav"},
            )
        )
        book.nav_path = nav_path

        # Put it back where it was in the reading order, if it was there at all.
        place = getattr(self, "_nav_spine_place", None)
        if place is not None:
            index, linear, properties = place
            book.spine.insert(
                min(index, len(book.spine)),
                SpineItem(path=nav_path, linear=linear, properties=set(properties)),
            )
            self.note(ctx, Level.INFO, "nav.kept-in-spine")

        entries = sum(1 for root in book.toc for _ in root.walk())
        # Two findings, not one with a conditional: replacing a navigation
        # document is routine and generating one the source never had is a
        # correction, and they are read differently.
        if self._had_nav:
            self.note(ctx, Level.INFO, "nav.regenerated", values={"count": entries})
        else:
            self.note(ctx, Level.FIX, "nav.generated", values={"count": entries})

    def _drop_ncx(self, ctx: Context) -> None:
        if ctx.book.ncx_path:
            ctx.book.remove(ctx.book.ncx_path)
            ctx.book.ncx_path = None
            self.note(ctx, Level.INFO, "nav.ncx-dropped")

    def _write_ncx(self, ctx: Context) -> None:
        book = ctx.book
        ncx_path = paths.content_path(ctx.policy, "toc.ncx")
        if book.ncx_path and book.ncx_path != ncx_path:
            book.remove(book.ncx_path)

        identifier = book.metadata.primary_identifier
        counter = [0]

        def render(nodes: list[NavPoint], indent: str) -> str:
            lines = []
            for node in nodes:
                counter[0] += 1
                order = counter[0]
                target = node.target
                if not target:
                    # NCX has no heading-only node; borrow the first child's target.
                    descendant = next((n for n in node.walk() if n.target), None)
                    target = descendant.target if descendant else None
                if not target:
                    continue
                target_path, _, fragment = target.partition("#")
                src = paths.relative(ncx_path, target_path)
                if fragment:
                    src = f"{src}#{fragment}"
                lines.append(f'{indent}<navPoint id="navPoint-{order}" playOrder="{order}">')
                lines.append(f"{indent}  <navLabel><text>{_escape(node.label or '—')}</text></navLabel>")
                lines.append(f'{indent}  <content src="{src}"/>')
                if node.children:
                    lines.append(render(node.children, indent + "  "))
                lines.append(f"{indent}</navPoint>")
            return "\n".join(lines)

        nav_map = render(book.toc, "    ")
        authors = "".join(
            f"\n  <docAuthor><text>{_escape(c.name)}</text></docAuthor>"
            for c in book.metadata.creators
            if c.role == "aut"
        )
        markup = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{_escape(identifier.value if identifier else '')}"/>
    <meta name="dtb:depth" content="{self._depth(book.toc)}"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{_escape(book.metadata.title)}</text></docTitle>{authors}
  <navMap>
{nav_map}
  </navMap>
</ncx>
"""
        book.add(
            Resource(path=ncx_path, media_type="application/x-dtbncx+xml", data=markup.encode("utf-8"))
        )
        book.ncx_path = ncx_path
        self.note(ctx, Level.INFO, "nav.ncx-written")

    def _depth(self, nodes: list[NavPoint], level: int = 1) -> int:
        if not nodes:
            return 1
        return max([level] + [self._depth(node.children, level + 1) for node in nodes])
