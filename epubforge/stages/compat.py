"""Reader-family compatibility: the last layer, and an entirely optional one.

This stage runs after everything else on purpose. By the time it starts the
book is finished and standards-clean; what happens here is a deliberate step
away from that, taken because a particular device needs it. Keeping it last
means no earlier stage has to know these concessions exist, and switching every
profile off leaves the pipeline exactly as it was.

The stage never removes anything and never rewrites a value the book already
had. It adds: a stylesheet, a declaration beside an existing one, a legacy
element, a container file. If a measure has nothing to add — no fonts to
declare, no fragmentation properties to mirror — it is skipped and said so,
rather than writing a claim the book does not support.
"""

from __future__ import annotations

import re

from .. import compat, paths, xhtml
from ..model import Resource
from ..report import Level
from .base import Context, Stage

#: ``break-*`` value → the ``page-break-*`` value that means the same thing.
#: Left out on purpose: ``column`` and ``region``, which have no page-break
#: equivalent, and ``all``, which is not a fragmentation break at all.
_BREAK_TO_PAGE_BREAK = {
    "auto": "auto",
    "avoid": "avoid",
    "avoid-page": "avoid",
    "page": "always",
    "always": "always",
    "left": "left",
    "right": "right",
    # recto/verso are direction-relative; for the left-to-right books this
    # applies to they are the recto=right, verso=left pair.
    "recto": "right",
    "verso": "left",
}

#: ``page-break-inside`` only ever accepted ``auto`` and ``avoid``.
_INSIDE_VALUES = {"auto", "avoid"}

_DECLARATION_BLOCK_RE = re.compile(r"\{([^{}]*)\}")
_BREAK_DECLARATION_RE = re.compile(
    r"(^|;)(\s*)break-(before|after|inside)\s*:\s*([^;}]+)", re.IGNORECASE
)


