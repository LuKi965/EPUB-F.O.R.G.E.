"""The measuring stage: reads the book, reports what it is, changes nothing.

Placed between metadata and content, and neither side is arbitrary. Earlier is
impossible because paths are only frozen once `StructureStage` has run, so a
stylesheet could not be found from the document that links it. Later is
pointless because `ContentStage` has by then rewritten the very markup the
profile is supposed to describe — it would be measuring our output and calling
it the book.

**This stage may not modify the model.** `docs/ROADMAP.md` calls that a
condition rather than a convention, and `tests/test_profile.py` holds it to a
byte-for-byte comparison of every resource before and after.
"""

from __future__ import annotations

from .. import fingerprint
from .. import typography
from .. import profile as book_profile
from .. import xhtml
from ..report import Level
from .base import Context, Stage


class ProfileStage(Stage):
    """Measures the book's shape and puts it in the report."""

    name = "profile"

    def run(self, ctx: Context) -> None:
        documents = []
        for resource in ctx.book.content_docs():
            try:
                documents.append(xhtml.parse_document(resource.data).root)
            except Exception:  # noqa: BLE001 — the content stage reports this
                continue
        if not documents:
            return

        css = "\n".join(sheet.text() for sheet in ctx.book.by_type("style"))
        profile = book_profile.measure(documents, css)
        ctx.profile = profile
        self._fingerprint(ctx, css)
        self._language(ctx, documents)
        self._report(ctx, profile)

    #: Characters of the book's own text below which the language rate says
    #: nothing. A page of prose is about two thousand.
    ENOUGH_TEXT = 500

    def _book_text(self, ctx: Context) -> str:
        """The book's text, excluding anything this tool wrote.

        The navigation document is skipped whether it came with the book or was
        generated here, because in the generated case its headings are ours and
        in the supplied case they are chapter titles rather than prose. The
        corpus signature draws the same line for the same reason.
        """
        from .. import xhtml

        parts = []
        for resource in ctx.book.content_docs():
            if resource.path == ctx.book.nav_path:
                continue
            try:
                root = xhtml.parse_document(resource.data).root
            except Exception:  # noqa: BLE001 — reported by the content stage
                continue
            parts.append("".join(root.itertext()))
        return "".join(parts)

    def _language(self, ctx: Context, documents) -> None:
        """Check the declared language against the text, because K11.

        A real library said this was worth doing: 2 187 books declaring `en`, of
        which 1 815 carry `„` — a mark English typesetting does not use at all.
        Calibre had left `dc:language` at its default and nothing had ever
        looked.

        It is not a typographic nicety. A reading system speaks `dc:language` to
        its text-to-speech engine and hyphenates by it, so a Polish book
        declaring English is read aloud in an English voice and broken across
        lines by English rules. Both are things a reader notices immediately and
        no validator mentions.

        Reported, never corrected. The tool does not know what the language *is*
        — it knows the declared one is contradicted by the text — and rewriting
        metadata on an inference is the kind of help nobody asked for. The
        person holding the book can pass `--language`.
        """
        declared = (ctx.book.metadata.language or "").strip().lower()
        if not declared or declared.startswith("pl"):
            return
        text = self._book_text(ctx)
        # Below this a rate is arithmetic, not evidence. The first version had
        # no floor and no exclusion, and fired on a Japanese manga: the only
        # document short enough to swing the average was the navigation page
        # *this tool had just generated*, whose title is "Spis treści" in a
        # Polish report — one `ś` in seventeen characters. Measuring our own
        # output and calling it the book is the mistake this stage's own
        # docstring warns about, and it took one fixture to make it.
        if len(text) < self.ENOUGH_TEXT:
            return
        share = typography.polish_share(text)
        if share < typography.POLISH_FLOOR:
            return
        self.note(
            ctx,
            Level.WARN,
            "profile.language-contradicted",
            values={"declared": declared, "rate": round(share, 1)},
        )

    def _fingerprint(self, ctx: Context, css: str) -> None:
        """Which tools made this book, most confident first.

        Reported rather than acted on. Nothing in the pipeline changes its mind
        because of it yet — roadmap [7] is where it starts to, since the care a
        paragraph deserves depends on whether it came out of InDesign or out of
        an OCR pass. Until then it is a fact about the book the report can state
        and a person can read, which is the same standing as everything else
        this stage produces.

        The package document is passed separately from the markup, because half
        of what a trace is worth is where it turned up: `<meta name="generator">`
        is a program saying its own name, and the same word in a chapter is
        prose. The reader keeps the source package for exactly this.
        """
        markup = "\n".join(
            resource.data.decode("utf-8", "replace")
            for resource in ctx.book.content_docs()
        )
        package = (ctx.book.source_package or b"").decode("utf-8", "replace")
        traces = fingerprint.identify(package=package, markup=markup, css=css)
        ctx.fingerprint = traces
        if not traces:
            return
        self.note(
            ctx,
            Level.INFO,
            "profile.made-by",
            values={"tools": fingerprint.describe(traces), "count": len(traces)},
            detail="; ".join(
                f"{trace.name}: {', '.join(trace.evidence)}"
                for trace in traces
                if trace.evidence
            )
            or None,
        )

    def _report(self, ctx: Context, profile) -> None:
        body = profile.body
        if body.consistent:
            self.note(
                ctx,
                Level.INFO,
                "profile.body-text-found",
                values={
                    "shape": ".".join(x for x in body.shape if x) or body.shape[0],
                    "percent": round(100 * body.share),
                    "blocks": body.blocks,
                },
            )
        elif body.blocks:
            # The number is kept rather than rounded away to "none". How far off
            # a book was from having a shape is the useful part, and a rule that
            # later declines to fire wants to say why.
            self.note(
                ctx,
                Level.INFO,
                "profile.body-text-inconsistent",
                values={"percent": round(100 * body.share), "blocks": body.blocks},
            )

        paradigm = profile.paragraphs.paradigm
        if paradigm == "MIXED":
            # Worth reporting from the first version because it costs nothing
            # and says a lot: a book from one source does not mix indented
            # paragraphs with spaced ones. When it does, somebody glued two
            # files together or ran one through two tools — which is exactly
            # what the fingerprint in point [6] will want to know.
            self.note(
                ctx,
                Level.INFO,
                "profile.paragraphs-mixed",
                values={
                    "indented": profile.paragraphs.indented,
                    "spaced": profile.paragraphs.spaced,
                },
            )
        elif paradigm != "UNKNOWN":
            self.note(
                ctx,
                Level.INFO,
                "profile.paragraphs-consistent",
                values={"paradigm": paradigm.lower()},
            )

        if len(profile.dead_classes) >= book_profile.INTENT_OCCURRENCES:
            self.note(
                ctx,
                Level.INFO,
                "profile.dead-classes-found",
                values={"count": len(profile.dead_classes)},
            )
        if profile.duplicate_classes:
            self.note(
                ctx,
                Level.INFO,
                "profile.duplicate-classes-found",
                values={
                    "groups": len(profile.duplicate_classes),
                    "names": sum(len(g) for g in profile.duplicate_classes),
                },
            )
        # Written out rather than looped. A rule id has to be a literal at the
        # call site — `tests/test_rules.py` enforces it — because the id is how
        # anybody finds the code that raises a finding, and a loop over a table
        # of them makes the whole set invisible to a search. It cost three lines
        # and caught itself the first time this ran.
        enough = book_profile.INTENT_OCCURRENCES
        if profile.separators >= enough:
            self.note(
                ctx,
                Level.INFO,
                "profile.scene-separators-found",
                values={"count": profile.separators},
            )
        if profile.break_runs >= enough:
            self.note(
                ctx,
                Level.INFO,
                "profile.break-runs-found",
                values={"count": profile.break_runs},
            )
        if profile.heading_candidates >= enough:
            self.note(
                ctx,
                Level.INFO,
                "profile.heading-candidates-found",
                values={"count": profile.heading_candidates},
            )
