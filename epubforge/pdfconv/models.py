"""What a conversion is asked for and what came of it.

A PDF is not a damaged EPUB. It is a document laid out in pages, and what this
module makes of it is a *new* publication — which is why the plan below is not
`RebuildPlan` with a flag, and the result is not a rebuild's `Result` with a
different word in it (D-057).

A leaf, like `settings.py`: nothing here imports the core, so the plan can be
built, copied and tested without a pipeline and without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .settings import PdfSettings

#: What to do when the file this conversion would write is already there.
#: `refuse` is the default and the only one that cannot lose somebody's work.
COLLISIONS = ("refuse", "overwrite", "beside")


@dataclass
class PdfDocumentInfo:
    """What is known about one PDF before converting it.

    Every field may honestly be "not established". A preflight that guesses is
    worse than one that says it did not look: `pages = 0` and `has_text = None`
    mean *not checked*, and the screen says so in those words rather than
    printing a confident zero.
    """

    source: Path
    size: int = 0
    #: Pages, when the reader has said. 0 means nobody has asked yet.
    pages: int = 0
    #: Whether a text layer was found. `None` means not checked — never `False`
    #: on the strength of not having looked.
    has_text: "bool | None" = None
    title: str = ""
    #: Why this document cannot be converted, in the person's language.
    refusal: str = ""

    @property
    def checked(self) -> bool:
        return self.has_text is not None

    @property
    def needs_ocr(self) -> bool:
        """A scan with no text layer. This version of the converter says so and
        converts nothing — there is no OCR here and there is not going to be
        one in this iteration (03-PDF-MODULE §2)."""
        return self.has_text is False


@dataclass
class PdfConversionPlan:
    """One conversion, as the person asked for it.

    Deliberately *not* every field of `Policy`: the converter's settings are
    the converter's, and a plan that carried the repair tool's forty options
    would be the same object wearing a different name.
    """

    sources: tuple[Path, ...]
    destination: "Path | None" = None
    settings: PdfSettings = field(default_factory=PdfSettings)
    #: What to do if the output name is taken.
    collision: str = "refuse"
    #: The two publication gates, which belong to the shared layer and not to
    #: the conversion. The defaults are the preset's own — including D-016,
    #: *without a way to check the appearance, nothing is written* — and they
    #: are on the plan because a person facing that refusal has to be able to
    #: answer it.
    validate: str = "off"
    render_gate: str = "stop"
    #: Whose conversion this is; it travels to the result and back so a job
    #: finishing after the person started another cannot write into the new one.
    session_id: str = ""
    #: Whether a question may interrupt. A batch nobody is watching answers
    #: nothing and changes nothing it cannot justify.
    ask: bool = True


@dataclass
class PdfConversionResult:
    """What became of one document.

    Three things kept apart on purpose, because a green EPUBCheck is not proof
    of a faithful conversion and a character count is not proof of a sensible
    reading order (03-PDF-MODULE §2):

    - `text_checked` — the characters of the text layer were counted into the
      output;
    - `epub_validated` — EPUBCheck read the file that was written;
    - the appearance of the pages was **not** checked, ever, and nothing here
      will claim it was.
    """

    source: Path
    #: Files this document published. Empty is not a failure by itself — a
    #: refusal and a trial both publish nothing, and they are different things.
    published_outputs: tuple[Path, ...] = ()
    layout: str = "reflowable"
    #: What went wrong, when something did.
    error: str = ""
    #: Quality notes for the person: reading order, skipped drawings, a
    #: complicated layout. Warnings, not failures.
    warnings: tuple[str, ...] = ()
    text_checked: bool = False
    epub_validated: bool = False
    #: The technical report, rendered once.
    report_text: str = ""

    @property
    def published(self) -> bool:
        return bool(self.published_outputs)
