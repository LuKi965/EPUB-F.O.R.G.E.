"""Top-level rebuild orchestration."""

from __future__ import annotations

import os
import pathlib
import tempfile
import zipfile
from dataclasses import dataclass, replace
from enum import Enum

from . import decisions, sources
from . import invariants
from . import memory
from . import balance
from . import plan
from . import budget as budget_module
from .budget import Budget, BudgetExceeded, Cancelled
from .model import Book
from .policy import Policy
from .question_texts import say
from .reader import EpubReadError, read_epub
from .references import Resolver
from .report import Action, Automation, Level, Report, Risk
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
#: from what we are about to rebuild from*. For a tool whose first rule is that
#: no character is lost, half a book is a worse outcome than a refusal.
#:
#: Measured on 0.2.19: an EPUB whose only chapter exceeded the per-entry limit
#: produced `status = succeeded-with-problems`, a file on disk, and **no
#: chapter** — the failure this project exists to make impossible, sold as
#: a success.
#:
#: `reader.name-dropped` is deliberately **not** here. An entry whose name has
#: no usable form — `../outside.bin`, an absolute path, a `__MACOSX` shadow —
#: is not a resource that went missing; it is one no manifest can name. Having
#: it here refused books that rebuild perfectly, which is this same failure
#: pointed the other way.
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


def _cannot_verify(policy: Policy, report: Report, queue, why: str = "") -> str:
    """The check is required and could not run. Now what?

    *why* is empty when the reason is the one this was written for — no
    browser on the machine — and otherwise says what stopped a browser that
    *is* here from finishing: an unreadable reading order, zero pages paired,
    an engine that fell over. EF-082 is why the second case exists at all. The
    two share every word of the decision and none of the wording, because
    "install Chromium" is not advice to somebody who has it.

    DELTA-2026-08-15-001, and it is the sharpest finding of that audit because
    the defect was *this program answering a question on somebody's behalf and
    recording it as though they had answered it.* The gate's default is `stop`,
    the owner chose that word himself, and with no browser on the machine it
    published — a warning in the report and the file on disk. A setting that
    says stop and does not stop is worse than no setting, because it is a
    promise somebody plans around.

    Both of the owner's instructions are honoured here and they are only in
    tension if the program is the one deciding:

    * *the verification is mandatory and may be knowingly declined* — so this
      asks, with the consequence of each answer spelled out, rather than
      refusing outright;
    * *a missing tool is not a reason to hold somebody's book hostage* — so
      there is an answer that publishes, a policy field that consents in
      advance for runs where nobody is watching, and `report` still means
      report.

    What is gone is the third thing, which nobody chose: *declining on the
    person's behalf and not telling them it was a decision.* With nobody there
    to ask, an unanswered question falls back to `KEEP`, `KEEP` here means "do
    not write the file", and that is `stop` meaning stop. The report says what
    was looked for, and the two ways forward.
    """
    # Each branch names its own identifier as a literal. Passing the id in a
    # variable reads as tidier and takes the catalogue out of the reach of the
    # test that keeps it honest — `test_rules` parses these call sites rather
    # than running them, and an id it cannot see is an id nothing checks.
    values = {"detail": why} if why else {"variable": render_module().ENV_BROWSER}

    def accepted() -> None:
        if why:
            report.add("render", Level.WARN, "render.incomplete-accepted", values=values)
        else:
            report.add("render", Level.WARN, "render.unverified-accepted", values=values)

    def unrun(level: Level) -> None:
        if why:
            report.add("render", level, "render.not-completed", values=values)
        else:
            report.add("render", level, "render.cannot-run", values=values)

    if policy.accept_unverified_render:
        accepted()
        return ""
    if policy.render_gate == "report":
        unrun(Level.WARN)
        return ""

    answer = queue.ask(
        decisions.Question(
            kind=decisions.VERIFICATION,
            where="",
            subject="render",
            summary=say("render.incomplete.summary") if why else say("render.unverified.summary"),
            detail=(
                say("render.incomplete.detail", detail=why)
                if why
                else say(
                    "render.unverified.detail",
                    variable=render_module().ENV_BROWSER,
                )
            ),
            options=(
                decisions.Option(
                    decisions.KEEP,
                    say("render.unverified.keep"),
                    say("render.unverified.keep.why"),
                ),
                decisions.Option(
                    "publish",
                    say("render.unverified.publish"),
                    say("render.unverified.publish.why"),
                ),
            ),
            recommended=decisions.KEEP,
            reversible=True,
            risk=Risk.APPEARANCE,
            group="render-unverified",
        )
    )
    if answer.option == "publish":
        accepted()
        return ""
    unrun(Level.ERROR)
    return "the appearance check could not run and nobody waived it"


def render_module():
    from . import render

    return render


def _render_gate(source: str, policy: Policy, report: Report, destination: str, queue):
    """F-028's half of the commit point: does the rebuilt book still look like it?

    Returns `None` when the policy asks for no rendering, and otherwise a
    function the writer hands the finished archive before it becomes the
    destination — the same hook the validator gate uses, and for the same
    reason: the only honest place to refuse is before the file exists.

    What happens when there is no browser is in `_cannot_verify`, and it is the
    part this got wrong for a release.
    """
    if policy.render_gate == "off":
        return None

    from . import render, render_fidelity

    def gate(candidate: str) -> str:
        if render.find_renderer() is None:
            return _cannot_verify(policy, report, queue)

        importer = sources.for_source(source)
        if importer is not None and importer.render_gate is not None:
            # A source with no *before* to draw: what the check means there is
            # the importer's to say (D-056), and `_cannot_verify` goes with it
            # because whether to publish unchecked is the core's decision.
            return importer.render_gate(candidate, policy, report, queue, _cannot_verify)

        # The rebuild's own ledger of moved files, so the pairing knows which
        # output page is which source page — names alone stopped being enough
        # when D-035 began naming documents by their role.
        moved = {
            change.before: change.after
            for change in report.changes
            if change.rule == "structure.relaid-out" and change.before and change.after
        }
        measured = render_fidelity.compare(
            source, candidate, sample=policy.render_sample, renames=moved,
            # Documents made shorter on somebody's word (D-054): held to
            # their ink rather than to screens that no longer line up.
            shortened=set((report.stats.get("space_removed") or {}).keys()),
        )
        if not measured.available:
            return _cannot_verify(policy, report, queue)
        if not measured.completed:
            # The engine is here and the comparison did not happen. Never
            # `render.checked`: a check that looked at no pages is not a
            # check, and the word for it is the same one used when there is
            # no browser at all (EF-082).
            return _cannot_verify(policy, report, queue, why=measured.reason)

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
            values = {
                "count": len(measured.pages),
                "engine": measured.engine,
                "documents": measured.documents,
                "total": measured.total,
                "screens": measured.screens,
            }
            if measured.whole:
                # Every compared document to its last screen (EF-089): the
                # word "checked" may mean the whole height only when it does.
                report.add("render", Level.INFO, "render.checked-whole", values=values)
            else:
                report.add("render", Level.INFO, "render.checked", values=values)
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
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as room:
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


