"""Navigation: EPUB 3 nav document, legacy NCX, landmarks and the cover page."""

from __future__ import annotations

import html
import re

from .. import covers, paths, xhtml, xmlchars
from ..decisions import KEEP, REFERENCE, Option, Question
from ..model import Landmark, NavPoint, Resource, SpineItem
from ..question_texts import say
from ..report import Action, Automation, Level, Risk
from ..xhtml import EPUB_NS, XHTML_NS
from .base import Context, Stage

#: The template lives in `covers` now (EF-080); re-exported for the tests and
#: any reader that knew it here.
COVER_PAGE_TEMPLATE = covers.COVER_PAGE_TEMPLATE

#: `href="…"` and `src="…"` as they appear in a content document. Narrow on
#: purpose: this rewrites bytes rather than a parse tree, so it touches the
#: attributes it can name and nothing else.
_HREF_ATTRIBUTE = re.compile(r"""\b(href|src)=(["'])([^"']*)\2""")



def _escape(value: str) -> str:
    """Escape for XML, over text XML is able to represent.

    The second half is not decoration. The navigation document and the NCX are
    *generated*, so they carry whatever the metadata says, and a title carrying a
    control character produced two written, unopenable files — measured on the
    default preset, reported as `succeeded`. There is no escape sequence for
    these characters; XML 1.0 simply has no way to hold them, so they go.

    Zbiór mieszka w `xmlchars` — jednym liściu, od którego zależą writer, `xhtml`
    i ten etap, i który nie zależy od nikogo. Pierwsza wersja miała trzy kopie
    tego samego wyrażenia, bo `navigation` importujący z `writer` wiązałby etap
    z tym, co działa po wszystkich etapach.
    """
    return html.escape(xmlchars.legal(value), quote=True)


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


#: ARIA roles for the navigation kinds that have one. A `nav` whose kind has no
#: role gets none: inventing one states something about the section that the
#: publisher did not.
_ARIA_ROLES = {
    "toc": "doc-toc",
    "page-list": "doc-pagelist",
    "index": "doc-index",
    "glossary": "doc-glossary",
    "bibliography": "doc-bibliography",
}


def heading(language: str, section: str) -> str:
    """One navigation heading, in the book's language where we have it."""
    tag = (language or "en").replace("_", "-").split("-")[0].lower()
    return NAV_HEADINGS.get(tag, NAV_HEADINGS["en"])[section]


def _label_attribute(book, kind: str) -> str:
    """The publisher's own `aria-label` on a section this program rebuilds
    from the model, written back word for word. Before the audit of
    2026-09-03 it left with the source document — the count of semantic
    attributes before and after a rebuild was the first thing to notice."""
    value = book.nav_labels.get(kind, "")
    return f' aria-label="{_escape(value)}"' if value else ""


