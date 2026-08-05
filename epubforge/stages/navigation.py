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


class NavigationStage(Stage):
    name = "navigation"

    def run(self, ctx: Context) -> None:
        # EPUB 2 sources have no navigation document at all; generating one is a
        # correction, whereas replacing an existing one is routine.
        self._had_nav = bool(ctx.book.nav_path)
        self._ensure_cover_page(ctx)
        self._prune_toc(ctx)
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
                self.note(ctx, Level.WARN, "declared cover image is missing from the archive")
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
        page_path = f"{ctx.policy.content_dir.strip('/')}/text/0000-cover.xhtml"
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
        self.note(
            ctx,
            Level.FIX,
            "generated a cover page so the artwork appears as the first spine item",
            location=page_path,
        )

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
            self.note(ctx, Level.FIX, f"dropped {removed} table-of-contents entry/entries pointing nowhere")
        if dangling_fragments:
            self.note(
                ctx,
                Level.FIX,
                f"cleared {dangling_fragments} navigation fragment(s) whose anchor does not exist",
                detail="The entry now points at the document, which is where the reader would land anyway.",
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
            self.note(
                ctx,
                Level.FIX,
                f"book had no usable table of contents; built one from {len(entries)} spine documents",
            )

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
                f"repointed {moved + in_documents} reference(s) at the regenerated "
                "navigation document",
                location=old_path,
                detail=(
                    f"{moved} in the navigation tables, {in_documents} inside content "
                    "documents. The source's own contents page is replaced, and a "
                    "reference left pointing at it makes the book invalid, not merely "
                    "inconsistent."
                ),
            )

    def _write_nav(self, ctx: Context) -> None:
        book = ctx.book
        nav_path = f"{ctx.policy.content_dir.strip('/')}/nav.xhtml"

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
                    "kept the publisher's contents page and put the regenerated "
                    "navigation beside it",
                    location=book.nav_path,
                    detail=(
                        "The page is in the reading order, so it is something the "
                        "reader turns to. Replacing it with generated markup would "
                        "lose whatever the publisher wrote there."
                    ),
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
            "      <h1>Table of Contents</h1>",
            self._render_nav_list(book.toc, nav_path, "      "),
            "    </nav>",
        ]

        if book.landmarks:
            sections.append('    <nav epub:type="landmarks" id="landmarks" hidden="hidden">')
            sections.append("      <h1>Landmarks</h1>")
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
            sections.append("      <h1>Page List</h1>")
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
    <title>{_escape(book.metadata.title)} — Contents</title>
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
            self.note(
                ctx,
                Level.INFO,
                "kept the navigation document in the reading order, where the source had it",
                detail=(
                    "A nav document in the spine is a page the reader can turn to. "
                    "Regenerating it used to remove that page."
                ),
            )

        entries = sum(1 for root in book.toc for _ in root.walk())
        self.note(
            ctx,
            Level.INFO if self._had_nav else Level.FIX,
            (
                f"regenerated the navigation document ({entries} entries)"
                if self._had_nav
                else f"generated the navigation document EPUB 3 requires ({entries} entries)"
            ),
            detail=None if self._had_nav else "The source had none; its table of contents came from the NCX.",
        )

    def _drop_ncx(self, ctx: Context) -> None:
        if ctx.book.ncx_path:
            ctx.book.remove(ctx.book.ncx_path)
            ctx.book.ncx_path = None

    def _write_ncx(self, ctx: Context) -> None:
        book = ctx.book
        ncx_path = f"{ctx.policy.content_dir.strip('/')}/toc.ncx"
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
        self.note(
            ctx,
            Level.INFO,
            "wrote a legacy NCX alongside the nav document for older readers",
        )

    def _depth(self, nodes: list[NavPoint], level: int = 1) -> int:
        if not nodes:
            return 1
        return max([level] + [self._depth(node.children, level + 1) for node in nodes])
