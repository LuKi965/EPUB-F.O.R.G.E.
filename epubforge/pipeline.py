"""Top-level rebuild orchestration."""

from __future__ import annotations

import os
import pathlib
import tempfile
from dataclasses import dataclass, replace
from enum import Enum

from . import decisions
from . import invariants
from . import memory
from . import budget as budget_module
from .budget import Budget, BudgetExceeded
from .model import Book
from .policy import Policy
from .reader import EpubReadError, read_epub
from .references import Resolver
from .report import Level, Report
from .stages import DEFAULT_STAGES, Context
from .writer import ArchiveVerificationError, PublicationRefused, write_epub


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


def _asker_from(resolver):
    """The resolver, if it can also answer a generic question.

    The window's `Ask` implements both: it is one dialog machinery serving two
    shapes of question, and asking a caller to pass the same object twice would
    be this program's plumbing leaking into its API.
    """
    return resolver if hasattr(resolver, "ask") else None


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


#: What a lost archive entry was, from its name, in words a person reads.
#:
#: Deliberately coarse. The entry never reached the model — that is what "lost"
#: means — so there is nothing to inspect but the name it had, and a confident
#: claim about a file nobody could open would be an invention.
_KIND_BY_SUFFIX = {
    "xhtml": "document", "html": "document", "htm": "document", "xml": "document",
    "css": "stylesheet",
    "jpg": "image", "jpeg": "image", "png": "image", "gif": "image",
    "webp": "image", "svg": "image", "bmp": "image", "tif": "image", "tiff": "image",
    "ttf": "font", "otf": "font", "woff": "font", "woff2": "font",
    "mp3": "audio", "m4a": "audio", "ogg": "audio", "wav": "audio",
    "mp4": "video", "webm": "video",
    "ncx": "navigation", "opf": "package",
}


def _diagnose_losses(book: Book, report: Report, lost: set[str]) -> None:
    """Say what each unreadable entry was and what it would have cost.

    The switch that used to publish anyway is gone, so a refusal is now the only
    outcome — and a refusal is only as useful as what it says. "Could not read
    one entry" tells somebody to go and look; this tells them whether the book
    lost a chapter or a decoration, whether anything in the book pointed at it,
    and therefore whether re-downloading is worth the trouble or urgent.

    Everything here is read off the name and off what survived. Nothing is
    guessed about the bytes, because there are none: that is the whole point.
    """
    # Not `book.spine`: an entry that never reached the model is not in the
    # rebuilt reading order *by definition*, so asking there answers "no" every
    # time and answers it about the wrong book. What the source said about the
    # file is in the report, put there by the reader when it went looking for a
    # manifest item and found nothing behind it.
    declared = {
        finding.location
        for finding in report.findings
        if finding.rule in ("reader.manifest-file-missing", "reader.spine-id-unknown")
        and finding.location
    }
    for name in sorted(lost):
        suffix = name.rpartition(".")[2].lower()
        kind = _KIND_BY_SUFFIX.get(suffix, "unknown")
        # Who pointed at it. A file nothing refers to is a different loss from
        # one three chapters link to, and the report should not make somebody
        # grep for the difference.
        referring = sum(
            1
            for resource in book.resources.values()
            if resource.media_type in ("application/xhtml+xml", "text/css", "image/svg+xml")
            and name.rpartition("/")[2].encode("utf-8") in resource.data
        )
        report.add(
            "reader",
            Level.ERROR,
            "package.input-lost-detail",
            values={
                "name": name,
                "kind": kind,
                # "the book said it had this" — the difference between a chapter
                # the publisher listed and a stray file the archive picked up.
                "declared": "yes" if any(name.endswith(d) or d.endswith(name) for d in declared) else "no",
                "referenced_by": referring,
            },
            location=name,
        )


def _fingerprint(book: Book) -> tuple:
    """Everything about a book that a stage could change, cheaply comparable.

    Bytes are hashed rather than held, so this costs one pass over the content
    and no second copy of a book that may be a quarter of a gigabyte. It covers
    what the audit's F-029 is about: the resources and their contents, the
    reading order, the navigation, and the metadata a reader sees.
    """
    import hashlib

    return (
        tuple(
            (path, hashlib.sha256(resource.data).digest(), resource.media_type)
            for path, resource in sorted(book.resources.items())
        ),
        tuple((item.path, item.linear) for item in book.spine),
        book.cover_path,
        book.nav_path,
        book.ncx_path,
        book.metadata.title,
        tuple(identifier.value for identifier in book.metadata.identifiers),
        len(book.toc),
        len(book.landmarks),
        len(book.page_list),
    )