def _ask_about_reconstructed(book, reconstructed, queue, report) -> bool:
    """Put each field that came out of a damaged package to whoever is there.

    Deliberately one question per field rather than one for the book: a person
    may know the title and have no idea what the identifier should be, and a
    single question would force one answer onto both.

    Returns whether every field was actually settled by somebody. `KEEP` is a
    settlement — a person looking at `ORIGINALpl` and deciding it is fine is a
    decision, and this program does not get a vote on it. Silence is not: an
    unanswered question means nobody has seen the value, and the caller refuses
    to publish rather than treating the silence as approval.
    """
    from . import decisions

    reading = {
        "title": book.metadata.title,
        "language": book.metadata.language,
        "author": ", ".join(creator.name for creator in book.metadata.creators),
    }
    unanswered = False
    for label in reconstructed:
        current = reading.get(label)
        if not current:
            continue
        question = decisions.Question(
            kind=decisions.METADATA,
            where=book.source_opf_path or "",
            summary=say(
                "metadata.reconstructed.summary", current=current, label=label
            ),
            detail=say("metadata.reconstructed.detail", current=current),
            options=(
                decisions.Option(
                    decisions.KEEP,
                    say("metadata.reconstructed.keep", current=current),
                    say("metadata.reconstructed.keep.why"),
                ),
                decisions.Option(
                    "write",
                    say("metadata.reconstructed.write"),
                    say("metadata.reconstructed.write.why"),
                    needs_value=True,
                ),
            ),
            recommended=decisions.KEEP,
            reversible=True,
            risk=Risk.NONE,
            group=f"metadata:{label}",
            subject=f"{label}={current}",
        )
        answer = queue.ask(question)
        if answer.source == "unanswered":
            unanswered = True
        if answer.option == "write" and answer.value:
            if label == "title":
                book.metadata.titles = [answer.value] + book.metadata.titles[1:]
            elif label == "language":
                book.metadata.language = answer.value
            elif label == "author":
                from .model import Creator

                book.metadata.creators = [Creator(name=answer.value)]
            report.add(
                "package",
                Level.FIX,
                "package.metadata-corrected",
                values={"field": label, "before": current, "after": answer.value},
                location=book.source_opf_path or "",
            )
            report.changed(
                "package",
                Action.REPLACED,
                f"metadata:{label}",
                before=current,
                after=answer.value,
                automation=Automation.ASKED,
                risk=Risk.CONTENT,
                reversible=True,
                rule="package.metadata-corrected",
            )
        elif answer.source != "unanswered":
            # BA-2026-003, i ten wpis kosztował najwięcej myślenia, bo tu **nic
            # się nie zmienia** — i właśnie dlatego ma być w bilansie.
            #
            # `Action.RECONSTRUCTED` stało w słowniku od chwili jego powstania
            # i nie było użyte ani razu. Wartość odczytana z uszkodzonego
            # pakietu jedzie do książki jako jej tytuł, język albo autor, i po
            # zapisie nic w wyniku nie mówi, że nie stała tam od początku.
            # Odzysk jest jedyną transformacją w tym programie, która publikuje
            # **odczyt parsera** jako fakt o książce; zostawienie go poza
            # rejestrem znaczyłoby, że bilans milczy dokładnie tam, gdzie
            # najtrudniej sprawdzić wynik po fakcie.
            #
            # Odwracalne: oryginał to uszkodzony pakiet, który wciąż jest na
            # dysku. Ryzyko `CONTENT`, bo zły tytuł albo zły język to nie jest
            # kwestia wyglądu — to jest książka opisana cudzym opisem.
            report.changed(
                "package",
                Action.RECONSTRUCTED,
                f"metadata:{label}",
                before="pakiet uszkodzony",
                after=current,
                automation=Automation.ASKED,
                risk=Risk.CONTENT,
                reversible=True,
                rule="package.metadata-reconstructed",
            )
    return not unanswered


def _source_gate(source: str, destination: str, report: Report):
    """The source is still not the destination, checked at the commit point.

    The same question `_refusals` asks before the stages run, asked again in
    the last moment at which nothing has been published. Between the two there
    is a whole rebuild, and the world is free to move underneath it: a link
    created, a directory renamed, a batch that resolved its destinations
    minutes ago. EF-081 was a hole in *how* the question was asked; asking it
    once, early, is a second hole in the same wall.
    """

    def gate(candidate: str) -> str:
        if not plan.same_file(destination, source):
            return ""
        report.add("writer", Level.ERROR, "package.source-protected", location=source)
        return "the destination is the source file"

    return gate