class CompatibilityStage(Stage):
    name = "compat"

    def run(self, ctx: Context) -> None:
        measures, unknown = compat.resolve(ctx.policy.compat_profiles)
        for name in unknown:
            self.note(
                ctx,
                Level.WARN,
                f"unknown compatibility profile {name!r}; ignored",
                rule="compat.unknown-profile",
                values={"profile": name, "known": ", ".join(sorted(compat.PROFILES))},
                detail=f"Known profiles: {', '.join(sorted(compat.PROFILES))}.",
            )
        if not measures:
            return

        self.note(
            ctx,
            Level.INFO,
            "applying compatibility profile(s): ", rule="compat.applied" + ", ".join(sorted(ctx.policy.compat_profiles)),
            detail=(
                "These are concessions to specific devices, not corrections. "
                "Nothing below removes or rewrites what the book already had."
            ),
        )

        if "ncx" in measures:
            self._ncx(ctx)
        if "html5-blocks" in measures:
            self._html5_blocks(ctx)
        if "page-break" in measures:
            self._page_breaks(ctx)
        if "apple-fonts" in measures:
            self._apple_fonts(ctx)
        if "guide" in measures:
            self._guide(ctx)

        if "kindle" in ctx.policy.compat_profiles:
            self._kindle_cover_advice(ctx)

    # ------------------------------------------------------------------ ncx
    def _ncx(self, ctx: Context) -> None:
        """The NCX is a policy switch; a profile that needs it says so loudly."""
        if ctx.book.ncx_path:
            return
        self.note(
            ctx,
            Level.WARN,
            "the selected profile needs the legacy NCX, but it was switched off", rule="compat.ncx-required",
            detail=(
                "Readers predating EPUB 3 build their chapter list from the NCX and "
                "ignore the navigation document. Drop --no-ncx to restore it."
            ),
        )

    # ---------------------------------------------------------- html5 blocks
    def _html5_blocks(self, ctx: Context) -> None:
        book = ctx.book
        documents = [r for r in book.content_docs()]
        if not documents:
            return

        sheet_path = paths.unique(
            paths.content_path(ctx.policy, f"styles/{compat.COMPAT_STYLESHEET_NAME}"),
            set(book.resources),
        )
        book.add(
            Resource(
                path=sheet_path,
                media_type="text/css",
                data=compat.HTML5_BLOCK_CSS.encode("utf-8"),
            )
        )

        linked = 0
        for resource in documents:
            try:
                root, _ = xhtml.parse(resource.data)
            except Exception:  # noqa: BLE001 - a document we cannot read is left alone
                continue
            if self._link_stylesheet(root, resource.path, sheet_path):
                resource.data = xhtml.serialize(root)
                linked += 1

        if not linked:
            book.remove(sheet_path)
            return

        self.note(
            ctx,
            Level.INFO,
            f"added {compat.COMPAT_STYLESHEET_NAME} to {linked} document(s)",
            rule="compat.stylesheet-added",
            values={"stylesheet": compat.COMPAT_STYLESHEET_NAME, "count": linked},
            detail=(
                "Declares the HTML5 sectioning elements as blocks. It is linked "
                "ahead of the book's own stylesheets, so every rule the publisher "
                "wrote still overrides it."
            ),
            location=sheet_path,
        )

    def _link_stylesheet(self, root, document_path: str, sheet_path: str) -> bool:
        head = root.find(xhtml.qname("head"))
        if head is None:
            return False
        href = paths.relative(document_path, sheet_path)

        for existing in head.iterfind(xhtml.qname("link")):
            if existing.get("href") == href:
                return False

        link = root.makeelement(xhtml.qname("link"), {})
        link.set("rel", "stylesheet")
        link.set("type", "text/css")
        link.set("href", href)

        # Ahead of the book's own sheets: same specificity, so whichever comes
        # last wins, and that must be the publisher's.
        first_sheet = next(
            (
                child
                for child in head
                if xhtml.local_name(child) == "link"
                and (child.get("rel") or "").lower() == "stylesheet"
            ),
            None,
        )
        if first_sheet is not None:
            first_sheet.addprevious(link)
        else:
            head.append(link)
        return True

    # ------------------------------------------------------------ page breaks
    def _page_breaks(self, ctx: Context) -> None:
        mirrored = 0
        touched: list[str] = []
        for resource in ctx.book.by_type("style"):
            text = resource.text()
            rewritten, count = self._mirror_breaks(text)
            if count:
                resource.data = rewritten.encode("utf-8")
                mirrored += count
                touched.append(resource.path)
        if not mirrored:
            return
        self.note(
            ctx,
            Level.INFO,
            f"mirrored {mirrored} fragmentation declaration(s) into page-break-* form",
            rule="compat.page-break-mirrored",
            values={"count": mirrored},
            detail=(
                "The modern break-* properties are left exactly as they are; the "
                "legacy spelling is added beside them for renderers that only know "
                "that one."
            ),
            location=touched[0] if len(touched) == 1 else None,
        )

    def _mirror_breaks(self, css_text: str) -> tuple[str, int]:
        total = 0

        def rewrite_block(match: re.Match) -> str:
            nonlocal total
            body = match.group(1)
            additions: list[str] = []
            lowered = body.lower()

            for declaration in _BREAK_DECLARATION_RE.finditer(body):
                axis = declaration.group(3).lower()
                value = declaration.group(4).strip().rstrip(";").lower()
                # A value the legacy property never had (column, region, a
                # multi-value form) has no faithful translation; leave it.
                legacy = _BREAK_TO_PAGE_BREAK.get(value)
                if legacy is None:
                    continue
                if axis == "inside" and legacy not in _INSIDE_VALUES:
                    continue
                property_name = f"page-break-{axis}"
                if f"{property_name}:" in lowered.replace(" ", ""):
                    continue
                additions.append(f"{property_name}: {legacy}")

            if not additions:
                return match.group(0)
            total += len(additions)
            # Inserted *before* the modern declarations, never after. The two
            # spellings are aliases in a current renderer, so whichever comes
            # last wins there — and that has to be the one the publisher wrote,
            # not our translation of it. Legacy renderers ignore break-* and see
            # only what we added, which is the whole point.
            return "{" + " ".join(f"{addition};" for addition in additions) + body + "}"

        return _DECLARATION_BLOCK_RE.sub(rewrite_block, css_text), total

    # ----------------------------------------------------------- apple fonts
    def _apple_fonts(self, ctx: Context) -> None:
        if not ctx.book.by_type("font"):
            self.note(
                ctx,
                Level.INFO,
                "skipped the Apple specified-fonts declaration: this book embeds no fonts", rule="compat.specified-fonts-skipped",
                detail="Declaring it anyway would state something the book does not do.",
            )
            return
        ctx.book.container_files[compat.APPLE_DISPLAY_OPTIONS_PATH] = (
            compat.APPLE_DISPLAY_OPTIONS.encode("utf-8")
        )
        self.note(
            ctx,
            Level.INFO,
            "declared specified-fonts for Apple Books", rule="compat.specified-fonts-added",
            detail=(
                "Without this file Apple Books ignores every embedded face and "
                "substitutes its own."
            ),
            location=compat.APPLE_DISPLAY_OPTIONS_PATH,
        )

    # ----------------------------------------------------------------- guide
    def _guide(self, ctx: Context) -> None:
        if not compat.guide_references(ctx.book):
            self.note(
                ctx,
                Level.INFO,
                "skipped the legacy <guide>: nothing in the book maps onto it", rule="compat.guide-skipped",
            )
            return
        ctx.book.compat.add("guide")
        self.note(
            ctx,
            Level.PRESERVED,
            "added the EPUB 2 <guide> element for readers that look for it", rule="compat.guide-added",
            detail=(
                "EPUB 3.3 no longer defines this element, though EPUBCheck still "
                "accepts it: the output stays valid, but it carries something the "
                "current specification dropped. Amazon's converter and RMSDK readers "
                "find the cover and the start-reading position here and nowhere else."
            ),
        )

    # -------------------------------------------------------- kindle advice
    def _kindle_cover_advice(self, ctx: Context) -> None:
        """Report, do not rewrite: an SVG cover wrapper is a layout decision."""
        book = ctx.book
        cover_page = next(
            (l.target.split("#")[0] for l in book.landmarks if l.epub_type == "cover"), None
        )
        resource = book.get(cover_page) if cover_page else None
        if resource is None or not resource.is_content_doc:
            return
        text = resource.text()
        if "<svg" not in text.lower():
            return
        self.note(
            ctx,
            Level.WARN,
            "the cover page wraps its image in SVG, which Amazon's converter handles poorly", rule="compat.svg-cover",
            detail=(
                "The wrapper is what scales the artwork to the page, so removing it "
                "would change the layout on every other reader. Left as it is; "
                "replace it with a plain <img> by hand if the Kindle cover comes out "
                "wrong."
            ),
            location=resource.path,
        )
