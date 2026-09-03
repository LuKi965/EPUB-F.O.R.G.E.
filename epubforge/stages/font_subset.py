"""Cut embedded fonts down to the characters the book actually uses.

Filar E of the 0.4 plan, and the measurement that opened it: 62 books of the
owner's 160 carry 491 font files weighing **116 MB**, and the heaviest of them
spends 11.05 MB on roughly a hundred distinct characters. Cut to what it
draws, that font came to 0.33 MB — three per cent.

Three things decide the shape of this stage, and each of them is a refusal
rather than a feature.

**It is off until somebody turns it on.** `fsType` says what may be
*embedded*; the right to *modify* a font lives in a text licence that no bit
in the file carries. Nobody but the owner of the book can weigh that, so the
program does not weigh it for them (`Policy.subset_fonts`, and the report
carries the weights either way).

**It runs last.** The glyph set has to be read from the *finished* book, not
the source: the navigation document this program generates carries labels
that were not in the source, the cover page it synthesises carries the title,
and a font cut to the source's characters would lose exactly the glyphs the
rebuild had just added. So this stage sits at the end of the pipeline and
reads what is there by then.

**Anything it cannot prove, it leaves alone.** A font whose licence bits it
cannot read, a font that says no subsetting, a book that arrived obfuscated,
a subset that came out no smaller, a subset the font library refused — every
one of those keeps the original bytes and earns a line in the report. The
alternative is a book that opens with squares where its accented letters
were, which is the plainest form of the damage S-03 names.
"""

from __future__ import annotations

import io

from .. import fonts_meta
from ..report import Action, Automation, Level, Risk
from .base import Context, Stage

#: Suffixes this stage will consider. `woff2` is deliberately absent: its
#: Brotli round trip is a second thing to go wrong for a format the shelf's
#: measurement never saw, and a stage that cannot say what it did to a file
#: has no business rewriting it.
SUBSETTABLE = (".ttf", ".otf")

#: Characters kept in every subset regardless of whether the book's text
#: happens to contain them. A space that fails to render is a word join, and
#: the two joiners are invisible in the text yet load-bearing where they
#: appear — none of the three is worth the risk of leaving out.
ALWAYS_KEPT = "  ​‍⁠\n"