def _both_gates(source: str, policy: Policy, report: Report, destination: str, queue, book=None):
    """The validator gate and the render gate, in that order, as one hook.

    Order matters and is not arbitrary: EPUBCheck costs seconds and rendering
    costs half a minute, so the cheap refusal goes first. A book the validator
    turns away is never drawn.
    """
    checks = [
        # Cheapest of all and the one whose failure is worst: two `stat` calls
        # against destroying the one file that cannot be produced again.
        _source_gate(source, destination, report),
        # K1 first, and cheapest of the three: it reads two archives and
        # compares words, where the validator starts a JVM and the renderer
        # draws pages. It is also the one whose refusal matters most — a book
        # that lost a paragraph is damaged whatever the other two say.
        _text_gate(source, policy, report, book),
        _publication_gate(source, policy, report),
        _render_gate(source, policy, report, destination, queue),
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


#: Rules whose whole job is to take text out of the book, or move it, each one
#: only after the person said so.
#:
#: A loss the ledger accounts for is not an unexplained loss; K1 exists for the
#: loss nobody asked for.
#:
#: Some of these *move* rather than remove, and belong here because K1 is "every
#: character, **in the same order**": a watermark token gathered to the head of
#: its document breaks the subsequence test without a character having left the
#: book.
#:
#: Named rather than inferred. A rule added later that removes or moves text and
#: is not listed here will be refused by the gate — the burden is on the change
#: to declare itself.
#: Rules whose whole job is to change the *shape* of text the book keeps —
#: three dots into an ellipsis, straight quotes into the book's own
#: convention, a space after a one-letter word made unbreakable. Every one of
#: them is behind a switch, checks its own work, and is named in the report.
#:
#: The sharpened half of K1 consults this set for the reason the subsequence
#: half consults `REMOVES_TEXT_ON_PURPOSE`: a difference a named pass made and
#: reported is accounted for, and the invariant is about the difference nobody
#: accounted for. Wiring the sharpened check without this refused sixteen
#: tests inside one run — every one of them a legitimate typographic repair,
#: which is how the two got told apart.
#:
#: The alternative was to fold quotes and dashes away in the comparison, the
#: way today's subsequence half does. That was rejected: it would mean a quote
#: changed by *anything at all* passes unseen, including the correction
#: subsystem D-020 is being built for, and the whole point of sharpening K1 is
#: that such a change stops being invisible.
CHANGES_TEXT_SHAPE_ON_PURPOSE = frozenset({
    "typography.ellipsis-normalised",
    "typography.quotes-retyped",
    "typography.conjunctions-bound",
    "typography.reverted",
    # Not a reshaping but a restoration, and it belongs here for the same
    # reason: a conversion left codes no font draws, the person answered
    # "repair", and the characters came back. `xmlchars.legal` folds the
    # broken ones out of the *source* side, so the difference the check sees
    # is the repaired punctuation appearing — which is the answer working.
    "xhtml.mojibake-translated",
    # A hyphen between the endpoints of a range becomes an en dash. The
    # stage's own guard forgives it — its canonical form folds every dash to a
    # hyphen — but the prose half of K1 does not fold dashes, deliberately, so
    # the rule has to be named here or a book whose only typographic change is
    # this one is refused. It was: measured on a book with nothing else to
    # repair, and hidden on the shelf because the two rules beside it were
    # already named and covered the difference by accident.
    "typography.ranges-dashed",
})

REMOVES_TEXT_ON_PURPOSE = frozenset({
    "xhtml.shop-notice-removed",
    "xhtml.watermark-removed",
    "xhtml.watermark-relocated",
    "hyphens.joined",
    # A substitution puts one letter in and takes another out, so it fails the
    # subsequence half as squarely as joining a word does — and this is the
    # set that half consults. It is named here rather than beside the mojibake
    # translation above, even though it reshapes the prose too, because the
    # sharper half reads the union of both sets and the subsequence half reads
    # only this one; one home for the fact is enough, and it has to be this one.
    "substitutions.replaced",
    # A running head or a page number a PDF brought along, removed on a
    # person's word (0.5, D-052): text the source had and the book should not.
})


def _removes_text_on_purpose() -> frozenset:
    """The core's set, plus every rule an importer declares as its own removal
    somebody consented to (D-056). Read at the moment of the check rather than
    frozen at import, because which importers exist is a fact about the
    program's assembly, not about this module."""
    return REMOVES_TEXT_ON_PURPOSE.union(
        *(imp.removes_text_on_purpose for imp in sources.registered())
    )

#: **`xhtml.watermark-consolidated` is deliberately not in the set above**, and
#: taking it out re-armed a gate that had been disarmed on most of a real shelf.
#:
#: Consolidation does not touch the text. It pops the inline style, adds a class
#: and sets `aria-hidden`; the token stays exactly where it was, in the same
#: order, with the same characters. Nothing about it can break K1.
#:
#: Listing it anyway was not merely redundant. The check below asks whether the
#: report carries **any** consented rule, not whether that rule explains the
#: loss — and consolidation is the *default* watermark mode, so it appears on
#: nearly every book that carries a marker at all. A book that consolidated a
#: watermark and lost two characters somewhere else was therefore warned about
#: and published, whatever had actually eaten them.
#:
#: Found on the owner's 93-book shelf, 0.2.28: one book came out `-2` characters
#: with `text_invariant: False`, excused by a consolidation that had removed
#: nothing. The gate that exists to refuse exactly that had been standing down
#: since the day consolidation became the default.


def _more_than_one_rendition(source: str) -> bool:
    """Whether the container offers more than one publication."""
    import zipfile

    try:
        from .reader import rootfiles

        with zipfile.ZipFile(source) as archive:
            entries = {
                name: archive.read(name)
                for name in archive.namelist()
                if name == "META-INF/container.xml" or name.endswith(".opf")
            }
        return len(rootfiles(entries)) > 1
    except Exception:  # noqa: BLE001 — not knowing means running the check
        return False


def _paired_by_name(source: str, candidate: str, book=None) -> "dict[str, str]":
    """Documents that are in both archives under the same name, paired with
    themselves — the ledger a rebuild that renamed nothing would have written.

    The navigation document is left out when it is *machinery* — the same
    distinction `stages.base.machinery_nav` draws, and for the same reason. A
    nav outside the reading order is this program's own regenerated table of
    contents, not a page of the book: comparing it against the publisher's
    would refuse every rebuild in `minimal` for doing its job. A nav a reader
    can turn to is in the spine, is an ordinary page, and stays here.
    """
    import zipfile

    machinery = ""
    if book is not None and book.nav_path:
        if not any(item.path == book.nav_path for item in book.spine):
            machinery = book.nav_path
    try:
        with zipfile.ZipFile(source) as before, zipfile.ZipFile(candidate) as after:
            present = set(after.namelist())
            return {
                name: name
                for name in before.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
                and name in present
                and name != machinery
            }
    except (OSError, zipfile.BadZipFile):
        return {}


def _consent_by_document(divergences, report: Report, source: str, candidate: str) -> "tuple[list, list]":
    """Which diverging documents the recorded changes account for — exactly —
    and which not, each with the link of the chain that broke.

    EF-083. Consent used to be a rule name anywhere in the report: a hyphen
    joined in chapter four excused a sentence missing from chapter nine, and
    the independent audit of 2026-09-05 showed it with a single dummy finding.
    The first repair made consent per document — and that was a scope, not
    a contract: a hyphen joined in chapter nine still excused a sentence
    missing from chapter nine (EF-083a, `DROGA-DO-1.0` 6.2).

    So every text-changing stage records what the document's prose was
    before and after its change (`Stage.text_changed`, on the report as
    `stats["text_changes"]`: a chain of `rule`, `before`, `after` digests per
    document), and a difference is excused only when that chain leads from
    the source's prose to the output's: the first entry starts from what the
    source says, each next one from where the previous left off, and the
    last one ends where the output is — every link a consented rule. A
    change nobody recorded breaks the chain wherever it happened, and the
    document is refused with the link that broke named.
    """
    from . import fidelity

    accounted = _removes_text_on_purpose() | CHANGES_TEXT_SHAPE_ON_PURPOSE
    recorded = report.stats.get("text_changes") or {}
    excused, unexcused = [], []
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(candidate) as after:
        for divergence in divergences:
            chain = recorded.get(divergence.output_path) or recorded.get(divergence.source_path) or []
            was = _prose_digest_in(before, divergence.source_path, fidelity)
            now = _prose_digest_in(after, divergence.output_path, fidelity)
            why = _chain_breaks(chain, accounted, was, now)
            if why is None:
                excused.append(divergence)
            else:
                unexcused.append((divergence, why))
    return excused, unexcused


def _prose_digest_in(archive, name: str, fidelity) -> str:
    try:
        return fidelity.prose_digest(archive.read(name))
    except KeyError:
        return "missing"


def _chain_breaks(chain, accounted, was: str, now: str) -> "str | None":
    """Why the recorded changes do not lead from *was* to *now*, or `None`
    when they do. Polish, because it is read in a refusal."""
    if not chain:
        return "żaden etap nie zapisał zmiany tekstu w tym dokumencie"
    expected = was
    for entry in chain:
        if not isinstance(entry, dict):
            return f"wpis {entry!r} nie mówi, jaki tekst był przed zmianą i po niej"
        rule = entry.get("rule")
        if rule not in accounted:
            return f"{rule} nie jest zmianą tekstu, na którą ktoś się zgodził"
        if entry.get("before") != expected:
            return f"przed {rule} tekst nie był już tym, który wszedł — zmiana bez wpisu wcześniej"
        expected = entry.get("after")
    if expected != now:
        return f"po ostatniej zapisanej zmianie ({chain[-1].get('rule')}) tekst zmienił się jeszcze raz bez wpisu"
    return None


def _consented_rules(divergences, report: Report) -> "list[str]":
    """The consented rules whose entries excused *divergences*, for the report."""
    accounted = _removes_text_on_purpose() | CHANGES_TEXT_SHAPE_ON_PURPOSE
    recorded = report.stats.get("text_changes") or {}
    rules = set()
    for divergence in divergences:
        chain = recorded.get(divergence.output_path) or recorded.get(divergence.source_path) or []
        rules |= {entry.get("rule") for entry in chain if isinstance(entry, dict)}
    return sorted(rules & accounted)


def _paired_divergences(source: str, candidate: str, report: Report, book=None) -> "list | None":
    """Every carried document whose prose came out different, or `None` when
    the two archives cannot be paired at all.

    Paired by name first and by the relaid-out ledger over it, not one or
    the other. EF-091: the ledger names only what moved, and a book this
    program has already rebuilt keeps its chapter names — so on a second
    rebuild the ledger held the navigation document alone, every chapter
    went unpaired, and the gate had no divergence to consult a consent
    for: a hyphen joined on the owner's answer was refused as text lost,
    and a sentence added to a chapter would have passed unseen. Measured
    on 2026-09-06 with a two-hyphen run (`to-mor-row`), whose second
    hyphen is met on the next rebuild by design.
    """
    from . import fidelity

    moved = _paired_by_name(source, candidate, book)
    moved.update({
        change.before: change.after
        for change in report.changes
        if change.rule == "structure.relaid-out" and change.before and change.after
    })
    if not moved:
        return None
    return fidelity.prose_is_identical(source, candidate, moved)


def _text_gate(source: str, policy: Policy, report: Report, book=None):
    """K1 at the gate: every word of the source is in the file about to be named.

    WP-11 / EF-027. The measurement existed — `fidelity.text_survives` — and was
    reachable from a separate command and from the corpus, which means it ran
    after the fact on a machine that had already written the book, or never.

    What it catches that the others do not is the quietest loss there is. The
    invariant gate in front of the writer sees a *document* disappear; a
    paragraph is not a document. EPUBCheck reads the file as a specification
    and has no opinion about how much of the book is in it. The render check
    draws a sample of pages, and the page a converter dropped a paragraph from
    is not necessarily in the sample.

    Character-level and as a **subsequence**, which is K1 as it is actually
    written and the rule the corpus has been running over a hundred and sixty
    real books. Not `fidelity.text_survives`, which compares word *sets*: that
    is a fair measurement after the fact and a bad gate, because unwrapping a
    `<span>` joins two half-words into one and a word disappears while every
    character is exactly where it was. Wiring the word-set version to the gate
    failed twenty-two tests inside a minute, every one of them a legitimate
    rebuild — which is how the two got told apart.
    """
    if not policy.verify_text_survives:
        return None

    from . import fidelity

    def gate(candidate: str) -> str:
        try:
            if _more_than_one_rendition(source):
                # `rebuild_all` writes each rendition into its own file, so the
                # source's reading order is the *union* of them and comparing it
                # against one output reports the other rendition's text as lost.
                # Said rather than silently passed: a gate that quietly excuses
                # itself is worse than one that is not there.
                report.add("package", Level.INFO, "package.text-check-per-rendition")
                return ""
            check = fidelity.text_is_preserved(source, candidate)
        except Exception as exc:
            # EF-083. This used to warn and publish, on the reasoning that a
            # check which cannot run is not a book that failed. The reasoning
            # is wrong for a *mandatory* check: nothing here knows whether the
            # book is whole, and a file written under that ignorance carries
            # the same word — succeeded — as one that was actually measured.
            # The two cases this could legitimately hit are handled above by
            # name (many renditions, a PDF source); what is left is a defect,
            # in the book or in this program, and either way the answer is not
            # to publish.
            report.add(
                "package",
                Level.ERROR,
                "package.text-check-failed",
                values={"detail": f"{type(exc).__name__}: {exc}"},
            )
            return f"K1 could not be measured: {type(exc).__name__}: {exc}"
        importer = sources.for_source(source)
        if check.ok and importer is not None and importer.second_opinion is not None:
            # The subsequence held, read through the conversion's own reader.
            # The second reader counts what the page draws (EF-087): a
            # character it saw and the output lacks is a loss, and it is
            # excused on the same terms as the rule below excuses the
            # subsequence — a named pass that removes or reshapes text, in
            # the report, with somebody's answer behind it. Quotes turned to
            # the book's convention and three dots made an ellipsis are that;
            # a sentence in a Form XObject that nobody converted is not, and
            # nothing in the report will say otherwise.
            second = importer.second_opinion(source, candidate)
            if not second.ok:
                accounted = _removes_text_on_purpose() | CHANGES_TEXT_SHAPE_ON_PURPOSE
                consented = sorted(
                    {finding.rule for finding in report.findings if finding.rule in accounted}
                )
                # Which passes the person consented to is the core's sum; what
                # a loss of *this* source's characters is called is the
                # importer's word, said where its identifier is a literal.
                refusal = importer.note_second_opinion(report, second, consented)
                if refusal:
                    return refusal
        if check.ok:
            return ""
        if importer is not None:
            # An imported source has no documents to pair the output's with,
            # so this cannot go through `_paired_divergences`. It used to go
            # by rule *name* over the whole report instead, which is the same
            # defect the note beside `REMOVES_TEXT_ON_PURPOSE` records for the
            # core and Q08 of the quality roadmap records for the converter: a
            # consented pass that removed one thing excusing the loss of
            # another. The importer accounts for it or the book is refused —
            # and an importer with nothing to account with refuses, because
            # absent accounting is not consent.
            consented = sorted(
                {
                    finding.rule
                    for finding in report.findings
                    if finding.rule in _removes_text_on_purpose()
                }
            )
            if (
                consented
                and importer.second_opinion is not None
                and importer.note_second_opinion is not None
            ):
                # Accounted against the importer's *character* count, not
                # against the subsequence check that failed here: this check
                # knows that the order broke and not which characters are
                # gone, and a ledger cannot be spent against a verdict. When
                # the two disagree — order broken, nothing missing — that is a
                # removal that closed up behind itself, which is what
                # rejoining a cut paragraph does.
                second = importer.second_opinion(source, candidate)
                refusal = importer.note_second_opinion(report, second, consented)
                if refusal:
                    return refusal
                return ""
        else:
            # Text did leave the book. Excused only where somebody asked for it
            # in the very document it left (EF-083): the diverging documents
            # are found by pairing source with output, and each has to carry
            # its own entry. A loss in a document with no entry, or a loss
            # that no carried document accounts for — a document gone whole —
            # is refused.
            divergences = _paired_divergences(source, candidate, report, book)
            if divergences:
                excused, unexcused = _consent_by_document(divergences, report, source, candidate)
                if not unexcused:
                    report.add(
                        "package",
                        Level.WARN,
                        "package.text-changed-on-request",
                        values={"rules": ", ".join(_consented_rules(excused, report)), "detail": check.detail},
                    )
                    return ""
                divergence, why = unexcused[0]
                check = replace(
                    check,
                    detail=f"{check.detail}; bez zgody w {divergence.output_path}: {why}",
                )
        report.add(
            "package",
            Level.ERROR,
            "package.text-lost",
            values={"detail": check.detail},
        )
        return f"K1: {check.detail}"

    def sharper(candidate: str) -> str:
        """K1's other half: a carried document's prose is *identical*.

        The rule above asks for a subsequence — nothing may be lost, and
        anything at all may be added — which leaves the gate blind in one
        direction: a sentence that *appeared* inside an existing document
        passes it without a word. Measured on the owner's 160 books before
        this was wired: every carried document already comes out character
        for character, so this refuses nothing that runs today and closes
        the direction the correction subsystem will need closed (D-020).

        The same three concessions the measurement earned, each named in
        `fidelity`: a `<style>` block is not prose, a `<title>` is the
        reading system's navigation rather than the reading flow (and this
        program fills an empty one in, saying so), and a character no
        conforming EPUB may carry is not text.
        """
        importer = sources.for_source(source)
        if importer is not None and importer.note_prose_check is not None:
            # No source document to pair a carried one with: the importer's own
            # whole-text check ran instead, and the importer says so — the rule
            # identifier belongs where it is raised.
            importer.note_prose_check(report)
            return ""
        try:
            if _more_than_one_rendition(source):
                return ""
            # EF-083: nothing relaid out — `minimal` publishes the source's
            # own layout — used to mean the check was skipped entirely, so
            # a word invented inside an existing paragraph passed `minimal`
            # without a sound. EF-091: the ledger naming only the navigation
            # document, as it does on a book this program has already
            # rebuilt, left every chapter unpaired the same way. A document
            # that was not moved pairs with *itself*, and `_paired_divergences`
            # is the one place both gates get that pairing from.
            divergences = _paired_divergences(source, candidate, report, book)
            if divergences is None:
                report.add("package", Level.INFO, "package.prose-check-unpaired")
                return ""
        except Exception as exc:
            # Mandatory, so the same answer as the rule above it: a check that
            # could not run does not get to be silence with a file attached.
            report.add(
                "package",
                Level.ERROR,
                "package.prose-check-failed",
                values={"detail": f"{type(exc).__name__}: {exc}"},
            )
            return f"K1 (prose) could not be measured: {type(exc).__name__}: {exc}"
        if not divergences:
            return ""
        excused, unexcused = _consent_by_document(divergences, report, source, candidate)
        if not unexcused:
            report.add(
                "package",
                Level.WARN,
                "package.prose-changed-on-request",
                values={"rules": ", ".join(_consented_rules(excused, report)), "detail": str(divergences[0])},
            )
            return ""
        divergence, why = unexcused[0]
        report.add(
            "package",
            Level.ERROR,
            "package.prose-changed",
            values={"count": len(unexcused), "detail": f"{divergence}\n    {why}"},
        )
        return f"K1: {divergence} ({why})"

    def both(candidate: str) -> str:
        return gate(candidate) or sharper(candidate)

    return both


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
        # The candidate is what gets renamed into place, so this verdict is the
        # verdict on the published file. Recorded so nothing pays for it twice.
        if produced.available:
            report.validated = produced
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
    cancelled=None,
    standing: "dict | None" = None,
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

    A source this program does not repair is refused here as it is in
    `rebuild` — before the container is opened, because there is no container
    (D-057).
    """
    refused = _refuse_a_source_this_does_not_repair(
        source, Report(source=source, output=destination)
    )
    if refused is not None:
        return [refused]

    offered = _renditions_of(source)
    if len(offered) < 2:
        return [
            rebuild(source, destination, policy, resolver=resolver,
                    cancelled=cancelled, standing=standing)
        ]

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
            rebuild(
                source, target, policy, resolver=resolver,
                rendition=rendition.path, cancelled=cancelled,
                standing=standing,
            )
        )
    return results


def _renditions_of(source: str) -> list:
    """What the container offers, read without committing to a rebuild.

    A cheap look at one small file. Failing to answer is not an error here: a
    source this cannot open is a source `rebuild` will report on properly, and
    guessing "one rendition" sends it there.

    `BudgetExceeded` is named alongside `Exception` and that is the whole point
    of this line. It derives from `BaseException` — deliberately, so that no
    local `except Exception` can swallow a limit — and the cost of that decision
    is that every place which *means* "answer nothing and let the proper path
    diagnose it" has to say so out loud. This one did not, so a container
    nested past the depth limit came out of the public `rebuild_all` as an
    uncaught traceback while the very same book came out of `rebuild` as a
    controlled `BLOCKED`. A limit that turns one entry point into a crash and
    another into a report is not one boundary, it is two.
    """
    import zipfile

    from .reader import rootfiles

    try:
        with zipfile.ZipFile(source) as archive:
            names = {
                name: b"" if name != "META-INF/container.xml" else archive.read(name)
                for name in archive.namelist()
            }
        return rootfiles(names)
    except (Exception, BudgetExceeded):  # noqa: BLE001 — `rebuild` diagnoses it
        return []


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
    cancelled=None,
    standing: "dict | None" = None,
) -> Result:
    """Rebuild *source* into a conforming EPUB 3.3 at *destination*.

    *cancelled* is asked, at every per-document checkpoint, whether the person
    has changed their mind. `None` means nobody can — which is what a library
    caller and the corpus both want, and what every caller got before
    DELTA-2026-08-15-001, when the window could only stop *between* books and
    "cancel" on a large one meant "finish this one first".

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

    **This is the entry for repairing an EPUB, and it takes EPUBs.** A file
    some other module of this program reads — a PDF, today — is refused here
    with nothing written and a line saying what to use instead (D-057). It was
    accepted before, and reading it went through a registry rather than through
    a branch; that was tidier code for the same workflow, and the workflow was
    the thing the owner asked to separate.
    """
    policy = policy or Policy()
    report = Report(source=source, output=destination)
    refused = _refuse_a_source_this_does_not_repair(source, report)
    if refused is not None:
        return refused
    return produce(
        source, destination, policy, report,
        read=_epub_reader(rendition), stages=stages, resolver=resolver,
        asker=asker, cancelled=cancelled, standing=standing,
    )


def _epub_reader(rendition: "str | None"):
    """The repair core's own reader, as the shape `produce` takes."""

    def read(source, report, budget, _policy):
        return read_epub(source, report, budget, rendition=rendition)

    return read


def _refuse_a_source_this_does_not_repair(source, report) -> "Result | None":
    """Refuse a file that belongs to another module of this program.

    The registry stays — it is how the publication gates know that a source
    with no package document has no version to state and no pages to draw. What
    it no longer is, is the way a job finds its reader: asking it here turns it
    from a door into a doorman. Registering the converter therefore cannot
    reopen this path, which is the case the acceptance list names.
    """
    importer = sources.for_source(str(source))
    if importer is None:
        return None
    if importer.instead_of_rebuilding is not None:
        # What to do with this file instead is the other module's sentence to
        # write; a rule identifier belongs where it is raised.
        importer.instead_of_rebuilding(report)
    else:  # pragma: no cover - every importer says what it offers
        report.add("reader", Level.ERROR, "package.not-a-book",
                   values={"kind": importer.name})
    return Result(report, None, None, Status.BLOCKED)


def produce(
    source: str,
    destination: str,
    policy: Policy,
    report: Report,
    *,
    read,
    stages: "tuple | list | None" = None,
    resolver: "Resolver | None" = None,
    asker=None,
    cancelled=None,
    standing: "dict | None" = None,
) -> Result:
    """Everything from the read to the written file, for whichever module asked.

    The shared half of the program, and deliberately not a second name for
    `rebuild`: the modules differ in *what they read* and *which stages they
    run*, and agree on everything after — the balance, K1, the validator, the
    publication gates, the atomic write. Splitting the workflow was the point;
    splitting these would mean two copies of the safeguards, or one module
    without them (03-PDF-MODULE §4).

    Not public API. `pipeline.rebuild` and `pdfconv.service.convert` are the
    two entries, and each composes this with its own reader and stage list.
    """
    # Made here, so the deadline covers reading as well as rebuilding: a book
    # that takes five minutes to *open* has already cost what the limit is for.
    # The ceiling is the policy's (`time_budget_seconds`), not the module's:
    # a person with a slow machine and a large PDF is entitled to more than
    # five minutes, and the refusal tells them where to say so.
    budget = Budget(cancelled=cancelled, seconds=float(policy.time_budget_seconds))

    # F-019. Every parse in this program charges the *active* budget rather
    # than one handed down through call sites, because the call-site version is
    # what produced a limit with a test file and no callers. Activated around
    # the read as well as the rebuild: a document big enough to matter is one
    # this program should refuse before it opens it, not after.
    try:
        with budget_module.active(budget):
            return _produce_inside_budget_or_cancelled(
                source, destination, policy, report, budget, stages, resolver,
                read, asker, standing=standing,
            )
    finally:
        # A batch runs a shelf one book after another in the same process, and
        # without this the second book starts against the first book's
        # high-water mark — freed memory that glibc is holding in its arenas
        # rather than live objects. Measured over six real books: 62 MiB
        # resident at the end without it, 46 MiB with; on a 108 MB book, 319 MiB
        # returned in one call. In a `finally` because a refused book has
        # allocated just as much as a published one.
        memory.release()


def _produce_inside_budget_or_cancelled(
    source, destination, policy, report, budget, stages, resolver, read, asker,
    standing=None,
) -> "Result":
    try:
        return _produce_inside_budget(
            source, destination, policy, report, budget, stages, resolver,
            read, asker, standing=standing,
        )
    except Cancelled:
        # The writer unlinks its staging file on any `BaseException`, so by the
        # time this is caught there is nothing half-written anywhere and
        # whatever was already at the destination is untouched. What is left is
        # to say so, rather than let a Cancel button look like a crash.
        report.add("package", Level.WARN, "package.cancelled")
        return Result(report, None, None, Status.BLOCKED)


def _produce_inside_budget(
    source, destination, policy, report, budget, stages, resolver, read, asker=None,
    standing=None,
) -> "Result":
    """One run, from the first refusal to the written file, in the order
    the refusals were added: each step either says no with a `Result` or
    hands on. The steps are functions of their own so that each can be read
    against the finding that put it here (audit 2026-09-03, A-04)."""
    refused = _refuse_when_memory_is_short(source, policy, report)
    if refused:
        return refused

    book, refused = _read_or_refuse(source, report, budget, read, policy)
    if refused:
        return refused

    # Counted here, before a single stage has touched the book: the balance is
    # between what the *source* had and what is about to be written, and taking
    # it any later would be counting the rebuild against itself.
    before_side = balance.Side.of(book)

    queue = _open_queue(source, policy, report, resolver, asker, standing)

    refused = _settle_reconstructed_metadata(book, policy, queue, report)
    if refused:
        return refused

    refused = _refuse_when_input_is_incomplete(book, report)
    if refused:
        return refused

    _state_the_version_change(book, report)

    policy = _settle_layout(book, policy, report)
    # BA-2026-002. Answers given about this book on a previous run are read back
    # first, so a rebuild run twice asks only what it has not been told. The
    # store is refused outright if the book has changed since — replaying
    # somebody's judgement onto a page they have not seen is worse than asking
    # again.
    ctx = Context(
        book=book, policy=policy, report=report, budget=budget,
        resolver=resolver, decisions=queue,
    )

    refused = _run_stages(ctx, stages, budget, report)
    if refused:
        return refused

    refused = _refuse_before_publication(source, destination, ctx, budget, report)
    if refused:
        return refused

    refused = _publish(source, destination, ctx, before_side, queue, report)
    if refused:
        return refused

    return _final_result(destination, ctx, queue, report)


def _refuse_when_memory_is_short(source, policy, report) -> "Result | None":
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
    if not policy.check_memory:
        return None
    verdict = memory.check(source, limit=policy.memory_limit)
    if verdict.fits:
        return None
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


def _value_rewrites(ctx, report: Report) -> "dict[str, set[str]]":
    """Attribute name → documents whose value of it a stage rewrote on
    purpose (`Stage.attribute_rewritten`), under every name the document
    has had: the stage names it as it was at the time, and the balance sees
    the source's name on one side and the output's on the other."""
    moved = {
        change.before: change.after
        for change in report.changes
        if change.rule == "structure.relaid-out" and change.before and change.after
    }
    back = {after: before for before, after in moved.items()}
    rewrites: dict[str, set[str]] = {}
    for name, paths in ctx.attribute_rewrites.items():
        aliases = set()
        for path in paths:
            aliases |= {path, moved.get(path, path), back.get(path, path)}
        rewrites[name] = aliases
    return rewrites


def _budget_refused(report: Report, area: str, exc: BudgetExceeded) -> None:
    """The refusal a spent budget produces, wherever it was spent.

    Both numbers, always — that was the rule from the start. And for the one
    limit that is a setting rather than a property of the book, a second line
    that says so: a wall-clock refusal on a slow machine is right about the
    machine and useless if it does not say the ceiling can be raised
    (`Policy.time_budget_seconds`; the 138-page PDF of 2026-09-06).
    """
    report.add(
        area,
        Level.ERROR,
        "package.budget-exceeded",
        values={"limit": exc.limit, "found": exc.found, "allowed": exc.allowed},
        location=exc.where,
    )
    if exc.limit == "wall clock":
        report.add(area, Level.INFO, "package.time-budget-is-a-setting", values={})


def _read_or_refuse(source, report, budget, read, policy) -> "tuple[Book | None, Result | None]":
    """The book, or the refusal that stands in for it.

    *read* is the caller's reader: `(source, report, budget, policy) -> Book`,
    raising what the EPUB reader raises. The **module composing the run** says
    which one it is, because that is the difference between a program with two
    jobs and a program with one job and a branch in it (D-057). Nothing after
    this line knows which module asked.
    """
    try:
        return read(source, report, budget, policy), None
    except BudgetExceeded as exc:
        # A refusal, not a crash, and it says both numbers. A limit whose
        # message does not say what it was is a limit nobody can act on.
        _budget_refused(report, "reader", exc)
        return None, Result(report, None, None, Status.BLOCKED)
    except EpubReadError as exc:
        # Unless the reader has already said why, in a rule of its own. This
        # line interpolates the exception's text, so a reader that both
        # reports and raises gets its reason printed twice — once translated
        # and once in whatever language the exception was written in.
        if not getattr(exc, "reported", False):
            report.add(
                "reader",
                Level.ERROR,
                "package.unreadable-source",
                values={"error": str(exc)},
            )
        return None, Result(report, None, None, Status.FAILED)


def _open_queue(source, policy, report, resolver, asker, standing) -> decisions.Queue:
    # A standing answer — "do this to all of them" — used to live and die
    # inside one rebuild, because the queue was born here. Measured on the
    # owner's shelf: 8 979 questions across 160 books, 8 737 of them one
    # family, and answering "all of them" in book one meant being asked again
    # in book two, and a hundred and fifty-eight times after that. A person
    # cannot finish that, and everything the style work achieved sits behind
    # it. So a caller running a batch passes one dict and the answer carries.
    #
    # Per-question answers deliberately do **not** carry: `stored` is keyed on
    # the book and refused when the book has changed, because replaying
    # somebody's judgement onto a page they have not seen is worse than asking
    # again (BA-2026-002). A standing answer is different in kind — it is an
    # answer about a *class*, given in the knowledge that it applies to
    # everything of that class, and the option says so before it is chosen.
    queue = decisions.Queue(
        asker=asker if asker is not None else _asker_from(resolver),
        standing=standing if standing is not None else {},
    )
    if policy.remember_decisions:
        stored = decisions.Queue.load(
            decisions.answers_path(source), source=source, asker=queue.asker
        )
        queue.stored = stored.stored
        for failure in stored.failures:
            report.add("decisions", Level.WARN, "decisions.store-unusable",
                       values={"reason": failure})
    return queue


def _settle_reconstructed_metadata(book, policy, queue, report) -> "Result | None":
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
    if not any(
        finding.rule == "reader.xml-recovered" and (finding.location or "").endswith(".opf")
        for finding in report.findings
    ):
        return None
    # A field the person has already written by hand is not a guess and
    # must not be asked about or counted as unconfirmed: they are holding
    # the book and they have told this program what the title is. Both
    # front ends fill `metadata_overrides` from the same boxes, so this is
    # the one place that has to know.
    overridden = set(policy.metadata_overrides)
    reconstructed = [
        label
        for label, value in (
            ("title", book.metadata.title),
            ("language", book.metadata.language),
            ("identifier", book.metadata.primary_identifier),
            ("author", ", ".join(c.name for c in book.metadata.creators)),
        )
        if value and label not in overridden
    ]
    report.add(
        "package",
        Level.WARN,
        "package.metadata-from-a-guess",
        values={"fields": ", ".join(reconstructed) or "nothing this model reads"},
        location=book.source_opf_path or "",
    )
    # BA-2026-002's third class of question, and the one the API was built
    # to carry: a metadata conflict. F-004 established that a field read out
    # of a recovered package document is a parser's reading of somebody's
    # book rather than the book's own word, and it has been *reported* since
    # — which leaves the person holding a warning and no way to act on it in
    # the same breath. Now it is a question, in the same shape as a broken
    # link and a hard hyphen, with the same rule: unanswered changes nothing.
    settled = _ask_about_reconstructed(book, reconstructed, queue, report)
    # DELTA-2026-08-15-001, and it is the same finding as the render gate's
    # wearing different clothes: *not answering is not consenting.* Leaving
    # the guess in place is a change to somebody's library — the title in
    # their reader becomes `ORIGINALpl`, a string no publisher wrote and
    # this program's own parser invented — and "unanswered changes nothing"
    # was true of the *book* and false of the *outcome*, because the outcome
    # was publishing the invention.
    #
    # So the fields still are not guessed at. What changed is what happens
    # when nobody settles them: the same three ways through as the render
    # gate, because one program should have one rule about consent. Answer
    # the question, consent in advance with a switch, or get no file and a
    # report naming every field that came out of the parser.
    if reconstructed and not settled and not policy.accept_reconstructed_metadata:
        report.add(
            "package",
            Level.ERROR,
            "package.metadata-unconfirmed",
            values={"fields": ", ".join(reconstructed)},
            location=book.source_opf_path or "",
        )
        return Result(report, book, None, Status.BLOCKED)
    return None


def _refuse_when_input_is_incomplete(book, report) -> "Result | None":
    lost = _input_lost(report)
    if not lost:
        return None
    _diagnose_losses(book, report, lost)
    report.add(
        "reader",
        Level.ERROR,
        "package.input-incomplete",
        values={"count": len(lost), "names": ", ".join(sorted(lost)[:3])},
    )
    return Result(report, book, None, Status.BLOCKED)


def _state_the_version_change(book, report) -> None:
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
    elif source_version in sources.imported_versions():
        # A book that did not come from a package has no version to state; the
        # importer's own line is the statement, with its numbers.
        return
    else:
        report.add("package", Level.WARN, "package.version-unusable")


def _run_stages(ctx, stages, budget, report) -> "Result | None":
    """Every stage in order, each held to the budget and to its own word.

    *stages* is the module's own composition — the repair core's list, or that
    list with a converter's stages in front of it (D-057). `None` means the
    core's list, which is what a caller with nothing to add wants; a caller
    that names the stages gets exactly those, which is how the tests pin one
    stage at a time. An entry may be a `Stage` class or anything callable that
    returns one, so a stage carrying its module's settings needs no channel
    through the policy to reach them.
    """
    book = ctx.book
    if stages is None:
        stages = DEFAULT_STAGES
    for stage_class in stages:
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
            _budget_refused(report, stage.name, exc)
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
    return None


def _refuse_before_publication(source, destination, ctx, budget, report) -> "Result | None":
    """The refusals that come after the stages and before the commit point."""
    book = ctx.book
    if book.has_drm:
        return Result(report, book, None, Status.BLOCKED)

    # Checked here rather than only in the front ends, so the guarantee holds
    # for a library caller too. The source is the one file this tool must never
    # be able to destroy: everything else it writes can be produced again from
    # it, and it cannot.
    #
    # By file identity rather than by string since EF-081: comparing
    # `abspath` strings let `CASE-SOURCE.EPUB` overwrite `case-source.epub` on
    # Windows, and a symbolic link do the same anywhere. Checked again in
    # `_source_gate` immediately before the replace, because this is early and
    # a lot happens in between.
    if plan.same_file(destination, source):
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
    # `preserve` publishes with the publisher's broken reference intact and the
    # finding in the report; `strict` refuses, because its promise is a file
    # that conforms and this one does not.
    #
    # BLOCKED rather than FAILED: nothing went wrong, the book was refused on
    # purpose by a rule the person chose with the mode.
    if ctx.policy.strict and ctx.unresolved:
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
        _budget_refused(report, "package", exc)
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
    return None


def _publish(source, destination, ctx, before_side, queue, report) -> "Result | None":
    """The balance, then the write behind both gates; `None` when the file
    is at the destination."""
    book, policy = ctx.book, ctx.policy
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
        # BA-2026-003's remaining criterion. The ledger says what this rebuild
        # did; the balance asks whether anything went missing that nothing in
        # the ledger accounts for — the other direction, and the one that does
        # not require trusting the thing under suspicion to have written itself
        # down.
        # What changed the text of which document, for the K1 gate's
        # per-document consent (EF-083). On the report rather than the
        # context because the gate is handed the report and nothing else.
        report.stats["text_changes"] = {
            path: [dict(entry) for entry in entries]
            for path, entries in sorted(ctx.text_changes.items())
        }
        reconciled = balance.reconcile(
            before_side, balance.Side.of(book), report.changes, _value_rewrites(ctx, report)
        )
        report.balance = reconciled
        if not reconciled.closes:
            report.add(
                "package",
                Level.ERROR,
                "package.balance-unexplained",
                values={"detail": str(reconciled)},
            )
            # EF-084. It said this and wrote the file anyway — an ERROR in the
            # report and a book on disk, which is the shape this program was
            # built to make impossible. "Something the source had is not in
            # the output and nothing accounts for it" is the same sentence K1
            # refuses on; the only difference is that K1 counts characters and
            # this counts resources. Measured before it was turned into a
            # refusal: zero unexplained balances across the owner's 160 books,
            # so nothing that rebuilds today stops rebuilding.
            return Result(report, book, None, Status.BLOCKED)
        # The audit's A-03: what a screen reader depends on and nothing else
        # here counts. A fall is said, with the numbers, and the book is
        # still published — a count of names inside tags is a reason to
        # look, and the first time it was taken it found a loss (EF-071)
        # that no gate had seen.
        if reconciled.attributes_fell:
            report.add(
                "package",
                Level.WARN,
                "package.attributes-fell",
                values={
                    "detail": "; ".join(
                        f"{name}: {was} → {now}" for name, was, now in reconciled.attributes_fell
                    ),
                },
            )
        # 6.14. The character balance is a number in a report and may not stop
        # a book, so a document it cannot read is skipped — but silently it
        # made the total lean: counted on one side and skipped on the other
        # reads as text lost, or as text appearing. The documents are off both
        # sides now, and this line is where the report says which.
        if reconciled.text_uncounted:
            before_characters, after_characters = reconciled.text_characters_compared
            report.add(
                "package",
                Level.WARN,
                "package.text-uncounted",
                values={
                    "count": len(reconciled.text_uncounted),
                    "documents": ", ".join(reconciled.text_uncounted[:3])
                    + (f" (+{len(reconciled.text_uncounted) - 3})" if len(reconciled.text_uncounted) > 3 else ""),
                    "before": before_characters,
                    "after": after_characters,
                },
            )
        write_epub(
            book,
            destination,
            report,
            content_dir=policy.content_dir,
            package_name=policy.package_name,
            before_publish=_both_gates(source, policy, report, destination, queue, book),
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
    return None


def _final_result(destination, ctx, queue, report) -> "Result":
    """Whether the written file is entitled to a flat "succeeded"."""
    book = ctx.book
    # `SUCCEEDED` is a claim, and a book that still carries references this
    # program could not resolve is not entitled to it. They are not errors —
    # they are defects the source arrived with, and refusing the book over them
    # would refuse a large part of every shelf — but a rebuild that hands back a
    # flat "succeeded" while a footnote marker leads nowhere has told the person
    # something untrue. The file is written; the status says there is something
    # in the report worth reading. The same goes for a document that only
    # parsed after a tag-soup recovery: what came out of that is a
    # reconstruction, and this program cannot show it means what went in.
    # Pillar C. The summary says whether anything is waiting for the person,
    # and it must say it from the record rather than from the shape of a rule
    # name: the queue knows exactly which questions came back `UNANSWERED`,
    # and guessing it from findings would tell somebody their book is waiting
    # on them when it is not.
    report.stats["questions_unanswered"] = sum(
        1 for _, answer in queue.given if answer.source == "unanswered"
    )
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
