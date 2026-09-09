"""PDF → EPUB: a module of this program, not a part of its repair core.

**One program, one name.** EPUB F.O.R.G.E. repairs EPUBs; this reads a PDF that
has a text layer and makes an EPUB of it, so that everything the repair core
does — the stages, the balance, K1, the validator, the publication gates, the
writer — can then be done to it exactly as to any other book. That is the whole
of the relationship, and it points one way: this module knows the core, the
core does not know this module.

D-056 (owner, 2026-09-08). Before it the converter was plugged into the core by
hand in eight places, its stage stood first in the list every EPUB went through,
and its settings showed in the window of a person who had dropped no PDF on it.
Nothing about the *behaviour* was wrong — an EPUB rebuilt with these settings
changed came out byte for byte the same, and that was measured before the
refactor — but the arrangement said something untrue about what this program is.

Everything the core needs is declared once, in `install()`, through
`epubforge.sources`. The only line in the core that names this module is the
call to `install()` in the package's assembly point, which is what an assembly
point is for.
"""

from __future__ import annotations

from .settings import LAYOUTS, RUNNING_HEADS, PdfSettings

__all__ = ["PdfSettings", "LAYOUTS", "RUNNING_HEADS", "install", "installed"]

_INSTALLED = False


def installed() -> bool:
    """Whether `install()` has run. For the tests that hold the wiring to its
    word — a module that silently failed to register would simply mean every
    PDF was read as a broken EPUB."""
    return _INSTALLED


def install() -> None:
    """Register the converter with the core, and its report lines with the
    catalogue. Idempotent, and cheap: nothing here opens a file, and
    `pdfminer` is imported by the reader only when it actually reads."""
    global _INSTALLED

    from .. import sources
    from . import rules
    from .gate import (characters_survive, instead_of_rebuilding,
                       note_prose_check, note_second_opinion, render_gate)
    from .stage import PdfStage

    rules.install()
    sources.register(sources.Importer(
        name="pdf",
        handles=reads,
        read=_read,
        book_version="pdf",
        source_text=text_of,
        second_opinion=characters_survive,
        render_gate=render_gate,
        note_prose_check=note_prose_check,
        note_second_opinion=note_second_opinion,
        instead_of_rebuilding=instead_of_rebuilding,
        # First, because it removes text on a person's word before any stage
        # reads the prose. Declared here so a reader of `sources.py` can see
        # what this source brings; the list a run actually uses is composed by
        # this module's own service (D-057).
        stages=(PdfStage,),
        # A running head or a page number a PDF brought along, removed on a
        # person's word (0.5, D-052): text the source had and the book should
        # not. K1 forgives it by name, as it forgives every removal somebody
        # consented to.
        removes_text_on_purpose=frozenset({"pdf.running-heads-removed"}),
    ))
    _INSTALLED = True


def reads(source: str) -> bool:
    """Whether this module reads *source*."""
    from . import reader

    return reader.is_pdf(source)


def text_of(source: str) -> str:
    """The whole text layer, in the order this module reads it — the left side
    of K1 for a PDF."""
    from . import reader

    return reader.text_of(source)


def _read(source: str, report, budget, policy):
    """The core hands over the whole policy; only this module reads the part of
    it that is the converter's."""
    from .reader import read_pdf

    return read_pdf(source, report, budget, policy.pdf.layout)
