"""Top-level rebuild orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from enum import Enum

from .model import Book
from .policy import Policy
from .reader import EpubReadError, read_epub
from .report import Level, Report
from .stages import DEFAULT_STAGES, Context
from .writer import write_epub


class Status(str, Enum):
    """How a rebuild ended, stated rather than inferred.

    Front ends used to work this out from ``output_path is not None``, which
    cannot distinguish "finished" from "a stage crashed and we wrote the pieces
    anyway". The distinction is the whole point of this type.
    """

    #: Nothing to report beyond fixes.
    SUCCEEDED = "succeeded"
    #: Written, but the report carries errors the tool could not resolve.
    SUCCEEDED_WITH_PROBLEMS = "succeeded-with-problems"
    #: Refused before writing: DRM, or a destination this tool will not touch.
    BLOCKED = "blocked"
    #: A stage raised, or the source could not be read. Nothing was written.
    FAILED = "failed"

    @property
    def wrote_a_file(self) -> bool:
        return self in (Status.SUCCEEDED, Status.SUCCEEDED_WITH_PROBLEMS)


@dataclass
class Result:
    report: Report
    book: Book | None
    output_path: str | None
    status: Status = Status.SUCCEEDED


def _settle_layout(book: Book, policy: Policy, report: Report) -> Policy:
    """Put the package document where the files are when the files do not move.

    `content_dir` decides where the package document, the navigation document
    and the NCX are written. It is only half a layout decision: the other half
    is where the *resources* go, and that is `reorganize_files`. With the
    reorganisation off — the container-only rebuild, whose whole promise is that
    content files come out byte for byte as they went in — the resources stay in
    the source's directory while the package moved to `EPUB/`. Every manifest
    href then had to climb out of it: `../OEBPS/images/cover.jpg`, seventy times
    over.

    That is legal. The path stays inside the container, and EPUBCheck passes it
    without a word. It is also the kind of path a reader guards against, because
    `..` inside an archive is how a zip-slip attack looks, and a reader that
    refuses it refuses the whole book.

    So when nothing is being moved, nothing moves — including the package
    document.
    """
    if policy.reorganize_files or not book.source_opf_path:
        return policy
    directory, _, name = book.source_opf_path.rpartition("/")
    if directory == policy.content_dir.strip("/") and name == policy.package_name:
        return policy
    report.add(
        "package",
        Level.INFO,
        f"kept the package document at {book.source_opf_path}",
        rule="package.layout-kept",
        values={"path": book.source_opf_path},
        detail=(
            "This rebuild does not move content files, so moving the package "
            "document away from them would leave every manifest href pointing "
            "back out of its own directory with `../`."
        ),
    )
    return replace(policy, content_dir=directory, package_name=name)


def rebuild(source: str, destination: str, policy: Policy | None = None) -> Result:
    """Rebuild *source* into a conforming EPUB 3.3 at *destination*."""
    policy = policy or Policy()
    report = Report(source=source, output=destination)

    try:
        book = read_epub(source, report)
    except EpubReadError as exc:
        report.add(
            "reader",
            Level.ERROR,
            f"could not read the source file: {exc}",
            rule="package.unreadable-source",
            values={"error": str(exc)},
        )
        return Result(report, None, None, Status.FAILED)

    # The version change is the single largest thing the rebuild does, so it is
    # stated outright rather than left for the reader to infer from the output.
    source_version = book.source_version
    if source_version.startswith("2"):
        report.add(
            "package",
            Level.FIX,
            f"rebuilt the package from EPUB {source_version} to EPUB 3.3",
            rule="package.upgraded",
            values={"version": source_version},
            detail="Package document, navigation and container structure were regenerated.",
        )
    elif source_version.startswith("3"):
        report.add(
            "package",
            Level.INFO,
            f"source was already EPUB {source_version}; the package was regenerated regardless",
            rule="package.regenerated",
            values={"version": source_version},
        )
    else:
        report.add(
            "package",
            Level.WARN,
            "package declared no usable version; treating it as EPUB 2 and rebuilding to 3.3", rule="package.version-unusable",
        )

    policy = _settle_layout(book, policy, report)
    ctx = Context(book=book, policy=policy, report=report)

    for stage_class in DEFAULT_STAGES:
        stage = stage_class()
        try:
            stage.run(ctx)
        except Exception as exc:  # noqa: BLE001 — reported, then the run stops
            # A stage mutates the shared Book as it goes, so an exception leaves
            # the model half-changed: some documents rewritten, some not, the
            # manifest describing a state that no longer exists. Continuing
            # through the remaining stages and writing the result produced a
            # file that looked finished and was not. There is no way to tell
            # from the outside, which is what made this the worst defect in the
            # program: every other failure could leave the building through it.
            #
            # The book is not lost — the source is untouched and the report says
            # exactly which stage failed. What is lost is the pretence that the
            # output is usable.
            report.add(
                stage.name,
                Level.ERROR,
                f"stage failed: {type(exc).__name__}: {exc}",
                rule="package.stage-failed",
                values={"stage": stage.name, "error": f"{type(exc).__name__}: {exc}"},
                detail=(
                    "Nothing was written. The model was left half-modified by the "
                    "failure, so anything built from it would be a book only in shape."
                ),
            )
            return Result(report, book, None, Status.FAILED)

    if book.has_drm:
        return Result(report, book, None, Status.BLOCKED)

    # Checked here rather than only in the front ends, so the guarantee holds
    # for a library caller too. The source is the one file this tool must never
    # be able to destroy: everything else it writes can be produced again from
    # it, and it cannot.
    if os.path.abspath(destination) == os.path.abspath(source):
        report.add(
            "writer",
            Level.ERROR,
            "refusing to write over the source file", rule="package.source-protected",
            location=source,
            detail="Nothing was written. Choose a different destination.",
        )
        return Result(report, book, None, Status.BLOCKED)

    parent = os.path.dirname(os.path.abspath(destination))
    if parent:
        os.makedirs(parent, exist_ok=True)
    write_epub(
        book,
        destination,
        report,
        content_dir=policy.content_dir,
        package_name=policy.package_name,
    )

    status = Status.SUCCEEDED if report.ok else Status.SUCCEEDED_WITH_PROBLEMS
    return Result(report, book, destination, status)