def _render_gate(source: str, policy: Policy, report: Report, destination: str):
    """F-028's half of the commit point: does the rebuilt book still look like it?

    Returns `None` when the policy asks for no rendering, and otherwise a
    function the writer hands the finished archive before it becomes the
    destination — the same hook the validator gate uses, and for the same
    reason: the only honest place to refuse is before the file exists.

    **Without a browser it does not refuse.** The owner's instruction was
    explicit and is a standing rule rather than a preference about this feature:
    tell the person the verification is required, and let them decline it
    knowingly. Refusing every rebuild on a machine with no browser would not be
    holding the line, it would be holding the person's book hostage to a
    dependency this program deliberately does not ship. So the report says, at
    warning level, that the check did not run, what it looks for, and both ways
    out — install one, or turn the gate off on purpose.
    """
    if policy.render_gate == "off":
        return None

    from . import render, render_fidelity

    def gate(candidate: str) -> str:
        if render.find_renderer() is None:
            report.add(
                "render",
                Level.WARN,
                "render.cannot-run",
                values={"variable": render.ENV_BROWSER},
            )
            return ""

        measured = render_fidelity.compare(
            source, candidate, sample=policy.render_sample
        )
        if not measured.available:
            report.add(
                "render", Level.WARN, "render.cannot-run",
                values={"variable": render.ENV_BROWSER},
            )
            return ""

        for page in measured.pages:
            if page.problems:
                report.add(
                    "render", Level.ERROR, "render.page-lost-content",
                    values={"detail": str(page)}, location=page.document,
                )
            elif page.notes:
                report.add(
                    "render", Level.INFO, "render.page-changed",
                    values={"detail": str(page)}, location=page.document,
                )
        if measured.ok:
            report.add(
                "render", Level.INFO, "render.checked",
                values={"count": len(measured.pages), "engine": measured.engine},
            )
            return ""

        kept = _keep_evidence(source, candidate, destination, measured, report)
        if policy.render_gate == "report":
            return ""
        return (
            f"{len(measured.problems)} page(s) lost content"
            + (f"; evidence in {kept}" if kept else "")
        )

    return gate


def _keep_evidence(source, candidate, destination, measured, report) -> str:
    """Save the before/after pictures for the pages that failed, beside the book.

    The owner's decision, and the argument for it is his: without them the
    sentence "this page has less on it than the source did" is something he
    would have to take on trust. Only the failing pages, because a folder of
    forty-eight identical-looking screenshots per book is not evidence, it is
    litter.
    """
    import shutil

    from . import render, render_fidelity

    wanted = {page.document for page in measured.problems}
    if not wanted:
        return ""
    folder = os.path.splitext(destination)[0] + ".zrzuty"
    try:
        os.makedirs(folder, exist_ok=True)
        browser = render.find_renderer()
        with tempfile.TemporaryDirectory() as room:
            room_path = pathlib.Path(room)
            before = render_fidelity._extract(source, room_path / "przed")
            after = render_fidelity._extract(candidate, room_path / "po")
            paired, _, _ = render_fidelity._pair(
                render_fidelity._spine_of(before), render_fidelity._spine_of(after)
            )
            for source_page, output_page in paired:
                if output_page.name not in wanted:
                    continue
                for label, page in (("przed", source_page), ("po", output_page)):
                    target = pathlib.Path(folder) / f"{output_page.stem}-{label}.png"
                    render.shoot(
                        page, target,
                        viewport=render_fidelity.VIEWPORTS[0], browser=browser,
                    )
    except (OSError, render.RenderError) as exc:
        report.add(
            "render", Level.WARN, "render.evidence-unwritten",
            values={"error": f"{type(exc).__name__}: {exc}"},
        )
        return ""
    del shutil
    return folder


