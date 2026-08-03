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

    parent = os.path.dirname(os.path.abspath(destination))
    if parent:
        os.makedirs(parent, exist_ok=True)
    write_epub(book, destination, report, content_dir=policy.content_dir)

    return Result(report, book, destination)