class NavigationStage(Stage):
    name = "navigation"

    def run(self, ctx: Context) -> None:
        # EPUB 2 sources have no navigation document at all; generating one is a
        # correction, whereas replacing an existing one is routine.
        self._had_nav = bool(ctx.book.nav_path)
        self._ensure_cover_page(ctx)
        self._prune_toc(ctx)
        self._repoint_duplicate_targets(ctx)
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
        """The cover page, if the structure stage did not already put it in.

        Synthesised by the structure stage since EF-080, **before** the
        files are numbered and before the text stages run — so that the page
        is named like every other page and repaired like every other page in
        the same pass. Kept here for a pipeline that runs this stage without
        that one; `covers.synthesise_cover_page` does nothing the second time.
        """
        page_path, warning = covers.synthesise_cover_page(ctx.book, ctx.policy)
        if warning or ctx.cover_image_missing:
            self.note(ctx, Level.WARN, "nav.cover-image-missing")
        page_path = page_path or ctx.synthesised_cover_page
        if page_path:
            # The structure stage renamed it with everything else; say where
            # it is now, not where it was born.
            location = ctx.path_map.get(page_path, page_path)
            self.note(ctx, Level.FIX, "nav.cover-page-generated", location=location)

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
        # The sections this program carries rather than models get the same
        # treatment as the contents: their targets are ordinary targets, and a
        # list of illustrations pointing at a renamed id is as broken as a
        # chapter entry pointing at one.
        for section in book.extra_navs:
            for root in section.entries:
                for node in root.walk():
                    node.target = ctx.remap_fragment(node.target)

        def fragment_exists(target: str | None) -> bool:
            if not target or "#" not in target:
                return True
            path, _, fragment = target.partition("#")
            known = ctx.document_ids.get(path)
            # Unknown document (an image, say): nothing to verify against.
            return fragment in known if known is not None else True

        # ------------------------------------------------------------------
        # KNOWN, NOT YET DECIDED — the same shape as F-010, in three places
        # below (`prune`, the landmark loop, the page-list loop).
        #
        # A contents entry, a landmark or a page-list entry whose anchor is
        # missing has that anchor removed and is kept pointing at the file. That
        # is exactly the transformation `references.py` forbids in a content
        # document: a page-list entry for page 214 that lands at the top of the
        # chapter is *wrong* rather than merely imprecise, and nothing in the
        # output says so.
        #
        # It is left alone here on purpose, and not out of agreement with it.
        # F-010's review asked for the content-document case to be fixed first
        # and for the others to be named rather than swept along, because they
        # are not the same argument: a navigation entry with no target at all is
        # dropped from the table, so "keep it exactly as the publisher wrote it"
        # has a second consequence here that it does not have in a chapter — the
        # entry can disappear from the contents entirely. That trade needs
        # measuring on real books before it is made.
        #
        # Tracked in the private notes as F-010b, beside F-016 and F-018.
        # ------------------------------------------------------------------
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
        for section in book.extra_navs:
            section.entries = prune(section.entries)

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

    def _repoint_duplicate_targets(self, ctx: Context) -> None:
        """Contents entries that all jump to one untangled id: asked, not guessed.

        EF-058, and the audit of it drew the line this method walks. A source
        document carried one id eleven times; the content stage untangles the
        copies correctly (`…_5`, `…_5-2`, …), but the eleven contents entries
        that pointed at `#…_5` keep pointing there — eleven entries, one
        landing place. Assigning the n-th entry to the n-th occurrence is
        *probable* and is not a fact: `references.py` allows `REPAIRED` only
        for a mapping the program itself produced, and reading somebody
        else's ordering is not that. Its third verb — ask — is what this is.

        Asked only when the counts agree. Ten entries over eleven occurrences
        leave no ordering that is even probable, so nothing is offered and the
        report carries a count instead. Without an answer nothing changes:
        every entry keeps jumping where it jumped yesterday.
        """
        if not ctx.untangled:
            return
        groups: dict[str, list[NavPoint]] = {}
        for root in ctx.book.toc:
            for node in root.walk():
                target = node.target
                if not target or "#" not in target:
                    continue
                path, _, fragment = target.partition("#")
                if fragment in ctx.untangled.get(path, {}):
                    groups.setdefault(target, []).append(node)

        for target, nodes in groups.items():
            path, _, fragment = target.partition("#")
            names = ctx.untangled[path][fragment]
            if len(nodes) < 2:
                continue
            if len(nodes) != len(names):
                self.note(ctx, Level.INFO, "nav.duplicate-target-found",
                          values={"count": len(nodes)}, location=path)
                continue
            texts = self._texts_at(ctx, path, names)
            shown = "\n".join(
                f"„{node.label}” → {texts.get(name, '') or f'#{name}'}"
                for node, name in list(zip(nodes, names))[:3]
            )
            question = Question(
                kind=REFERENCE,
                where=path,
                summary=say("toc.duplicate.summary", count=len(nodes)),
                detail=say("toc.duplicate.detail", where=path,
                           count=len(nodes), shown=shown),
                options=(
                    Option(KEEP, say("toc.duplicate.keep"), say("toc.duplicate.keep.why")),
                    Option("repoint", say("toc.duplicate.repoint"),
                           say("toc.duplicate.repoint.why", count=len(nodes))),
                ),
                recommended="repoint",
                reversible=True,
                risk=Risk.CONTENT,
                group="toc:duplicate-target",
                subject=f"{len(nodes)} entries",
            )
            if ctx.decide(question).option != "repoint":
                self.note(ctx, Level.INFO, "nav.duplicate-target-found",
                          values={"count": len(nodes)}, location=path)
                continue
            for node, name in zip(nodes, names):
                node.target = f"{path}#{name}"
            self.note(ctx, Level.FIX, "nav.entries-repointed",
                      values={"count": len(nodes)}, location=path)
            self.changed(
                ctx, Action.REPLACED, path,
                before=f"{len(nodes)} contents entries, every one landing on #{fragment}",
                after="each entry points at its own untangled id, in document order",
                automation=Automation.ASKED,
                risk=Risk.CONTENT, reversible=True,
                rule="nav.entries-repointed",
            )

    def _texts_at(self, ctx: Context, path: str, names: list[str]) -> dict[str, str]:
        """The visible text at each id, for the question's preview."""
        resource = ctx.book.get(path)
        if resource is None:
            return {}
        try:
            root = ctx.parsed(resource).root
        except Exception:  # noqa: BLE001 — no preview beats no question
            return {}
        wanted = set(names)
        found: dict[str, str] = {}
        for element in xhtml.iter_elements(root):
            name = element.get("id")
            if name in wanted and name not in found:
                found[name] = " ".join("".join(element.itertext()).split())[:60]
        return found

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

        def consider(path: str) -> None:
            if not path:
                return
            ordered.append(path)
            if path in placed or path in wanted:
                return
            resource = book.resources.get(path)
            if resource is not None and resource.is_content_doc:
                wanted.append(path)

        roots = list(book.toc) + [root for s in book.extra_navs for root in s.entries]
        for root in roots:
            for node in root.walk():
                consider(node.target_path)
        # Landmarks and the page list are navigation too, and EPUBCheck does not
        # distinguish: `RSC-011` is about the navigation *document*, and all
        # three end up inside it. This used to walk the contents alone, so a
        # book whose cover page is reached from `<guide>` and never from the
        # table of contents — which is how EPUB 2 covers are normally wired —
        # went out with a landmark pointing outside the spine.
        #
        # Found on the owner's 67-book collection: four books came out of
        # `preserve` carrying `RSC-011` where their sources carried none, and
        # all four had `xhtml.cover-fitted` in their findings. The mechanism was
        # right and its input was half the navigation.
        for landmark in book.landmarks:
            consider(landmark.target.split("#", 1)[0] if landmark.target else "")
        for page in book.page_list:
            consider(page.target.split("#", 1)[0] if page.target else "")
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

        # Deduplicated by *type and target*, not by type alone.
        #
        # By type alone reads "a book has one cover and one table of contents",
        # which is true of the handful of types that mean a place in the
        # publication and false of everything else. Project Gutenberg writes its
        # page list as `epub:type="landmarks"` with 294 entries all typed
        # `normal`; this kept the first and deleted 293 links into the book,
        # silently, on every Gutenberg title. Found by the fidelity harness on
        # the third book it was pointed at — a validator has nothing to say
        # about it, and neither did any test here.
        #
        # `_ensure_cover_page` above removes the source's own `cover` landmark
        # before inserting its own, so the one case that really must not double
        # is handled where the decision is made rather than by a sweep here.
        seen: set[tuple[str, str]] = set()
        deduped: list[Landmark] = []
        for landmark in book.landmarks:
            key = (landmark.epub_type, landmark.target)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(landmark)
        if len(deduped) != len(book.landmarks):
            self.note(
                ctx,
                Level.FIX,
                "nav.landmarks-deduplicated",
                values={"count": len(book.landmarks) - len(deduped)},
            )
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

    #: What the regenerated navigation calls each of its sections. The ids are
    #: written in `_write_nav`; naming them once means the mapping below cannot
    #: quietly stop matching the document it describes.
    SECTION_IDS = {"toc": "toc", "landmarks": "landmarks", "page-list": "page-list"}

    def _fragment_map(self, ctx: Context, old_path: str) -> dict[str, str]:
        """`{old anchor: new anchor}` for the navigation document being replaced.

        The one deterministic repair available here, and the reason F-010 has a
        clause about regenerated resources at all. A book that links to
        `nav.xhtml#spis` is linking to the source's table of contents; this
        stage is about to write a table of contents of its own and knows what it
        calls it. `spis -> toc` is therefore not a guess — it is a fact about a
        transformation this program is performing, which is the only kind of
        evidence that earns the word *repaired*.

        Only the `<nav>` elements are mapped, and only by `epub:type`, because
        those are the parts of the old document the new one is a replacement
        for. Anything else the old navigation carried an id for — a heading, a
        list item — has no counterpart in the regenerated document, and the
        reference to it is treated as changed by a transformation this program
        chose to make, which is the fourth case in the audit's list and the only
        place a fragment is allowed to go without a person saying so.
        """
        resource = ctx.book.get(old_path)
        if resource is None:
            return {}
        try:
            markup = resource.data.decode("utf-8", "replace")
        except (AttributeError, UnicodeDecodeError):  # pragma: no cover - defensive
            return {}

        present = {"toc"}
        if ctx.book.landmarks:
            present.add("landmarks")
        if ctx.book.page_list:
            present.add("page-list")

        mapping: dict[str, str] = {}
        for tag in re.finditer(r"<nav\b[^>]*>", markup, re.IGNORECASE):
            attributes = dict(re.findall(r"""\b([\w:-]+)=["']([^"']*)["']""", tag.group(0)))
            kind = (attributes.get("epub:type") or "").strip().lower()
            old_id = (attributes.get("id") or "").strip()
            new_id = self.SECTION_IDS.get(kind)
            if old_id and new_id and kind in present:
                mapping[old_id] = new_id
        return mapping

    def _redirect(self, ctx: Context, old_path: str, new_path: str) -> None:
        """Point everything that referenced `old_path` at `new_path` instead.

        Called just before the source's navigation document is replaced. Three
        kinds of reference have to follow it: the entries of the tables this
        stage is about to render, the landmarks and page list beside them, and
        plain links inside content documents — a book whose foreword says "back
        to contents" is linking to the page that is about to stop existing.

        Retargeted rather than deleted: a link to the table of contents still
        means the table of contents, and the new document is it. Where the
        anchor inside it also has a counterpart, the anchor follows too — see
        `_fragment_map`.
        """
        book = ctx.book
        moved = 0
        mapped = 0
        fragments = self._fragment_map(ctx, old_path)

        def arrival(fragment: str) -> str:
            """Where a reference to `old_path#fragment` now points."""
            nonlocal mapped
            new_fragment = fragments.get(fragment)
            if not new_fragment:
                return new_path
            mapped += 1
            return f"{new_path}#{new_fragment}"

        def retarget(target: str | None) -> str | None:
            nonlocal moved
            if not target:
                return target
            path, _, fragment = target.partition("#")
            if path != old_path:
                return target
            moved += 1
            return arrival(fragment)

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
                nonlocal replaced, mapped
                attribute, quote, value = match.group(1), match.group(2), match.group(3)
                if not value or paths.is_remote(value) or value.startswith("#"):
                    return match.group(0)
                href, _, fragment = value.partition("#")
                if paths.resolve(resource.path, href) != old_path:
                    return match.group(0)
                replaced += 1
                landing = paths.relative(resource.path, new_path)
                new_fragment = fragments.get(fragment)
                if new_fragment:
                    mapped += 1
                    landing = f"{landing}#{new_fragment}"
                return f"{attribute}={quote}{landing}{quote}"

            updated = _HREF_ATTRIBUTE.sub(repoint, text)
            if replaced:
                resource.data = updated.encode("utf-8")
                in_documents += replaced

        if mapped:
            # Said separately from the repointing, because it is a different
            # claim. Moving a reference to the document that replaced its target
            # is bookkeeping; carrying its anchor across is the one place in
            # this stage where a fragment survives a document being regenerated,
            # and F-010 exists because that was not happening.
            self.note(
                ctx,
                Level.FIX,
                "nav.fragment-carried",
                values={"count": mapped},
                location=new_path,
            )
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
        """The navigation document, regenerated from the model: the contents,
        then the landmarks and the page list when the book has them, then
        every section the publisher wrote that this program does not model."""
        book = ctx.book
        nav_path = self._settle_nav_path(ctx)
        language = _escape(book.metadata.language or ctx.policy.default_language)

        sections = self._toc_section(book, nav_path, language)
        if book.landmarks:
            sections.extend(self._landmarks_section(book, nav_path, language))
        if book.page_list:
            sections.extend(self._page_list_section(book, nav_path, language))
        carried, extra = self._carried_sections(book, nav_path)
        sections.extend(extra)

        self._note_what_was_carried(ctx, book, nav_path, carried)
        self._add_nav_document(ctx, nav_path, language, sections)

        entries = sum(1 for root in book.toc for _ in root.walk())
        # Two findings, not one with a conditional: replacing a navigation
        # document is routine and generating one the source never had is a
        # correction, and they are read differently.
        if self._had_nav:
            self.note(ctx, Level.INFO, "nav.regenerated", values={"count": entries})
        else:
            self.note(ctx, Level.FIX, "nav.generated", values={"count": entries})

    def _settle_nav_path(self, ctx: Context) -> str:
        """Where the regenerated document goes, and what becomes of the old one."""
        book = ctx.book
        nav_path = paths.content_path(ctx.policy, "nav.xhtml")

        # A navigation document is allowed to be part of the reading order, and
        # that is how a *visible* table of contents is built — the page the
        # reader can turn to. `Book.remove` drops the resource and its spine
        # entry together, so replacing the old document silently deleted that
        # page from the book. No error, no warning: the source had two spine
        # items and the output had one.
        #
        # The answer is below: a nav that is a page stays a page, as the
        # publisher wrote it, and the regenerated document goes in beside it,
        # outside the reading order. (An earlier design carried the old
        # document's spine place over to the new one; it never ran — the
        # place was never recorded — and was removed on 2026-09-04 together
        # with the catalogue entry that described it.)

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
        return nav_path

    def _toc_section(self, book, nav_path: str, language: str) -> list[str]:
        return [
            f'    <nav epub:type="toc" id="toc" role="doc-toc"{_label_attribute(book, "toc")}>',
            f"      <h1>{_escape(heading(language, 'toc'))}</h1>",
            self._render_nav_list(book.toc, nav_path, "      "),
            "    </nav>",
        ]

    def _landmarks_section(self, book, nav_path: str, language: str) -> list[str]:
        lines = [
            f'    <nav epub:type="landmarks" id="landmarks"{_label_attribute(book, "landmarks")} hidden="hidden">',
            f"      <h1>{_escape(heading(language, 'landmarks'))}</h1>",
            "      <ol>",
        ]
        for landmark in book.landmarks:
            target_path, _, fragment = landmark.target.partition("#")
            href = paths.relative(nav_path, target_path)
            if fragment:
                href = f"{href}#{fragment}"
            label = _escape(landmark.label or landmark.epub_type.replace("-", " ").title())
            lines.append(
                f'        <li><a epub:type="{_escape(landmark.epub_type)}" href="{href}">{label}</a></li>'
            )
        lines.append("      </ol>")
        lines.append("    </nav>")
        return lines

    def _page_list_section(self, book, nav_path: str, language: str) -> list[str]:
        lines = [
            '    <nav epub:type="page-list" id="page-list" role="doc-pagelist"'
            f'{_label_attribute(book, "page-list")} hidden="hidden">',
            f"      <h1>{_escape(heading(language, 'page-list'))}</h1>",
            "      <ol>",
        ]
        for page in book.page_list:
            target_path, _, fragment = page.target.partition("#")
            href = paths.relative(nav_path, target_path)
            if fragment:
                href = f"{href}#{fragment}"
            lines.append(f'        <li><a href="{href}">{_escape(page.label)}</a></li>')
        lines.append("      </ol>")
        lines.append("    </nav>")
        return lines

    def _carried_sections(self, book, nav_path: str) -> tuple[int, list[str]]:
        # Everything else the source's navigation held: a list of tables, of
        # illustrations, of anything the publisher named. F-018. This program
        # does not model them and does not need to — an entry is a label and a
        # target — but it regenerates the document they lived in, so not writing
        # them back is deleting them. `epub:type` is carried verbatim: it is the
        # publisher's word for what the section is, and there is nothing to
        # translate it into.
        carried = 0
        lines: list[str] = []
        for index, section in enumerate(book.extra_navs):
            entries = [node for node in section.entries if node.target or node.children]
            if not entries:
                continue
            carried += 1
            attributes = f' epub:type="{_escape(section.epub_type)}"' if section.epub_type else ""
            role = f' role="{_ARIA_ROLES[section.epub_type]}"' if section.epub_type in _ARIA_ROLES else ""
            hidden = ' hidden="hidden"' if section.hidden else ""
            label = f' aria-label="{_escape(section.aria_label)}"' if section.aria_label else ""
            lines.append(
                f'    <nav{attributes} id="nav-{index + 1}"{role}{label}{hidden}>'
            )
            if section.heading:
                lines.append(f"      <h1>{_escape(section.heading)}</h1>")
            lines.append(self._render_nav_list(entries, nav_path, "      "))
            lines.append("    </nav>")
        return carried, lines

    def _note_what_was_carried(self, ctx: Context, book, nav_path: str, carried: int) -> None:
        written_labels = [kind for kind in ("toc", "landmarks", "page-list") if book.nav_labels.get(kind)
                          and (kind == "toc" or (kind == "landmarks" and book.landmarks)
                               or (kind == "page-list" and book.page_list))]
        if written_labels:
            self.note(
                ctx,
                Level.PRESERVED,
                "nav.labels-carried",
                values={"count": len(written_labels), "names": ", ".join(written_labels)},
                location=nav_path,
            )
        if carried:
            self.note(
                ctx,
                Level.PRESERVED,
                "nav.sections-carried",
                values={
                    "count": carried,
                    "names": ", ".join(
                        section.epub_type or "?" for section in book.extra_navs
                    ),
                },
                location=nav_path,
            )

    def _add_nav_document(self, ctx: Context, nav_path: str, language: str, sections: list[str]) -> None:
        book = ctx.book
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

    def _drop_ncx(self, ctx: Context) -> None:
        if ctx.book.ncx_path:
            dropped = ctx.book.ncx_path
            ctx.book.remove(dropped)
            ctx.book.ncx_path = None
            # In the ledger, because the balance is right to ask about it and
            # this is the answer. Found on the owner's own run: with "omit the
            # legacy NCX" ticked, the source's `toc.ncx` left the book, the
            # balance saw one resource fewer with nothing accounting for it, and
            # reported an error on a removal he had *asked for*.
            #
            # A false alarm from a check like this is worse than no check: it
            # teaches the person to read past the one message that means
            # something. The removal is deliberate, it is his to ask for, and it
            # now says so where a machine can read it.
            self.changed(
                ctx,
                Action.REMOVED,
                "other",
                before=dropped,
                after="",
                risk=Risk.NONE,
                reversible=True,
                rule="nav.ncx-dropped",
            )
            self.note(ctx, Level.INFO, "nav.ncx-dropped")

    def _write_ncx(self, ctx: Context) -> None:
        book = ctx.book
        ncx_path = paths.content_path(ctx.policy, "toc.ncx")
        if book.ncx_path and book.ncx_path != ncx_path:
            # The same file under a new name, written again below. Recorded as a
            # move rather than a removal so the balance sees what happened: the
            # count is unchanged and nothing has gone missing.
            book.remove(book.ncx_path)
            self.changed(
                ctx,
                Action.MOVED,
                "other",
                before=book.ncx_path,
                after=ncx_path,
                risk=Risk.NONE,
                reversible=True,
                rule="nav.ncx-written",
            )

        identifier = book.metadata.primary_identifier
        counter = [0]
        # `playOrder` is a property of the *place*, not of the entry, and the
        # NCX specification says so: two navPoints that name the same target
        # must carry the same number. Written as a running counter it does not,
        # and EPUBCheck answers `different playOrder values for
        # navPoint/navTarget/pageTarget that refer to same target` — which in
        # strict mode is a refusal to publish.
        #
        # It shows up when a book arrives with the same `id` on several
        # headings: every table-of-contents entry then names one anchor, this
        # program numbers them 6…16, and the file it wrote is invalid even
        # though the one it read was not (EF-058, one book of the owner's 160).
        # Repointing those entries at the headings they were probably *meant*
        # for is a different question and not this one — it is a guess about the
        # source, and `references.py` is where the rule about guessing lives.
        # Numbering is not a guess: the same place gets the same number.
        given: dict[str, int] = {}

        def render(nodes: list[NavPoint], indent: str) -> str:
            lines = []
            for node in nodes:
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
                counter[0] += 1
                identifier = counter[0]
                if src not in given:
                    given[src] = len(given) + 1
                order = given[src]
                lines.append(f'{indent}<navPoint id="navPoint-{identifier}" playOrder="{order}">')
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