def _both_gates(source: str, policy: Policy, report: Report, destination: str):
    """The validator gate and the render gate, in that order, as one hook.

    Order matters and is not arbitrary: EPUBCheck costs seconds and rendering
    costs half a minute, so the cheap refusal goes first. A book the validator
    turns away is never drawn.
    """
    checks = [
        _publication_gate(source, policy, report),
        _render_gate(source, policy, report, destination),
    ]
    checks = [check for check in checks if check is not None]
    if not checks:
        return None

    def gate(candidate: str) -> str:
        for check in checks:
            refusal = check(candidate)
            if refusal:
                return refusal
        return ""

    return gate


def _publication_gate(source: str, policy: Policy, report: Report):
    """The audit's K.2 invariant 12, as a callable handed to the writer.

    Returns `None` when the policy asks for no gate — the writer then publishes
    the way it always did — and otherwise a function that is given the finished
    archive before it becomes the destination, and answers with a reason to
    refuse or the empty string.

    Why the comparison mode exists at all: `preserve` promises to publish a book
    the way its publisher wrote it, defects included, and to say so. Refusing
    every book EPUBCheck dislikes would break that promise on most of a real
    shelf — the corpus has titles that arrive with errors and have arrived with
    them for years. What `preserve` may never do is *add* one. So the gate
    validates the source too and compares, and the refusal names exactly what
    this rebuild introduced.

    The comparison is on message **shapes** rather than counts or codes.
    `RSC-005` is EPUBCheck's catch-all for "does not match the schema" and
    covers a hundred different defects; a book that arrives with one RSC-005 and
    leaves with a different one would pass a count. The shape is the sentence
    with everything book-specific masked out, which is exactly the granularity
    at which "the same complaint" means something.
    """
    if policy.validate_before_publish == "off":
        return None

    from .validate import find_epubcheck, validate

    def gate(candidate: str) -> str:
        if find_epubcheck() is None:
            # Asymmetric on purpose; the reasoning is in `Policy`. "clean" is an
            # absolute claim about the file and an unchecked claim is not one;
            # "no-new-errors" is a comparison, and there is nothing to compare.
            if policy.validate_before_publish == "clean":
                report.add(
                    "epubcheck",
                    Level.ERROR,
                    "package.gate-cannot-run",
                    values={"gate": policy.validate_before_publish},
                )
                return "the validator this gate needs is not installed"
            report.add("epubcheck", Level.WARN, "package.gate-skipped", values={})
            return ""

        produced = validate(candidate, report, content_untouched=not policy.rewrite_content)
        if not produced.available:
            if policy.validate_before_publish == "clean":
                report.add(
                    "epubcheck",
                    Level.ERROR,
                    "package.gate-cannot-run",
                    values={"gate": policy.validate_before_publish},
                )
                return "the validator did not answer"
            return ""

        if policy.validate_before_publish == "clean":
            if produced.clean:
                return ""
            report.add(
                "epubcheck",
                Level.ERROR,
                "package.gate-refused",
                values={
                    "count": produced.fatal + produced.errors,
                    "detail": "; ".join(produced.messages[:3]),
                },
            )
            return f"EPUBCheck reports {produced.fatal + produced.errors} error(s)"

        # "no-new-errors": what did this rebuild add?
        if produced.clean:
            return ""
        # The source is validated into a report of its own, so the book's own
        # long-standing defects do not arrive in this run's report looking like
        # something that happened today.
        before = validate(source, Report(source=source))
        if not before.available:
            report.add("epubcheck", Level.WARN, "package.gate-skipped", values={})
            return ""
        introduced = {
            shape: count
            for shape, count in produced.shapes.items()
            if count > before.shapes.get(shape, 0)
        }
        if not introduced:
            # The book arrived with these and leaves with these. Said out loud,
            # because "published, and it is still invalid" is worth knowing even
            # when it is not this program's doing.
            report.add(
                "epubcheck",
                Level.WARN,
                "package.errors-were-already-there",
                values={"count": produced.fatal + produced.errors},
            )
            return ""
        report.add(
            "epubcheck",
            Level.ERROR,
            "package.gate-refused-new",
            values={
                "count": sum(introduced.values()),
                "detail": "; ".join(list(introduced)[:3]),
                # Because "new" is doing more work than it looks when the
                # version changed: EPUB 3 has rules EPUB 2 did not, and a defect
                # that arrived with the book can be new to the *validator*
                # without being new to the book.
                "source_version": report.stats.get("source_version", "?"),
            },
        )
        return f"this rebuild introduced {sum(introduced.values())} EPUBCheck error(s)"

    return gate


