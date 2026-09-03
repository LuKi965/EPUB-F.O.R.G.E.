"""The Kobo export, last of all and only when asked for.

Runs after every other stage on purpose: everything before it reasons about
the book as a book, and this rewrites every text node into the shape one
renderer wants. Off, it does nothing at all, and the pipeline is exactly what
it was — the same rule the compatibility stage lives by, for the same reason.
"""

from __future__ import annotations

import os

from .. import kepub, xhtml
from ..report import Action, Level
from .base import Context, Stage


class KepubStage(Stage):
    name = "kepub"

    def run(self, ctx: Context) -> None:
        if not ctx.policy.kepub:
            return

        # The renderer is chosen by the file name. A person who asked for the
        # Kobo markers and named the file `.epub` gets a plain EPUB with spans
        # in it, and is told so before the file is written.
        output = ctx.report.output or ""
        if output and not output.lower().endswith(kepub.EXTENSION):
            self.note(
                ctx, Level.WARN, "kepub.name",
                values={"name": os.path.basename(output), "extension": kepub.EXTENSION},
                location=output,
            )

        documents = spans = images = already = 0
        for resource in ctx.book.content_docs():
            try:
                root = ctx.take(resource).root
            except Exception:  # noqa: BLE001 — a document we cannot read is left alone
                continue
            if root is None:
                continue
            marking = kepub.mark(root)
            if marking.already:
                already += 1
            if marking.changed:
                resource.data = xhtml.serialize(root)
                documents += 1
                spans += marking.spans
                images += marking.images

        if already:
            self.note(ctx, Level.INFO, "kepub.already-marked", values={"count": already})
        if documents:
            self.note(
                ctx, Level.FIX, "kepub.marked",
                values={"docs": documents, "spans": spans, "images": images},
            )
            self.changed(
                ctx, Action.ADDED, "kobo-markers",
                before=f"{documents} document(s) as the book had them",
                after=(
                    f"{spans} sentence span(s) and {images} image span(s) "
                    f"inside div#{kepub.INNER_ID}, with Kobo's style block"
                ),
                rule="kepub.marked",
            )

        is_cover, first_page = kepub.first_page_reads_as_a_cover(ctx.book)
        if not is_cover and first_page:
            self.note(
                ctx, Level.INFO, "kepub.first-page-not-a-cover",
                values={"name": os.path.basename(first_page)},
                location=first_page,
            )
