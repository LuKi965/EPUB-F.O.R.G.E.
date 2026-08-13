"""Top-level rebuild orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from enum import Enum

from . import invariants
from .budget import Budget, BudgetExceeded
from .model import Book
from .policy import Policy
from .reader import EpubReadError, read_epub
from .references import Resolver
from .report import Level, Report
from .stages import DEFAULT_STAGES, Context
from .writer import ArchiveVerificationError, write_epub


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
    try:
        kept = replace(policy, content_dir=directory, package_name=name)
    except ValueError as exc:
        # The source's own layout is somebody else's file, and keeping it means
        # writing its directory name into archive member names and into the XML
        # of `container.xml`. A name `Policy` refuses is a name this must not
        # copy: the book still rebuilds, under the layout this program chooses.
        report.add(
            "package",
            Level.WARN,
            "package.layout-unusable",
            values={"path": book.source_opf_path, "reason": str(exc)},
        )
        return policy
    report.add(
        "package",
        Level.INFO,
        "package.layout-kept",
        values={"path": book.source_opf_path},
    )
    return kept


#: Findings that mean a member of the source archive never reached the model.
#:
#: Not "something went wrong" — specifically *an entry of the input is missing
#: from what we are about to rebuild from*. The reader raised each of these and
#: then carried on, on the reasoning that one monstrous entry is skipped and the
#: rest of the book is still worth reading. That reasoning is written into the
#: reader beside the archive-wide limit, where it reaches the opposite
#: conclusion: *for a tool whose first rule is that no character is lost, half a
#: book is a worse outcome than a refusal.* Both cannot be right, and the
#: archive-wide one is.
#:
#: Measured, on 0.2.19: an EPUB whose only chapter exceeded the per-entry limit
#: produced `status = succeeded-with-problems`, a file on disk, and **no
#: chapter**. That is the failure this project exists to make impossible, sold
#: as a success.
#: `reader.name-dropped` is deliberately **not** here, and the first draft of
#: this set had it. An entry whose name has no usable form — `../outside.bin`,
#: an absolute path, a `__MACOSX` shadow — is not a publication resource that
#: went missing; it is an entry no manifest can name and no document can link
#: to. Refusing a book because its archive carries one would refuse books that
#: rebuild perfectly today, which is the failure mode this whole change is
#: against, pointed the other way. The suite caught it within the hour.
LOSES_INPUT = frozenset({
    "reader.entry-too-large",
    "reader.entry-unreadable",
    "reader.manifest-id-duplicated",
})


def _input_lost(report: Report) -> set[str]:
    """Which entries of the source did not survive being read."""
    return {
        finding.location or finding.rule
        for finding in report.findings
        if finding.rule in LOSES_INPUT
    }


def rebuild_all(
    source: str,
    destination: str,
    policy: Policy | None = None,
    *,
    resolver: "Resolver | None" = None,
) -> list[Result]:
    """Rebuild every rendition the container offers, each into its own file.

    The audit's F-025 and the owner's decision on 2026-08-13: *rebuild each
    version separately.* A container may list several `rootfile` elements — the
    same work as a fixed-layout edition and a reflowable one, in two languages,
    with and without narration — and each is a complete publication with its own
    manifest, spine and metadata. This program read the first and said nothing,
    so a two-rendition book came out as one, with the other rendition's files
    carried along as unmanifested strays: an output declaring a publication the
    source does not have.

    Refusing was the other option and the owner did not take it. Merging was
    never one — two renditions are two books, and a reading system chooses
    between them; a rebuild that flattened them would be deciding on the
    reader's behalf which edition they get.

    The first rendition goes to *destination* exactly as `rebuild` would put it,
    so nothing changes for the overwhelming majority of books. The others go
    beside it, named after what the container calls them.
    """
    offered = _renditions_of(source)
    if len(offered) < 2:
        return [rebuild(source, destination, policy, resolver=resolver)]

    stem, extension = os.path.splitext(destination)
    results: list[Result] = []
    used: set[str] = set()
    for index, rendition in enumerate(offered):
        if index == 0:
            target = destination
        else:
            suffix = _rendition_suffix(rendition, index)
            target = f"{stem}.{suffix}{extension}"
            while target in used:  # pragma: no cover - two labels folding to one
                suffix = f"{suffix}-{index}"
                target = f"{stem}.{suffix}{extension}"
        used.add(target)
        results.append(
            rebuild(source, target, policy, resolver=resolver, rendition=rendition.path)
        )
    return results


def _renditions_of(source: str) -> list:
    """What the container offers, read without committing to a rebuild.

    A cheap look at one small file. Failing to answer is not an error here: a
    source this cannot open is a source `rebuild` will report on properly, and
    guessing "one rendition" sends it there.
    """
    import zipfile

    from .reader import rootfiles

    try:
        with zipfile.ZipFile(source) as archive:
            names = {
                name: b"" if name != "META-INF/container.xml" else archive.read(name)
                for name in archive.namelist()
            }
    except Exception:  # noqa: BLE001 — `rebuild` reports what is wrong with it
        return []
    return rootfiles(names)


def _rendition_suffix(rendition, index: int) -> str:
    """A filename fragment naming one rendition, from what the container said.

    The publisher's own `rendition:label` when there is one, folded to something
    a filesystem will take; failing that the properties they did declare —
    `pre-paginated`, a language — because "rendition-2" tells the person holding
    two files nothing about which is which.
    """
    from . import paths

    label = rendition.label
    if label:
        slug = paths.ascii_slug(label, fallback="").rstrip(".")
        if slug:
            return slug
    return f"rendition-{index + 1}"


def rebuild(
    source: str,
    destination: str,
    policy: Policy | None = None,
    stages: "tuple[type, ...] | list[type] | None" = None,
    *,
    resolver: "Resolver | None" = None,
    rendition: str | None = None,
) -> Result:
    """Rebuild *source* into a conforming EPUB 3.3 at *destination*.

    *stages* exists for one question that cannot be asked any other way: does a
    stage that claims to only measure actually leave the output untouched? The
    answer is a rebuild with it and a rebuild without it, compared byte for
    byte, and there is no way to get the second without being able to say which
    stages ran. Nothing in the application passes it.

    *rendition* names which package document to rebuild from, for a container
    that offers several — see `rebuild_all`, which is what calls it with one.

    *resolver* is somebody to ask when the rebuild reaches a question it cannot
    answer — today, a reference whose anchor does not exist. `None` means nobody
    is there, which is what a batch run, the corpus and a library caller all
    want; the rebuild then changes nothing it cannot justify and says so in the
    report. See :mod:`epubforge.references`.
    """
    policy = policy or Policy()
    report = Report(source=source, output=destination)
    # Made here, so the deadline covers reading as well as rebuilding: a book
    # that takes five minutes to *open* has already cost what the limit is for.
    budget = Budget()

    try:
        book = read_epub(source, report, budget, rendition=rendition)
    except BudgetExceeded as exc:
        # A refusal, not a crash, and it says both numbers. A limit whose
        # message does not say what it was is a limit nobody can act on.
        report.add(
            "reader",
            Level.ERROR,
            "package.budget-exceeded",
            values={"limit": exc.limit, "found": exc.found, "allowed": exc.allowed},
            location=exc.where,
        )
        return Result(report, None, None, Status.BLOCKED)
    except EpubReadError as exc:
        report.add(
            "reader",
            Level.ERROR,
            "package.unreadable-source",
            values={"error": str(exc)},
        )
        return Result(report, None, None, Status.FAILED)

    lost = _input_lost(report)
    if lost and not policy.allow_incomplete:
        report.add(
            "reader",
            Level.ERROR,
            "package.input-incomplete",
            values={"count": len(lost), "names": ", ".join(sorted(lost)[:3])},
        )
        return Result(report, book, None, Status.BLOCKED)
    if lost:
        report.add(
            "reader",
            Level.WARN,
            "package.input-incomplete-allowed",
            values={"count": len(lost), "names": ", ".join(sorted(lost)[:3])},
        )

    # The version change is the single largest thing the rebuild does, so it is
    # stated outright rather than left for the reader to infer from the output.
    source_version = book.source_version
    if source_version.startswith("2"):
        report.add("package", Level.FIX, "package.upgraded", values={"version": source_version})
    elif source_version.startswith("3"):
        report.add(
            "package",
            Level.INFO,
            "package.regenerated",
            values={"version": source_version},
        )
    else:
        report.add("package", Level.WARN, "package.version-unusable")

    policy = _settle_layout(book, policy, report)
    ctx = Context(book=book, policy=policy, report=report, budget=budget, resolver=resolver)

    for stage_class in (DEFAULT_STAGES if stages is None else stages):
        stage = stage_class()
        try:
            budget.deadline(stage.name)
            stage.run(ctx)
        except BudgetExceeded as exc:
            report.add(
                stage.name,
                Level.ERROR,
                "package.budget-exceeded",
                values={"limit": exc.limit, "found": exc.found, "allowed": exc.allowed},
                location=exc.where,
            )
            return Result(report, book, None, Status.BLOCKED)
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
                "package.stage-failed",
                values={"stage": stage.name, "error": f"{type(exc).__name__}: {exc}"},
            )
            return Result(report, book, None, Status.FAILED)

    if book.has_drm:
        return Result(report, book, None, Status.BLOCKED)

    # Checked here rather than only in the front ends, so the guarantee holds
    # for a library caller too. The source is the one file this tool must never
    # be able to destroy: everything else it writes can be produced again from
    # it, and it cannot.
    if os.path.abspath(destination) == os.path.abspath(source):
        report.add("writer", Level.ERROR, "package.source-protected", location=source)
        return Result(report, book, None, Status.BLOCKED)

    # Strict mode's half of F-010.
    #
    # A reference whose anchor does not exist cannot be repaired by this program
    # — see `references.py` for why removing the fragment is not a repair but a
    # forgery. What is left is a choice about the *result*, and the two modes
    # answer it differently, which is the only place they are allowed to
    # disagree about this at all.
    #
    # `preserve` publishes the book with the publisher's own broken reference
    # intact and the finding in the report. `strict` does not: its whole promise
    # is a file that conforms, and this book does not, so it says so instead of
    # producing something that validates by having had meaning removed from it.
    #
    # BLOCKED rather than FAILED — nothing went wrong here. The book was refused
    # on purpose, by a rule the person chose when they chose the mode, and the
    # report names every reference and the document holding it. If somebody is
    # at the window, they were asked first: a resolver turns most of these into
    # answers before this line is reached.
    if policy.strict and ctx.unresolved:
        report.add(
            "writer",
            Level.ERROR,
            "package.unresolved-references",
            values={
                "count": len(ctx.unresolved),
                "examples": "; ".join(str(u) for u in ctx.unresolved[:3]),
            },
        )
        return Result(report, book, None, Status.BLOCKED)

    # The commit point. Everything above may mutate the book; from here it is
    # either published or it is not, and nothing in between reaches a name a
    # person will open. The archive verifier inside `write_epub` asks whether
    # the ZIP survived the trip to disk; this asks whether the book makes sense
    # — a question nothing had been asking.
    broken = invariants.check(book)
    if broken:
        # One finding, not one per violation, and the catalogue's own tests
        # taught me that within the minute. A rule id passed as a variable is an
        # id nothing can check — the test that forbids it exists because a
        # tagging pass once spliced one into a concatenation and two releases
        # went out reporting `compat.appliedapple, kindle`. Nine ids whose whole
        # Polish translation was a copy of the English `{detail}` were not nine
        # rules; they were one rule with nine shapes, and the shapes belong in
        # the values.
        report.add(
            "writer",
            Level.ERROR,
            "package.invariant-failed",
            values={
                "count": len(broken),
                "detail": "; ".join(str(violation) for violation in broken[:3]),
            },
        )
        return Result(report, book, None, Status.BLOCKED)

    # Writing is where the outside world gets a vote: a full disk, a read-only
    # folder, a name the filesystem will not take. Until 0.2.22 those left this
    # function as an exception — reproduced with a destination whose parent is
    # a file, which raised `NotADirectoryError` straight out of `rebuild`. In a
    # batch that is not one failed book, it is the end of the batch: the ninth
    # of a thousand takes the other 991 with it and none of them appear in the
    # report either.
    #
    # Only the errors the world produces are caught. A bug in the writer still
    # raises, because a `Result` saying FAILED would hide it.
    try:
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
    except ArchiveVerificationError:
        # Not the world saying no — this program's own read-back saying the file
        # it wrote is not the file it meant to. Nobody else can see that, so it
        # is not turned into a tidy failed result.
        raise
    except OSError as exc:
        report.add(
            "writer",
            Level.ERROR,
            "package.not-written",
            values={"error": f"{type(exc).__name__}: {exc}"},
            location=destination,
        )
        return Result(report, book, None, Status.FAILED)

    # `SUCCEEDED` is a claim, and a book that still carries references this
    # program could not resolve is not entitled to it. They are not errors —
    # they are defects the source arrived with, and refusing the book over them
    # would refuse a large part of every shelf — but a rebuild that hands back a
    # flat "succeeded" while a footnote marker leads nowhere has told the person
    # something untrue. The file is written; the status says there is something
    # in the report worth reading. The same goes for a document that only
    # parsed after a tag-soup recovery: what came out of that is a
    # reconstruction, and this program cannot show it means what went in.
    clean = report.ok and not ctx.unresolved and not ctx.recovered
    status = Status.SUCCEEDED if clean else Status.SUCCEEDED_WITH_PROBLEMS
    return Result(report, book, destination, status)