def _reread(destination: str) -> str:
    """What is wrong with the file this program just wrote, read as an input.

    Returns an empty string when it reads back cleanly. Only errors count: a
    rebuilt book legitimately carries the source's own defects as warnings, and
    a check that refused those would be refusing the book for being the book.
    """
    check = Report(source=destination)
    try:
        again = read_epub(destination, check)
    except Exception as exc:  # noqa: BLE001 — an unreadable output is the finding
        return f"{type(exc).__name__}: {exc}"
    problems = [f.rule or f.message for f in check.findings if f.level is Level.ERROR]
    if not again.spine:
        problems.append("the reading order came back empty")
    return "; ".join(problems[:3])


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
    asker=None,
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

    # F-019. Every parse in this program charges the *active* budget rather
    # than one handed down through call sites, because the call-site version is
    # what produced a limit with a test file and no callers. Activated around
    # the read as well as the rebuild: a document big enough to matter is one
    # this program should refuse before it opens it, not after.
    with budget_module.active(budget):
        return _rebuild_inside_budget(
            source, destination, policy, report, budget, stages, resolver, rendition,
            asker,
        )


def _rebuild_inside_budget(
    source, destination, policy, report, budget, stages, resolver, rendition, asker=None
) -> "Result":
    # EF-020, and the benchmark it asked for came first. `reader.py` has held a
    # ceiling of 2 GiB of content since early on, and the measurement turned it
    # into a different fact than anybody had read into it: text costs twelve
    # times its own size once it is an element tree, so 2 GiB of content is a
    # promise the process may reach twenty-four gigabytes. A machine with 2 GiB
    # free dies at around 160 MB of text — killed, with no report, no
    # diagnosis, no output and on Windows nothing a person can act on.
    #
    # This is the same limit converted into the unit the machine actually has.
    # It is read from the ZIP directory, so it costs milliseconds, and it
    # refuses *before* the memory is asked for rather than during. Off by a
    # switch, because the estimate is a model and the person in front of the
    # machine knows things the model does not.
    if policy.check_memory:
        verdict = memory.check(source, limit=policy.memory_limit)
        if not verdict.fits:
            report.add(
                "reader",
                Level.ERROR,
                "package.memory-refused",
                values={
                    "needed": memory.human(verdict.estimate.peak_bytes),
                    "budget": memory.human(verdict.limit),
                    "text": memory.human(verdict.estimate.text_bytes),
                },
            )
            return Result(report, None, None, Status.BLOCKED)

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

    # **F-004.** A package document that only parsed after recovery is a parser's
    # reading of somebody's book, and the fields taken from it are that reading
    # rather than the book's own words. Reproduced: crossed tags turned the title
    # into "ORIGINALpl" and lost the language, and the book was published with
    # nothing said at all.
    #
    # The owner's decision was neither "refuse" nor "publish quietly": show the
    # difference and let it be corrected. So the report names the fields that
    # came out of the guess — they are the ones the window and the command line
    # already let anybody override by hand — and the status stops being a clean
    # success. What it deliberately does not do is invent the right answer.
    if any(
        finding.rule == "reader.xml-recovered" and (finding.location or "").endswith(".opf")
        for finding in report.findings
    ):
        reconstructed = [
            label
            for label, value in (
                ("title", book.metadata.title),
                ("language", book.metadata.language),
                ("identifier", book.metadata.primary_identifier),
                ("author", ", ".join(c.name for c in book.metadata.creators)),
            )
            if value
        ]
        report.add(
            "package",
            Level.WARN,
            "package.metadata-from-a-guess",
            values={"fields": ", ".join(reconstructed) or "nothing this model reads"},
            location=book.source_opf_path or "",
        )

    lost = _input_lost(report)
    if lost:
        _diagnose_losses(book, report, lost)
        report.add(
            "reader",
            Level.ERROR,
            "package.input-incomplete",
            values={"count": len(lost), "names": ", ".join(sorted(lost)[:3])},
        )
        return Result(report, book, None, Status.BLOCKED)

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
    # BA-2026-002. Answers given about this book on a previous run are read back
    # first, so a rebuild run twice asks only what it has not been told. The
    # store is refused outright if the book has changed since — replaying
    # somebody's judgement onto a page they have not seen is worse than asking
    # again.
    queue = decisions.Queue(asker=asker if asker is not None else _asker_from(resolver))
    if policy.remember_decisions:
        stored = decisions.Queue.load(
            decisions.answers_path(source), source=source, asker=queue.asker
        )
        queue.stored = stored.stored
        for failure in stored.failures:
            report.add("decisions", Level.WARN, "decisions.store-unusable",
                       values={"reason": failure})
    ctx = Context(
        book=book, policy=policy, report=report, budget=budget,
        resolver=resolver, decisions=queue,
    )

    for stage_class in (DEFAULT_STAGES if stages is None else stages):
        stage = stage_class()
        # F-029, the checkable part. Making the model immutable is a refactor of
        # the whole program; making a stage's *claim* enforceable is this, and it
        # covers what the finding is about — a stage that says it only measures
        # and quietly does not, in a program where any stage can change anything.
        before = _fingerprint(book) if not stage.mutates else None
        try:
            budget.deadline(stage.name)
            stage.run(ctx)
            # **F-020.** Asked before the stage and not after, which measures
            # everything except the thing that takes the time. Reproduced: a
            # 0.05 s limit, a stage that sleeps 0.20 s, and a published book —
            # because the only checkpoint was the one that ran while there was
            # still time left. The last stage in the list never had a check
            # after it at all, so a rebuild could pass the limit by any margin
            # and still publish.
            budget.deadline(stage.name)
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
        if before is not None and _fingerprint(book) != before:
            # Not a warning. A stage that changed the book while declaring it
            # would not is a stage whose every other claim is now unevidenced,
            # and the output was produced under an assumption that turned out
            # false. Nothing is written.
            report.add(
                stage.name,
                Level.ERROR,
                "package.stage-broke-its-word",
                values={"stage": stage.name},
            )
            return Result(report, book, None, Status.BLOCKED)

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
    # The last checkpoint, and the one that decides whether a book that already
    # cost more than it was allowed still gets published. Everything above may
    # have finished inside the limit and then spent it on the invariant check
    # or the write; nothing after this line is a good place to find out.
    try:
        budget.deadline("publication")
    except BudgetExceeded as exc:
        report.add(
            "package",
            Level.ERROR,
            "package.budget-exceeded",
            values={"limit": exc.limit, "found": exc.found, "allowed": exc.allowed},
            location=exc.where,
        )
        return Result(report, book, None, Status.BLOCKED)

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
            before_publish=_both_gates(source, policy, report, destination),
        )
    except PublicationRefused:
        # Already reported by the gate itself, in more detail than an exception
        # message carries. Nothing was published and nothing at the destination
        # was touched.
        return Result(report, book, None, Status.BLOCKED)
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
    # And a package document that had to be guessed at is the same argument one
    # level up from a guessed-at chapter: what came out is a reconstruction, and
    # a flat "succeeded" would be this program vouching for somebody else's
    # parser. The file is still written — it may well be exactly right — but the
    # status sends the person to the report, where the fields in question are
    # named.
    if any(finding.rule == "package.metadata-from-a-guess" for finding in report.findings):
        clean = False
    # The audit's K.2 invariant 11: *the result can be read again by the same
    # strict reader, without recovery and without an error.* Nothing checked it,
    # and it is the cheapest end-to-end statement this program can make about
    # its own output — the writer's verifier asks whether the ZIP survived the
    # trip to disk, the invariant gate asks whether the model made sense, and
    # neither asks whether what was written can be read back as a book.
    #
    # A warning rather than a refusal: the file exists, it may well open in a
    # reading system, and refusing to hand it over on the strength of this
    # program's own second opinion would be the fail-open reasoning of 0.2.19
    # pointed the other way. But it is said, and it takes the flat "succeeded"
    # away.
    reread = _reread(destination)
    if reread:
        report.add(
            "writer",
            Level.WARN,
            "package.not-readable-again",
            values={"detail": reread},
            location=destination,
        )
        clean = False

    status = Status.SUCCEEDED if clean else Status.SUCCEEDED_WITH_PROBLEMS
    return Result(report, book, destination, status)
