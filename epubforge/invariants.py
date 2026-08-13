"""What has to be true of a book before it is allowed to become a file.

The audit's F-006, second half. 0.2.20 closed the read side: a source that
cannot be read in full stops the rebuild before any stage runs. The write side
had nothing. The archive verifier in `writer.py` reads entry order, the mimetype
and CRCs — properties of a ZIP — and had no opinion about whether the *book*
made sense. So a stage could leave a spine entry pointing at a document that no
longer exists, the archive would be technically perfect, and it would be
published atomically.

**Scope, and why it is narrower than "everything must resolve".**

Only things this program builds are checked. The spine, the manifest, the
navigation, the fallback chains and the package document are ours: we assembled
them, and if one of them points at nothing then we made that mistake this run.
A dangling link *inside a content document* is a different animal — it is
usually the source's own, `preserve` keeps it on purpose, and the report already
says so by name (`xhtml.dead-reference-kept`). Making that fatal would refuse a
large fraction of real books for a defect they arrived with, which is the
failure mode of the first draft of the read-side gate, repeated.

So: everything the rebuild is responsible for must be true, and everything the
book arrived with is reported rather than refused. That line is arguable and it
is drawn here rather than left implicit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Book


@dataclass(frozen=True)
class Violation:
    """One thing that is not true, in words a person can act on."""

    rule: str
    detail: str
    location: str = ""

    def __str__(self) -> str:
        where = f" ({self.location})" if self.location else ""
        return f"{self.detail}{where}"


def check(book: Book) -> list[Violation]:
    """Everything wrong with *book* that must stop it becoming a file."""
    found: list[Violation] = []
    found += _spine_resolves(book)
    found += _navigation_resolves(book)
    found += _fallbacks_resolve(book)
    found += _cover_resolves(book)
    return found


def _spine_resolves(book: Book) -> list[Violation]:
    """Every reading-order entry is a document this archive will hold.

    The audit's own example of a book that validates and is broken: a stage
    repairs part of a publication and leaves a spine entry naming a document it
    removed. The writer noticed and *reported* it, then carried on — `writer.py`
    logs a missing spine item and keeps going, which is the same fail-open shape
    as the reader's skipped entry.
    """
    found = []
    seen: set[str] = set()
    for item in book.spine:
        if item.path not in book.resources:
            found.append(Violation(
                "invariant.spine-target-missing",
                f"the reading order names {item.path}, which is not in the book",
                item.path,
            ))
        elif item.path in seen:
            # Two `itemref`s for one document is not merely untidy: a reading
            # system paginates it twice and the same page has two positions.
            found.append(Violation(
                "invariant.spine-duplicated",
                f"{item.path} appears in the reading order more than once",
                item.path,
            ))
        seen.add(item.path)
    if not book.spine:
        found.append(Violation(
            "invariant.spine-empty",
            "the reading order is empty, so there is nothing to open the book at",
        ))
    return found


def _navigation_resolves(book: Book) -> list[Violation]:
    """The navigation this program generated points at documents that exist.

    Generated rather than carried, which is what makes it ours to be right
    about. A table of contents leading nowhere is the defect a reader meets
    first and the one that makes a book feel broken.
    """
    found = []
    if book.nav_path and book.nav_path not in book.resources:
        found.append(Violation(
            "invariant.nav-missing",
            f"the navigation document {book.nav_path} is not in the book",
            book.nav_path,
        ))
    for root in book.toc:
        for node in root.walk():
            target = node.target_path
            if target and target not in book.resources:
                found.append(Violation(
                    "invariant.nav-target-missing",
                    f"a contents entry leads to {target}, which is not in the book",
                    target,
                ))
    for landmark in book.landmarks:
        target = (landmark.target or "").split("#")[0]
        if target and target not in book.resources:
            found.append(Violation(
                "invariant.landmark-target-missing",
                f"the {landmark.epub_type} landmark leads to {target}, which is not in the book",
                target,
            ))
    return found


def _fallbacks_resolve(book: Book) -> list[Violation]:
    """A fallback chain ends, and ends somewhere real.

    A cycle is the interesting half. `a` falls back to `b` and `b` to `a` is a
    manifest a reading system can follow until it stops being a reading system,
    and nothing in the model prevented one being written.
    """
    found = []
    for path, resource in book.resources.items():
        target = getattr(resource, "fallback", None)
        if not target:
            continue
        seen = {path}
        while target:
            if target in seen:
                found.append(Violation(
                    "invariant.fallback-cycle",
                    f"the fallback chain starting at {path} comes back to {target}",
                    path,
                ))
                break
            if target not in book.resources:
                found.append(Violation(
                    "invariant.fallback-missing",
                    f"{path} falls back to {target}, which is not in the book",
                    path,
                ))
                break
            seen.add(target)
            target = getattr(book.resources[target], "fallback", None)
    return found


def _cover_resolves(book: Book) -> list[Violation]:
    found = []
    if book.cover_path and book.cover_path not in book.resources:
        found.append(Violation(
            "invariant.cover-missing",
            f"the cover image {book.cover_path} is not in the book",
            book.cover_path,
        ))
    return found
