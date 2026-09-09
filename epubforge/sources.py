"""Sources that are not already books, and the seam they plug into.

This program repairs EPUBs. Everything it does *after* reading — the stages,
the balance, K1, the validator, the gates, the writer — is work on an EPUB,
whatever the file on disk was. Reading is the one place where a source that is
not an EPUB needs a program of its own.

So the core does not learn what those sources are. It asks this registry three
questions and never a fourth: **is there an importer for this file**, **what
does it read**, and **what does it want done differently in the gates** —
because a source with no package document has no version to state, no sibling
document to pair the output's prose against, and no pages to draw for a
before-and-after comparison.

D-056 (owner, 2026-09-08): *„program jest jeden i nazywa się EPUB FORGE. Ale
osobny moduł to na pewno, bo główny moduł FORGE służy do naprawiania EPUB i nie
należy w niego wmiksowywać konwerterów PDF."* Before it, `pipeline.py` carried
six `pdf.is_pdf(source)` branches and `fidelity.py` two, and `PdfStage` stood
first in the list every EPUB went through. The behaviour was already separate —
an EPUB rebuilt with the PDF settings changed came out byte for byte the same —
but the code was not, and the settings showed in the window of a person who had
dropped no PDF on it.

The one place in the core that knows a converter exists by name is the
package's assembly point (`epubforge/__init__.py`), which is what an assembly
point is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Importer:
    """A program that turns some other file into a :class:`Book`.

    Every field but the first three is a place where the core would otherwise
    have had to ask "and what if this was not an EPUB?". They are optional; an
    importer that fills none of them gets the ordinary treatment everywhere.
    """

    #: What this reads, for the report and for a person reading a traceback.
    name: str
    #: Whether *source* is a file this importer can read. Cheap: it is asked of
    #: every file the program is handed, before anything is opened.
    handles: Callable[[str], bool]
    #: `(source, report, budget, policy) -> Book`, or a refusal raised as
    #: `EpubReadError` / `BudgetExceeded` exactly as the EPUB reader raises it.
    read: Callable[..., object]
    #: The `Book.source_version` a book from this importer carries. The core
    #: uses it for one thing: not to report a package version that never was.
    book_version: str = ""
    #: The left side of K1 for this source — its whole text, in reading order.
    #: Without it K1 has nothing to hold the output against and says so.
    source_text: "Callable[[str], str] | None" = None
    #: A second opinion on K1, counted without going through the importer's own
    #: reader: `(source, candidate) -> fidelity.Check`. A reader that cannot see
    #: a construct is missing it from *both* sides of a subsequence test, which
    #: is how EF-087 passed a page whose only sentence was never converted.
    second_opinion: "Callable[[str, str], object] | None" = None
    #: The appearance check for a book from this source:
    #: `(candidate, policy, report, queue) -> str`. There is no *before* to
    #: draw, so the ordinary page-for-page comparison cannot run.
    render_gate: "Callable[..., str] | None" = None
    #: Says, into the report, what stands in for the document-for-document
    #: prose check — which needs a source document to pair each output document
    #: with, and an imported source has none. A callable rather than a rule
    #: name, because a rule identifier has to be a literal where it is raised
    #: or nobody can grep their way from a report line to the code.
    note_prose_check: "Callable[[object], None] | None" = None
    #: Says what the second opinion's refusal means and returns the refusal the
    #: gate should carry, or "" when the loss was consented to:
    #: `(report, check, consented) -> str`. The *decision* is the core's — it
    #: computes which named passes the person agreed to — and the *wording* is
    #: the importer's, for the same reason `note_prose_check` is.
    note_second_opinion: "Callable[..., str] | None" = None
    #: Stages this importer's own service puts in front of the core's. The
    #: core does not read this: the module composing a run says which stages it
    #: runs (D-057). It is declared here so that a reader of this file can see
    #: what a source brings with it without opening the module.
    stages: tuple = field(default_factory=tuple)
    #: Says, into the report, why the EPUB repair entry will not take this file
    #: and what to use instead: `(report) -> None`. A callable and not a rule
    #: name, for the reason `note_prose_check` is one — a rule identifier has
    #: to be a literal where it is raised or nobody can grep their way from a
    #: report line to the code.
    instead_of_rebuilding: "Callable[[object], None] | None" = None
    #: Rules of this importer's own that K1 forgives by name, on the same terms
    #: as the core's: a removal somebody consented to, said in the report.
    removes_text_on_purpose: frozenset = frozenset()


_REGISTERED: list[Importer] = []


def register(importer: Importer) -> None:
    """Add an importer. Registering the same name twice replaces it, so that
    importing a module twice cannot make the program read a file twice."""
    global _REGISTERED
    _REGISTERED = [known for known in _REGISTERED if known.name != importer.name]
    _REGISTERED.append(importer)


def registered() -> tuple:
    return tuple(_REGISTERED)


def for_source(source: str) -> "Importer | None":
    """The importer that reads *source*, or `None` — which means "an EPUB",
    because that is what this program is for and what it assumes."""
    # Deliberately not guarded: `handles` is a name test, and an importer whose
    # name test raises is a defect that should be seen rather than swallowed
    # into "this must be an EPUB then".
    for importer in _REGISTERED:
        if importer.handles(str(source)):
            return importer
    return None


def imported_versions() -> frozenset:
    """The `source_version` values that mean "this did not come from a package"."""
    return frozenset(imp.book_version for imp in _REGISTERED if imp.book_version)