def _characters(ctx: Context) -> "set[str]":
    """Every character the finished book can put on a page.

    Deliberately generous, and read out of the documents as *text* rather
    than as markup: an attribute value is not drawn, but `content: "→"` in a
    stylesheet is, so the stylesheets go in whole. Over-keeping costs bytes;
    under-keeping costs a glyph, and those are not comparable.
    """
    seen: "set[str]" = set(ALWAYS_KEPT)
    for resource in ctx.book.resources.values():
        if resource.is_content_doc:
            try:
                # `ctx.parsed` hands back a `ParseResult`, not a tree — the
                # root element is one field of it.
                root = ctx.parsed(resource).root
            except Exception:  # noqa: BLE001 — an unparsable document still has text
                root = None
            if root is not None:
                for element in root.iter():
                    if isinstance(element.tag, str):
                        seen.update(element.text or "")
                        seen.update(element.tail or "")
                continue
        if resource.is_content_doc or resource.media_type == "text/css":
            # The fallback for a document that would not parse, and the whole
            # of the treatment for a stylesheet: every character in the file.
            # Coarse on purpose — a stylesheet is small and a missing arrow
            # from `content:` is a hole in the page.
            try:
                seen.update(resource.data.decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                continue
    return seen


def _subset(data: bytes, characters: "set[str]") -> "tuple[bytes, set[str]] | None":
    """The font cut to *characters*, and the tables that did not survive.

    The dropped tables are returned rather than swallowed. `fontTools` says
    on its own logger which ones it could not carry — on the shelf that is
    FontForge's `FFTM` and Apple's `feat`, `morx` and `Silt` — and those are
    not nothing: `feat` and `morx` are Apple Advanced Typography, so a
    reading system that uses them would lose whatever they did. Which of the
    owner's readers use them is unmeasured, and the honest place for an
    unmeasured consequence is the report rather than a docstring.
    """
    try:
        from fontTools import subset as fontsubset
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    # `fontTools` talks on several loggers at once and one of them fires per
    # coverage table: on the shelf's heaviest books that is eighty lines of
    # "Coverage is not sorted by glyph ids" for two books. Quieted across the
    # whole operation — load, subset and save — because this stage reports the
    # same facts itself, in the report, in the reader's language, and because
    # a hundred and sixty books' worth on a console is not a message, it is
    # weather. Nothing is hidden by it: every failure comes back as `None`
    # from the `except` below and is counted and reported as a refusal.
    import logging

    root = logging.getLogger("fontTools")
    was = root.level
    root.setLevel(logging.ERROR)
    try:
        return _cut(data, characters, fontsubset, TTFont)
    except Exception:  # noqa: BLE001 — a font library that refuses is an answer
        return None
    finally:
        root.setLevel(was)


def _cut(data: bytes, characters: "set[str]", fontsubset, TTFont):
    """The cut itself, with the noise already turned down by the caller."""
    font = TTFont(io.BytesIO(data), fontNumber=0, lazy=False)
    had = set(font.keys())
    options = fontsubset.Options()
    # Layout features stay: a book that uses ligatures or small caps is
    # relying on them, and dropping them changes how the page looks while
    # the text stays identical — the exact damage the appearance gate
    # exists to catch, done deliberately.
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    # `--drop-tables` defaults already shed the exotic tables the shelf
    # measurement saw warnings about (FontForge's FFTM, Apple's feat and
    # morx). Named here so the choice is visible rather than inherited.
    subsetter = fontsubset.Subsetter(options=options)
    subsetter.populate(text="".join(sorted(characters)))
    subsetter.subset(font)
    out = io.BytesIO()
    font.save(out)
    return out.getvalue(), had - set(font.keys())


class FontSubsetStage(Stage):
    """Runs last, and only when asked."""

    name = "fonts"

    def run(self, ctx: Context) -> None:
        if not ctx.policy.subset_fonts:
            return
        book = ctx.book
        if book.encrypted:
            # An obfuscated book keeps its fonts byte for byte. The shelf has
            # none, so this is untested against a real one — which is the
            # reason to refuse rather than the reason to try.
            self.note(ctx, Level.PRESERVED, "font.subset-skipped-obfuscated")
            return

        characters = _characters(ctx)
        before = after = 0
        cut = 0
        refused: dict[str, int] = {}
        dropped: set[str] = set()
        for path, resource in list(book.resources.items()):
            if not path.lower().endswith(SUBSETTABLE):
                continue
            allowed, reason = fonts_meta.may_be_subset(resource.data)
            if not allowed:
                refused[reason] = refused.get(reason, 0) + 1
                continue
            outcome = _subset(resource.data, characters)
            if outcome is None:
                refused["failed"] = refused.get("failed", 0) + 1
                continue
            trimmed, lost_tables = outcome
            dropped.update(lost_tables)
            if len(trimmed) >= len(resource.data):
                # Nothing gained, and a rewritten file is a changed file.
                refused["no-gain"] = refused.get("no-gain", 0) + 1
                continue
            # Read before the swap: `resource.data` is the new bytes the
            # moment it is assigned, and a ledger whose "before" is the
            # "after" would report every cut as having saved nothing.
            was = len(resource.data)
            before += was
            after += len(trimmed)
            cut += 1
            resource.data = trimmed
            self.changed(
                ctx,
                Action.REPLACED,
                path,
                before=_kib(was),
                after=_kib(len(trimmed)),
                automation=Automation.ASKED,
                risk=Risk.APPEARANCE,
                reversible=False,
                rule="font.subset",
            )
        if cut:
            self.note(
                ctx,
                Level.FIX,
                "font.subset",
                values={
                    "count": cut,
                    "before": _kib(before),
                    "after": _kib(after),
                    "saved": _kib(before - after),
                },
            )
        if dropped:
            # Named, not counted: "three tables" tells nobody anything, and
            # the actual four-letter tags tell a person who knows fonts a
            # great deal — including which of their readers might care.
            self.note(
                ctx,
                Level.INFO,
                "font.subset-tables-dropped",
                values={"names": ", ".join(sorted(dropped))},
            )
        # Spelled out one by one, and the invariant that caught the first two
        # attempts is right both times: neither an f-string nor a lookup is a
        # literal, and an identifier no search of this codebase can find is
        # one that can quietly leave the catalogue (`test_rules.py`).
        if refused.get("restricted"):
            self.note(ctx, Level.PRESERVED, "font.subset-refused-restricted",
                      values={"count": refused["restricted"]})
        if refused.get("preview-print"):
            self.note(ctx, Level.PRESERVED, "font.subset-refused-preview-print",
                      values={"count": refused["preview-print"]})
        if refused.get("no-subsetting"):
            self.note(ctx, Level.PRESERVED, "font.subset-refused-no-subsetting",
                      values={"count": refused["no-subsetting"]})
        if refused.get("unreadable"):
            self.note(ctx, Level.PRESERVED, "font.subset-refused-unreadable",
                      values={"count": refused["unreadable"]})
        if refused.get("failed"):
            self.note(ctx, Level.PRESERVED, "font.subset-refused-failed",
                      values={"count": refused["failed"]})
        if refused.get("no-gain"):
            self.note(ctx, Level.PRESERVED, "font.subset-refused-no-gain",
                      values={"count": refused["no-gain"]})


def _kib(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    return f"{size / 1024:.0f} KB"
