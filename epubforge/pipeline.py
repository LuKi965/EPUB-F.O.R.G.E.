"""Top-level rebuild orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .model import Book
from .policy import Policy
from .reader import EpubReadError, read_epub
from .report import Level, Report
from .stages import DEFAULT_STAGES, Context
from .writer import write_epub


@dataclass
class Result:
    report: Report
    book: Book | None
    output_path: str | None


def rebuild(source: str, destination: str, policy: Policy | None = None) -> Result:
    """Rebuild *source* into a conforming EPUB 3.3 at *destination*."""
    policy = policy or Policy()
    report = Report(source=source, output=destination)

    try:
        book = read_epub(source, report)
    except EpubReadError as exc:
        report.add("reader", Level.ERROR, f"could not read the source file: {exc}")
        return Result(report, None, None)

    # The version change is the single largest thing the rebuild does, so it is
    # stated outright rather than left for the reader to infer from the output.
    source_version = book.source_version
    if source_version.startswith("2"):
        report.add(
            "package",
            Level.FIX,
            f"rebuilt the package from EPUB {source_version} to EPUB 3.3",
            detail="Package document, navigation and container structure were regenerated.",
        )
    elif source_version.startswith("3"):
        report.add(
            "package",
            Level.INFO,
            f"source was already EPUB {source_version}; the package was regenerated regardless",
        )
    else:
        report.add(
            "package",
            Level.WARN,
            "package declared no usable version; treating it as EPUB 2 and rebuilding to 3.3",
        )

    ctx = Context(book=book, policy=policy, report=report)

    for stage_class in DEFAULT_STAGES:
        stage = stage_class()
        try:
            stage.run(ctx)
        except Exception as exc:  # A failing stage must not lose the whole book.
            report.add(
                stage.name,
                Level.ERROR,
                f"stage failed: {type(exc).__name__}: {exc}",
                detail="The rebuild continued with the remaining stages.",
            )

    if book.has_drm:
        return Result(report, book, None)

    # Checked here rather than only in the front ends, so the guarantee holds
    # for a library caller too. The source is the one file this tool must never
    # be able to destroy: everything else it writes can be produced again from
    # it, and it cannot.
    if os.path.abspath(destination) == os.path.abspath(source):
        report.add(
            "writer",
            Level.ERROR,
            "refusing to write over the source file",
            location=source,
            detail="Nothing was written. Choose a different destination.",
        )
        return Result(report, book, None)

    parent = os.path.dirname(os.path.abspath(destination))
    if parent:
        os.makedirs(parent, exist_ok=True)
    write_epub(book, destination, report, content_dir=policy.content_dir)

    return Result(report, book, destination)
