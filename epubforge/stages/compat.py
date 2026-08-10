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
                "compat.unknown-profile",
                values={"profile": name, "known": ", ".join(sorted(compat.PROFILES))},
            )
        if not measures:
            return

        self.note(
            ctx,
            Level.INFO,
            "compat.applied",
            values={"profiles": ", ".join(sorted(ctx.policy.compat_profiles))},
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
        if "legacy-font-types" in measures:
            self._legacy_font_types(ctx)

        if "kindle" in ctx.policy.compat_profiles:
            self._kindle_cover_advice(ctx)

    #: What a font was called before RFC 8081 registered the `font/*` tree.
    #: Adobe RMSDK predates it and knows only these; EPUB 3.3 lists them as
    #: legacy types a reading system must still accept, so declaring one is a
    #: concession rather than an error.
    LEGACY_FONT_TYPES = {
        "font/ttf": "application/x-font-truetype",
        "font/otf": "application/vnd.ms-opentype",
        "font/sfnt": "application/font-sfnt",
    }

    def _legacy_font_types(self, ctx: Context) -> None:
        """Declare embedded fonts by the name an RMSDK reader recognises.

        `font/ttf` is the EPUB 3.3 core media type and what this tool writes
        everywhere else. Calibre's book check flags it as inconsistent with the
        extension, which is Calibre guessing from an older table — that alone
        would not be worth a measure, since EPUBCheck accepts the current type
        without a word.

        What is worth it is the device behind that table: Adobe RMSDK shipped
        before RFC 8081 existed and looks the type up in a fixed list. A font
        declared by a name it does not know is a font it does not load, and the
        book falls back to the reader's own face on a device that has one bad
        one. So the owner's call — if EPUB 3 does not need it, it belongs in a
        backwards-compatibility profile — is right, and this is that profile.
        """
        changed = 0
        for resource in ctx.book.by_type("font"):
            legacy = self.LEGACY_FONT_TYPES.get((resource.media_type or "").lower())
            if legacy:
                resource.media_type = legacy
                changed += 1
        if changed:
            self.note(
                ctx,
                Level.PRESERVED,
                "compat.legacy-font-types",
                values={"count": changed},
            )

    # ------------------------------------------------------------------ ncx
    def _ncx(self, ctx: Context) -> None:
        """The NCX is a policy switch; a profile that needs it says so loudly."""
        if ctx.book.ncx_path:
            return
        self.note(ctx, Level.WARN, "compat.ncx-required")

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
            "compat.stylesheet-added",
            values={"stylesheet": compat.COMPAT_STYLESHEET_NAME, "count": linked},
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
            "compat.page-break-mirrored",
            values={"count": mirrored},
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
            self.note(ctx, Level.INFO, "compat.specified-fonts-skipped")
            return
        ctx.book.container_files[compat.APPLE_DISPLAY_OPTIONS_PATH] = (
            compat.APPLE_DISPLAY_OPTIONS.encode("utf-8")
        )
        self.note(
            ctx,
            Level.INFO,
            "compat.specified-fonts-added",
            location=compat.APPLE_DISPLAY_OPTIONS_PATH,
        )

    # ----------------------------------------------------------------- guide
    def _guide(self, ctx: Context) -> None:
        if not compat.guide_references(ctx.book):
            self.note(ctx, Level.INFO, "compat.guide-skipped")
            return
        ctx.book.compat.add("guide")
        self.note(ctx, Level.PRESERVED, "compat.guide-added")

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
        self.note(ctx, Level.WARN, "compat.svg-cover", location=resource.path)
